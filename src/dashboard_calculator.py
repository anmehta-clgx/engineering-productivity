"""Dashboard calculator module for aggregating metrics and calculating scores."""
import logging
import datetime
import re
import pandas as pd
from config import COMPLETION_STATUSES

logger = logging.getLogger(__name__)


def calculate_scores(metrics_df: pd.DataFrame, flow_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate metrics by Sprint and calculate the Dashboard Index.
    
    Args:
        metrics_df: DataFrame with raw issue metrics
        flow_df: DataFrame with flow survey data
        
    Returns:
        DataFrame with aggregated dashboard scores
    """
    # Parse dates first
    metrics_df['Sprint Start Date'] = metrics_df['Sprint Name'].apply(_parse_sprint_date)
    metrics_df['Created Date Parsed'] = pd.to_datetime(metrics_df['Created Date'], errors='coerce')
    
    # Keep unfiltered copy for bug counting (we want all bugs created by date, regardless of sprint assignment)
    unfiltered_metrics_df = metrics_df.copy()
    
    # Exclude active sprint (determine the most recent sprint by date)
    if not metrics_df.empty:
        most_recent_sprint_date = metrics_df['Sprint Start Date'].max()
        # Filter out the most recent sprint (active sprint) for sprint-based metrics
        metrics_df = metrics_df[metrics_df['Sprint Start Date'] < most_recent_sprint_date].copy()
        logger.info(f"Excluded active sprint with start date: {most_recent_sprint_date}")
    
    # Filter for completed tickets
    done_mask = metrics_df['Status'].str.lower().isin(COMPLETION_STATUSES)
    
    # Count completed tickets (all types)
    ticket_counts = metrics_df[done_mask].groupby('Sprint Name').size().reset_index(name='Completed Tickets')
    
    # Track story points
    sprint_velocity = metrics_df[done_mask].groupby('Sprint Name')['Story Points'].sum().reset_index()
    sprint_velocity.rename(columns={'Story Points': 'Total Story Points'}, inplace=True)

    # Total Cycle Time for completed items
    cycle_time_sum = metrics_df[done_mask].groupby('Sprint Name')['Days In Progress'].sum().reset_index()
    dev_cycle_sum = metrics_df[done_mask].groupby('Sprint Name')['Dev Cycle Time'].sum().reset_index()
    review_cycle_sum = metrics_df[done_mask].groupby('Sprint Name')['Review Cycle Time'].sum().reset_index()
    acceptance_cycle_sum = metrics_df[done_mask].groupby('Sprint Name')['Acceptance Cycle Time'].sum().reset_index()
    
    # Total Delivered Count (exclude Tasks - they are automatically accepted)
    non_task_mask = metrics_df['Issue Type'] != 'Task'
    delivered_count = metrics_df[non_task_mask].groupby('Sprint Name')['Reached Delivered'].sum().reset_index()
    
    # Rejection Count (Sum, exclude Tasks)
    rejection_sum = metrics_df[non_task_mask].groupby('Sprint Name')['Rejection Count'].sum().reset_index()
    
    # Count bugs created during each sprint period
    # For each sprint, count bugs where created date falls within that sprint's week
    # Use unfiltered data so we count ALL bugs created by date, regardless of sprint assignment
    bugs_created_per_sprint = _count_bugs_created_in_sprint_periods(unfiltered_metrics_df)

    # Merge Aggregates
    dashboard = ticket_counts.merge(sprint_velocity, on='Sprint Name', how='outer')
    dashboard = dashboard.merge(cycle_time_sum, on='Sprint Name', how='outer')
    dashboard = dashboard.merge(dev_cycle_sum, on='Sprint Name', how='outer')
    dashboard = dashboard.merge(review_cycle_sum, on='Sprint Name', how='outer')
    dashboard = dashboard.merge(acceptance_cycle_sum, on='Sprint Name', how='outer')
    dashboard = dashboard.merge(delivered_count, on='Sprint Name', how='outer')
    dashboard = dashboard.merge(rejection_sum, on='Sprint Name', how='outer')
    dashboard = dashboard.merge(bugs_created_per_sprint, on='Sprint Name', how='outer')
    
    # Fill NaNs
    dashboard.fillna(0, inplace=True)
    
    # --- SCORING LOGIC ---
    
    # Avg Cycle Time per Ticket (all types)
    dashboard['Avg Cycle Time per Ticket'] = dashboard.apply(
        lambda row: row['Days In Progress'] / row['Completed Tickets'] if row['Completed Tickets'] > 0 else 0, axis=1
    ).round(2)
    
    # Break out cycle time per ticket metrics
    dashboard['Avg Dev Cycle Time per Ticket'] = dashboard.apply(
        lambda row: row['Dev Cycle Time'] / row['Completed Tickets'] if row['Completed Tickets'] > 0 else 0, axis=1
    ).round(2)
    
    dashboard['Avg Review Cycle Time per Ticket'] = dashboard.apply(
        lambda row: row['Review Cycle Time'] / row['Completed Tickets'] if row['Completed Tickets'] > 0 else 0, axis=1
    ).round(2)
    
    dashboard['Avg Acceptance Cycle Time per Ticket'] = dashboard.apply(
        lambda row: row['Acceptance Cycle Time'] / row['Completed Tickets'] if row['Completed Tickets'] > 0 else 0, axis=1
    ).round(2)
    
    # Cycle time per point for reference
    dashboard['Avg Cycle Time per Point (Total)'] = dashboard.apply(
        lambda row: row['Days In Progress'] / row['Total Story Points'] if row['Total Story Points'] > 0 else 0, axis=1
    ).round(2)

    # Rejection Ratio %
    dashboard['Rejection Ratio %'] = dashboard.apply(
        lambda row: (row['Rejection Count'] / row['Reached Delivered'] * 100) if row['Reached Delivered'] > 0 else 0, axis=1
    )
    dashboard['Rejection Ratio %'] = dashboard['Rejection Ratio %'].round(1)
    
    # Bug Score (20% penalty per bug, capped at 5 bugs = 0 score)
    dashboard['Bug Score'] = dashboard['Bugs Created'].apply(
        lambda bugs: max(0, 100 - (bugs * 20))
    ).round(1)
    
    # Rejection Score (inverse of rejection ratio)
    dashboard['Rejection Score'] = dashboard['Rejection Ratio %'].apply(
        lambda r: max(0, 100 - r)
    ).round(1)

    # Merge Flow Scores from survey data
    dashboard = dashboard.merge(flow_df, left_on='Sprint Name', right_on='sprint_name', how='left')
    dashboard['Flow Survey Score'] = dashboard['flow_score_raw']
    
    # Velocity Score (60% weight) - Composite of Efficiency + Throughput
    # Calculate historical medians (excluding zero values)
    median_tickets = dashboard[dashboard['Completed Tickets'] > 0]['Completed Tickets'].median()
    median_cycle_time = dashboard[dashboard['Avg Cycle Time per Ticket'] > 0]['Avg Cycle Time per Ticket'].median()
    
    # Throughput Score (60% of Velocity): Based on ticket count
    def calc_throughput_score(actual_tickets):
        if actual_tickets <= 0 or median_tickets <= 0: return 0
        if actual_tickets >= median_tickets:
            # Above median: scale from 70% to 100%
            score = 70 + (actual_tickets / median_tickets - 1) * 100
            return min(100, score)
        else:
            # Below median: scale proportionally down from 70%
            return 70 * (actual_tickets / median_tickets)
    
    dashboard['Throughput Score'] = dashboard['Completed Tickets'].apply(calc_throughput_score).round(1)
    
    # Efficiency Score (40% of Velocity): Based on cycle time per ticket (inverse: lower is better)
    def calc_efficiency_score(actual_cycle_time):
        if actual_cycle_time <= 0 or median_cycle_time <= 0: return 0
        if actual_cycle_time <= median_cycle_time:
            # Better than median: scale from 70% to 100%
            score = 70 + (1 - actual_cycle_time / median_cycle_time) * 100
            return min(100, score)
        else:
            # Worse than median: scale proportionally down from 70%
            return 70 * (median_cycle_time / actual_cycle_time)
    
    dashboard['Efficiency Score'] = dashboard['Avg Cycle Time per Ticket'].apply(calc_efficiency_score).round(1)
    
    # Composite Velocity Score: 60% Throughput + 40% Efficiency
    dashboard['Velocity Score'] = (
        (dashboard['Throughput Score'] * 0.60) + 
        (dashboard['Efficiency Score'] * 0.40)
    ).round(1)

    # Quality Score (25% weight) - 60% bug score + 40% rejection score
    dashboard['Quality Score'] = dashboard.apply(
        lambda row: (row['Bug Score'] * 0.60) + (row['Rejection Score'] * 0.40), axis=1
    ).round(1)
    
    # Flow Score (15% weight)
    dashboard['Flow Score'] = dashboard['Flow Survey Score'].apply(
        lambda x: round(min(100, max(0, x)), 1) if pd.notna(x) else None
    )
    
    # FINAL IMPACT INDEX
    # When flow score is missing (NaN), exclude it and adjust weights: 70% velocity, 30% quality
    # When flow score exists, use: 60% velocity, 15% flow, 25% quality
    def calculate_final_index(row):
        if pd.isna(row['Flow Score']):
            # No flow data: 70% velocity, 30% quality
            return (row['Velocity Score'] * 0.70) + (row['Quality Score'] * 0.30)
        else:
            # Has flow data: 60% velocity, 15% flow, 25% quality
            return (row['Velocity Score'] * 0.60) + (row['Flow Score'] * 0.15) + (row['Quality Score'] * 0.25)
    
    dashboard['FINAL AI IMPACT INDEX'] = dashboard.apply(calculate_final_index, axis=1).round(1)

    # Sort by sprint date (already calculated during filtering)
    dashboard['Sprint Start Date'] = dashboard['Sprint Name'].apply(_parse_sprint_date)
    dashboard.sort_values(by='Sprint Start Date', ascending=False, inplace=True)
    
    # Remove active sprint from dashboard (but its bugs were still counted for past sprints)
    if not dashboard.empty:
        most_recent_sprint_date = dashboard['Sprint Start Date'].max()
        dashboard = dashboard[dashboard['Sprint Start Date'] < most_recent_sprint_date].copy()
        logger.info(f"Removed active sprint from dashboard output")

    # Return final columns
    final_cols = [
        "Sprint Name",
        "Completed Tickets",
        "Total Story Points",
        "Avg Cycle Time per Ticket",
        "Avg Dev Cycle Time per Ticket",
        "Avg Review Cycle Time per Ticket",
        "Avg Acceptance Cycle Time per Ticket",
        "Bugs Created",
        "Bug Score",
        "Rejection Ratio %",
        "Rejection Score",
        "Flow Survey Score",
        "Throughput Score",
        "Efficiency Score", 
        "Velocity Score", 
        "Quality Score", 
        "Flow Score", 
        "FINAL AI IMPACT INDEX"
    ]
    return dashboard[final_cols]


def _count_bugs_created_in_sprint_periods(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Count bugs created during each sprint's time period.
    
    Args:
        metrics_df: DataFrame with all issues
        
    Returns:
        DataFrame with Sprint Name and Bugs Created count
    """
    # Get all unique sprints and their date ranges
    sprints = metrics_df[['Sprint Name', 'Sprint Start Date']].drop_duplicates()
    sprints = sprints[sprints['Sprint Start Date'] != datetime.datetime.min].copy()
    sprints = sprints.sort_values('Sprint Start Date')
    
    # Build date ranges (assume 1 week sprints - 5 business days)
    sprint_ranges = []
    for _, row in sprints.iterrows():
        start_date = row['Sprint Start Date']
        # Sprint period: start date to start date + 6 days (to cover full week including weekend)
        end_date = start_date + datetime.timedelta(days=6)
        sprint_ranges.append({
            'Sprint Name': row['Sprint Name'],
            'Start': start_date,
            'End': end_date
        })
    
    # Count bugs created in each sprint period
    bug_counts = []
    for sprint_range in sprint_ranges:
        # Filter bugs created during this sprint period
        bugs_in_period = metrics_df[
            (metrics_df['Issue Type'] == 'Bug') &
            (metrics_df['Created Date Parsed'] >= sprint_range['Start']) &
            (metrics_df['Created Date Parsed'] <= sprint_range['End'])
        ]
        bug_counts.append({
            'Sprint Name': sprint_range['Sprint Name'],
            'Bugs Created': len(bugs_in_period)
        })
    
    return pd.DataFrame(bug_counts)


def _parse_sprint_date(name):
    """Parse date from sprint name in format 'Iteration MM.DD.YY'.
    
    Args:
        name: Sprint name string
        
    Returns:
        datetime object or datetime.min if parsing fails
    """
    if not isinstance(name, str): 
        return datetime.datetime.min
    try:
        match = re.search(r'Iteration (\d{2}\.\d{2}\.\d{2})', name)
        if match:
            return datetime.datetime.strptime(match.group(1), '%m.%d.%y')
    except:
        pass
    return datetime.datetime.min

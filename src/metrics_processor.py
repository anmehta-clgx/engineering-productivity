"""Metrics processor module for calculating issue-level metrics."""
import os
import logging
import datetime
import re
from typing import Optional, Dict, Any
import pandas as pd
from config import (
    FIELD_STORY_POINTS,
    FIELD_SPRINT,
    COMPLETION_STATUSES,
    DELIVERY_STATUSES,
    FLOW_DATA_FILE,
    FIELD_TEAM_FILTER_VALUE
)

logger = logging.getLogger(__name__)


def calculate_business_days(start_datetime, end_datetime) -> float:
    """Calculate the number of business days (excluding weekends) between two datetimes.
    
    Args:
        start_datetime: Start datetime (timezone aware)
        end_datetime: End datetime (timezone aware)
        
    Returns:
        float: Number of business days (excluding weekends)
    """
    if start_datetime >= end_datetime:
        return 0.0
    
    # Convert to date objects for date iteration
    start_date = start_datetime.date()
    end_date = end_datetime.date()
    
    # Count full business days
    business_days = 0
    current_date = start_date
    
    while current_date < end_date:
        # Monday = 0, Sunday = 6
        if current_date.weekday() < 5:  # Monday-Friday
            business_days += 1
        current_date += datetime.timedelta(days=1)
    
    # Handle partial days at start and end
    # Calculate what fraction of the first and last day to include
    total_seconds = (end_datetime - start_datetime).total_seconds()
    
    if business_days == 0:
        # Duration is within a single day or only weekend days
        if start_datetime.weekday() < 5:  # weekday
            return total_seconds / 86400
        else:  # weekend
            return 0.0
    
    # For multi-day spans, adjust for partial days
    # Start partial day
    start_end_of_day = datetime.datetime.combine(start_date, datetime.time.max).replace(tzinfo=start_datetime.tzinfo)
    start_partial = 0.0
    if start_datetime.weekday() < 5:  # weekday
        seconds_in_first_day = (start_end_of_day - start_datetime).total_seconds()
        start_partial = seconds_in_first_day / 86400
        business_days -= 1  # Remove the full day we counted
    
    # End partial day
    end_start_of_day = datetime.datetime.combine(end_date, datetime.time.min).replace(tzinfo=end_datetime.tzinfo)
    end_partial = 0.0
    if end_datetime.weekday() < 5:  # weekday
        seconds_in_last_day = (end_datetime - end_start_of_day).total_seconds()
        end_partial = seconds_in_last_day / 86400
        business_days -= 1  # Remove the full day we counted
    
    return business_days + start_partial + end_partial


def process_issue_metrics(issue, team_filter=None) -> Optional[Dict]:
    """Calculate raw metrics for a single issue. Returns None if issue should be filtered out.
    
    Args:
        issue: Jira issue object
        team_filter: Team filter value for sprint goal filtering
        
    Returns:
        Dictionary of metrics or None if issue should be filtered
    """
    if team_filter is None:
        team_filter = FIELD_TEAM_FILTER_VALUE
    
    key = issue.key
    
    # Safe get story points
    sp = getattr(issue.fields, FIELD_STORY_POINTS, 0)
    if sp is None: sp = 0
    story_points = float(sp)

    # Analyze Changelog first to determine completion date
    changelog = issue.changelog
    histories = sorted(changelog.histories, key=lambda x: x.created)
    
    # Get Sprint Name - use the sprint with the latest start date
    sprint_name = "Unknown Sprint"
    last_sprint = None
    raw_sprint = getattr(issue.fields, FIELD_SPRINT, None)
    best_date = datetime.datetime.min
    
    if raw_sprint and len(raw_sprint) > 0:
        best_sprint = None
        
        for s in raw_sprint:
            s_name_temp = "Unknown"
            if hasattr(s, 'name'):
                s_name_temp = s.name
            elif isinstance(s, dict) and 'name' in s:
                s_name_temp = s['name']
            elif isinstance(s, str):
                match = re.search(r'name=([^,]+)', s)
                if match: s_name_temp = match.group(1)
                else: s_name_temp = s
            
            # Parse date
            current_date = datetime.datetime.min
            # Regex for "Iteration MM.DD.YY" (Start Date)
            d_match = re.search(r'Iteration (\d{2}\.\d{2}\.\d{2})', s_name_temp)
            if d_match:
                try:
                    current_date = datetime.datetime.strptime(d_match.group(1), '%m.%d.%y')
                except: pass
            
            if current_date >= best_date:
                best_date = current_date
                best_sprint = s
                sprint_name = s_name_temp

        last_sprint = best_sprint

        # --- FILTER: Check Sprint Goal for team name ---
        sprint_goal = ''
        if hasattr(last_sprint, 'goal'):
            sprint_goal = getattr(last_sprint, 'goal', '')
        
        if sprint_goal is None: sprint_goal = ''
        
        if team_filter not in sprint_goal:
            # Skip this issue as it belongs to another team
            return None

    # Calculate In Progress Time & Rejections (excluding weekends)
    time_in_progress_days = 0.0
    dev_time_days = 0.0  # Time in "started"
    review_time_days = 0.0  # Time in "peer review" and "finished"
    acceptance_time_days = 0.0  # Time in "delivered"
    rejection_count = 0
    was_rejected = False
    
    current_status = "To Do"
    last_change_time = datetime.datetime.strptime(issue.fields.created, '%Y-%m-%dT%H:%M:%S.%f%z')
    
    for history in histories:
        change_time = datetime.datetime.strptime(history.created, '%Y-%m-%dT%H:%M:%S.%f%z')
        
        for item in history.items:
            if item.field == 'status':
                # Normalize statuses: remove dashes, trim spaces, lowercase
                from_status = item.fromString.strip('- ').lower() if item.fromString else ""
                to_status = item.toString.strip('- ').lower() if item.toString else ""
                
                # Accumulate time based on current state (excluding weekends)
                duration_days = calculate_business_days(last_change_time, change_time)
                
                if current_status in ["started", "peer review", "finished", "delivered"]:
                    time_in_progress_days += duration_days
                    
                    # Break out into specific cycle time buckets
                    if current_status == "started":
                        dev_time_days += duration_days
                    elif current_status in ["peer review", "finished"]:
                        review_time_days += duration_days
                    elif current_status == "delivered":
                        acceptance_time_days += duration_days

                # Track Rejections (Delivered -> Rejected)
                if from_status == 'delivered' and to_status == 'rejected':
                    rejection_count += 1
                    was_rejected = True
                
                # Update state
                current_status = to_status
                last_change_time = change_time

    # If currently in progress, add time until now (excluding weekends)
    if current_status in ["started", "peer review", "finished", "delivered"]:
        now = datetime.datetime.now(datetime.timezone.utc)
        duration_days = calculate_business_days(last_change_time, now)
        time_in_progress_days += duration_days
        
        # Break out into specific cycle time buckets
        if current_status == "started":
            dev_time_days += duration_days
        elif current_status in ["peer review", "finished"]:
            review_time_days += duration_days
        elif current_status == "delivered":
            acceptance_time_days += duration_days

    days_in_progress = round(time_in_progress_days, 2)
    days_dev = round(dev_time_days, 2)
    days_review = round(review_time_days, 2)
    days_acceptance = round(acceptance_time_days, 2)

    # Robust Status Check
    raw_status = str(issue.fields.status)
    if hasattr(issue.fields.status, 'name'):
        raw_status = issue.fields.status.name
        
    status_clean = raw_status.lower().replace("-", "").strip()
    is_done = status_clean in COMPLETION_STATUSES
    
    # 'Delivered' count logic
    reached_delivered = 1 if status_clean in DELIVERY_STATUSES else 0 

    # Get Issue Type
    issue_type = "Unknown"
    if hasattr(issue.fields, 'issuetype') and issue.fields.issuetype:
        if hasattr(issue.fields.issuetype, 'name'):
            issue_type = issue.fields.issuetype.name
        else:
            issue_type = str(issue.fields.issuetype)
    
    # Get Created Date
    created_date = None
    if hasattr(issue.fields, 'created') and issue.fields.created:
        try:
            created_date = datetime.datetime.strptime(issue.fields.created, '%Y-%m-%dT%H:%M:%S.%f%z')
            # Convert to timezone-naive for comparison
            created_date = created_date.replace(tzinfo=None)
        except ValueError:
            try:
                created_date = datetime.datetime.strptime(issue.fields.created, '%Y-%m-%dT%H:%M:%S%z')
                created_date = created_date.replace(tzinfo=None)
            except ValueError:
                logger.warning(f"Could not parse created date for {key}: {issue.fields.created}")

    return {
        "Issue Key": key,
        "Issue Type": issue_type,
        "Story Points": story_points,
        "Sprint Name": sprint_name,
        "Days In Progress": days_in_progress,
        "Dev Cycle Time": days_dev,
        "Review Cycle Time": days_review,
        "Acceptance Cycle Time": days_acceptance,
        "Rejection Count": rejection_count,
        "Reached Delivered": reached_delivered,
        "Status": status_clean.title(),
        "Timestamp": datetime.datetime.now().isoformat(),
        "Was Rejected?": "Yes" if was_rejected else "No",
        "Created Date": created_date.isoformat() if created_date else None,
        "Sprint Start Date": best_date.isoformat() if best_date != datetime.datetime.min else None
    }


def load_flow_data() -> pd.DataFrame:
    """Read local CSV for Flow Metrics.
    
    Returns:
        DataFrame with flow survey data
    """
    if not os.path.exists(FLOW_DATA_FILE):
        logger.warning(f"{FLOW_DATA_FILE} not found. Returning empty DataFrame.")
        return pd.DataFrame(columns=["sprint_name", "flow_score_raw"])
    
    try:
        df = pd.read_csv(FLOW_DATA_FILE)
        # Ensure columns exist and normalize string
        if "sprint_name" in df.columns:
            df["sprint_name"] = df["sprint_name"].astype(str).str.strip()
        return df
    except Exception as e:
        logger.error(f"Error reading flow data: {e}")
        return pd.DataFrame(columns=["sprint_name", "flow_score_raw"])

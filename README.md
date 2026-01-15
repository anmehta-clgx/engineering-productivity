# Team AI Impact Index Dashboard

An automated dashboard that measures and tracks team productivity and AI adoption impact using data from Jira and team flow surveys.

## Overview

This tool generates an **AI Impact Index** by combining three core dimensions:
- **Velocity** (60%): Team throughput and efficiency
- **Flow** (25%): Team satisfaction and workflow quality from surveys
- **Quality** (15%): Defect rejection rates

## Methodology

### Core Metrics

#### 1. Velocity Score (60% of Final Index)
Combines throughput and efficiency using a **median-based graded curve**:

**Throughput (60% of Velocity)**
- **What it measures**: Number of completed tickets per sprint (Stories, Bugs, Tasks)
- **Why**: Captures all work, including unpointed items like bugs and tasks
- **Scoring approach**: 
  - Median tickets = 70% score (meets expectations)
  - 2× median = 100% score (excellent)
  - Below median scales proportionally down
  - Formula for above-median: `70 + (actual/median - 1) × 100` (capped at 100)
  - Formula for below-median: `70 × (actual/median)`

**Efficiency (40% of Velocity)**
- **What it measures**: Average cycle time per ticket (business days, excluding weekends)
- **Why**: Measures process health independently of volume
- **Scoring approach**: 
  - Median cycle time = 70% score (meets expectations)
  - 0.5× median (2× faster) = 100% score (excellent)
  - Above median (slower) scales proportionally down
  - Formula for better-than-median: `70 + (1 - actual/median) × 100` (capped at 100)
  - Formula for worse-than-median: `70 × (median/actual)`

**Why this weighting (60/40)?**
- Throughput weighted higher because shipping value matters most
- Prevents gaming: doing 1 ticket fast scores low on throughput
- Creating many small tickets is encouraged (better flow, smaller batches)

#### 2. Quality Score (15% of Final Index)
- **What it measures**: Combined quality metric of bug creation and rejections
- **Formula**: `(Bug Score × 60%) + (Rejection Score × 40%)`
  - **Bug Score** = max(0, 100 - (Bugs Created × 20)) — caps at 5 bugs = 0 score
  - **Rejection Score** = 100 - Rejection %
  - **Rejection %** = (Rejections / Delivered Items) × 100
    - Delivered Items = Stories + Bugs (excludes Tasks, which are auto-accepted)
- **Why**: Prioritizes actual quality issues (bugs) while still penalizing poor testing (rejections). Bug score capped at 5 bugs based on 90th percentile across teams.
- **Note**: Tasks excluded (auto-accepted in workflow)

#### 3. Flow Score (25% of Final Index)
- **What it measures**: Team-reported flow state from surveys
- **Scale**: 0-100, directly from survey responses
- **Why**: Captures subjective experience, psychological safety, and process friction

### Design Principles

#### No Arbitrary Targets
- **Problem**: Targets like "1 day per story point" are arbitrary and can be unrealistic
- **Solution**: All scoring is relative to team's own historical median performance
- **Benefit**: Self-adjusting baseline that moves with team capability

#### Graded on a Curve
- **70% = Median**: Represents "meeting expectations" (typical performance)
- **100% = Excellence**: Requires 2× improvement over median
- **Below 70%**: Indicates underperformance relative to team baseline
- **Rationale**: Creates meaningful differentiation while being achievable

#### Cycle Time Per Ticket (Not Per Point)
- **Data-driven decision**: Analysis showed 69% of tickets are unpointed (bugs, tasks)
- **Problem with per-point**: Ignores majority of team's work
- **Story point variance**: Low variance (CV=0.46) means ticket size differences are minimal
- **Independence**: Throughput (ticket count) and efficiency (time per ticket) don't double-count

#### Ticket Count vs Story Points
- **Throughput uses ticket count** because:
  - Captures all work types equally
  - Can't be gamed by inflating estimates
  - Aligns with DORA metrics (deployment frequency, not story points)
  - More objective and comparable over time
- **Story points still tracked** for planning purposes (retained in output)

### Research Foundation

This methodology aligns with industry research:

- **DORA Metrics** (Google DevOps Research): Focus on lead time and deployment frequency, not velocity
- **"Accelerate" (Forsgren, Humble, Kim)**: Story points poor for measurement; use cycle time + throughput
- **"Actionable Agile Metrics" (Vacanti)**: Use cycle time, throughput (item count), and WIP - not velocity
- **Flow Framework (Kersten)**: Flow Time + Flow Velocity (items, not points) + Flow Efficiency

## Status Definitions

The metrics pipeline relies on the following Jira status definitions:

- **Unstarted**: Issue has not been picked up yet.
- **Started**: Issue is "In Progress", actively being worked on (counts toward cycle time).
- **Blocked**: Issue cannot be worked on.
- **Peer Review**: Issue is "code complete", waiting on PR review from other developers (counts toward cycle time).
- **Finished**: Issue is merged in, but has not yet been verified in the testing environment (counts toward cycle time).
- **Delivered**: Issue has been verified by the developer in the testing environment (counts toward cycle time).
- **Accepted**: Issue has been verified by the TPM. **(Counts as Completion)**.
- **Rejected**: TPM rejected the issue, it needs to be restarted.
- **UAT**: Used to track releases, considered equivalent to **Accepted**.
- **Ready for Release**: Used to track releases, considered equivalent to **Accepted**.
- **Closed-Completed**: Used to track releases, considered equivalent to **Accepted**.
- **Closed-Canceled**: Issue should no longer be worked on.

## Cycle Time Calculation

**Definition**: Business days a ticket spends in active work states, excluding weekends.

**Active States**:
- Started (Development)
- Peer Review
- Finished (Final Review)
- Delivered (Customer Acceptance)

**Completion States** (used for "done" filter):
- Accepted
- UAT
- Ready for Release
- Closed-Completed

**Weekend Exclusion**: Uses `calculate_business_days()` method to exclude Saturdays and Sundays from all cycle time calculations.

## Data Sources

### Jira
- **Project**: Filtered by project key and team field (configurable via `FIELD_TEAM_FILTER_VALUE` in config)
- **Sprint Filter**: Only sprints with the configured team name in the sprint goal
- **Fields Used**:
  - Story Points: `customfield_10006`
  - Sprint: `customfield_10001`
  - Status, Issue Type, Created/Updated dates
  - Changelog (for cycle time calculation)

### Flow Survey Data
- **Source**: Local CSV file (`flow_survey_data.csv`)
- **Format**: `sprint_name`, `flow_score_raw` (0-100 scale)
- **Frequency**: Collected per sprint via team survey

## Output

### Executive Dashboard
Columns in final report:
- **Iteration Name**
- **Velocity Score** (60% weight)
- **Quality Score** (15% weight)
- **Flow Score** (25% weight)
- **Overall Score**

### Raw Data Log
Detailed per-ticket metrics for audit and analysis. Includes the following fields:
- Sprint Name
- Issue Key
- Issue Type
- Story Points
- Days In Progress
- Dev Cycle Time
- Review Cycle Time
- Acceptance Cycle Time
- Rejection Count
- Reached Delivered
- Status
- Timestamp
- Was Rejected?
- Created Date
- Sprint Start Date

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file:
```bash
JIRA_URL=https://yourinstance.atlassian.net
JIRA_USER=your-email@example.com
JIRA_TOKEN=your-api-token
JIRA_PROJECT_KEY=PROJ
GOOGLE_CREDENTIALS_JSON=/path/to/credentials.json  # Optional
```

## Usage

Run the main script to fetch data from Jira and calculate metrics:

```bash
python3 main.py [team_filter]
```

**Optional Parameter:**
- `team_filter`: Override the default team filter value from config. Example: `python3 main.py Foundation`

If no parameter is provided, uses the `FIELD_TEAM_FILTER_VALUE` from the configuration.

The dashboard will:
1. Fetch issues from Jira with changelog
2. Calculate cycle times and metrics per issue
3. Aggregate by sprint with median-based scoring
4. Display results in console
5. Upload to Google Sheets (if configured) or save to local files in `output/` directory

## Google Sheets Integration

Supports two authentication methods:
1. **Service Account**: Set `GOOGLE_CREDENTIALS_JSON` to path or JSON string
2. **Application Default Credentials**: Automatically used if service account not configured

**Offline mode**: If Google Sheets is unavailable, results are saved to local files in the `output/` directory:
- `Engineering Productivity - {JIRA_PROJECT_KEY} - {FIELD_TEAM_FILTER_VALUE}.xlsx` (main dashboard with Executive Dashboard and Raw Data Log tabs)
- `Raw Data Output - {JIRA_PROJECT_KEY} - {FIELD_TEAM_FILTER_VALUE}.csv` (raw metrics for analysis)

## Interpreting Scores

### Velocity Score
- **90-100**: Exceptional sprint - high throughput and fast cycle time
- **70-89**: Solid performance - meeting or exceeding typical baseline
- **50-69**: Below expectations - investigate bottlenecks
- **< 50**: Concerning - significant underperformance

### Quality Score
- **95-100**: Excellent - minimal bugs (0-1) and low rejections
- **80-94**: Good - moderate bugs (2-3) or some rejections
- **< 80**: Quality issues - high bug creation (4+) or high rejection rate

### Flow Score
- **80-100**: Team feels highly productive and aligned
- **60-79**: Moderate satisfaction - room for improvement
- **< 60**: Team experiencing friction or dissatisfaction

### Final AI Impact Index
- **85-100**: Outstanding - team operating at peak
- **70-84**: Strong - healthy performance
- **55-69**: Adequate - meets minimum expectations
- **< 55**: Needs attention - multiple areas underperforming

## Anti-Gaming Features

1. **Throughput dominance (60%)**: Can't excel with 1 fast ticket
2. **Median baseline**: Can't artificially lower expectations over time
3. **Quality gate (15%)**: High rejection rate penalizes overall score
4. **Ticket count (not points)**: Can't inflate by changing estimates
5. **Curve caps at 100%**: Prevents runaway scores from outliers

## Future Enhancements

- Cycle time variance (predictability metric)
- Configurable weights via environment variables

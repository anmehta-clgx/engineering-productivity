"""Configuration module for Team AI Impact Dashboard."""
import os
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# Jira Configuration
JIRA_URL = os.getenv("JIRA_URL")
JIRA_USER = os.getenv("JIRA_USER")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "PROJ")

# Google Sheets Configuration
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
SHEET_NAME = "Team AI Impact Index"

# Jira Custom Field IDs
FIELD_STORY_POINTS = "customfield_10006"
FIELD_SPRINT = "customfield_10001"
FIELD_TEAM_FILTER_KEY = "customfield_10400"
FIELD_TEAM_FILTER_VALUE = "Foundation"

# Status Configurations
COMPLETION_STATUSES = ['accepted', 'uat', 'ready for release', 'closedcompleted', 'closed completed']
DELIVERY_STATUSES = COMPLETION_STATUSES + ['delivered']

# ============================================================
# SCORING CONFIGURATION - All adjustable weights and targets
# ============================================================
# 
# Modify these values to adjust scoring behavior without changing code logic.
# All percentages are expressed as decimals (e.g., 0.60 = 60%).
# Weight groups should sum to 1.0 (100%).
#

# Final AI Impact Index Weights (must sum to 1.0)
WEIGHT_VELOCITY = 0.60      # 60% - Team throughput and efficiency
WEIGHT_QUALITY = 0.25       # 25% - Bug creation and rejection rates
WEIGHT_FLOW = 0.15          # 15% - Team satisfaction and workflow quality

# Velocity Score Sub-Weights (must sum to 1.0)
VELOCITY_WEIGHT_THROUGHPUT = 0.60   # 60% - Number of tickets completed
VELOCITY_WEIGHT_EFFICIENCY = 0.40   # 40% - Average cycle time per ticket

# Quality Score Sub-Weights (must sum to 1.0)
QUALITY_WEIGHT_BUGS = 0.60         # 60% - Bug creation rate
QUALITY_WEIGHT_REJECTIONS = 0.40   # 40% - Rejection rate

# Throughput & Efficiency Scoring Curves
MEDIAN_BASELINE_SCORE = 70.0       # Score for performing at team's median (meets expectations)
EXCELLENCE_SCORE = 100.0           # Score for excellent performance
THROUGHPUT_EXCELLENCE_MULTIPLIER = 2.0   # 2x median tickets = 100% score
EFFICIENCY_EXCELLENCE_MULTIPLIER = 0.5   # 0.5x median cycle time (2x faster) = 100% score

# Quality Scoring Parameters
BUG_PENALTY_PER_BUG = 20.0        # Points deducted per bug created
BUG_PENALTY_CAP = 5               # Maximum bugs before score reaches 0

# Flow Score Defaults
FLOW_DEFAULT_SCORE = 70.0         # Default flow score when no survey data exists (represents "meeting expectations")

# Sprint Configuration
SPRINT_DURATION_DAYS = 6          # Number of days to count for sprint period (0-indexed, so 6 = 7 days including start day)

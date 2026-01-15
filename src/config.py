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

# Data Files
FLOW_DATA_FILE = "../flow_survey_data.csv"

# Jira Custom Field IDs
FIELD_STORY_POINTS = "customfield_10006"
FIELD_SPRINT = "customfield_10001"
FIELD_TEAM_FILTER_KEY = "customfield_10400"
FIELD_TEAM_FILTER_VALUE = "Foundation"

# Status Configurations
COMPLETION_STATUSES = ['accepted', 'uat', 'ready for release', 'closedcompleted', 'closed completed']
DELIVERY_STATUSES = COMPLETION_STATUSES + ['delivered']

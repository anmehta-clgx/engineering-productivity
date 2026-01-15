"""Jira client module for fetching and connecting to Jira."""
import sys
import logging
from typing import List, Any
from jira import JIRA
from jira.exceptions import JIRAError
from config import (
    JIRA_URL,
    JIRA_USER,
    JIRA_TOKEN,
    JIRA_PROJECT_KEY,
    FIELD_STORY_POINTS,
    FIELD_SPRINT,
    FIELD_TEAM_FILTER_KEY,
    FIELD_TEAM_FILTER_VALUE
)

logger = logging.getLogger(__name__)


class JiraClient:
    """Handles Jira connection and data fetching."""
    
    def __init__(self, team_filter=None):
        """Initialize Jira client with credentials from config."""
        self.team_filter = team_filter if team_filter is not None else FIELD_TEAM_FILTER_VALUE
        self._validate_credentials()
        self.client = self._connect()
    
    @staticmethod
    def _validate_credentials():
        """Validate that required Jira credentials are present."""
        if not all([JIRA_URL, JIRA_USER, JIRA_TOKEN]):
            logger.error("Missing required JIRA environment variables.")
            sys.exit(1)
    
    def _connect(self) -> JIRA:
        """Connect to Jira instance."""
        try:
            return JIRA(server=JIRA_URL, basic_auth=(JIRA_USER, JIRA_TOKEN))
        except Exception as e:
            logger.error(f"Failed to connect to Jira: {e}")
            sys.exit(1)
    
    def fetch_issues(self) -> List[Any]:
        """Fetch recent issues from Jira with changelog.
        
        Returns:
            List of Jira issue objects
        """
        jql_query = (
            f'project = "{JIRA_PROJECT_KEY}" AND '
            f'"{FIELD_TEAM_FILTER_KEY}" = "{self.team_filter}" '
            f'ORDER BY created DESC'
        )
        
        logger.info(f"Fetching issues with JQL: {jql_query}")
        issues = []
        
        try:
            next_token = None
            while True:
                kwargs = {
                    "maxResults": 100,
                    "expand": 'changelog',
                    "fields": (
                        f'summary,status,issuetype,created,updated,'
                        f'{FIELD_STORY_POINTS},{FIELD_SPRINT},{FIELD_TEAM_FILTER_KEY}'
                    )
                }
                if next_token:
                    kwargs['nextPageToken'] = next_token
                    
                fetched = self.client.enhanced_search_issues(jql_query, **kwargs)
                issues.extend(fetched)
                
                next_token = getattr(fetched, 'nextPageToken', None)
                if not next_token:
                    break
                    
            logger.info(f"Fetched {len(issues)} issues via enhanced_search_issues.")
            return issues
        except Exception as e:
            logger.error(f"Error fetching Jira issues: {e}")
            return []

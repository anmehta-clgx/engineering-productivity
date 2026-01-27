import logging
import sys
import pandas as pd
from jira_client import JiraClient
from sheets_client import SheetsClient
from metrics_processor import process_issue_metrics, load_flow_data
from dashboard_calculator import calculate_scores
from config import FIELD_TEAM_FILTER_VALUE

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TeamImpactDashboard:
    """Main orchestrator for Team AI Impact Dashboard."""
    
    def __init__(self, team_filter=None):
        """Initialize dashboard with Jira and Sheets clients."""
        self.team_filter = team_filter if team_filter is not None else FIELD_TEAM_FILTER_VALUE
        self.jira_client = JiraClient(team_filter=self.team_filter)
        self.sheets_client = SheetsClient(team_filter=self.team_filter)
    
    def run(self):
        """Run the complete dashboard generation process."""
        logger.info("Starting Team AI Impact Index Build...")
        
        # 1. Fetch External Data
        flow_df = load_flow_data(team_filter=self.team_filter)
        jira_issues = self.jira_client.fetch_issues()
        
        if not jira_issues:
            logger.warning("No issues found. Exiting.")
            return

        # 2. Process Raw Metrics
        raw_metrics = []
        for issue in jira_issues:
            try:
                metrics = process_issue_metrics(issue, team_filter=self.team_filter)
                if metrics:
                    raw_metrics.append(metrics)
            except Exception as e:
                logger.warning(f"Error processing issue {issue.key}: {e}")
        
        raw_df = pd.DataFrame(raw_metrics)
        
        # 3. Calculate Aggregated Dashboard
        dashboard_df = calculate_scores(raw_df, flow_df)
        
        # 4. Display in Console for Verification
        preview = False
        if preview:
            print("\n--- EXECUTIVE DASHBOARD PREVIEW ---")
            print(dashboard_df.to_string(index=False))
            print("\n-----------------------------------")

        # 5. Push to Google Sheets
        self.sheets_client.update_sheets(raw_df, dashboard_df)
        logger.info("Done.")


if __name__ == "__main__":
    # Parse command-line arguments
    team_filter = sys.argv[1] if len(sys.argv) > 1 else FIELD_TEAM_FILTER_VALUE
    logger.info(f"Running dashboard for team: {team_filter}")
    
    app = TeamImpactDashboard(team_filter=team_filter)
    app.run()

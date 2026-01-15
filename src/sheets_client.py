"""Google Sheets client module for connecting and updating sheets."""
import os
import json
import logging
import pandas as pd
import gspread
from openpyxl.formatting.rule import ColorScaleRule
from config import GOOGLE_CREDENTIALS_JSON, GOOGLE_SHEET_URL, SHEET_NAME, JIRA_PROJECT_KEY, FIELD_TEAM_FILTER_VALUE

logger = logging.getLogger(__name__)


class SheetsClient:
    """Handles Google Sheets connection and data updates."""
    
    def __init__(self, team_filter=None):
        """Initialize Google Sheets client."""
        self.team_filter = team_filter if team_filter is not None else FIELD_TEAM_FILTER_VALUE
        self.client = self._connect()
    
    def _connect(self) -> gspread.Client:
        """Connect to Google Sheets using available credentials.
        
        Returns:
            Google Sheets client or None if connection fails
        """
        # Method 1: Service Account JSON file (FREE - no Google Cloud paid account needed!)
        if GOOGLE_CREDENTIALS_JSON:
            try:
                logger.info("Attempting to use Service Account credentials...")
                if GOOGLE_CREDENTIALS_JSON.strip().startswith("{"):
                    # JSON string in environment variable
                    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
                    return gspread.service_account_from_dict(creds_dict)
                elif os.path.exists(GOOGLE_CREDENTIALS_JSON):
                    # Path to JSON file
                    return gspread.service_account(filename=GOOGLE_CREDENTIALS_JSON)
                else:
                    logger.error(f"Service account file not found: {GOOGLE_CREDENTIALS_JSON}")
            except Exception as e:
                logger.error(f"Failed to use Service Account credentials: {e}")

        # Method 2: API Key (only works for PUBLIC sheets - read-only)
        api_key = os.getenv('GOOGLE_API_KEY')
        if api_key:
            try:
                logger.info("Attempting to use API Key (read-only for public sheets)...")
                logger.warning("Note: API Keys only work for PUBLIC sheets and read-only access")
                # Return a special marker to use the API key method
                return 'USE_API_KEY'
            except Exception as e:
                logger.error(f"Failed to use API Key: {e}")

        # No valid authentication method found
        logger.error("=" * 60)
        logger.error("NO GOOGLE SHEETS ACCESS - Running in OFFLINE MODE")
        logger.error("=" * 60)
        logger.info(f"Data will be saved to: ../output/Engineering Productivity - {JIRA_PROJECT_KEY} - {self.team_filter}.xlsx and ../output/Raw Data Output - {JIRA_PROJECT_KEY} - {self.team_filter}.csv")
        return None
    
    def update_sheets(self, raw_df: pd.DataFrame, dashboard_df: pd.DataFrame):
        """Write dataframes to Google Sheets tabs.
        
        Args:
            raw_df: Raw metrics dataframe
            dashboard_df: Aggregated dashboard dataframe
        """
        if not self.client:
            logger.warning("Google Sheets client is not connected. Saving to local files instead...")
            self._save_local_files(raw_df, dashboard_df)
            return

        try:
            # Open Sheet - priority: URL/ID from env var, then by name
            if GOOGLE_SHEET_URL:
                logger.info(f"Opening Google Sheet from URL: {GOOGLE_SHEET_URL[:50]}...")
                try:
                    sh = self.client.open_by_url(GOOGLE_SHEET_URL)
                except Exception as e:
                    logger.error(f"Failed to open sheet by URL: {e}")
                    # Extract sheet ID from URL and try by key
                    import re
                    match = re.search(r'/d/([a-zA-Z0-9-_]+)', GOOGLE_SHEET_URL)
                    if match:
                        sheet_id = match.group(1)
                        logger.info(f"Trying to open by extracted ID: {sheet_id}")
                        sh = self.client.open_by_key(sheet_id)
                    else:
                        raise Exception(f"Could not extract sheet ID from URL: {GOOGLE_SHEET_URL}")
            else:
                try:
                    sh = self.client.open(SHEET_NAME)
                except gspread.SpreadsheetNotFound:
                    logger.info(f"Spreadsheet '{SHEET_NAME}' not found. Creating it.")
                    sh = self.client.create(SHEET_NAME)
                    sh.share(os.getenv("ADMIN_EMAIL", "admin@example.com"), perm_type='user', role='writer')
            
            # Update Tab 1: Raw_Data_Log (receives what was the full executive dashboard)
            try:
                ws_raw = sh.worksheet("Raw_Data_Log")
            except gspread.WorksheetNotFound:
                ws_raw = sh.add_worksheet(title="Raw_Data_Log", rows=1000, cols=20)
            
            ws_raw.clear()
            ws_raw.update([dashboard_df.columns.values.tolist()] + dashboard_df.values.tolist())
            
            # Update Tab 2: Executive_Dashboard (simplified to 5 columns with renamed headers)
            try:
                ws_dash = sh.worksheet("Executive_Dashboard")
            except gspread.WorksheetNotFound:
                ws_dash = sh.add_worksheet(title="Executive_Dashboard", rows=100, cols=5)
            
            # Create simplified dashboard with renamed columns
            simplified_dash = dashboard_df[[
                'Sprint Name', 'Velocity Score', 'Quality Score', 'Flow Score', 'FINAL AI IMPACT INDEX'
            ]].copy()
            simplified_dash.rename(columns={
                'Sprint Name': 'Iteration Name',
                'FINAL AI IMPACT INDEX': 'Overall Score'
            }, inplace=True)
            
            ws_dash.clear()
            ws_dash.update([simplified_dash.columns.values.tolist()] + simplified_dash.values.tolist())
            
            # Apply color scale to Overall Score column (column E, index 5)
            self._apply_color_scale(sh, ws_dash, simplified_dash)
            
            logger.info("Successfully updated Google Sheets.")
            
        except Exception as e:
            logger.error(f"Failed to update Google Sheets: {e}")
    
    def _apply_color_scale(self, spreadsheet, worksheet, dataframe):
        """Apply color scale conditional formatting to Overall Score column.
        
        Args:
            spreadsheet: gspread Spreadsheet object
            worksheet: gspread Worksheet object
            dataframe: DataFrame to determine data range
        """
        try:
            num_rows = len(dataframe) + 1  # +1 for header
            
            # Define color scale: red (low) -> yellow (mid) -> green (high)
            requests = [{
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": worksheet.id,
                            "startRowIndex": 1,  # Start after header
                            "endRowIndex": num_rows,
                            "startColumnIndex": 4,  # Column E (Overall Score)
                            "endColumnIndex": 5
                        }],
                        "gradientRule": {
                            "minpoint": {
                                "color": {"red": 0.957, "green": 0.427, "blue": 0.427},  # Red
                                "type": "MIN"
                            },
                            "midpoint": {
                                "color": {"red": 1.0, "green": 0.902, "blue": 0.6},  # Yellow
                                "type": "PERCENTILE",
                                "value": "50"
                            },
                            "maxpoint": {
                                "color": {"red": 0.573, "green": 0.816, "blue": 0.518},  # Green
                                "type": "MAX"
                            }
                        }
                    },
                    "index": 0
                }
            }]
            
            spreadsheet.batch_update({"requests": requests})
            logger.info("Applied color scale to Overall Score column")
            
        except Exception as e:
            logger.warning(f"Could not apply color scale: {e}")
    
    def _save_local_files(self, raw_df: pd.DataFrame, dashboard_df: pd.DataFrame):
        """Save dataframes to local files when Google Sheets is unavailable.
        
        Args:
            raw_df: Raw metrics dataframe
            dashboard_df: Aggregated dashboard dataframe
        """
        try:
            # Save as Excel file with multiple sheets
            os.makedirs('../output', exist_ok=True)
            output_file = f'../output/Engineering Productivity - {JIRA_PROJECT_KEY} - {self.team_filter}.xlsx'
            
            # Create simplified dashboard with renamed columns
            simplified_dash = dashboard_df[[
                'Sprint Name', 'Velocity Score', 'Quality Score', 'Flow Score', 'FINAL AI IMPACT INDEX'
            ]].copy()
            simplified_dash.rename(columns={
                'Sprint Name': 'Iteration Name',
                'FINAL AI IMPACT INDEX': 'Overall Score'
            }, inplace=True)
            
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                simplified_dash.to_excel(writer, sheet_name='Executive_Dashboard', index=False)
                dashboard_df.to_excel(writer, sheet_name='Raw_Data_Log', index=False)
                
                # Apply color scale to Overall Score column in Executive_Dashboard
                workbook = writer.book
                worksheet = writer.sheets['Executive_Dashboard']
                
                # Column E (Overall Score) - apply to data rows only
                num_rows = len(simplified_dash)
                color_scale = ColorScaleRule(
                    start_type='min', start_color='F4B4B4',  # Red
                    mid_type='percentile', mid_value=50, mid_color='FFE699',  # Yellow
                    end_type='max', end_color='92D192'  # Green
                )
                worksheet.conditional_formatting.add(f'E2:E{num_rows + 1}', color_scale)
                
                # Auto-adjust column widths for Executive_Dashboard
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value:
                                max_length = max(max_length, len(str(cell.value)))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)  # Add padding, cap at 50
                    worksheet.column_dimensions[column_letter].width = adjusted_width
                
                # Auto-adjust column widths for Raw_Data_Log
                raw_worksheet = writer.sheets['Raw_Data_Log']
                for column in raw_worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if cell.value:
                                max_length = max(max_length, len(str(cell.value)))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)  # Add padding, cap at 50
                    raw_worksheet.column_dimensions[column_letter].width = adjusted_width
            
            logger.info(f"✓ Saved to Excel file: {output_file}")
            logger.info("  You can manually upload this to Google Sheets")
            
            # Also save raw data as CSV for easy viewing
            csv_file = f'../output/Raw Data Output - {JIRA_PROJECT_KEY} - {self.team_filter}.csv'
            raw_df.to_csv(csv_file, index=False)
            logger.info(f"✓ Saved raw data to: {csv_file}")
            
        except Exception as e:
            logger.error(f"Failed to save local files: {e}")
            logger.error(f"Failed to update Google Sheets: {e}")

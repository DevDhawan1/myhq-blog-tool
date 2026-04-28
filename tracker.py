import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = ["Title", "Slug", "Category", "Post ID", "Status", "Date Published", "Edit URL", "Live URL"]


def _get_worksheet(credentials_file: str, sheet_url: str):
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_url(sheet_url).sheet1


def ensure_headers(credentials_file: str, sheet_url: str) -> None:
    """Add header row if the sheet is empty."""
    try:
        ws = _get_worksheet(credentials_file, sheet_url)
        if not ws.row_values(1):
            ws.append_row(HEADERS)
    except Exception:
        pass


def append_tracking_row(credentials_file: str, sheet_url: str, row: dict) -> bool:
    """Append one blog publish record. Returns True on success."""
    try:
        ws = _get_worksheet(credentials_file, sheet_url)
        ws.append_row([
            row.get("title", ""),
            row.get("slug", ""),
            row.get("category", ""),
            str(row.get("post_id", "")),
            row.get("status", "draft"),
            row.get("date", datetime.now().strftime("%Y-%m-%d")),
            row.get("edit_url", ""),
            row.get("live_url", ""),
        ])
        return True
    except Exception:
        return False


def update_post_status(credentials_file: str, sheet_url: str, post_id: int, new_status: str) -> bool:
    """Find a row by Post ID and update its Status column."""
    try:
        ws = _get_worksheet(credentials_file, sheet_url)
        cell = ws.find(str(post_id))
        if cell:
            ws.update_cell(cell.row, 5, new_status)
            return True
        return False
    except Exception:
        return False

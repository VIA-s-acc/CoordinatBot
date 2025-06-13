import gspread
from oauth2client.service_account import ServiceAccountCredentials

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

CREDS_FILE = 'coordinate-462818-25b2ec4c500a.json'

def get_client():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
    return gspread.authorize(creds)

def list_spreadsheets():
    client = get_client()
    return client.list_spreadsheet_files()

def open_sheet_by_id(spreadsheet_id: str):
    client = get_client()
    return client.open_by_key(spreadsheet_id)

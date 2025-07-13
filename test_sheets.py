from googleapiclient.discovery import build
from google.oauth2 import service_account
import os
import base64
import json

SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '1pbNY5cdwHtmzdKBUZB-GV7bE6TaVajrFCBt9x7oyhko')
RANGE = 'Expenses'

def get_google_creds():
    GOOGLE_CREDS_B64 = os.environ.get("GOOGLE_CREDS_B64")
    if GOOGLE_CREDS_B64:
        creds_json = base64.b64decode(GOOGLE_CREDS_B64).decode('utf-8')
        creds_info = json.loads(creds_json)
        return service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
    else:
        return service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )

creds = get_google_creds()
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

values = [
    [
        "2024-07-13",
        "2024-07-13T21:13:00",
        "200",
        "INR",
        "Lunch",
        "gaurav",
        "No file",
        "200 for lunch"
    ]
]

result = sheet.values().append(
    spreadsheetId=SPREADSHEET_ID,
    range=RANGE,
    valueInputOption='USER_ENTERED',
    body={'values': values}
).execute()

print("Row appended:", result)

from googleapiclient.discovery import build
from google.oauth2 import service_account

SPREADSHEET_ID = '1pbNY5cdwHtmzdKBUZB-GV7bE6TaVajrFCBt9x7oyhko'
RANGE = 'Expenses'

creds = service_account.Credentials.from_service_account_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
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
                                                                
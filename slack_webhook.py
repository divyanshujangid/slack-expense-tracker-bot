from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
import datetime
import os

app = Flask(__name__)

# === Google Sheets Setup ===
SERVICE_ACCOUNT_FILE = 'credentials.json'
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', 'YOUR_SPREADSHEET_ID')  # set your ID or use env var
RANGE = 'Expenses'

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

@app.route("/slack/events", methods=["POST"])
def slack_events():
    print("\n=== POST RECEIVED ===")
    print(request.json)

    data = request.json
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    if data.get("event", {}).get("type") == "message":
        event = data["event"]
        text = event.get("text", "")
        user = event.get("user", "")
        print(f"NEW MESSAGE: {text} from user {user}")

        # Handle multi-line and multi-expense messages
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                amount, description = line.split("-", 1)
                amount = amount.strip()
                description = description.strip()
            except Exception:
                amount = ""
                description = line.strip()

            values = [
                [
                    datetime.date.today().isoformat(),
                    datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    amount,
                    "INR",
                    description,
                    user,
                    "",  # Invoice URL (future)
                    line
                ]
            ]
            try:
                result = sheet.values().append(
                    spreadsheetId=SPREADSHEET_ID,
                    range=RANGE,
                    valueInputOption='USER_ENTERED',
                    body={'values': values}
                ).execute()
                print(f"Row appended for: {line}")
            except Exception as e:
                print(f"Error appending row for '{line}': {e}")

    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

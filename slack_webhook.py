from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
import dropbox
import pytz
import requests
import datetime
import os
import base64
import json
import re
import tempfile

app = Flask(__name__)

# === ENV VARS ===
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
GOOGLE_CREDS_B64 = os.environ.get('GOOGLE_CREDS_B64')
DROPBOX_ACCESS_TOKEN = os.environ.get('DROPBOX_ACCESS_TOKEN')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
RANGE = 'Expenses'

def get_google_creds():
    creds_info = json.loads(base64.b64decode(GOOGLE_CREDS_B64).decode('utf-8'))
    return service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            # No longer using Drive
        ]
    )

creds = get_google_creds()
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

def extract_expense_info(line):
    # Example: "$200 - lunch", "1500 INR dinner", "19$ Anthropic", "₹220 Chai"
    match = re.match(r'([₹$€£]?\s?[\d,]+(?:\.\d{1,2})?)\s*([A-Za-z$₹€£]*)\s*[-:]?\s*(.*)', line)
    if match:
        amount = match.group(1).replace(',', '').replace(' ', '')
        currency = match.group(2) if match.group(2) else ''
        description = match.group(3).strip() or line
    else:
        amount = ''
        currency = ''
        description = line
    # Clean up currency
    if not currency and amount and amount[0] in '₹$€£':
        currency = amount[0]
        amount = amount[1:]
    return amount.strip(), currency.strip(), description.strip()

def upload_file_to_dropbox(file_bytes, filename):
    dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
    path = f"/{filename}"
    try:
        dbx.files_upload(file_bytes, path, mute=True)
        shared_link_metadata = dbx.sharing_create_shared_link_with_settings(path)
        link = shared_link_metadata.url.replace("?dl=0", "?raw=1")
        return link
    except Exception as e:
        print("Dropbox upload failed:", e)
        return ""

@app.route("/slack/events", methods=["POST"])
def slack_events():
    print("\n=== POST RECEIVED ===")
    data = request.json
    print(data)

    # Slack URL verification (for the initial setup)
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    if data.get("event", {}).get("type") == "message":
        event = data["event"]
        text = event.get("text", "")
        user = event.get("user", "")
        files = event.get("files", [])
        timestamp = datetime.datetime.fromtimestamp(
            float(event.get("ts", datetime.datetime.now().timestamp())),
            tz=pytz.timezone('Asia/Kolkata')
        ).strftime('%Y-%m-%d %H:%M:%S')

        # Support multi-line/multi-expense messages
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            amount, currency, description = extract_expense_info(line)
            invoice_url = ""
            # If there's a file, upload it and get the URL (one file per message)
            if files:
                for file_obj in files:
                    url = file_obj.get("url_private_download") or file_obj.get("url_private")
                    fname = file_obj.get("name", "invoice")
                    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
                    r = requests.get(url, headers=headers)
                    if r.status_code == 200:
                        invoice_url = upload_file_to_dropbox(r.content, fname)
                    else:
                        print("Failed to download file:", r.text)
                        invoice_url = ""
                    break  # Only upload first file per message
            values = [
                [
                    datetime.date.today().isoformat(),
                    timestamp,
                    amount,
                    currency or "INR",
                    description,
                    user,
                    invoice_url,
                    line
                ]
            ]
            try:
                sheet.values().append(
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
    print(f"Using Google Sheet ID: {SPREADSHEET_ID}")
    app.run(host="0.0.0.0", port=5000)

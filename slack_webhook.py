from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload
import pytz
import requests
import datetime
import os
import base64
import json
import re
import tempfile

app = Flask(__name__)

# Google Sheets and Drive Setup
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
GOOGLE_CREDS_B64 = os.environ.get('GOOGLE_CREDS_B64')
SHARED_DRIVE_ID = os.environ.get('SHARED_DRIVE_ID')
INVOICE_FOLDER_ID = os.environ.get('INVOICE_FOLDER_ID')  # optional, can be the same as SHARED_DRIVE_ID

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')

RANGE = 'Expenses'

def get_google_creds():
    creds_info = json.loads(base64.b64decode(GOOGLE_CREDS_B64).decode('utf-8'))
    return service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
    )

creds = get_google_creds()
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()
drive_service = build('drive', 'v3', credentials=creds)

def extract_expense_info(line):
    # Try to extract amount, currency, description
    # Example matches: "$200 - lunch", "1500 INR dinner", "19$ Anthropic", "₹220 Chai"
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

def upload_file_to_drive(file_url, filename):
    # Download file from Slack using bot token
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    r = requests.get(file_url, headers=headers)
    if r.status_code != 200:
        print("Failed to download file:", r.text)
        return ""

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(r.content)
        tmp.flush()
        mime_type = r.headers.get('Content-Type', 'application/octet-stream')
        file_metadata = {
            'name': filename,
            'driveId': SHARED_DRIVE_ID,
            'supportsAllDrives': True,
            'parents': [INVOICE_FOLDER_ID or SHARED_DRIVE_ID]
        }
        media = MediaFileUpload(tmp.name, mimetype=mime_type)
        try:
            drive_file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                supportsAllDrives=True,
                fields='id, webViewLink'
            ).execute()
            file_id = drive_file.get('id')
            link = drive_file.get('webViewLink')
            # Make public (anyone with link)
            drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True
            ).execute()
            return link
        except Exception as e:
            print("File upload error:", e)
            return ""
        finally:
            os.unlink(tmp.name)

@app.route("/slack/events", methods=["POST"])
def slack_events():
    print("\n=== POST RECEIVED ===")
    data = request.json
    print(data)

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

        # Handle multi-line and multi-expense messages
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            amount, currency, description = extract_expense_info(line)

            invoice_url = ""
            # If there's a file, upload it and get the URL
            if files:
                for file_obj in files:
                    url = file_obj.get("url_private_download") or file_obj.get("url_private")
                    fname = file_obj.get("name", "invoice")
                    invoice_url = upload_file_to_drive(url, fname)
                    break  # Only one file per line for now

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
    app.run(host="0.0.0.0", port=5000)

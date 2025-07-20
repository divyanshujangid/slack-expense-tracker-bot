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
import time

app = Flask(__name__)

# Env Variables
def get_env(name, default=None, required=True):
    value = os.environ.get(name, default)
    if required and value is None:
        raise Exception(f"Missing required environment variable: {name}")
    return value

SPREADSHEET_ID = get_env('SPREADSHEET_ID')
GOOGLE_CREDS_B64 = get_env('GOOGLE_CREDS_B64')
SHARED_DRIVE_ID = get_env('SHARED_DRIVE_ID')
INVOICE_FOLDER_ID = os.environ.get('INVOICE_FOLDER_ID', SHARED_DRIVE_ID)
SLACK_BOT_TOKEN = get_env('SLACK_BOT_TOKEN')

RANGE = 'Expenses'

# Deduplication (in-memory, auto-clears old entries)
processed_events = {}
EVENT_TTL = 600  # 10 minutes

def is_duplicate(event):
    event_id = event.get('client_msg_id') or event.get('ts') or event.get('event_ts')
    now = time.time()
    # Clean out old events
    for k in list(processed_events.keys()):
        if now - processed_events[k] > EVENT_TTL:
            del processed_events[k]
    if event_id in processed_events:
        return True
    processed_events[event_id] = now
    return False

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
    match = re.match(r'([₹$€£]?\s?[\d,]+(?:\.\d{1,2})?)\s*([A-Za-z$₹€£]*)\s*[-:]?\s*(.*)', line)
    if match:
        amount = match.group(1).replace(',', '').replace(' ', '')
        currency = match.group(2) if match.group(2) else ''
        description = match.group(3).strip() or line
    else:
        amount = ''
        currency = ''
        description = line
    if not currency and amount and amount[0] in '₹$€£':
        currency = amount[0]
        amount = amount[1:]
    return amount.strip(), currency.strip(), description.strip()

def upload_file_to_drive(file_url, filename):
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

        # DEDUPLICATION
        if is_duplicate(event):
            print(f"Duplicate event, skipping: {event.get('client_msg_id') or event.get('ts')}")
            return "", 200

        text = event.get("text", "")
        user = event.get("user", "")
        files = event.get("files", [])
        timestamp = datetime.datetime.fromtimestamp(
            float(event.get("ts", datetime.datetime.now().timestamp())),
            tz=pytz.timezone('Asia/Kolkata')
        ).strftime('%Y-%m-%d %H:%M:%S')

        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            amount, currency, description = extract_expense_info(line)
            invoice_url = ""
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
    print(f"Using Google Sheet ID: {SPREADSHEET_ID}")
    app.run(host="0.0.0.0", port=5000)

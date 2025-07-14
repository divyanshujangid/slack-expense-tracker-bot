import os
import re
import datetime
import requests
import base64
import json
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
import pytz

# === CONFIG ===
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', 'YOUR_SPREADSHEET_ID')
RANGE = 'Expenses'
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
IST = pytz.timezone('Asia/Kolkata')

# --- Credentials Loader (local or Railway/Cloud env var)
def get_google_creds():
    GOOGLE_CREDS_B64 = os.environ.get("GOOGLE_CREDS_B64")
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    if GOOGLE_CREDS_B64:
        creds_json = base64.b64decode(GOOGLE_CREDS_B64).decode('utf-8')
        creds_info = json.loads(creds_json)
        return service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=scopes
        )
    else:
        return service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=scopes
        )

creds = get_google_creds()
sheets_service = build('sheets', 'v4', credentials=creds)
drive_service = build('drive', 'v3', credentials=creds)

app = Flask(__name__)

def extract_amount_currency(text):
    """
    Parses string to get amount and currency symbol
    """
    match = re.match(r'^\s*([\₹$€£]?)(\d+(?:\.\d+)?)([A-Za-z]{3}|[\₹$€£]?)', text)
    if not match:
        return "", "INR"
    symbol = match.group(1) or match.group(3)
    amount = match.group(2)
    # Currency detection logic
    currency_map = {
        "₹": "INR", "$": "USD", "€": "EUR", "£": "GBP",
        "INR": "INR", "USD": "USD", "EUR": "EUR", "GBP": "GBP"
    }
    currency = currency_map.get(symbol.upper(), "INR")
    return amount, currency

def get_ist_timestamp(slack_ts):
    dt_utc = datetime.datetime.fromtimestamp(float(slack_ts), tz=pytz.UTC)
    dt_ist = dt_utc.astimezone(IST)
    return dt_ist.strftime('%Y-%m-%d %H:%M:%S'), dt_ist.date().isoformat()

def upload_file_to_drive(file_url, filename):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    resp = requests.get(file_url, headers=headers)
    if resp.status_code != 200:
        return ""
    file_metadata = {"name": filename}
    import tempfile
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        tmp.write(resp.content)
        tmp.flush()
        drive_file = drive_service.files().create(
            body=file_metadata,
            media_body=tmp.name,
            fields='id'
        ).execute()
    file_id = drive_file.get('id')
    drive_service.permissions().create(
        fileId=file_id,
        body={'role': 'reader', 'type': 'anyone'},
        fields='id'
    ).execute()
    link = f"https://drive.google.com/uc?id={file_id}&export=download"
    return link

@app.route("/slack/events", methods=["POST"])
def slack_events():
    print("\n=== POST RECEIVED ===")
    data = request.json

    # Slack verification
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    if data.get("event", {}).get("type") == "message":
        event = data["event"]
        user = event.get("user", "")
        text = event.get("text", "")
        slack_ts = event.get("ts", "")
        files = event.get("files", [])

        timestamp_str, date_str = get_ist_timestamp(slack_ts) if slack_ts else (
            datetime.datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S'),
            datetime.date.today().isoformat()
        )

        invoice_links = []
        for f in files:
            file_url = f.get('url_private_download') or f.get('url_private')
            filename = f.get('name', 'Invoice')
            if file_url:
                link = upload_file_to_drive(file_url, filename)
                if link:
                    invoice_links.append(link)
        invoice_url = ", ".join(invoice_links) if invoice_links else ""

        # Parse multi-line messages
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            # Try "amount - description" split
            if "-" in line:
                left, right = line.split("-", 1)
                amount, currency = extract_amount_currency(left.strip())
                description = right.strip().capitalize()
            else:
                amount, currency = extract_amount_currency(line)
                description = line if not amount else line.replace(amount, '', 1).strip().capitalize()

            values = [[
                date_str,           # Date
                timestamp_str,      # Timestamp (IST)
                amount,             # Amount
                currency,           # Currency
                description,        # Description
                user,               # User
                invoice_url,        # Invoice URL
                line                # Original Message
            ]]
            try:
                sheets_service.spreadsheets().values().append(
                    spreadsheetId=SPREADSHEET_ID,
                    range=RANGE,
                    valueInputOption='USER_ENTERED',
                    body={'values': values}
                ).execute()
                print(f"Row appended: {values}")
            except Exception as e:
                print(f"Failed to append row: {e}")

    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

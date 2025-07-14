from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
import datetime
import os
import base64
import json
import pytz
import tempfile
import requests
import magic  # For MIME type detection

app = Flask(__name__)

# === Google Sheets Setup ===
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', 'YOUR_SPREADSHEET_ID')
RANGE = 'Expenses'

# Load Google Service Account Credentials
def get_google_creds():
    GOOGLE_CREDS_B64 = os.environ.get("GOOGLE_CREDS_B64")
    if GOOGLE_CREDS_B64:
        creds_json = base64.b64decode(GOOGLE_CREDS_B64).decode('utf-8')
        creds_info = json.loads(creds_json)
        return service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
    else:
        return service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )

creds = get_google_creds()
sheet_service = build('sheets', 'v4', credentials=creds)
sheet = sheet_service.spreadsheets()
drive_service = build('drive', 'v3', credentials=creds)

# Set your local timezone
LOCAL_TIMEZONE = os.environ.get("TIMEZONE", "Asia/Kolkata")

def get_local_now():
    utc_now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    local_tz = pytz.timezone(LOCAL_TIMEZONE)
    return utc_now.astimezone(local_tz)

def detect_currency_and_amount(text):
    # Simple detection of amount and currency symbol (₹, $, €, etc.)
    import re
    match = re.search(r'([₹$€¥]?)(\d+(\.\d{1,2})?)', text)
    if match:
        symbol, amount, _ = match.groups()
        if symbol == '₹':
            currency = 'INR'
        elif symbol == '$':
            currency = 'USD'
        elif symbol == '€':
            currency = 'EUR'
        elif symbol == '¥':
            currency = 'JPY'
        else:
            currency = 'INR'  # Default
        return amount, currency
    return "", "INR"

def extract_description(text):
    # After the amount, whatever is left is description
    import re
    parts = re.split(r'([₹$€¥]?\d+(\.\d{1,2})?)', text, maxsplit=1)
    desc = ""
    if len(parts) > 2:
        desc = parts[2].strip(" -:.") or "Expense"
    else:
        desc = text.strip()
    return desc

def upload_file_to_drive(file_url, filename):
    # Download the file to a temp file
    resp = requests.get(file_url)
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(resp.content)
        tmp_path = tmp_file.name

    # Detect MIME type
    mime = magic.Magic(mime=True)
    mime_type = mime.from_file(tmp_path)
    file_metadata = {'name': filename}
    media = MediaFileUpload(tmp_path, mimetype=mime_type)
    drive_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    file_id = drive_file.get('id')
    link = drive_file.get('webViewLink')
    # Make the file public
    drive_service.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()
    os.unlink(tmp_path)
    return link

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
        files = event.get("files", [])
        print(f"NEW MESSAGE: {text} from user {user}")

        invoice_url = ""
        if files:
            # Handle only first file for simplicity, can be looped if needed
            file_info = files[0]
            file_url = file_info.get("url_private_download") or file_info.get("url_private")
            filename = file_info.get("name")
            # Use SLACK_BOT_TOKEN for authentication in headers
            slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
            headers = {"Authorization": f"Bearer {slack_token}"}
            # Download with auth
            resp = requests.get(file_url, headers=headers)
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(resp.content)
                tmp_path = tmp_file.name
            # Detect MIME type
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(tmp_path)
            media = MediaFileUpload(tmp_path, mimetype=mime_type)
            file_metadata = {'name': filename}
            drive_file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            file_id = drive_file.get('id')
            invoice_url = drive_file.get('webViewLink')
            drive_service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
            ).execute()
            os.unlink(tmp_path)

        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            amount, currency = detect_currency_and_amount(line)
            description = extract_description(line)
            now = get_local_now()
            values = [
                [
                    now.date().isoformat(),
                    now.strftime('%Y-%m-%d %H:%M:%S'),
                    amount,
                    currency,
                    description,
                    user,
                    invoice_url,
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

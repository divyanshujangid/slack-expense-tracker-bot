from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload
import datetime
import pytz
import os
import base64
import json
import requests
import filetype

app = Flask(__name__)

# === Google Sheets & Drive Setup ===
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
RANGE = 'Expenses'

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

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")

def get_currency_and_amount(text):
    import re
    # Try to extract currency and amount (₹, $, etc.)
    match = re.search(r'([\₹$€])?\s?([0-9]+(?:[.,][0-9]+)?)', text)
    if match:
        currency = match.group(1) if match.group(1) else "INR"
        amount = match.group(2)
    else:
        currency = "INR"
        amount = ""
    return currency, amount

def download_slack_file(url, bot_token, filename):
    headers = {"Authorization": f"Bearer {bot_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Slack file download failed: {response.status_code}")
    temp_path = f"/tmp/{filename}"
    with open(temp_path, "wb") as f:
        f.write(response.content)
    return temp_path

def upload_file_to_drive(file_path, filename):
    kind = filetype.guess(file_path)
    mime_type = kind.mime if kind else 'application/octet-stream'
    file_metadata = {'name': filename}
    media = MediaFileUpload(file_path, mimetype=mime_type)
    drive_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    file_id = drive_file.get('id')
    link = drive_file.get('webViewLink')
    # Make file public (optional)
    drive_service.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()
    return link

def format_description(text):
    # You can make this smarter (e.g., with LLM), here is a simple fallback:
    return text.split("-", 1)[-1].strip().capitalize()

@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.json
    print("\n=== POST RECEIVED ===")
    print(data)

    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    if data.get("event", {}).get("type") == "message":
        event = data["event"]
        text = event.get("text", "")
        user = event.get("user", "")
        files = event.get("files", [])
        ts = event.get("ts")
        # --- Date and Time ---
        # Slack ts is in seconds with decimals
        local_tz = pytz.timezone("Asia/Kolkata")
        dt = datetime.datetime.fromtimestamp(float(ts), tz=local_tz)
        date_str = dt.date().isoformat()
        time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        print(f"NEW MESSAGE: {text} from user {user}")

        # --- Parse expenses from lines ---
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            currency, amount = get_currency_and_amount(line)
            description = format_description(line)
            invoice_urls = []

            # --- Handle file uploads ---
            if files:
                for file_info in files:
                    url = file_info.get('url_private_download') or file_info.get('url_private')
                    filename = file_info.get('name')
                    try:
                        temp_file_path = download_slack_file(url, SLACK_BOT_TOKEN, filename)
                        drive_link = upload_file_to_drive(temp_file_path, filename)
                        invoice_urls.append(drive_link)
                        print(f"File uploaded to Drive: {drive_link}")
                    except Exception as e:
                        print(f"File upload error: {e}")

            # --- Append to Google Sheet ---
            values = [
                [
                    date_str,
                    time_str,
                    amount,
                    currency,
                    description,
                    user,
                    ", ".join(invoice_urls) if invoice_urls else "",
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

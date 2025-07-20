from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
import dropbox
import requests
import datetime
import os
import base64
import json
import re
import tempfile
import time
import pytesseract
from PIL import Image
import pytz

app = Flask(__name__)

# === Environment Setup ===
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
GOOGLE_CREDS_B64 = os.environ.get('GOOGLE_CREDS_B64')
DROPBOX_ACCESS_TOKEN = os.environ.get('DROPBOX_ACCESS_TOKEN')
RANGE = 'Expenses'
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")

# === Google Sheets Setup ===
def get_google_creds():
    creds_info = json.loads(base64.b64decode(GOOGLE_CREDS_B64).decode('utf-8'))
    return service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )

creds = get_google_creds()
sheets_service = build('sheets', 'v4', credentials=creds)
sheet = sheets_service.spreadsheets()

# === Helpers ===
def extract_expense_info(line):
    match = re.match(r'([₹$€£]?\s?[\d,]+(?:\.\d{1,2})?)\s*([A-Za-z$₹€£]*)\s*[-:]?\s*(.*)', line)
    if match:
        amount = match.group(1).replace(',', '').replace(' ', '')
        currency = match.group(2) if match.group(2) else ''
        description = match.group(3).strip() or line
    else:
        amount, currency, description = '', '', line
    if not currency and amount and amount[0] in '₹$€£':
        currency, amount = amount[0], amount[1:]
    if not currency:
        currency = 'INR'
    return amount.strip(), currency.strip(), description.strip()

def upload_file_to_dropbox(file_content, filename):
    dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
    unique_name = f"{int(time.time())}_{filename}"
    dropbox_path = f"/{unique_name}"
    try:
        dbx.files_upload(file_content, dropbox_path, mode=dropbox.files.WriteMode("add"))
        try:
            link = dbx.sharing_create_shared_link_with_settings(dropbox_path)
            return link.url
        except dropbox.exceptions.ApiError as e:
            if hasattr(e.error, 'get_shared_link_already_exists') or 'shared_link_already_exists' in str(e):
                links = dbx.sharing_list_shared_links(path=dropbox_path).links
                if links:
                    return links[0].url
            print("Dropbox link creation failed:", e)
            return None
    except Exception as ex:
        print("Dropbox upload failed:", ex)
        return None

def run_ocr_on_image(content):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        text = pytesseract.image_to_string(Image.open(tmp_path))
        os.unlink(tmp_path)
        return text.strip()
    except Exception as e:
        print("OCR failed:", e)
        return "OCR failed"

# Deduplication memory
processed_events = set()

# === Routes ===
@app.route("/slack/events", methods=["POST"])
def slack_events():
    print("\n=== POST RECEIVED ===")
    data = request.json
    print(data)

    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    if data.get("event", {}).get("type") == "message":
        event = data["event"]
        event_id = event.get('client_msg_id') or event.get('ts') or event.get('event_ts')
        if event_id in processed_events:
            print(f"Duplicate event, skipping: {event_id}")
            return "", 200
        processed_events.add(event_id)

        text = event.get("text", "").strip()
        user = event.get("user", "")
        files = event.get("files", [])

        tz = pytz.timezone('Asia/Kolkata')
        timestamp = datetime.datetime.fromtimestamp(
            float(event.get("ts", datetime.datetime.now().timestamp()))
        ).astimezone(tz).strftime('%Y-%m-%d %H:%M:%S')

        lines = text.splitlines() if text else []
        if not lines:
            lines = ["No message"]

        for line in lines:
            line = line.strip()
            if not line:
                continue
            amount, currency, description = extract_expense_info(line)

            if files:
                for file_obj in files:
                    url = file_obj.get("url_private_download") or file_obj.get("url_private")
                    fname = file_obj.get("name", "invoice")
                    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
                    r = requests.get(url, headers=headers)
                    if r.status_code != 200:
                        print("Failed to download file:", r.text)
                        continue

                    file_content = r.content
                    invoice_url = upload_file_to_dropbox(file_content, fname)
                    ocr_text = run_ocr_on_image(file_content)

                    values = [
                        [
                            datetime.date.today().isoformat(),
                            timestamp,
                            amount,
                            currency or "INR",
                            description,
                            user,
                            invoice_url,
                            ocr_text or "No OCR text"
                        ]
                    ]
                    try:
                        sheet.values().append(
                            spreadsheetId=SPREADSHEET_ID,
                            range=RANGE,
                            valueInputOption='USER_ENTERED',
                            body={'values': values}
                        ).execute()
                        print(f"Row appended for file: {fname}")
                    except Exception as e:
                        print(f"Error appending row for file '{fname}': {e}")
            else:
                values = [
                    [
                        datetime.date.today().isoformat(),
                        timestamp,
                        amount,
                        currency or "INR",
                        description,
                        user,
                        "",  # no file
                        ""   # no OCR
                    ]
                ]
                try:
                    sheet.values().append(
                        spreadsheetId=SPREADSHEET_ID,
                        range=RANGE,
                        valueInputOption='USER_ENTERED',
                        body={'values': values}
                    ).execute()
                    print(f"Row appended for text only: {line}")
                except Exception as e:
                    print(f"Error appending row for '{line}': {e}")

    return "", 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    print(f"Using Google Sheet ID: {SPREADSHEET_ID}")
    app.run(host="0.0.0.0", port=5000)

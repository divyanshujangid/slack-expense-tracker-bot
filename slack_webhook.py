from flask import Flask, request, jsonify
import datetime, os, re, io, requests
import dropbox
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# === CONFIG ===
SPREADSHEET_ID = os.environ['SPREADSHEET_ID']
RANGE = 'Expenses'
DROPBOX_ACCESS_TOKEN = os.environ['DROPBOX_ACCESS_TOKEN']

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
]

app = Flask(__name__)
processed_events = set()

def get_google_creds():
    creds_json = os.environ.get("GOOGLE_CREDS_B64")
    if not creds_json:
        raise Exception("GOOGLE_CREDS_B64 not set")
    import base64, json
    creds_dict = json.loads(base64.b64decode(creds_json))
    creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)
    return creds

def get_sheets_service():
    creds = get_google_creds()
    return build('sheets', 'v4', credentials=creds)

def extract_amount_currency_desc(text):
    if not text: return "", "INR", ""
    match = re.match(r"([₹$€£]?\s?\d+(?:\.\d{1,2})?)\s*([₹$€£]|INR|USD|EUR|GBP)?\s*[-:]?\s*(.*)", text, re.IGNORECASE)
    if match:
        amount = match.group(1).replace(" ", "")
        currency = match.group(2) or ""
        desc = match.group(3).strip() or text
        if not currency and amount and amount[0] in "₹$€£":
            currency = amount[0]
            amount = amount[1:]
        if not currency:
            currency = "INR"
        return amount, currency, desc
    return "", "INR", text

def upload_file_to_dropbox(file_content, filename):
    dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
    path = f"/{filename}"
    try:
        dbx.files_upload(file_content, path, mute=True, mode=dropbox.files.WriteMode.overwrite)
        # Try to create a shared link (handle case where it exists)
        try:
            shared_link = dbx.sharing_create_shared_link_with_settings(path).url
        except dropbox.exceptions.ApiError as e:
            if (hasattr(e, "error") and hasattr(e.error, "get_path") and
                hasattr(e.error.get_path(), "is_conflict") and
                e.error.get_path().is_conflict()):
                # Already exists, get all links
                links = dbx.sharing_list_shared_links(path=path).links
                if links:
                    shared_link = links[0].url
                else:
                    raise
            else:
                raise
        # force raw download link
        shared_link = shared_link.replace("?dl=0", "?dl=1").replace("?dl=1", "?raw=1")
        return shared_link
    except Exception as e:
        print("Dropbox upload failed:", e)
        return ""

@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.json
    print("=== POST RECEIVED ===")
    print(data)

    # Slack url_verification
    if data and data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    # Slack event_callback
    if data and data.get("type") == "event_callback":
        event = data.get("event", {})
        event_id = event.get('client_msg_id') or event.get('ts') or event.get('event_ts')
        if event_id in processed_events:
            print("Duplicate event, skipping:", event_id)
            return "", 200
        processed_events.add(event_id)

        text = event.get("text", "")
        user = event.get("user", "")
        ts = event.get("ts", "")
        files = event.get("files", [])

        # Fix timestamp extraction
        if ts:
            dt = datetime.datetime.fromtimestamp(float(ts))
            formatted_ts = dt.strftime('%Y-%m-%d %H:%M:%S')
            date_str = dt.date().isoformat()
        else:
            dt = datetime.datetime.now()
            formatted_ts = dt.strftime('%Y-%m-%d %H:%M:%S')
            date_str = dt.date().isoformat()

        # Allow empty text if files exist
        if not text and files:
            text = "No message"

        amount, currency, description = extract_amount_currency_desc(text)

        invoice_url = ""
        if files:
            slack_file = files[0]
            url_private = slack_file['url_private']
            filename = slack_file['name']
            mimetype = slack_file.get('mimetype', 'application/octet-stream')
            slack_bot_token = os.environ.get('SLACK_BOT_TOKEN')
            if not slack_bot_token:
                print("SLACK_BOT_TOKEN not set in environment!")
            else:
                response = requests.get(url_private, headers={"Authorization": f"Bearer {slack_bot_token}"})
                if response.status_code == 200:
                    invoice_url = upload_file_to_dropbox(response.content, filename)
                else:
                    print("Failed to download file from Slack:", response.text)
                    invoice_url = url_private  # fallback to Slack's URL

        # Append row to sheet (even if text is 'No message' and file exists)
        sheets_service = get_sheets_service()
        sheet = sheets_service.spreadsheets()
        values = [[
            date_str,
            formatted_ts,
            amount,
            currency,
            description,
            user,
            invoice_url,
            text or "No message"
        ]]
        print("Appending to sheet id:", SPREADSHEET_ID)
        print("Row:", values)
        try:
            sheet.values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=RANGE,
                valueInputOption='USER_ENTERED',
                body={'values': values}
            ).execute()
            print("Row appended for:", text)
        except Exception as e:
            print("Error appending row:", e)
    return "", 200

if __name__ == "__main__":
    print(f"Using Google Sheet ID: {SPREADSHEET_ID}")
    app.run(host="0.0.0.0", port=5000)

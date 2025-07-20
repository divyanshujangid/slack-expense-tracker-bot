import os.path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# If modifying these SCOPES, delete the file token.json
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    creds = None
    # The token.json stores user access and refresh tokens
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no valid creds, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save creds for future runs
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def upload_file(filepath, drive_folder_id=None):
    service = get_drive_service()
    file_metadata = {'name': os.path.basename(filepath)}
    if drive_folder_id:
        file_metadata['parents'] = [drive_folder_id]
    media = MediaFileUpload(filepath, resumable=True)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    # Make public
    service.permissions().create(
        fileId=file['id'],
        body={'role': 'reader', 'type': 'anyone'}
    ).execute()
    url = f"https://drive.google.com/file/d/{file['id']}/view"
    print(f"Uploaded: {url}")
    return url

if __name__ == '__main__':
    # Usage example
    FILE_TO_UPLOAD = 'image.png'
    # Optional: put your Drive folder ID here (or leave as None)
    DRIVE_FOLDER_ID = None  # e.g., '1qU02Cg_C24Vt-nHj2jrKERNP0Dj-Vwfp'
    upload_file(FILE_TO_UPLOAD, DRIVE_FOLDER_ID)

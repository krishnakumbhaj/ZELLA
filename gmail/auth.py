from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import os

# 🔐 Required Gmail scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]

def authenticate_gmail():
    creds = None

    # 🧠 Check if token already exists
    if os.path.exists('credentials/token.json'):
        creds = Credentials.from_authorized_user_file('credentials/token.json', SCOPES)

    # 🔁 If no valid token, re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials/credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080)

        # 💾 Save new token
        os.makedirs('credentials', exist_ok=True)
        with open('credentials/token.json', 'w') as token:
            token.write(creds.to_json())

    # 📡 Build Gmail service
    service = build('gmail', 'v1', credentials=creds)
    return service

if __name__ == "__main__":
    service = authenticate_gmail()
    print("✅ Authenticated successfully!")

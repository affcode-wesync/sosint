"""
Google OAuth Authentication Script
Run this ONCE to authorize and get token.json
"""
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/contacts'
]

def authenticate():
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')
    credentials_path = os.path.join(os.path.dirname(__file__), 'credentials.json')

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                print("=" * 60)
                print("ERROR: credentials.json not found!")
                print("=" * 60)
                print()
                print("1. Go to https://console.cloud.google.com")
                print("2. Create a new project (or use existing)")
                print("3. Go to APIs & Services > Library")
                print("4. Search 'People API' and Enable it")
                print("5. Also enable 'Contacts API'")
                print("6. Go to APIs & Services > Credentials")
                print("7. Click 'Create Credentials' > OAuth client ID")
                print("8. Choose 'Desktop app'")
                print("9. Download JSON and save as 'credentials.json'")
                print("   in this folder:", os.path.dirname(__file__))
                print()
                print("Then run this script again: py auth.py")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        print("SUCCESS: token.json saved!")
    else:
        print("Already authenticated!")

    return creds


def get_credentials():
    """Get valid credentials for API calls"""
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')

    if not os.path.exists(token_path):
        return None

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds


if __name__ == '__main__':
    authenticate()

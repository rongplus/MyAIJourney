import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]

TOKEN_FILE = "youtube_token.json"
CLIENT_SECRET = "client_secrets.json"


def get_credentials():

    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES,
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:

            print("Refreshing Access Token...")

            creds.refresh(Request())

        else:

            print("Opening browser for first authorization...")

            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET,
                SCOPES,
            )

            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds
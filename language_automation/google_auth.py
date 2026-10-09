"""
Google credentials for the pipeline scripts (spec 005, contracts/pipeline-credentials.md).

1. FTM_GOOGLE_CREDENTIALS: the web page's sign-in for this run (JSON). Used as is, never saved.
2. FTM_HOSTED=1 without it: refused. A server never falls back to token.json.
3. Otherwise (developer command line): token.json, or the desktop sign-in with credentials.json.
"""
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Asked for by the web sign-in (web_signin.py): the ID token proves the account's email and organization
WEB_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
# Command line: what token.json has always been granted. Refreshing it with more scopes than it
# was granted fails with invalid_scope, so the CLI keeps exactly these.
CLI_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
CREDENTIALS_ENV = "FTM_GOOGLE_CREDENTIALS"
TOKEN_FILE = "token.json"
CLIENT_FILE = "credentials.json"


class AuthError(Exception):
    """No usable Google sign-in for this run. The message is safe to print."""


def is_hosted():
    return os.environ.get("FTM_HOSTED") == "1"


def uses_token_file():
    """True only when credentials come from token.json (developer command line)."""
    return not os.environ.get(CREDENTIALS_ENV) and not is_hosted()


def load_credentials():
    raw = os.environ.get(CREDENTIALS_ENV)
    if raw:
        try:
            # scopes=None: keep exactly the scopes this sign-in was granted
            creds = Credentials.from_authorized_user_info(json.loads(raw))
            if not creds.valid:
                creds.refresh(Request())
        except Exception:
            raise AuthError("the Google sign-in for this run is invalid or expired") from None
        return creds

    if is_hosted():
        raise AuthError("no Google sign-in was provided for this run")

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, CLI_SCOPES)
    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None  # refresh token revoked or expired: sign in again
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, CLI_SCOPES)
        creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w") as token_file:
        token_file.write(creds.to_json())
    return creds

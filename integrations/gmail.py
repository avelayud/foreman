"""
integrations/gmail.py
Gmail OAuth flow and sent mail reader.

Usage (CLI test):
    python -m integrations.gmail

Returns the last 25 sent emails as a list of plain-text strings.
"""

import os
import base64
import re
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Only need read access to Gmail
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"


def _get_gmail_service():
    """Authenticate and return an authorized Gmail API service."""
    creds = None

    # Load existing token if present
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh or run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}. "
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    # Multipart: recurse into parts
    for part in payload.get("parts", []):
        result = _decode_body(part)
        if result:
            return result

    return ""


def _clean_text(text: str) -> str:
    """Strip quoted reply chains, excessive whitespace, and signatures."""
    # Remove lines starting with > (quoted reply)
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        # Stop at common reply separators
        if re.match(r"^On .+ wrote:$", stripped):
            break
        if stripped.startswith("--") and len(stripped) <= 3:
            break
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def get_sent_emails(max_results: int = 25) -> list[str]:
    """
    Fetch the last `max_results` sent emails from Gmail.

    Returns a list of plain-text email bodies (cleaned, no quoted replies).
    """
    service = _get_gmail_service()

    # List messages in the SENT label
    result = service.users().messages().list(
        userId="me",
        labelIds=["SENT"],
        maxResults=max_results
    ).execute()

    messages = result.get("messages", [])
    if not messages:
        print("No sent messages found.")
        return []

    emails = []
    for msg_stub in messages:
        msg = service.users().messages().get(
            userId="me",
            id=msg_stub["id"],
            format="full"
        ).execute()

        body = _decode_body(msg.get("payload", {}))
        cleaned = _clean_text(body)

        if cleaned:
            emails.append(cleaned)

    print(f"✅ Fetched {len(emails)} sent emails from Gmail.")
    return emails


if __name__ == "__main__":
    emails = get_sent_emails(25)
    for i, email in enumerate(emails, 1):
        print(f"\n--- Email {i} ---")
        print(email[:300] + ("..." if len(email) > 300 else ""))

"""
integrations/gmail.py
Gmail OAuth + full mailbox integration.

Capabilities:
  - get_sent_emails()          → tone profiler (read sent mail)
  - send_email()               → send outreach, returns (message_id, thread_id)
  - get_thread()               → read a full conversation thread
  - get_correspondence()       → all messages to/from a customer email address
  - get_inbox_replies()        → check threads for inbound replies

Scopes required: gmail.send + gmail.modify
If you have an existing token.json with readonly scope, delete it and re-run
OAuth to get a new token with the expanded scopes.

Usage (CLI test):
    python -m integrations.gmail
"""

import base64
import email as emaillib
import json
import os
import re
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# gmail.modify covers read + label changes; gmail.send for sending
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_gmail_service():
    """Authenticate and return an authorized Gmail API service.

    Credential resolution order:
      1. GMAIL_TOKEN_JSON env var  — used on Railway (paste contents of token.json)
      2. token.json file           — used locally
    If the token is expired it is refreshed in-memory using the refresh_token.
    """
    creds = None

    # 1. Env var (Railway production)
    token_env = os.getenv("GMAIL_TOKEN_JSON", "").strip()
    if token_env:
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(token_env), SCOPES
            )
        except Exception as exc:
            raise RuntimeError(f"GMAIL_TOKEN_JSON is set but could not be parsed: {exc}") from exc

    # 2. File fallback (local development)
    if not creds and TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # 3. Refresh if expired (refresh_token is long-lived — no browser needed)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist locally if possible so subsequent local runs skip the refresh
        try:
            TOKEN_PATH.write_text(creds.to_json())
        except OSError:
            pass

    elif not creds or not creds.valid:
        # Need a fresh OAuth browser flow — only works locally
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                f"⚠ credentials.json not found at {CREDENTIALS_PATH}. "
                "Download from Google Cloud Console → APIs & Services → Credentials.\n"
                "On Railway: set GMAIL_TOKEN_JSON to the contents of your local token.json."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ── Message parsing ───────────────────────────────────────────────────────────

def _decode_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        result = _decode_body(part)
        if result:
            return result

    return ""


def _clean_text(text: str) -> str:
    """Strip quoted reply chains, excessive whitespace, and signatures."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if re.match(r"^On .+ wrote:$", stripped):
            break
        if stripped.startswith("--") and len(stripped) <= 3:
            break
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _parse_message(msg: dict) -> dict:
    """Parse a Gmail API message object into a clean dict."""
    headers = msg.get("payload", {}).get("headers", [])
    body = _decode_body(msg.get("payload", {}))
    label_ids = msg.get("labelIds", [])

    date_str = _get_header(headers, "Date")
    try:
        from email.utils import parsedate_to_datetime
        sent_at = parsedate_to_datetime(date_str) if date_str else None
        # Normalize to UTC before stripping tzinfo for SQLite compatibility
        if sent_at and sent_at.tzinfo:
            from datetime import timezone as _tz
            sent_at = sent_at.astimezone(_tz.utc).replace(tzinfo=None)
    except Exception:
        sent_at = None

    return {
        "message_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "subject": _get_header(headers, "Subject"),
        "sent_at": sent_at,
        "body": _clean_text(body),
        "is_inbound": "INBOX" in label_ids,
        "is_sent": "SENT" in label_ids,
    }


# ── Read operations ───────────────────────────────────────────────────────────

def get_sent_emails(max_results: int = 25) -> list[str]:
    """
    Fetch the last N sent emails as plain-text strings.
    Used by the tone profiler.
    """
    service = _get_gmail_service()
    result = service.users().messages().list(
        userId="me", labelIds=["SENT"], maxResults=max_results
    ).execute()

    messages = result.get("messages", [])
    emails = []
    for stub in messages:
        msg = service.users().messages().get(
            userId="me", id=stub["id"], format="full"
        ).execute()
        body = _clean_text(_decode_body(msg.get("payload", {})))
        if body:
            emails.append(body)

    print(f"✅ Fetched {len(emails)} sent emails from Gmail.")
    return emails


def get_correspondence(email_address: str, max_results: int = 30) -> list[dict]:
    """
    Return all messages to or from a specific email address.
    Used by CustomerAnalyzer to build a prior-relationship profile.
    """
    service = _get_gmail_service()
    query = f"to:{email_address} OR from:{email_address}"
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = result.get("messages", [])
    parsed = []
    for stub in messages:
        msg = service.users().messages().get(
            userId="me", id=stub["id"], format="full"
        ).execute()
        parsed.append(_parse_message(msg))

    return parsed


def get_thread(thread_id: str) -> list[dict]:
    """
    Return all messages in a Gmail thread, oldest first.
    Used by reply detection and follow-up agent.
    """
    service = _get_gmail_service()
    result = service.users().threads().get(
        userId="me", id=thread_id, format="full"
    ).execute()
    messages = result.get("messages", [])
    return [_parse_message(m) for m in messages]


def get_inbox_replies(thread_ids: list[str]) -> dict[str, list[dict]]:
    """
    For each thread_id, return any inbound (customer reply) messages.
    Returns { thread_id: [reply_message, ...] } for threads that have replies.
    """
    service = _get_gmail_service()
    replies = {}

    for thread_id in thread_ids:
        try:
            result = service.users().threads().get(
                userId="me", id=thread_id, format="full"
            ).execute()
            messages = result.get("messages", [])
            inbound = [_parse_message(m) for m in messages if "INBOX" in m.get("labelIds", [])]
            if inbound:
                replies[thread_id] = inbound
        except Exception as e:
            print(f"  [gmail] Error fetching thread {thread_id}: {e}")

    return replies


# ── Send ──────────────────────────────────────────────────────────────────────

def send_email(
    to: str,
    subject: str,
    body: str,
    thread_id: str = None,
) -> tuple[str, str]:
    """
    Send an email from the operator's Gmail account.

    Args:
        to:        Recipient email address
        subject:   Email subject line
        body:      Plain-text body
        thread_id: If replying in a thread, pass the existing thread_id

    Returns:
        (message_id, thread_id) — store thread_id on OutreachLog for reply tracking
    """
    service = _get_gmail_service()

    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to
    msg["subject"] = subject

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    request_body = {"raw": raw}

    if thread_id:
        request_body["threadId"] = thread_id

    result = service.users().messages().send(
        userId="me", body=request_body
    ).execute()

    return result.get("id"), result.get("threadId")


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing Gmail integration...")
    emails = get_sent_emails(5)
    for i, e in enumerate(emails, 1):
        print(f"\n--- Sent {i} ---\n{e[:200]}")

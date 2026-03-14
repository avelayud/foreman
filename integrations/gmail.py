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
import html as _html_module
import json
import os
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
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
    "https://www.googleapis.com/auth/calendar",
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
            token_data = json.loads(token_env)
        except (json.JSONDecodeError, ValueError):
            try:
                token_data = json.loads(base64.b64decode(token_env).decode("utf-8"))
            except Exception as exc:
                raise RuntimeError(f"GMAIL_TOKEN_JSON is set but could not be parsed: {exc}") from exc
        try:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
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
        "rfc_message_id": _get_header(headers, "Message-ID"),  # RFC 2822 id for In-Reply-To
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


def search_inbox_by_sender(email_address: str, since_date=None, max_results: int = 10) -> list[dict]:
    """
    Search the operator's inbox for messages FROM a specific email address.
    Optionally filter to messages sent after `since_date` (datetime).

    Used as a fallback in reply_detector when a customer's reply lands on a
    different Gmail thread than the one we sent (client threading differences).

    Returns a list of parsed message dicts, newest first.
    """
    service = _get_gmail_service()

    query = f"from:{email_address} in:inbox"
    if since_date:
        # Gmail search uses YYYY/MM/DD — subtract 1 day buffer for timezone slop
        from datetime import timedelta
        since_str = (since_date - timedelta(days=1)).strftime("%Y/%m/%d")
        query += f" after:{since_str}"

    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = result.get("messages", [])
    parsed = []
    for stub in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=stub["id"], format="full"
            ).execute()
            parsed.append(_parse_message(msg))
        except Exception as e:
            print(f"  [gmail] search_inbox_by_sender: error fetching {stub['id']}: {e}")

    return parsed


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

def _plain_to_html(body: str) -> str:
    """Convert paragraph-separated plain text to simple inline HTML.

    Splits on blank lines → <p> tags. Single newlines within a paragraph
    become <br>. HTML special characters are escaped.
    Sending as HTML prevents email clients (Gmail in particular) from
    misinterpreting quoted-printable soft-wrap markers as hard line breaks.
    """
    paragraphs = re.split(r'\n{2,}', body.strip())
    parts = []
    for para in paragraphs:
        para = para.strip()
        if para:
            escaped = _html_module.escape(para)
            escaped = escaped.replace('\n', '<br>')
            parts.append(f'<p style="margin:0 0 1em 0;line-height:1.5">{escaped}</p>')
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#000000">'
        + ''.join(parts)
        + '</div>'
    )


def send_email(
    to: str,
    subject: str,
    body: str,
    thread_id: str = None,
    in_reply_to: str = None,
) -> tuple[str, str]:
    """
    Send an email from the operator's Gmail account.

    Args:
        to:           Recipient email address
        subject:      Email subject line
        body:         Plain-text body
        thread_id:    If replying in a thread, pass the existing gmail thread_id.
                      The function will fetch the thread to set In-Reply-To /
                      References headers so the recipient sees it in the same thread.
        in_reply_to:  Explicit RFC 2822 Message-ID to set as In-Reply-To.
                      Should be the rfc_message_id of the customer's most recent
                      inbound reply. When provided, this overrides the thread-
                      derived last-message-ID so the recipient's client correctly
                      threads the message under their sent reply.

    Returns:
        (message_id, thread_id) — store thread_id on OutreachLog for reply tracking
    """
    service = _get_gmail_service()

    # Send as multipart/alternative (plain + HTML).
    # HTML prevents Gmail from misinterpreting quoted-printable soft-wrap
    # markers as hard line breaks on the recipient side.
    msg = MIMEMultipart("alternative")
    msg["to"] = to
    msg["subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(_plain_to_html(body), "html", "utf-8"))

    # When replying, set RFC 2822 threading headers so the recipient's mail
    # client groups this message in the same thread.
    #
    # IMPORTANT: also lock the subject to the original thread's subject.
    # Changing the subject on a reply causes Gmail (and most clients) to start a
    # new conversation on the recipient's side even when In-Reply-To is set.
    #
    # Strategy: fetch each message individually with format="metadata" so we can
    # grab both Message-ID and Subject headers reliably.
    if thread_id:
        try:
            # Step 1: get ordered list of message IDs in the thread
            thread_result = service.users().threads().get(
                userId="me", id=thread_id, format="minimal"
            ).execute()
            thread_messages = thread_result.get("messages", [])

            # Step 2: fetch each message's headers (Message-ID + Subject)
            all_rfc_ids = []
            original_subject = None
            for idx, m in enumerate(thread_messages):
                m_data = service.users().messages().get(
                    userId="me",
                    id=m["id"],
                    format="metadata",
                    metadataHeaders=["Message-ID", "Subject"],
                ).execute()
                headers = m_data.get("payload", {}).get("headers", [])
                rfc_id = _get_header(headers, "Message-ID")
                if rfc_id:
                    all_rfc_ids.append(rfc_id)
                # Capture original thread subject from the first message
                if idx == 0:
                    original_subject = _get_header(headers, "Subject") or None

            print(
                f"[gmail] Thread {thread_id}: {len(thread_messages)} msgs, "
                f"rfc_ids={all_rfc_ids}"
            )

            # Lock subject to the original thread's subject so the recipient's
            # mail client keeps this reply in the same conversation. Prefix "Re: "
            # only if the original didn't already have it.
            if original_subject:
                canonical_subject = (
                    original_subject
                    if original_subject.lower().startswith("re:")
                    else f"Re: {original_subject}"
                )
                msg.replace_header("Subject", canonical_subject)
                print(f"[gmail] Subject locked to thread original: {canonical_subject!r}")

            if all_rfc_ids:
                # If caller supplied an explicit in_reply_to (the customer's reply
                # RFC Message-ID stored at detection time), use it directly.
                # This ensures the recipient's client threads our next message
                # under their sent reply rather than our outbound.
                effective_in_reply_to = in_reply_to or all_rfc_ids[-1]

                # Ensure in_reply_to is present in the References chain
                if in_reply_to and in_reply_to not in all_rfc_ids:
                    all_rfc_ids.append(in_reply_to)

                msg["In-Reply-To"] = effective_in_reply_to
                msg["References"] = " ".join(all_rfc_ids)
                print(f"[gmail] In-Reply-To={effective_in_reply_to!r} (explicit={bool(in_reply_to)})")
            else:
                # No RFC IDs from thread — fall back to explicit in_reply_to if we have it
                if in_reply_to:
                    msg["In-Reply-To"] = in_reply_to
                    msg["References"] = in_reply_to
                    print(f"[gmail] No thread RFC IDs; using explicit In-Reply-To={in_reply_to!r}")
                else:
                    print(
                        f"[gmail] WARNING: no RFC Message-IDs found in thread {thread_id} "
                        f"— email will send without threading headers"
                    )

        except Exception as e:
            import traceback
            print(f"[gmail] Could not fetch thread headers for threading: {e}")
            traceback.print_exc()

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

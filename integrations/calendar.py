"""
integrations/calendar.py
Google Calendar integration — read free/busy, surface available slots.

Requires calendar.readonly scope in token.json. If your existing token.json
was issued without this scope, delete token.json and re-run Gmail OAuth —
it will request both Gmail and Calendar permissions in one flow.

Usage:
    from integrations.calendar import get_available_slots, format_slots_for_email
    slots = get_available_slots(days_ahead=10, duration_minutes=90)
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"

CALENDAR_AVAILABLE = True


def _get_calendar_service():
    creds = None

    import base64
    token_env = os.getenv("GMAIL_TOKEN_JSON", "").strip()
    if token_env:
        try:
            token_data = json.loads(token_env)
        except (json.JSONDecodeError, ValueError):
            try:
                token_data = json.loads(base64.b64decode(token_env).decode("utf-8"))
            except Exception as exc:
                raise RuntimeError(f"GMAIL_TOKEN_JSON parse error: {exc}") from exc
        try:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception as exc:
            raise RuntimeError(f"GMAIL_TOKEN_JSON parse error: {exc}") from exc

    if not creds and TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        try:
            TOKEN_PATH.write_text(creds.to_json())
        except OSError:
            pass
    elif not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                "credentials.json not found. Re-run Gmail OAuth locally to add calendar scope."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_available_slots(
    days_ahead: int = 10,
    duration_minutes: int = 90,
    working_hours: tuple = (8, 17),
    max_slots: int = 6,
) -> list[dict]:
    """
    Return available appointment slots over the next `days_ahead` business days.

    Each slot dict:
        {
          "start": datetime (Eastern, tz-aware),
          "end":   datetime (Eastern, tz-aware),
          "label": "Tuesday, March 18 at 10:00 AM",
        }

    Uses Google Calendar freebusy API against the operator's primary calendar.
    Skips weekends. Returns up to max_slots results.
    """
    try:
        import zoneinfo
        eastern = zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        import pytz
        eastern = pytz.timezone("America/New_York")

    service = _get_calendar_service()
    slots = []
    now = datetime.now(tz=eastern)

    for offset in range(1, days_ahead + 7):  # +7 buffer for weekends
        day = now + timedelta(days=offset)
        if day.weekday() >= 5:  # skip Sat/Sun
            continue

        day_start = day.replace(
            hour=working_hours[0], minute=0, second=0, microsecond=0
        )
        day_end = day.replace(
            hour=working_hours[1], minute=0, second=0, microsecond=0
        )

        try:
            result = service.freebusy().query(body={
                "timeMin": day_start.isoformat(),
                "timeMax": day_end.isoformat(),
                "items": [{"id": "primary"}],
            }).execute()
            busy_periods = result["calendars"]["primary"]["busy"]
        except Exception as e:
            print(f"[calendar] freebusy error for {day.date()}: {e}")
            busy_periods = []

        # Convert busy periods to aware datetimes
        busy = []
        for period in busy_periods:
            b_start = datetime.fromisoformat(period["start"])
            b_end = datetime.fromisoformat(period["end"])
            if b_start.tzinfo is None:
                b_start = b_start.replace(tzinfo=eastern)
            if b_end.tzinfo is None:
                b_end = b_end.replace(tzinfo=eastern)
            busy.append((b_start.astimezone(eastern), b_end.astimezone(eastern)))
        busy.sort(key=lambda x: x[0])

        # Find free gaps within working hours
        cursor = day_start
        for b_start, b_end in busy:
            gap = (b_start - cursor).total_seconds() / 60
            if gap >= duration_minutes:
                slot_end = cursor + timedelta(minutes=duration_minutes)
                slots.append({
                    "start": cursor,
                    "end": slot_end,
                    "label": cursor.strftime("%A, %B %-d at %-I:%M %p"),
                })
                if len(slots) >= max_slots:
                    break
            cursor = max(cursor, b_end)

        if len(slots) >= max_slots:
            break

        # Gap after last busy block
        gap = (day_end - cursor).total_seconds() / 60
        if gap >= duration_minutes and len(slots) < max_slots:
            slot_end = cursor + timedelta(minutes=duration_minutes)
            slots.append({
                "start": cursor,
                "end": slot_end,
                "label": cursor.strftime("%A, %B %-d at %-I:%M %p"),
            })

        if len(slots) >= max_slots:
            break

    return slots[:max_slots]


def get_available_slots_for_date(
    date_str: str,
    duration_minutes: int = 60,
    working_hours: tuple = (8, 17),
) -> list[dict]:
    """
    Return available appointment slots for a specific date (YYYY-MM-DD).

    Generates candidates at 30-min increments within working hours, removes
    any that overlap with busy calendar events.

    Each slot dict:
        {"start_iso": "2026-03-18T10:00:00", "time": "10:00", "label": "10:00 AM"}
    """
    try:
        import zoneinfo
        eastern = zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        import pytz
        eastern = pytz.timezone("America/New_York")

    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return []

    target_start = target.replace(hour=working_hours[0], minute=0, second=0, microsecond=0)
    target_end = target.replace(hour=working_hours[1], minute=0, second=0, microsecond=0)

    # Fetch busy periods from Google Calendar
    busy = []
    try:
        ts = target_start.replace(tzinfo=eastern)
        te = target_end.replace(tzinfo=eastern)
        service = _get_calendar_service()
        result = service.freebusy().query(body={
            "timeMin": ts.isoformat(),
            "timeMax": te.isoformat(),
            "items": [{"id": "primary"}],
        }).execute()
        for period in result["calendars"]["primary"]["busy"]:
            b_start = datetime.fromisoformat(period["start"])
            b_end = datetime.fromisoformat(period["end"])
            if b_start.tzinfo is not None:
                b_start = b_start.astimezone(eastern).replace(tzinfo=None)
            if b_end.tzinfo is not None:
                b_end = b_end.astimezone(eastern).replace(tzinfo=None)
            busy.append((b_start, b_end))
        busy.sort()
    except Exception:
        pass  # If calendar unavailable, return all slots as free

    # Generate candidates at 30-min steps, skip any that overlap busy blocks
    slots = []
    cursor = target_start
    step = timedelta(minutes=30)
    while cursor + timedelta(minutes=duration_minutes) <= target_end:
        slot_end = cursor + timedelta(minutes=duration_minutes)
        if not any(b_start < slot_end and b_end > cursor for b_start, b_end in busy):
            h, m = cursor.hour, cursor.minute
            ampm = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            slots.append({
                "start_iso": cursor.strftime("%Y-%m-%dT%H:%M:%S"),
                "time": cursor.strftime("%H:%M"),
                "label": f"{h12}:{m:02d} {ampm}",
            })
        cursor += step

    return slots


def create_calendar_event(
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    customer_email: str = None,
    description: str = "",
    location: str = "",
) -> dict:
    """
    Create a Google Calendar event on the operator's primary calendar.

    When customer_email is provided they are added as an attendee and Google Calendar
    automatically sends them an .ics invite email — no manual MIME construction needed.

    Returns the created event dict (contains 'id', 'htmlLink', etc.).
    """
    try:
        import zoneinfo
        eastern = zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        import pytz
        eastern = pytz.timezone("America/New_York")

    service = _get_calendar_service()

    # Attach Eastern timezone if datetime is naive
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=eastern)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=eastern)

    event_body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "America/New_York",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "America/New_York",
        },
    }

    if customer_email:
        event_body["attendees"] = [{"email": customer_email}]

    result = service.events().insert(
        calendarId="primary",
        body=event_body,
        sendUpdates="all",  # GCal sends .ics invite to attendees automatically
    ).execute()

    print(f"[calendar] Created event '{summary}' — {result.get('htmlLink', '')}")
    return result


def get_event_status(event_id: str) -> dict:
    """
    Fetch a Calendar event and return its status and attendee responses.
    Returns {"exists": False} if event is 404 or cancelled.
    Returns {"exists": True, "status": str, "start": datetime|None, "end": datetime|None, "attendees": list}
    """
    try:
        service = _get_calendar_service()
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        if event.get('status') == 'cancelled':
            return {"exists": False}
        start_raw = event.get('start', {})
        end_raw = event.get('end', {})
        start_dt = None
        end_dt = None
        if 'dateTime' in start_raw:
            start_dt = datetime.fromisoformat(start_raw['dateTime'].replace('Z', '+00:00')).replace(tzinfo=None)
        if 'dateTime' in end_raw:
            end_dt = datetime.fromisoformat(end_raw['dateTime'].replace('Z', '+00:00')).replace(tzinfo=None)
        attendees = [
            {"email": a.get("email", ""), "responseStatus": a.get("responseStatus", "needsAction")}
            for a in event.get("attendees", [])
        ]
        return {"exists": True, "status": event.get("status", "confirmed"), "start": start_dt, "end": end_dt, "attendees": attendees}
    except Exception as e:
        err_str = str(e).lower()
        if "404" in err_str or "not found" in err_str:
            return {"exists": False}
        raise


def format_slots_for_email(slots: list[dict], max_proposals: int = 3) -> str:
    """
    Format 2–3 slots as a natural-language list for inclusion in an email.
    Example: "Tuesday, March 18 at 10:00 AM, Wednesday, March 19 at 2:00 PM,
              or Thursday, March 20 at 9:00 AM"
    """
    if not slots:
        return "I'd be happy to work around your schedule — what times work best for you?"

    top = slots[:max_proposals]
    labels = [s["label"] for s in top]

    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} or {labels[1]}"
    return f"{labels[0]}, {labels[1]}, or {labels[2]}"

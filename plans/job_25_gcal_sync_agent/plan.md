# Job 25 — Google Calendar Sync Agent

**Phase:** 8 (quality + reliability — parallel with Job 24)
**Status:** ⬜ Not started
**Depends on:** Job 24 (`health_override` field must exist — used when surfacing conflicts)
**Goal:** A daily agent that reads attendee response status from Google Calendar for every Foreman booking that has a linked GCal event. Catches calendar acceptances, declines, deletions, and time changes that never made it into the Foreman inbox — the primary source of stuck conversation states for customers in the `invite_sent` stage.

---

## Background

When Foreman sends a calendar invite (from the Meetings Queue), it creates a Google Calendar event and stores `Booking.google_cal_event_id`. After that, the only way Foreman currently knows what happened is if the customer's acceptance email lands in the Gmail inbox AND reply_detector picks it up in the same thread.

That fails silently in two common cases:
1. **GCal acceptance arrives in a different thread.** Google Calendar sends an automated `calendar-notification@google.com` system email — separate Gmail thread, not the outreach thread. Our thread-based and address-based scans both miss it.
2. **Customer declines or proposes a new time directly in Google Calendar.** No email reply at all — just a GCal API state change.

Result: bookings sit in `invite_sent` / tentative state indefinitely. The operator has to manually check their calendar and mark things done.

GCal Sync Agent fixes this by going directly to the source — polling the Calendar API for attendee responses on every tracked event.

---

## What the Agent Checks

For each `Booking` where `google_cal_event_id IS NOT NULL` and `status IN ('tentative', 'confirmed')`:

### Case 1 — Customer Accepted
`attendee.responseStatus == "accepted"` for the customer's email address
- Set `Booking.status = "confirmed"`
- Set `Customer.reactivation_status = "booked"` (if currently `invite_sent` or `replied`)
- Log an inbound OutreachLog entry with `response_classification = "calendar_accepted"` and `draft_queued = True` (so it appears in the timeline but generates no draft)
- Print: `[gcal_sync] customer={id} accepted — booking confirmed, status → booked`

### Case 2 — Customer Declined
`attendee.responseStatus == "declined"` for the customer's email
- Set `Booking.status = "cancelled"`
- Set `Customer.reactivation_status = "replied"` (if currently `invite_sent` or `booked`)
- Log an inbound OutreachLog entry with `response_classification = "calendar_declined"` and `draft_queued = False`
- Response generator will pick this up and generate a redraft via `_handle_calendar_declined()`
- Print: `[gcal_sync] customer={id} declined — booking cancelled, queuing redraft`

### Case 3 — Event Deleted from GCal
GCal API returns `404` or `status == "cancelled"` for the event
- Set `Booking.status = "cancelled"`
- Set `Booking.orphaned = True` (new flag — see model changes)
- Set `Customer.reactivation_status = "replied"` (if currently `invite_sent` or `booked`)
- Surface in `/updates` under new "📅 Calendar Updates" section — "Event deleted from calendar"
- Do NOT auto-generate a draft — operator should decide what to do next
- Print: `[gcal_sync] customer={id} event deleted — booking orphaned, status → replied`

### Case 4 — Event Time Changed
GCal event `start.dateTime` differs from `Booking.slot_start` by more than 30 minutes (threshold prevents false positives from timezone normalization)
- Update `Booking.slot_start` and `Booking.slot_end` to match GCal event
- Set `Booking.time_changed = True` (new flag)
- Surface in `/updates` under "📅 Calendar Updates" — "Appointment time changed in calendar"
- Do NOT change customer status or generate a draft
- Print: `[gcal_sync] customer={id} event time changed from {old} to {new} — booking updated`

### Case 5 — No Attendee Response Yet (`needsAction` or `tentative`)
- No action. Leave booking and customer state unchanged.
- These are polled again on the next run.

---

## Deduplication

The agent must not double-apply. Before acting on Case 1 or 2:
- Check if a `calendar_accepted` or `calendar_declined` inbound log already exists for this customer with `created_at` after the booking was created
- If yes → skip (already handled by reply_detector or a prior sync run)

For Case 3 and 4:
- Check `Booking.orphaned` and `Booking.time_changed` flags — if already set, skip

---

## New `Booking` Fields

```python
orphaned       = Column(Boolean, default=False)   # True when GCal event was deleted
time_changed   = Column(Boolean, default=False)   # True when GCal event time was modified
```

SCHEMA_PATCHES entries for both.

These are display-only flags (surfaced in `/updates`). No enforcement logic rides on them.

---

## New `integrations/calendar.py` Function

Add `get_event_status(event_id: str) -> dict` to the existing calendar integration:

```python
def get_event_status(event_id: str) -> dict:
    """
    Fetch a Calendar event and return its status and attendee responses.
    Returns:
        {
            "exists": bool,
            "status": "confirmed" | "cancelled",  # GCal event status
            "start": datetime | None,
            "end": datetime | None,
            "attendees": [{"email": str, "responseStatus": str}, ...]
        }
    Returns {"exists": False} if event is 404 / deleted.
    """
```

This is the only new Calendar API call. The existing `create_calendar_event()` function is unchanged.

**Auth note:** Uses the same OAuth token as the existing calendar integration. No new scopes needed — `calendar.readonly` or `calendar.events` (already granted when the operator authorized GCal for booking proposals).

---

## New Agent — `agents/gcal_sync.py`

```python
"""
agents/gcal_sync.py
Google Calendar Sync Agent.

For every Foreman booking with a google_cal_event_id, checks attendee
response status via the Calendar API. Handles acceptances, declines,
deletions, and time changes that were never detected via Gmail.

Usage:
    python -m agents.gcal_sync --operator-id 1
"""

def run(operator_id: int) -> dict:
    """
    Sync all tracked GCal events with Foreman bookings.
    Returns: {accepted: int, declined: int, deleted: int, time_changed: int, skipped: int}
    """
```

If GCal credentials are not available (no `token.json` or missing calendar scope), the agent logs a warning and exits gracefully — same pattern as the existing calendar integration.

**Schedule:** Startup + every 6 hours via APScheduler. Daily is too infrequent if an operator is actively working a booking same-day. 6 hours balances API quota with freshness.

---

## Updates Inbox Changes (`/updates`)

Add a new "📅 Calendar Updates" section. Shows only when there are orphaned or time-changed bookings:

```
📅 Calendar Updates                                         (badge count)
──────────────────────────────────────────────────────────────────────
Sam Keller     Event deleted from calendar    Mar 15 → [View Conversation →]
Jane Davis     Appointment time changed       Mar 18 2pm → Mar 19 10am [View →]
```

- Sorted by booking created_at desc
- "View Conversation →" links to `/conversations/{customer_id}`
- Cleared automatically when operator logs the outcome or the booking is resolved
- Added to the Updates sidebar badge count (`conversations_attention_count`)

---

## Agents Page

```python
{
    "key": "gcal_sync",
    "name": "Google Calendar Sync",
    "icon": "📅",
    "description": "Runs every 6 hours. Checks attendee response status on every tracked calendar event. Catches acceptances and declines that arrive as GCal system emails (different thread) instead of customer email replies. Also detects event deletions and time changes.",
    "status": "active",   # or "needs_setup" if calendar scope not authorized
    "status_label": "Active (every 6h)" / "Needs Calendar Auth",
    "last_run_at": _agent_last_run.get("gcal_sync"),
    "stat_label": "Events synced",
    "stat_value": str(gcal_tracked_events),  # count of bookings with gcal_event_id
    "cli": "python -m agents.gcal_sync --operator-id 1",
    "phase": "Phase 8",
}
```

If `integrations/calendar.py` raises on import (no token), set `status = "needs_setup"` and hide the Run Now button.

---

## New API Routes

| Method | Path | Description |
|---|---|---|
| POST | `/api/agent/run-gcal-sync` | Run GCal sync synchronously (Agents page Run Now) |
| GET | `/api/updates/calendar` | Return orphaned + time-changed bookings (for Updates inbox) |

---

## Tasks

- [ ] `task_01_booking_model.md` — `Booking.orphaned` + `Booking.time_changed` + SCHEMA_PATCHES
- [ ] `task_02_calendar_integration.md` — `integrations/calendar.py` — add `get_event_status(event_id)`
- [ ] `task_03_gcal_sync_agent.md` — `agents/gcal_sync.py` — 5 cases, dedup, graceful fallback
- [ ] `task_04_scheduler.md` — register gcal_sync in APScheduler (every 6h) + startup run + `_agent_last_run` entry
- [ ] `task_05_api_routes.md` — `/api/agent/run-gcal-sync` + `/api/updates/calendar`
- [ ] `task_06_updates_inbox.md` — "Calendar Updates" section in `templates/updates.html` + badge count
- [ ] `task_07_agents_page.md` — add gcal_sync to agents list + Run Now button + needs_setup handling

---

## Files to Attach in Claude Code

```
PROJECT_PLAN.md
core/models.py
core/database.py
integrations/calendar.py
agents/gcal_sync.py       (new — won't exist yet)
api/app.py
templates/updates.html
templates/agents.html
```

---

## Key Constraints

- **No new OAuth scopes required.** The existing GCal token must already have `calendar.events` or `calendar.readonly` from the booking proposal flow. If it doesn't, `get_event_status()` will 403 and the agent catches it gracefully, logs "calendar scope not available", and skips without crashing.
- **API quota awareness.** Standard GCal quota is 1 million requests/day. With 200 customers and at most ~20 active bookings at any time, 6-hour polling = ~80 API calls/day. Well within quota. If this scales, add a batch events fetch using `events.list` with `eventIds` filter.
- **No cascading draft generation for Case 3 (deleted events).** Unlike Case 2 (decline), a deleted event is ambiguous — maybe the operator deleted it intentionally. Surface it in `/updates` and let the operator decide.
- **Time change threshold is 30 minutes**, not zero — avoids false positives from timezone normalization differences between Foreman's stored UTC and GCal's returned local time.
- **Deduplication is critical.** The reply_detector might have already logged a `calendar_accepted` for this customer from a same-thread notification. Always check before creating duplicate log entries.

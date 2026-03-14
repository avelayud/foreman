# Job 26 — Edit / Reschedule Meeting Invite

**Phase:** 8
**Status:** ⬜ Not started
**Depends on:** Nothing — fully independent
**Goal:** Let operators edit a confirmed meeting invite directly from the Appointment panel — change time, service type, notes, or email body — and re-send the updated invite without creating a duplicate booking.

---

## Background

Right now, once a meeting invite is sent (`Booking.status = "confirmed"`), there is no in-app way to change it. If the customer asks to reschedule or the operator picks the wrong slot, the only options are:
1. Cancel the booking and start over (loses context)
2. Manually edit the calendar event outside Foreman

This job adds an "Edit Appointment" button in the Appointment panel that opens an inline edit form, lets the operator update the relevant fields, and re-sends the confirmation email + updates the GCal event.

---

## UI — Edit Appointment button

In `templates/conversation_detail.html`, inside the confirmed booking state (`active_booking.status == 'confirmed'`):
- Add an "Edit Appointment" button next to the existing green confirmed banner
- Clicking it reveals an inline edit form (replaces the static display, same panel — no new page)
- The form is pre-filled with current values

```
✓  Fri Mar 20, 2026 · 10:00 AM – 11:00 AM
   HVAC Tune-up · Invite sent · $850
   [Edit Appointment]
```

---

## Edit Form Fields

- **Date** — date picker (pre-filled with current slot_start date)
- **Time** — time picker (pre-filled with current slot_start time)
- **Duration** — dropdown (30 min / 1 hr / 1.5 hr / 2 hr / 3 hr)
- **Service type** — text input (pre-filled)
- **Internal notes** — textarea (pre-filled from booking.notes)
- **Update email body** — toggle (default OFF). When ON, shows a textarea + ↺ Generate button to regenerate the confirmation email for the new time
- **Thread reply body** — optional short note to send in the original Gmail thread (e.g. "Quick update — I've moved your appointment to Friday at 10am")

Buttons:
- **Save Changes** — saves and re-sends (if mode=production)
- **Cancel** — collapses back to static view without saving

---

## Backend — `POST /api/booking/{booking_id}/edit`

```python
class EditBookingRequest(BaseModel):
    slot_start: str           # ISO datetime
    slot_end: str             # ISO datetime
    service_type: str | None = None
    notes: str | None = None
    email_body: str | None = None        # updated confirmation email (optional)
    thread_reply_body: str | None = None # short thread note (optional)
```

Steps:
1. Load booking — verify it belongs to operator, status in ('tentative', 'confirmed')
2. Update `booking.slot_start`, `booking.slot_end`, `booking.service_type`, `booking.notes`
3. If `booking.google_cal_event_id` exists: call `update_calendar_event(event_id, new_start, new_end, summary, description)` (new function in `integrations/calendar.py`)
4. If `email_body` provided AND mode=production: re-send via `_gmail_send_message()` using existing `gmail_thread_id` so it lands in the same thread
5. If `thread_reply_body` provided AND mode=production: send short note to Gmail thread
6. Log an outbound OutreachLog entry with `response_classification = "booking_confirmed"` and a note in content: "Appointment rescheduled to {new_time}"
7. Return `{status: "updated", booking_id, gcal_updated, email_sent}`

---

## New `integrations/calendar.py` Function

```python
def update_calendar_event(event_id: str, start_dt: datetime, end_dt: datetime,
                           summary: str | None = None,
                           description: str | None = None) -> dict:
    """
    Patch an existing GCal event's time (and optionally summary/description).
    Returns the updated event dict.
    """
```

Uses `events.patch()` — only sends changed fields, does not recreate the event.

---

## Constraints

- **No duplicate bookings.** Edit updates the existing Booking record in place — does not create a new one.
- **GCal update is best-effort.** If the calendar patch fails (stale token, deleted event), log the error but still save the booking changes.
- **Dry run mode.** In dry_run mode, save booking changes and update GCal but do NOT send the email. Show a dry-run notice.
- **Tentative bookings can also be edited** — the form should work even before the invite is sent.

---

## Tasks

- [ ] `task_01_calendar_update_fn.md` — `integrations/calendar.py` — add `update_calendar_event()`
- [ ] `task_02_edit_endpoint.md` — `api/app.py` — `POST /api/booking/{booking_id}/edit` endpoint
- [ ] `task_03_ui.md` — `templates/conversation_detail.html` — Edit Appointment button + inline edit form + JS

---

## Files to Read First

```
integrations/calendar.py
api/app.py  (confirm-booking endpoint for reference)
templates/conversation_detail.html
```

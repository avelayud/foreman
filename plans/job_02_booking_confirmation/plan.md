# Job 02 — Booking Confirmation Detection + Calendar Write-back

**Status:** ⬜ Backlog (Phase 6b)
**Goal:** When a customer confirms a specific proposed time slot, Foreman automatically creates a `Booking` record, updates the customer status to `booked`, and writes a Google Calendar event. The operator's job becomes review-only.

---

## Problem

Phase 6 proposal flow ends at "Operator approves booking proposal → sends via Gmail." There is no automatic detection of the customer's confirmation reply, no `Booking` record creation, and no calendar event creation. The operator must manually use "Mark as Booked" today.

## Solution

1. Add `booking_confirmed` as a 6th classifier category (distinct from `booking_intent`)
2. On confirmation: parse date/time from the reply, create `Booking` record, flip status to `booked`
3. Add `create_calendar_event()` to `integrations/calendar.py` with `calendar.events` write scope
4. Add `calendar_event_id` to `Booking` model
5. Show confirmation banner on conversation workspace (replaces draft panel when booked)

## Key Design Decisions

- `booking_intent` = customer wants to book but hasn't confirmed a specific slot
- `booking_confirmed` = customer has accepted a specific proposed time — THIS triggers auto-Booking creation
- Handle OAuth scope upgrade gracefully: catch 403, show banner on `/calendar`, no crash
- Date/time parsing: Claude extracts structured date from reply text (not regex)

## Files Involved

- `agents/response_classifier.py` — add `booking_confirmed` category
- `agents/reply_detector.py` — route `booking_confirmed` to booking creation pipeline
- `agents/conversation_agent.py` — parse date/time from confirmation reply
- `integrations/calendar.py` — add `create_calendar_event()`
- `core/models.py` — add `calendar_event_id` to `Booking`; migration needed
- `templates/conversation_detail.html` — confirmation banner replacing draft panel
- `api/app.py` — handle new status transitions

## Tasks (to be detailed)

| Task | Description | Status |
|------|-------------|--------|
| task_01 | Add `booking_confirmed` to response classifier | todo |
| task_02 | Auto-create Booking record on confirmation | todo |
| task_03 | Calendar write-back (create event) | todo |
| task_04 | Conversation workspace confirmation banner | todo |

## Acceptance Criteria

- [ ] Reply "Yes, Thursday at 2pm works!" → classified as `booking_confirmed`
- [ ] `Booking` record created with correct date/time
- [ ] `Customer.reactivation_status` flipped to `booked`
- [ ] `OutreachLog.converted_to_job = True`, `converted_at` set
- [ ] Google Calendar event created (or graceful fallback if scope not granted)
- [ ] Conversation workspace shows "Booked for [date]" banner instead of draft panel

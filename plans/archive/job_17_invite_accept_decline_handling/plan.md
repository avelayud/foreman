# Job 17 — Calendar Invite Acceptance / Decline Handling

**Status:** ⬜ Not started
**Depends on:** Job 14 (calendar_accepted classification), Job 16 (invite_sent status)
**Goal:** When a customer accepts the calendar invite, log it as a timeline event and take no further action — no draft, no status change, conversation stays in "Invite Sent" state. When a customer declines, queue a follow-up asking if another time works.

---

## Background

After Job 14 lands, `calendar_accepted` and `calendar_declined` are valid classifications. This job defines what happens downstream for each.

**Accept flow:**
- Customer accepts → `calendar_accepted` inbound log
- Timeline event: "✓ Customer accepted invite" (green badge)
- No draft queued, no status change
- `reactivation_status` stays `"invite_sent"` — appointment is still on

**Decline flow:**
- Customer declines → `calendar_declined` inbound log
- Status resets: `reactivation_status = "replied"` (they're back in conversation)
- Associated confirmed booking → status set to `"cancelled"`
- Response generator queues a follow-up draft: friendly, asks if another time works, proposes 2–3 available day/time windows (just days, not hard slots — keep it flexible)
- Draft goes to Outreach Queue (not Meetings Queue) since it's a conversation reply, not a formal invite

**New time proposal after decline:**
- If the decline email contains a proposed new time (customer replies with text proposing a time), the response classifier should catch this as `booking_confirmed` (customer proposing a new specific time) and the normal booking flow resumes
- If no new time in decline, just queue the "does another time work?" follow-up

**Conflict edge case (future to-do):**
- If customer proposes a new time that conflicts with operator's calendar, the system cannot currently handle this automatically. Log as a note in the to-do list; operator handles manually for now.

---

## Deliverables

1. `agents/response_generator.py` — Add `calendar_accepted` to skip list (no draft); add `calendar_declined` handler that:
   - Resets `reactivation_status = "replied"`
   - Cancels associated `Booking` (status → "cancelled")
   - Calls `generate_response(classification="calendar_declined")` to queue follow-up
2. `agents/conversation_agent.py` — Add `calendar_declined` draft type: friendly message asking if another time works, proposes 2–3 available day windows (AM/PM blocks, not hard times), flexible language
3. `api/app.py` — Conversation detail health: `calendar_accepted` + `"invite_sent"` status → health key stays "invite_sent" (no "needs_response")
4. `api/app.py` — `calendar_declined` triggers `reactivation_status = "replied"` → health key "needs_response"

---

## Tasks

- [ ] Read response_generator.py skip list
- [ ] Add calendar_accepted skip
- [ ] Add calendar_declined handler (reset status, cancel booking, queue draft)
- [ ] Add calendar_declined draft type in conversation_agent.py
- [ ] Verify health logic in app.py handles both new classifications correctly

---

## Future To-Do (add to PROJECT_PLAN.md)

- Reschedule meeting invite from conversation page
- Reschedule meeting invite from calendar page
- Conflict detection when customer proposes new time that conflicts with operator calendar

---

## Files to Attach

```
agents/response_generator.py
agents/conversation_agent.py
api/app.py              (search: _conversation_health, calendar_accepted, invite_sent)
```

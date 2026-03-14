# Job 21 — Meetings Queue Scope: Invites Only

**Status:** ⬜ Not started
**Goal:** The Meetings Queue should only contain calendar invites and rescheduling drafts. All other outbound drafts (responses, follow-ups, inquiries) go to the Outreach Queue. Also: when a customer requests a call, the response should propose available day/time windows inline in the reply (not create a formal invite) — that reply goes to Outreach Queue, not Meetings Queue.

---

## Background

Currently `_MEETINGS_CLASSIFICATIONS = ("booking_intent", "booking_confirmed")`. This means:
- `booking_intent`: a slot-proposal draft (customer wants to book, we propose times) → goes to Meetings Queue
- `booking_confirmed`: a confirmation draft (customer confirmed a specific time) → goes to Meetings Queue

The user wants:
- Meetings Queue = ONLY `booking_confirmed` (confirmed time, ready to send invite)
- `booking_intent` response = a conversational reply that proposes available day windows → goes to Outreach Queue
- The `booking_intent` draft should read naturally: answer any other questions the customer had AND propose 2–3 day/time windows in the body of the email (not a formal slot card)

This simplifies the Meetings Queue to a single purpose: send the calendar invite once a time is agreed upon.

---

## Deliverables

1. `api/app.py` — Change `_MEETINGS_CLASSIFICATIONS` from `("booking_intent", "booking_confirmed")` to `("booking_confirmed",)` only
2. `api/app.py` — Update `_get_queue_count` and `_get_meetings_queue_count` accordingly
3. `api/app.py` — Update GET /outreach route to include `booking_intent` drafts (they no longer need to be excluded)
4. `agents/conversation_agent.py` — Update `booking_intent` draft generation: instead of a formal slot proposal (the current `BookingProposalDraft` format), generate a conversational reply that:
   - Answers any questions the customer asked
   - Proposes 2–3 available day windows naturally in the email body (e.g., "I have availability Tuesday or Thursday afternoon — would either of those work for you?")
   - Does NOT use the hard slot-picker UI format
   - Uses real calendar availability to determine which days to propose (already done — just change the output format)
5. `templates/meetings.html` — Remove the "Booking Proposals" section (proposal_items loop) since `booking_intent` no longer routes here; simplify page to only show `booking_confirmed` items
6. `templates/outreach.html` — Ensure `booking_intent` drafts display correctly (they'll now appear here as regular reply drafts)

---

## Tasks

- [ ] Read conversation_agent.py — find `_generate_booking_proposal` or equivalent
- [ ] Read meetings.html — find proposal_items section
- [ ] Read outreach.html — verify booking_intent drafts will render correctly
- [ ] Change _MEETINGS_CLASSIFICATIONS
- [ ] Update _get_queue_count / _get_meetings_queue_count
- [ ] Update outreach queue filter
- [ ] Rewrite booking_intent draft format in conversation_agent.py (conversational reply with day windows)
- [ ] Remove booking proposals section from meetings.html
- [ ] Verify outreach.html renders booking_intent correctly

---

## Files to Attach

```
api/app.py              (search: _MEETINGS_CLASSIFICATIONS, _get_queue_count, _get_meetings_queue_count, /outreach route)
agents/conversation_agent.py
templates/meetings.html
templates/outreach.html
```

# Job 14 — Fix False Positive: Calendar Acceptance Triggers Redraft

**Status:** ⬜ Not started
**Goal:** When a customer accepts a Google Calendar invite, Gmail delivers an acceptance email to the operator's inbox. The reply detector is picking this up, classifying it as `booking_confirmed`, and incorrectly triggering "Action Required — Pending Scheduling" on the conversation page. Calendar acceptance emails must be detected early and routed to a new `calendar_accepted` classification that logs a timeline event and takes no further action.

---

## Background

Observed: Sam Keller accepted the calendar invite. Gmail sent an automated acceptance email ("Accepted: [event name]"). The reply detector found this in the inbox, matched it to Sam's thread, classified it as `booking_confirmed`, set `draft_queued=False`, and the conversation page started showing "Pending Scheduling" + "Redraft Meeting Invite."

This is a significant false positive. Calendar acceptance emails have a recognizable pattern:
- Subject: `Accepted: {event title}` or `{Name} has accepted your invitation to {event}`
- Body: Contains RSVP status, calendar event details, no human-written text
- Sender: Often the customer's email but may be `calendar-notification@google.com`

Similarly, decline emails need to be handled differently (see Job 17).

---

## Deliverables

1. `agents/reply_detector.py` — Before classifying a reply, check if the email subject/body matches known calendar notification patterns. If it's an acceptance, set `response_classification = "calendar_accepted"` and skip draft generation entirely.
2. `agents/reply_detector.py` — Same for decline: set `response_classification = "calendar_declined"`
3. `agents/response_classifier.py` (or wherever LLM classification happens) — Add `calendar_accepted` and `calendar_declined` as valid classifications with clear descriptions so the LLM also recognizes them
4. `api/app.py` — In conversation detail route, `calendar_accepted` classification should NOT trigger any "needs response" or redraft logic. Status stays `"booked"` (or `"invite_sent"` after Job 16 lands).
5. `templates/conversation_detail.html` — Add `calendar_accepted` timeline badge ("✓ Customer Accepted Invite") — green, no action required indicator
6. `agents/response_generator.py` — Skip `calendar_accepted` and `calendar_declined` in the draft generation loop (already skips `unsubscribe_request` — add these two)

---

## Tasks

- [ ] Read reply_detector.py — find where inbound emails are classified
- [ ] Read response_classifier.py — find the LLM prompt and valid classification list
- [ ] Add pre-classification regex/keyword check for calendar acceptance/decline patterns in reply_detector
- [ ] Update response_classifier valid classification list + prompt
- [ ] Add `calendar_accepted` / `calendar_declined` to skip list in response_generator
- [ ] Update conversation_detail health logic — `calendar_accepted` should not trigger needs_response
- [ ] Add timeline badge for calendar_accepted in conversation_detail.html
- [ ] Test: simulate a calendar acceptance email being picked up

---

## Detection Patterns

Pre-classify as `calendar_accepted` if subject matches:
- `^Accepted:` (case-insensitive)
- Contains "has accepted your invitation"
- Contains "accepted this invitation"

Pre-classify as `calendar_declined` if subject matches:
- `^Declined:` (case-insensitive)
- Contains "has declined your invitation"
- Contains "declined this invitation"

---

## Files to Attach

```
agents/reply_detector.py
agents/response_classifier.py  (or wherever classify_reply lives)
agents/response_generator.py
api/app.py                      (search: _conversation_health, pending_draft_log)
templates/conversation_detail.html
```

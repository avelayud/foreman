# Job 20 — Live Status Refresh After Send Actions

**Status:** ⬜ Not started
**Goal:** After an operator sends a draft or confirms a booking, conversation status chips should update immediately without requiring a full page reload. Currently the status stays stale until the operator manually refreshes.

---

## Background

When an operator:
- Approves and sends a reply from the Outreach Queue → conversation should flip from "Needs Response" to "Awaiting Reply"
- Confirms a booking / sends invite → conversation should flip to "Invite Sent" (after Job 16)
- Marks as booked from dashboard → should reflect in conversations list

The backend updates are atomic and correct — the issue is purely frontend: the page doesn't re-fetch status after a successful action.

---

## Deliverables

1. `templates/conversations.html` — After `approve-send` succeeds (in JS callback), re-fetch `/api/conversation/{customer_id}/status` and update the health chip inline without full reload; OR reload the row
2. `templates/outreach.html` — After approve-send, update the card status chip inline
3. `templates/conversation_detail.html` — After approve-send or confirm-booking JS callback succeeds, either reload the page (simpler) or update the health chip and stage chip inline
4. `api/app.py` — Add lightweight `GET /api/conversation/{customer_id}/status` endpoint that returns `{health_key, health_label, chip_cls, stage_label, stage_cls, reactivation_status}` — used by frontend for inline refresh
5. `templates/base.html` — After any send action, update the nav badge counts (`queue_count`, `meetings_queue_count`) inline without full reload (or trigger a badge refresh fetch)

---

## Implementation Approach

Simplest path that works well:
- For conversation_detail.html: just `window.location.reload()` after a 1s delay — page is small and fast to load
- For conversations list and outreach queue: add the new `/api/conversation/{id}/status` endpoint and update individual row chips after success
- For nav badges: add `GET /api/nav-counts` endpoint returning `{queue_count, meetings_queue_count}` and call it after any send action

---

## Tasks

- [ ] Add `GET /api/conversation/{customer_id}/status` endpoint to app.py
- [ ] Add `GET /api/nav-counts` endpoint to app.py
- [ ] Update conversations.html JS: call status endpoint after approve-send
- [ ] Update outreach.html JS: call status endpoint after approve-send
- [ ] Update conversation_detail.html: reload after approve-send and confirm-booking
- [ ] Update base.html or add JS utility function to refresh nav badge counts

---

## Files to Attach

```
api/app.py
templates/conversations.html
templates/outreach.html
templates/conversation_detail.html
templates/base.html
```

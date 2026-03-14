# Job 16 — New "Invite Sent" Conversation Status

**Status:** ⬜ Not started
**Goal:** Replace the "Booked → Closed" mapping with a correct "Invite Sent — Awaiting Visit" status. A scheduled appointment is not a closed conversation — it's an active one with a pending outcome. This is foundational for Jobs 17, 19, and parts of 20.

---

## Background

Currently: when `confirm_booking` sends the invite, `reactivation_status` is set to `"booked"`. `_conversation_health` maps `"booked"` → "Closed" chip. This is wrong in two ways:
1. The appointment hasn't happened yet — it's pending
2. On-site visits and calls are both scheduled via this flow — neither should be "Closed" until the visit outcome is logged

The new model:
- `reactivation_status = "invite_sent"` — set when the calendar invite + confirmation email is sent
- Health chip: "Invite Sent" with a blue/purple color (distinct from Awaiting Reply, Needs Response, Closed)
- Stays in this state until: (a) customer accepts/declines (Job 17), (b) visit outcome logged (existing post-visit flow), or (c) booking is cancelled
- "Closed" is only reached after `visit_outcome` is logged (job_won / no_show / cancelled)

`"booked"` can remain as a valid internal status for backward compat, OR we migrate to `"invite_sent"`. Recommendation: add `"invite_sent"` as a new status value and use it going forward; keep `"booked"` mapped to the old behavior for any legacy records.

---

## Deliverables

1. `core/models.py` — No schema change needed (reactivation_status is a string column); just document the new value
2. `core/database.py` — No migration needed
3. `api/app.py` — In `confirm_booking`: after email sent, set `reactivation_status = "invite_sent"` instead of `"booked"`
4. `api/app.py` — `_conversation_health()`: add `"invite_sent"` case → returns new health key `"invite_sent"` with label "Invite Sent" and a distinct chip color
5. `api/app.py` — `CONVERSATION_HEALTH_META`: add `"invite_sent"` entry
6. `api/app.py` — `REACTIVATION_STAGE_MAP`: add `"invite_sent"` entry with label "Invite Sent", progress 100%, status_cls "s-booked"
7. `api/app.py` — Update all queries that check `reactivation_status.in_(...)` to include `"invite_sent"` where `"booked"` was included
8. `api/app.py` — Conversations list: `"invite_sent"` customers go in `group_upcoming` (not closed/declined)
9. `api/app.py` — `delete_outreach` cascade: also reset `"invite_sent"` → `"replied"` (add alongside `"booked"`)
10. `templates/conversation_detail.html` — Add `stage-invite-sent` CSS class for the new chip
11. `templates/conversations.html` — Ensure "Invite Sent" customers show in the active conversations list with the right chip

---

## Tasks

- [ ] Read `_conversation_health`, `CONVERSATION_HEALTH_META`, `REACTIVATION_STAGE_MAP` in app.py
- [ ] Read all `reactivation_status == "booked"` references — update to also handle `"invite_sent"`
- [ ] Update confirm_booking to set `"invite_sent"` instead of `"booked"`
- [ ] Add health key + stage map entries
- [ ] Update conversation list grouping
- [ ] Update delete_outreach cascade
- [ ] Add CSS chip class
- [ ] Verify conversations list and conversation detail both show correct state

---

## CSS for New Chip

```css
.stage-invite-sent { background: #ede9fe; color: #6d28d9; border-color: #c4b5fd; }
```

---

## Files to Attach

```
api/app.py                  (search: _conversation_health, CONVERSATION_HEALTH_META, REACTIVATION_STAGE_MAP, reactivation_status.*booked, confirm_booking, delete_outreach)
templates/conversation_detail.html
templates/conversations.html
core/models.py
```

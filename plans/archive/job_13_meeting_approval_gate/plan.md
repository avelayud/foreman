# Job 13 — Meeting Approval Gate + Stop Auto-Send

**Status:** ⬜ Not started
**Goal:** (1) A meeting invite was sent at the wrong time (Wed 2pm default) before the operator explicitly approved it. Find and close the auto-send path that allowed this. (2) Require the operator to have filled in an estimate value (or checked "Unknown") before the Confirm Booking button is enabled.

---

## Background

Two related issues surfaced during real usage with Sam Keller:
- A meeting invite went out at the defaulted Wednesday 2pm time — 13 minutes before the operator intentionally sent the Tuesday 2pm invite. Something triggered a send without operator action.
- No estimate was enforced before sending. Estimate is needed for dashboard revenue tracking.

Likely cause of the auto-send: the `confirm_booking` endpoint or the `approve-send` endpoint has a code path where `approval_status="scheduled"` + `scheduled_send_at` in the past automatically fires. Or a background scheduler is triggering scheduled items. This needs to be traced and disabled/gated.

---

## Deliverables

1. `api/app.py` — Audit all background jobs and schedulers for anything that sends outbound emails automatically without explicit operator action. Specifically look at the scheduled send path.
2. `api/app.py` — In `confirm_booking`: server-side validation — if `estimated_value is None` AND `estimate_unknown is False`, return 400 with a clear error message
3. `templates/meetings.html` — Client-side gate: "Confirm Booking + Send Invite" button checks that either the estimate input has a value OR the "Unknown" checkbox is checked before submitting; shows inline error if not
4. `api/app.py` — If there is a background auto-sender for `approval_status="scheduled"` items, disable it or add a flag requiring explicit operator send (no silent auto-sends)

---

## Tasks

- [ ] Search api/app.py for any scheduler jobs that send emails (look for `approval_status == "scheduled"`, APScheduler jobs)
- [ ] Trace: how did the Wed 2pm invite get sent? Follow the `confirm_booking` and `approve-send` code paths
- [ ] Add server-side estimate gate in confirm_booking
- [ ] Add client-side estimate gate in meetings.html confirmBooking() JS
- [ ] Disable or gate any auto-send scheduler that doesn't require explicit operator confirmation
- [ ] Verify: no email should ever be sent without a button click from the operator

---

## Files to Attach

```
api/app.py          (search: scheduler, approve_and_send, confirm_booking, scheduled_send_at, APScheduler)
templates/meetings.html
```

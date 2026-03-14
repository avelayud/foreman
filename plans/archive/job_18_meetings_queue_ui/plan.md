# Job 18 — Meetings Queue UI Overhaul

**Status:** ⬜ Not started
**Goal:** Restructure the booking_confirmed card in the Meetings Queue to be more space-efficient and operationally clear. Key changes: availability windows instead of individual slots, side-by-side Appointment Details + Calendar Invite Email, customer details moved into the action panel, simpler subject line.

---

## Background

Current layout of the booking_confirmed card:
- Left side (full width): Appointment Details → Customer field → Subject → Body → Reply in Thread
- Right side: Confirm Booking panel + Quick Links

Problems identified in live usage:
1. Showing every 30-min slot wastes space — operator just needs to see windows of availability (e.g., "9–11 AM", "1–3 PM") and pick a specific time from a smaller list
2. "Customer" field is redundant (already in header)
3. The appointment slot defaults to a wrong day/time instead of pre-populating from what the customer actually said
4. Subject line includes day/time (e.g., "Confirmed - AC Assessment Tuesday 3/25 at 2pm") — this is wrong because the slot changes when operator picks a different time; subject should be generic
5. Appointment Details and Calendar Invite Email should be side-by-side (two columns within the left panel) to save vertical space

---

## Deliverables

1. `templates/meetings.html` — Restructure left panel of booking_confirmed card:
   - Top row: two columns — left = Appointment Details, right = Calendar Invite Email (subject + body)
   - Below: Reply in Thread (full width)
2. `templates/meetings.html` — Remove "Customer" field (redundant with header)
3. `templates/meetings.html` — Move customer email + phone to the right action panel, below "Confirm Booking" box, above Quick Links
4. `templates/meetings.html` — Availability slots: group by morning (7–12), afternoon (12–5), evening (5–8) and show time-window buttons rather than individual 30-min slots
5. `api/app.py` — `/api/calendar/slots` endpoint: add an optional `group=true` param that returns grouped windows instead of individual slots; OR handle grouping client-side in JS
6. `templates/meetings.html` — Subject field: strip day/time from the pre-populated subject value; just use the service type and customer name (e.g., "Confirming your AC service appointment")
7. `api/app.py` — Pre-populate appointment slot from `booking_slot_start` extracted from the customer's reply (already stored on the draft log) — ensure `item.booking_slot_start_input` is correctly set when the meetings queue is loaded
8. `api/app.py` — Calendar event description: change "Booked via Foreman reactivation outreach" → "Booked via Foreman"

---

## New Left Panel Layout

```
┌─────────────────────────────────────────────────────────────┐
│ [Appointment Details col]     [Calendar Invite Email col]    │
│  Day / Time / Duration         Subject                       │
│  Availability windows          Body (textarea, 6 rows)       │
│  Service Type                                                │
│  Notes                                                       │
├─────────────────────────────────────────────────────────────┤
│ [Reply in Thread — full width, 3 rows]                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Tasks

- [ ] Read current meetings.html booking_confirmed card HTML structure
- [ ] Read `/api/calendar/slots` endpoint in app.py
- [ ] Redesign left panel with two-column top section
- [ ] Remove Customer field
- [ ] Add customer email/phone to right action panel
- [ ] Implement availability window grouping (client-side JS or server-side)
- [ ] Fix subject line pre-population (strip day/time)
- [ ] Verify booking_slot_start_input is correctly set for pre-population
- [ ] Fix calendar event description text

---

## Files to Attach

```
templates/meetings.html
api/app.py          (search: /api/calendar/slots, booking_slot_start_input, meetings_queue_items, confirm_booking)
```

# Job 19 — Conversation Page: Appointment Confirmed Module Overhaul

**Status:** ⬜ Not started
**Depends on:** Job 16 (invite_sent status) — strongly recommended before this
**Goal:** After a meeting invite is sent, the conversation page should surface the appointment clearly at the top. Opportunity value should support a range (low/high), feed the dashboard, and only prompt for value if not already provided. Remove the confusing blue "booking created" banner.

---

## Background

Current state after invite is sent:
- "Appointment Confirmed" panel is at the BOTTOM of the right column, below the draft panel
- The blue "Booking created — what's the estimate?" banner shows at the top, which is confusing (duplicate prompt)
- Opportunity value is a single number — operators often don't know exactly, they know a range
- Opportunity value doesn't clearly flow into dashboard revenue pipeline

Desired state:
- Appointment module moves to TOP of right column (above Draft panel) when `active_booking.status == "confirmed"` or `reactivation_status == "invite_sent"`
- Opportunity value: two fields — Low ($) and High ($), whole numbers only, OR "Unknown" checkbox
- Value feeds `estimated_job_value` on Customer record (for dashboard) and `estimated_value` on Booking
- Remove the blue "Booking created" banner entirely
- One-time "Booking sent!" success toast on first page load after sending (stored in sessionStorage so it only shows once per session, not on every reload)
- No blue prompt banner if estimate was already provided during booking

---

## Deliverables

1. `templates/conversation_detail.html` — Move the "Appointment Confirmed" / "Pending — Invite Not Sent" schedule panel block to render ABOVE the draft panel when `active_booking` exists
2. `templates/conversation_detail.html` — Remove the blue "Booking created — what's the estimate?" banner (`#estimate-banner`) entirely
3. `templates/conversation_detail.html` — Inside the confirmed booking panel: move opportunity value above job notes; change to two inputs (low $, high $) + "Unknown" checkbox
4. `templates/conversation_detail.html` — Add one-time "Booking sent!" toast using sessionStorage key `booking_sent_{booking_id}` — show once, dismiss on click or after 4s
5. `api/app.py` — `POST /api/booking/{booking_id}/notes`: update to accept `estimated_value_low` and `estimated_value_high` (integers); store range on Booking; update `customer.estimated_job_value` to midpoint for scoring
6. `core/models.py` — Add `estimated_value_low` and `estimated_value_high` integer columns to Booking
7. `core/database.py` — Add `estimated_value_low` and `estimated_value_high` to SCHEMA_PATCHES for Booking
8. `api/app.py` — Dashboard and conversations list: use `estimated_value_low`/`high` range where available; display as "$X–$Y" or "$X" (if same)
9. `templates/conversation_detail.html` — Update opportunity value display to show range if both set

---

## Opportunity Value Range Display

- Input: two number fields side-by-side labeled "Low" and "High", step=100, min=0
- Display: if low == high or only one set → "$1,200"; if range → "$800 – $1,500"
- Midpoint stored on `customer.estimated_job_value` for scoring engine compatibility

---

## Tasks

- [ ] Read current conversation_detail.html — find schedule-panel, estimate-banner, and their positions relative to draft-panel
- [ ] Read /api/booking/{id}/notes endpoint
- [ ] Read core/models.py — Booking model columns
- [ ] Move schedule panel above draft panel in the Jinja2/HTML order
- [ ] Remove estimate-banner
- [ ] Replace single-value estimate input with low/high range inputs
- [ ] Add sessionStorage one-time toast
- [ ] Update /api/booking/{id}/notes endpoint to accept range
- [ ] Add columns to Booking model + SCHEMA_PATCHES
- [ ] Update dashboard/conversations list to display range

---

## Files to Attach

```
templates/conversation_detail.html
api/app.py              (search: /api/booking, estimate, active_booking, schedule-panel)
core/models.py
core/database.py
```

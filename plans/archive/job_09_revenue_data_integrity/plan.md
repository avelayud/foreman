# Job 09 — Revenue Data Integrity

**Phase:** 8 (internal quality, runs parallel to or after Job 05/06)
**Status:** ⬜ Not started
**Goal:** Enforce three data capture checkpoints so revenue metrics are actually reliable. Operators cannot close out a post-visit conversation without logging what happened. Surface pending post-visit items in the Updates inbox.

---

## Background

Revenue tracking is only as good as the data operators put in. Today the booking value field is optional and easy to skip. This job makes data capture a required checkpoint at three moments: booking creation, post-visit outcome, and quote/close. Enforcement is in-app only — no external nudges. ERP/CRM integration will eventually backfill gaps retroactively.

---

## The Three Checkpoints

### Checkpoint 1 — Booking Creation (Mandatory Estimate)
When any booking is created (auto-detected `booking_confirmed` or manually via Schedule Appointment panel), the operator must enter an estimated job value before confirming. Two valid inputs: a dollar amount, or explicit "Value Unknown" checkbox. Neither can be skipped.

Applies to:
- Auto-created bookings via `_auto_create_booking()` in reply_detector → surface the modal in the conversation workspace after auto-creation
- Manually created bookings via `POST /api/customer/{id}/book-and-invite` → enforce in the Schedule Appointment panel form

### Checkpoint 2 — Post-Visit Outcome (Locked Conversation)
Daily agent finds all bookings where `scheduled_at` has passed and `visit_outcome = "pending"`. For each matching customer:
- Conversation is **locked** — cannot be archived or marked complete at the API level
- Banner shown on conversation workspace: "Your appointment with [customer] was on [date]. What happened?"
- Three action buttons: **Confirmed — Quote Given** / **Confirmed — No Quote Yet** / **No Show**
- Customer surfaced in `/updates` under a new "Needs Post-Visit Update" section

### Checkpoint 3 — Quote + Close Capture
- **Quote Given** button → modal: "What was the quote amount?" → stored as `Booking.quote_given`
- **Job Won** button (shown after quote is given) → modal: "What was the final invoice value?" → stored as `Booking.final_invoice_value`, sets `job_won = True`, `closed_at = now`
- **No Show** → sets `visit_outcome = "no_show"`, unlocks conversation, no further capture needed

---

## New `Booking` Fields

```python
visit_outcome       = Column(String, default="pending")   # pending / confirmed / no_show
quote_given         = Column(Float, nullable=True)
quote_given_at      = Column(DateTime(timezone=True), nullable=True)
job_won             = Column(Boolean, default=False)
final_invoice_value = Column(Float, nullable=True)
closed_at           = Column(DateTime(timezone=True), nullable=True)
```

SCHEMA_PATCHES entries for all 6 new columns.

---

## New Agent — `PostVisitAgent`

**File:** `agents/post_visit.py`

**Logic:**
```python
def run(operator_id, db):
    """Find all bookings where scheduled_at < now and visit_outcome == 'pending'.
    For each: set Customer.needs_post_visit_update = True.
    Returns count of customers flagged."""
```

**Schedule:** Startup + daily via APScheduler (same pattern as Priority Scorer).

**Customer model addition:**
```python
needs_post_visit_update = Column(Boolean, default=False)
```
This flag is what the Updates inbox queries. Cleared when operator logs outcome.

---

## Conversation Lock Enforcement

In `api/app.py`, any endpoint that archives, closes, or removes a customer from active conversations must check:

```python
if customer.needs_post_visit_update:
    return JSONResponse(status_code=403, content={
        "error": "post_visit_required",
        "message": "Log the outcome of your appointment with this customer before closing."
    })
```

Endpoints to enforce:
- Any future archive/close endpoint
- `reactivation_status` manual update endpoints if they exist
- For now: the conversation workspace "Mark as Booked" flow if it allows status changes post-booking

---

## Updates Inbox Changes (`/updates`)

Add a new section at the top of `/updates` — above "Needs Response" or as the first section:

**"📋 Needs Post-Visit Update"** (red/urgent — these are blocking)
- Shows all customers where `needs_post_visit_update = True`
- Each row: customer name, appointment date, estimated value, "Log Outcome →" link to conversation workspace
- Badge count included in the sidebar updates counter

---

## Conversation Workspace Changes (`templates/conversation_detail.html`)

**Post-visit banner** (shown when `customer.needs_post_visit_update = True`):
```
┌─────────────────────────────────────────────────────────┐
│ 📋 Your appointment with [Name] was on [date].           │
│ What happened?                                           │
│                                                          │
│ [Quote Given]    [Confirmed — No Quote Yet]   [No Show]  │
└─────────────────────────────────────────────────────────┘
```

**Quote Given flow:**
- Modal: "What was the quote amount?" + dollar input
- On save: `POST /api/booking/{id}/quote` → stores `quote_given`, `quote_given_at`, sets `visit_outcome = "confirmed"`, clears `needs_post_visit_update`
- Conversation unlocked
- "Job Won" button appears in the booking summary panel

**Job Won flow:**
- Modal: "What was the final invoice value?" + dollar input + optional notes
- On save: `POST /api/booking/{id}/close` → stores `final_invoice_value`, `job_won = True`, `closed_at`, updates `OutreachLog.converted_job_value`

**No Show flow:**
- Confirmation: "Mark as no show?" 
- On confirm: `POST /api/booking/{id}/no-show` → sets `visit_outcome = "no_show"`, clears `needs_post_visit_update`, unlocks conversation

**Confirmed — No Quote Yet flow:**
- Sets `visit_outcome = "confirmed"`, clears lock
- "Quote Given" + "Job Won" buttons remain available in booking panel for later
- No blocking — operator can return to this later

---

## Booking Creation Enforcement

### Auto-detected bookings (`_auto_create_booking()` in reply_detector)
- After auto-creating a booking, set a flag `Booking.awaiting_estimate = True`
- Conversation workspace detects this flag and shows an estimate capture banner:
  ```
  📌 Booking created for [date]. What's the estimated job value?
  [ $_____ ]  [ Unknown ]  [Save]
  ```
- `POST /api/booking/{id}/estimate` → stores `estimated_value`, clears `awaiting_estimate`

### Manual bookings (Schedule Appointment panel)
- `estimated_value` input field is already in the panel
- Make it required (HTML `required` + backend validation) — reject if null and not marked unknown
- "Value Unknown" checkbox disables the input and passes `estimated_value = null, estimate_unknown = True`

---

## Revenue Funnel (Analytics Page Addition)

Add a "Revenue Pipeline" card to `/analytics`:

```
Foreman-Attributed Pipeline

Booked          23    $31,400 estimated
Visit Confirmed 18    78% show rate
Quote Given     14    $18,600 in quotes
Job Won         11    $12,200 confirmed revenue
                      avg close rate: 79%
```

Computed server-side in `core/analytics.py` — new `get_revenue_pipeline(operator_id, db)` function.

---

## New API Routes

| Method | Path | Description |
|---|---|---|
| POST | `/api/booking/{id}/estimate` | Save estimated_value on booking |
| POST | `/api/booking/{id}/quote` | Save quote_given + set visit_outcome=confirmed |
| POST | `/api/booking/{id}/close` | Save final_invoice_value + job_won=True |
| POST | `/api/booking/{id}/no-show` | Set visit_outcome=no_show, clear lock |
| GET | `/api/updates/post-visit` | Return customers needing post-visit update (for Updates inbox) |

---

## Tasks

- [ ] task_01_booking_model.md — new Booking fields + Customer.needs_post_visit_update
- [ ] task_02_schema_patches.md — SCHEMA_PATCHES for all new columns
- [ ] task_03_post_visit_agent.md — agents/post_visit.py + APScheduler registration
- [ ] task_04_api_routes.md — 5 new booking endpoints
- [ ] task_05_conversation_lock.md — 403 enforcement on archive/close endpoints
- [ ] task_06_updates_inbox.md — "Needs Post-Visit Update" section in /updates
- [ ] task_07_conversation_banners.md — post-visit banner + modals in conversation_detail.html
- [ ] task_08_booking_creation_enforcement.md — mandatory estimate on auto + manual bookings
- [ ] task_09_analytics_funnel.md — Revenue Pipeline card in /analytics

---

## Files to Attach in Claude Code

```
PROJECT_PLAN.md
core/models.py
core/database.py
agents/reply_detector.py
api/app.py
templates/conversation_detail.html
templates/updates.html
core/analytics.py
```

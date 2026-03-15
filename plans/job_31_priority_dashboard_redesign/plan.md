# Job 31 — Priority Dashboard Redesign

**Phase:** 8
**Status:** ⬜ Not started
**Depends on:** Nothing — fully independent
**Goal:** Redesign the Priority Dashboard so the top-of-page metric tiles tell a clear story about pipeline health and revenue opportunity. Replace the current generic tiles with an opinionated layout that surfaces the most decision-relevant numbers: uncontacted revenue, in-flight revenue, and conversion performance.

---

## Background

The current tiles show: Customers, Contacted, Replied, Booked, Conversion Rate, Avg Job Value, Dormant Days, Total Outreach. These are activity metrics — they measure what happened, not what needs to happen. An operator glancing at the dashboard can't immediately answer: "How much money is sitting untouched? What's moving through the pipeline right now? Am I making progress?"

The redesign separates **opportunity** (money available) from **pipeline** (money in motion) from **outcomes** (money captured), making the answer to those questions instant.

---

## New Metric Architecture

### Row 1 — Opportunity (the "what's available" row)

| Tile | Value | Sub-label |
|------|-------|-----------|
| **Uncontacted Revenue** | `$XX,XXX` | `N customers never contacted` |
| **In-Flight Revenue** | `$XX,XXX` | `N active conversations` |
| **Booked Pipeline** | `$XX,XXX` | `N appointments confirmed` |
| **Converted (YTD)** | `$XX,XXX` | `N jobs closed this year` |

**Uncontacted Revenue** = sum of `estimated_job_value` for customers with `reactivation_status == "never_contacted"` and `estimated_job_value > 0`. If no values set, show customer count with a "No values set — add estimates to track" note.

**In-Flight Revenue** = sum of `estimated_job_value` for customers with `reactivation_status in ("outreach_sent", "replied", "invite_sent")`.

**Booked Pipeline** = sum of `Booking.estimated_value` for bookings with `status in ("tentative", "confirmed")` and `job_won IS NOT TRUE`.

**Converted (YTD)** = sum of `Booking.final_invoice_value` for bookings with `job_won = True` and `closed_at >= start of current year`.

---

### Row 2 — Pipeline Health (the "how is outreach performing" row)

| Tile | Value | Sub-label |
|------|-------|-----------|
| **Reply Rate** | `XX%` | `N replies / N contacted` |
| **Booking Rate** | `XX%` | `N booked / N replied` |
| **Avg Days to Reply** | `X.X days` | `across active sequences` |
| **Needs Attention** | `N` | `needs response or follow-up` |

**Reply Rate** = customers who ever replied / customers ever contacted (outreach_sent or further).
**Booking Rate** = customers who reached booked / customers who replied.
**Avg Days to Reply** = avg(first inbound log created_at - first outbound log sent_at) across all customers who replied.
**Needs Attention** = `conversations_attention_count` (already computed).

---

### Row 3 — Priority Queue (redesigned, no action buttons)

The current priority queue table shows action buttons (Draft Outreach, Mark as Booked) inline. **Remove all action buttons from this table.** The operator takes action from the conversation page — the dashboard priority queue is read-only. Also remove Mark as Booked from the dashboard entirely (that flow belongs on the conversation page).

Each row in the priority queue should show:
- Customer name (links to conversation)
- Score badge (high/medium/low tier color)
- Status tag (same pill format as conversations page — `status-pill s-*` classes, matching the tagging style used on Conversations, Outreach Queue, Meetings Queue)
- Days dormant
- Estimated value

Update the section label to "Outreach Priority Queue" and add: "Sorted by opportunity score. Take action from the conversation page."

---

## Data Computation — `api/app.py` GET /

Add a `compute_dashboard_metrics(db, operator_id)` function that returns a dict with all tile values. Called once per page load, results passed to template.

```python
def compute_dashboard_metrics(db, operator_id: int) -> dict:
    # Uncontacted revenue
    uncontacted = db.query(Customer).filter_by(
        operator_id=operator_id, reactivation_status="never_contacted"
    ).all()
    uncontacted_rev = sum(c.estimated_job_value or 0 for c in uncontacted)
    uncontacted_with_val = sum(1 for c in uncontacted if c.estimated_job_value)

    # In-flight revenue
    in_flight_statuses = ("outreach_sent", "replied", "invite_sent")
    in_flight = db.query(Customer).filter(
        Customer.operator_id == operator_id,
        Customer.reactivation_status.in_(in_flight_statuses)
    ).all()
    in_flight_rev = sum(c.estimated_job_value or 0 for c in in_flight)

    # Booked pipeline
    from core.models import Booking
    booked = db.query(Booking).filter(
        Booking.operator_id == operator_id,
        Booking.status.in_(["tentative", "confirmed"]),
        Booking.job_won.isnot(True)
    ).all()
    booked_rev = sum(b.estimated_value or 0 for b in booked)

    # Converted YTD
    from datetime import date
    year_start = datetime(date.today().year, 1, 1)
    converted = db.query(Booking).filter(
        Booking.operator_id == operator_id,
        Booking.job_won == True,
        Booking.closed_at >= year_start
    ).all()
    converted_rev = sum(b.final_invoice_value or 0 for b in converted)

    # Reply rate
    contacted = [c for c in db.query(Customer).filter(
        Customer.operator_id == operator_id,
        Customer.reactivation_status != "never_contacted",
        Customer.reactivation_status != "unsubscribed",
    ).all()]
    replied = [c for c in contacted if c.reactivation_status in (
        "replied", "invite_sent", "booked", "sequence_complete"
    )]
    reply_rate = round(len(replied) / len(contacted) * 100) if contacted else 0

    # Booking rate
    booking_rate = round(len([c for c in replied if c.reactivation_status in ("invite_sent", "booked")]) / len(replied) * 100) if replied else 0

    return {
        "uncontacted_rev": uncontacted_rev,
        "uncontacted_count": len(uncontacted),
        "uncontacted_with_val": uncontacted_with_val,
        "in_flight_rev": in_flight_rev,
        "in_flight_count": len(in_flight),
        "booked_rev": booked_rev,
        "booked_count": len(booked),
        "converted_rev": converted_rev,
        "converted_count": len(converted),
        "reply_rate": reply_rate,
        "replied_count": len(replied),
        "contacted_count": len(contacted),
        "booking_rate": booking_rate,
    }
```

---

## Tile Visual Design

**Row 1 tiles** use larger numbers (Playfair, 28px) since they represent dollar amounts — the primary signal.
**Row 2 tiles** use standard sizing (Playfair, 22px).

Each tile:
```
┌────────────────────────┐
│ UNCONTACTED REVENUE     │  ← 9px mono label, uppercase
│ $24,500                 │  ← 28px Playfair, navy
│ 12 customers            │  ← 11px mono, text-3
└────────────────────────┘
```

Row 1 tiles get a left color accent bar matching the pipeline stage:
- Uncontacted: `var(--red)` (opportunity sitting idle)
- In-flight: `var(--amber)` (active conversations)
- Booked: `var(--blue)` (confirmed pipeline)
- Converted: `var(--green)` (closed revenue)

---

## Template Changes — `templates/dashboard.html`

Replace the current `<div class="metric-grid">` section (8 tiles) with the new 2-row layout. Keep the priority queue table below unchanged.

---

## Key Constraint

If `estimated_job_value` is null for many customers (not yet filled in), the uncontacted/in-flight revenue tiles will show $0 or a low number that looks wrong. In that case, add a sub-note in amber: "Add opportunity values to conversations to track pipeline revenue." Only show this note when `uncontacted_with_val < uncontacted_count * 0.5` (fewer than half have values set).

---

## Tasks

- [ ] `task_01_backend.md` — add `compute_dashboard_metrics()` to `api/app.py` GET / route
- [ ] `task_02_template.md` — `templates/dashboard.html` — replace tile section with 2-row layout + color accents

---

## Files to Read First

```
api/app.py  (GET / dashboard route)
templates/dashboard.html
core/models.py  (Customer, Booking fields)
```

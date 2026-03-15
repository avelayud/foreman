# Job 32 — Analytics Dashboard Overhaul

**Phase:** TBD — requires product thinking before execution
**Status:** 🟡 Backlog (design needed first)
**Depends on:** Jobs 29, 31 (conversations + dashboard redesigns complete — shared vocabulary for what metrics matter)
**Goal:** TBD — the current analytics page needs a complete rethink before a job plan can be written.

---

## Design Constraints From Job 31

When Job 31 (Priority Dashboard) is executed, two things must carry into the analytics design:
1. **No action buttons anywhere on read-only pages.** Mark as Booked and Draft Outreach have been removed from the dashboard priority queue. The analytics page should follow the same rule — all views are observational, no inline actions.
2. **Status tagging consistency.** All list rows and table rows that show a customer's status must use the `status-pill s-*` tag format (same as Conversations page, Outreach Queue, Meetings Queue). Plain text status labels are not acceptable in list contexts.

## Why This Is Backlog

Analytics is the hardest page to get right because it requires a clear answer to: *what decisions should an operator be able to make after looking at this page?* Without a clear answer, we'll build charts that look interesting but don't change behavior.

Current analytics page problems (observed):
- Charts exist but the questions they answer aren't clear
- No separation between activity metrics (what I did) vs outcome metrics (what resulted)
- No time-series — can't see if things are improving
- No comparison (this week vs last week, this month vs same month last year)

---

## Questions to Answer Before Writing the Plan

1. **What are the 3 highest-leverage operator decisions** that analytics should inform?
   - "Should I run more outreach this week?" → need outreach volume + conversion rate trend
   - "Are my emails working?" → reply rate by sequence position, by subject line type
   - "Am I growing revenue?" → pipeline value trend over time

2. **What time horizons matter?** Last 30 days? Rolling 12 months? YTD?

3. **What's the right level of segmentation?** By customer category? By service type? By outreach type?

---

## Candidate Sections (to be scoped in planning)

### 1. Revenue Trend
- Monthly bar chart: `converted_rev` per month for last 12 months
- Overlay: `booked_pipeline` per month (leading indicator)

### 2. Outreach Funnel
- Contacted → Replied → Booked → Converted (funnel chart or step chart)
- Show absolute numbers + conversion rates at each step
- Compare: current month vs previous month

### 3. Reply Rate by Sequence Position
- Line chart: reply rate at Day 1, Day 3, Day 7, Day 14 outreach
- Helps identify which follow-up step is most effective

### 4. Customer Segment Breakdown
- Donut or bar: distribution of contacted/replied/booked/converted by segment
- (High value, end-of-life, new lead, referral, maintenance)

### 5. Agent Activity Log
- Table: which agents ran, when, how many actions taken
- Helps diagnose if agents are running on schedule

---

## Pre-Requisites

Before writing the full plan:
- Discuss with operator what questions they most want answered
- Confirm which metrics are reliably populated in the DB (many fields are nullable)
- Decide on charting approach (Chart.js, D3, or pure SVG — we've been using pure SVG for the donut in Job 29)

---

## Placeholder Tasks

- [ ] Product discussion — agree on 3–5 core analytics questions
- [ ] Data audit — which metrics are reliably populated vs sparse
- [ ] Plan.md — write full job plan once scope is agreed
- [ ] Execute

---

## Files to Read First (when ready)

```
api/app.py  (GET /analytics route)
templates/analytics.html
core/models.py
```

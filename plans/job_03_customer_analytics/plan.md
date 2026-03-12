# Job 03 — Customer Analytics Page (`/analytics`)

**Status:** ⬜ Backlog
**Depends On:** Job 01 (profiles populated), Job 04 (instrumentation in place)
**Goal:** Build a new read-only analytics page for understanding customer base composition and Foreman's revenue impact. Distinct from the dashboard (which is for action) — this is for understanding.

---

## Two Tabs

### Tab 1 — Customer Insights
- 4 snapshot stat cards (all-time): Total Customers, Avg Lifetime Value, Avg Days Dormant, Customers with 3+ Jobs
- Value Tier Donut chart: High (>$2k LTV) / Mid ($500–$2k) / Low (<$500), center label = total count
- Dormancy Distribution horizontal bar: Active (<6mo) / Priority Dormant (6–18mo) / Cold (18mo+)
- Engagement by Segment grouped bar: per value tier → Sent / Replied / Booked counts
- Job Type Breakdown horizontal bar: all job types by frequency + computed insight ("Customers with maintenance history score X points higher on average")
- Response Classification Breakdown: per classification bucket — count, % of total replied, avg days to convert (for `booking_confirmed`)

### Tab 2 — Revenue & ROI
- 4 revenue stat cards: Revenue Generated ($0 if none — never hidden), Pipeline Value, Jobs Booked, Avg Job Value
- Outreach Funnel: stepped horizontal bars — Dormant Identified → Contacted → Replied → Booked, with rates at each step
- Outreach Activity Over Time: line chart — sent vs. replies over time, time-range toggle, weekly aggregation if >60 days
- Revenue Over Time: bar chart (weekly converted revenue) + cumulative running total line
- Recent Conversions table: last 10 customers converted — name / outreach sent / responded / job value / days to book

---

## Key Design Decisions

- **Read-only.** No actions, no customer table, no Mark as Booked — that's the dashboard
- **Time range toggle:** `?range=30|90|all` page reload; only affects time-series charts, not composition data
- **Chart.js via CDN** — no npm, no build step
- **All aggregations server-side** in new `core/analytics.py`
- **Sidebar:** "Analytics" link between Conversations and Agents in `base.html`

## Empty States
- Scoring not run → banner linking to /agents
- No outreach → inline message per chart section
- No conversions → revenue cards show $0, charts show message pointing to Mark as Booked flow

## Files to Create

- `core/analytics.py` — all aggregation functions
- `templates/analytics.html` — two-tab layout with Chart.js

## Files to Modify

- `api/app.py` — add `GET /analytics` route
- `templates/base.html` — sidebar nav link

## Tasks (to be detailed)

| Task | Description | Status |
|------|-------------|--------|
| task_01 | `core/analytics.py` — all aggregation functions | todo |
| task_02 | `templates/analytics.html` — Tab 1: Customer Insights | todo |
| task_03 | `templates/analytics.html` — Tab 2: Revenue & ROI | todo |
| task_04 | Route + nav integration | todo |

## Acceptance Criteria

- [ ] `/analytics` loads without error
- [ ] Tab 1 donut chart renders with correct value tier counts
- [ ] Tab 2 funnel shows correct Dormant → Contacted → Replied → Booked progression
- [ ] Time range toggle filters time-series charts only (composition data unchanged)
- [ ] Empty states display correctly when no outreach/no conversions
- [ ] Sidebar "Analytics" link is present and active-highlighted when on /analytics

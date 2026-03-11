# Foreman — Project Plan & Status Tracker

> Share this file at the start of a new chat so work can resume with correct context.

---

## Product Vision

**Vision:** AI Operating System for Field Service Revenue
**Product:** AI Reactivation System for HVAC & Field Service Businesses
**Tagline:** Turn your past customers into booked jobs. Automatically.

**Target customer:** HVAC, plumbing, and electrical contractors. Owner-operated teams of 3–15. Not highly technical. May be using QuickBooks, Jobber, HousecallPro — or nothing beyond a phone. HVAC is the primary beachhead.

**Positioning:** Foreman is a revenue system, not a CRM or email tool. The core value proposition: identify which past customers are most likely to need service now, reach out in the operator's voice, convert responses to booked jobs, and show exactly how much revenue it generated. Priced below Jobber/HousecallPro, dramatically above them in AI-driven proactive outreach capability.

**Core loop:** Score → Prioritize → Outreach → Classify Response → Convert to Job → Track Revenue

---

## Current Status

- **Active Phase:** Phase 5 (in progress)
- **State:** Core workflows fully operational. Conversations, drafts, reply detection, and follow-up all working end-to-end against real Gmail. Now building customer scoring + revenue dashboard to transform the product from email assistant to revenue system.
- **Last Updated:** 2026-03-11
- **Live URL:** https://web-production-3df3a.up.railway.app
- **Repo:** https://github.com/avelayud/foreman

---

## Recently Completed (2026-03-11)

### Conversation workspace
- Redesigned **Conversation Detail** page:
  - Two-column layout: timeline (left) + draft panel + expanded message (right)
  - Timeline sorted newest-first; each item shows AI-generated one-sentence summary
  - Click any timeline item to expand full email body on the right
  - Draft panel auto-loads on page open; context-aware (reply vs. follow-up)
  - Approve & Queue button moves draft directly to outreach queue
  - Full-width collapsible sections: Opportunity Snapshot + Conversation Recap & Talking Points
- Active Conversations list shows most recent message (inbound or outbound) with "Customer replied" signal

### Draft generation
- Reply drafts: read full conversation thread + customer job history; answer specific questions with real domain knowledge (HVAC filter lifespans, equipment ages, etc.)
- Follow-up drafts: include full previous outreach thread so draft explicitly references what was sent
- Body normalization: collapses single newlines within paragraphs to prevent broken email formatting
- Draft panel shows informative error if no sent emails exist for the customer

### Dashboard
- "View all →" now scrolls to browse section and activates tab via JS
- Live search box on browse card — filter any customer by name in real time

### Sidebar
- Attention badge on Conversations nav item (needs_response + needs_follow_up count)

### Timestamp handling
- All timestamps stored as UTC; display filter converts to Eastern (EDT/EST auto via `America/New_York`)
- Fixed Gmail inbound timestamp bug: was stripping timezone before UTC conversion, storing local EDT as naive datetime
- Migration script `data/fix_inbound_timestamps.py` corrects existing inbound logs (adds EDT offset)
- Railway Postgres: run `UPDATE outreach_logs SET sent_at = sent_at + INTERVAL '4 hours' WHERE direction = 'inbound' AND gmail_thread_id IS NOT NULL AND sent_at IS NOT NULL;` once to fix existing records

### Railway / infra
- Railway CLI workflow confirmed: `brew install railway` → `railway login` → `railway link` → `railway connect Postgres`
- Public networking must be enabled on Postgres service for external psql access

---

## Build Phases Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| 1 | Foundation (models/config/DB) | ✅ Complete | Stable |
| 2 | Tone Profiler + Dashboard UI | ✅ Complete | Stable |
| 3 | Reactivation Analyzer + Approval Queue | ✅ Complete | Stable |
| 4 | Gmail Send + Follow-up Intelligence + Conversation UX | ✅ Complete | Fully operational |
| 5 | Customer Scoring + Revenue Dashboard | 🟡 In Progress | See checklist below |
| 6 | Response Classifier + Booking Conversion | ⬜ Not Started | Planned |
| 7 | Follow-up Sequence Engine + Calendar Integration | ⬜ Not Started | Planned |
| 8 | SMS Channel (Twilio) | ⬜ Not Started | Planned |
| 9 | Service Interval Prediction (AI Analytics) | ⬜ Not Started | Planned |
| 10 | Jobber / HousecallPro Integration | ⬜ Not Started | Planned |
| 11 | QuickBooks Data Ingestion | ⬜ Not Started | Planned |
| 12 | ML-Trained Scoring Model (sklearn) | ⬜ Not Started | Planned |

---

## Phase 4 — All Done

- [x] Gmail send path on approval/send-now
- [x] Thread ID persistence on outbound logs
- [x] Customer Analyzer agent
- [x] Reply Detector agent (background thread, every 15 min)
- [x] Follow-up Sequencer agent
- [x] Reactivation agent integrated with analyzer context
- [x] Active Conversations page (health state, attention badge)
- [x] Conversation Detail page (AI timeline summaries, draft panel, expandable messages)
- [x] Outreach queue redesign + approve/schedule/send-now flow
- [x] Production/dry-run toggle in UI
- [x] Scheduled send worker loop in app
- [x] Timestamp UTC normalization + EDT/EST display filter
- [x] Dashboard browse-all with search

---

## Phase 5 — Customer Scoring + Revenue Dashboard

**Goal:** Transform the product from email assistant to revenue system. A second contractor should be able to log in, see their priority customer list, understand why each customer is ranked, and see Foreman's impact in dollars — without any help from us.

- [ ] Rebuild seed data (`data/reseed.py`): 200 customers, 5yr HVAC history, realistic distributions (see Seed Data spec below)
- [ ] `core/scoring.py`: rules-based scoring engine, `score()` + `score_all_customers()`
- [ ] Customer model migration: add `score`, `score_breakdown`, `priority_tier`, `estimated_job_value`, `service_interval_days`, `predicted_next_service`
- [ ] OutreachLog model migration: add `response_classification`, `classified_at`, `converted_to_job`, `converted_job_value`, `converted_at`
- [ ] Scoring job: runs on startup + APScheduler daily refresh
- [ ] Rebuild `dashboard.html`: revenue metrics row + priority customer queue (see Dashboard spec below)
- [ ] "Mark as Booked" flow: modal on conversation workspace + dashboard action button, logs job value

---

## Phase 6 — Response Classifier + Booking Conversion

**Goal:** Foreman intelligently routes every inbound reply. Booking intent triggers a calendar slot proposal. Operator's manual workload drops significantly.

- [ ] `agents/response_classifier.py`: Claude classifier, 5 categories (booking_intent, callback_request, price_inquiry, not_interested, unclear)
- [ ] Wire classifier into reply detector pipeline (runs on each new inbound reply)
- [ ] Classification stored on `OutreachLog.response_classification`
- [ ] Conversation workspace updated to show classification badge + recommended next action
- [ ] Basic calendar slot management (operator sets weekly availability template)
- [ ] Auto-draft time proposal when `booking_intent` detected
- [ ] Booking confirmation flow (customer confirms, slot logged)

---

## Phase 7 — Follow-up Sequence Engine + Calendar Integration

- [ ] `agents/followup_agent.py`: generates follow-up draft, respects sequence state (don't re-contact if already replied)
- [ ] `FollowUpSequence` model: touch count, next scheduled touch, status
- [ ] APScheduler job: daily check for customers due for follow-up
- [ ] Google Calendar OAuth + read availability
- [ ] Slot proposals pull real calendar gaps
- [ ] Operator edit capture: diff between generated draft and sent email fed back to tone profiler

---

## Phase 8 — SMS Channel (Twilio)

- [ ] Twilio integration (`integrations/twilio.py`)
- [ ] SMS draft generation (shorter, more direct tone profile variant)
- [ ] Reply detection via Twilio webhook
- [ ] Response classifier handles SMS replies
- [ ] Operator chooses channel per customer (email / SMS / both)

---

## Phase 9 — Service Interval Prediction

- [ ] Per-customer service interval calculation from job history
- [ ] `predicted_next_service` populated and surfaced in dashboard
- [ ] Automated service reminder triggered when predicted_next_service is approaching
- [ ] Dashboard shows "overdue vs. their own cadence" as a distinct signal
- [ ] Customer profile analytics page: full history, score breakdown, predicted needs

---

## Phases 10–12 (Future)

- **Phase 10:** Jobber + HousecallPro API integration (OAuth, job history sync)
- **Phase 11:** QuickBooks data ingestion (invoice history → revenue enrichment)
- **Phase 12:** sklearn ML scoring model trained on real `converted_to_job` outcome labels

---

## Scoring Model Spec (Phase 5)

Rules-based weighted scorer. Designed to be interpretable and replaceable with a trained model once real conversion data exists.

**Weights v1:**

| Signal | Field | Max Points | Logic |
|---|---|---|---|
| Recency | days since last job | 40 | >365 days = 40, scales linearly below |
| Lifetime value | sum of job revenue | 20 | >$2000 = 20, >$500 = 10, else 5 |
| Job frequency | count of prior jobs | 15 | jobs × 3, capped at 15 |
| Job type | maintenance vs repair | 15 | Any maintenance = 15, repair-only = 8, single job = 4 |
| Prior engagement | response to past outreach | 10 | Positive response = 10, any reply = 5, none = 0 |

Output: `{ "total": 78, "breakdown": { "recency": 40, ... }, "priority_tier": "high" }`

Priority tiers: high ≥70, medium 40–69, low <40.

Stored on Customer model. Recalculated on startup + daily via APScheduler.

**Phase 12 ML upgrade:** Once 3–6 months of real conversion outcomes exist, retrain using `converted_to_job` as label with sklearn RandomForest. Rules-based weights serve as feature engineering baseline.

---

## Dashboard Spec (Phase 5 Rebuild)

The dashboard is the operator's daily work queue — a revenue command center.

**Top metrics row (8 cards):**
1. Dormant customers identified (score >40, not contacted in 90 days)
2. % dormant customers contacted
3. Responses received
4. Active conversations
5. Jobs booked (converted_to_job = True)
6. Revenue generated (sum of converted_job_value)
7. Potential revenue (sum of estimated_job_value for uncontacted priority customers)
8. Avg job value

**Priority customer queue:**
Ranked by score descending. Columns: Score badge (green ≥70, yellow 40–69, red <40) | Customer name | Last service | Days dormant | Est. job value | Outreach status | Action button.

**Filter tabs:** All | High Priority | Not Contacted | Awaiting Reply | Active | Booked

---

## Seed Data Spec (Phase 5)

200 customers with statistically realistic HVAC service history so the scoring model produces a meaningful distribution.

**Distributions:**
- Dormancy: ~30% active (<6mo), ~40% priority dormant (6–18mo), ~30% cold (18mo+)
- Customer value: ~20% high-value ($2000+ lifetime, 4+ jobs), ~50% mid-value ($500–2000, 2–4 jobs), ~30% low-value (<$500, 1–2 jobs)
- Service intervals: normal distribution ~9 months mean, 3 months std dev
- Job types: Maintenance, AC Repair, Furnace Repair, Emergency Service, New Install, Seasonal Tune-Up
- Revenue per job: Maintenance $89–149, Repair $200–800, Emergency $350–1200, Install $2500–8000
- OutreachLog entries: 0–3 per customer, mix of reply types (booking_intent, not_interested, callback_request, price_inquiry, no reply)

**Post-seed output:** print score distribution, revenue totals, dormancy breakdown.

---

## Known Risks / Watch-outs

- `reply_detector` + `follow_up` run as background threads (15-min poll); not backed by a durable scheduler — will miss cycles on dyno restart. Acceptable for now; move to cron/Celery if reliability becomes an issue.
- Postgres password was shared in a chat session — **rotate credentials** in Railway (Postgres → Settings → Regenerate).
- Single-tenant: `OPERATOR_ID = 1` hardcoded throughout. Must audit before onboarding second operator.

---

## Backlog

- **Durable scheduler**: wire `reply_detector` and `follow_up` to a cron or task queue so they survive restarts
- **Email draft quality loop**: operator feedback signal, prompt A/B testing, tone calibration refinement
- **Voice profiles from Gmail**: generate profiles from actual sent mail instead of manual seed
- **Voice profile config screen**: let operator fine-tune each voice's response style
- **Multi-tenant isolation audit**: all queries filter by operator_id before any second-user onboarding

---

## Local Run

```bash
# SQLite (default local dev)
DATABASE_URL=sqlite:///./foreman.db venv/bin/python -m api.run

# Against Railway Postgres (public proxy must be enabled)
DATABASE_URL=postgresql://<user>:<pass>@hopper.proxy.rlwy.net:26095/railway venv/bin/python -m api.run
```

### Manual agent runs
```bash
venv/bin/python -m agents.tone_profiler --operator-id 1
venv/bin/python -m agents.reactivation --operator-id 1 --limit 10
venv/bin/python -m agents.customer_analyzer --operator-id 1 --all
venv/bin/python -m agents.reply_detector --operator-id 1
venv/bin/python -m agents.follow_up --operator-id 1 --limit 20
```

---

## Decisions Log

| Date | Topic | Decision |
|---|---|---|
| 2026-03-08 | Product direction | Reactivation-first wedge before full FSM stack |
| 2026-03-09 | Deployment platform | Railway for Python + Postgres simplicity |
| 2026-03-10 | Agent naming | "Reactivation" renamed in UI to **Reactivation Analyzer** |
| 2026-03-10 | Operator safety | Added Dry Run / Production mode toggle |
| 2026-03-10 | Queue behavior | Approved but unsent drafts remain visible as scheduled/pending |
| 2026-03-10 | Conversation UX | Separate conversation page; conversation-only timeline |
| 2026-03-10 | Deploy hardening | Added startup retries, DB URL normalization, and Python launcher |
| 2026-03-11 | Timestamps | All stored as UTC; display via `America/New_York` zoneinfo filter |
| 2026-03-11 | Draft context | Follow-up drafts now include full thread; reply drafts include job history + domain knowledge |
| 2026-03-11 | Product pivot | Repositioned as revenue system (not email assistant); scoring + revenue dashboard added as Phase 5 |
| 2026-03-11 | Scoring approach | Rules-based weighted scorer first (works on fake data); ML model deferred to Phase 12 when real conversion labels exist |
| 2026-03-11 | Phase renumbering | SMS moved from Phase 5 to Phase 8; scoring/revenue dashboard inserted as new Phase 5 |

---

## New Chat Resume Prompt

```text
I'm continuing work on Foreman — an AI reactivation system for HVAC & field service contractors.

Please read PROJECT_PLAN.md and README.md first to get full context.

Current state: Phase 4 complete. Phase 5 is in progress — building customer scoring engine + revenue dashboard.

Phase 5 priorities in order:
1. Rebuild seed data (data/reseed.py): 200 customers, 5yr HVAC history, realistic distributions (see Seed Data Spec in PROJECT_PLAN.md)
2. core/scoring.py: rules-based scoring engine (see Scoring Model Spec)
3. Model migrations: Customer + OutreachLog additions (see Phase 5 checklist)
4. Rebuild dashboard.html: revenue metrics row + priority customer queue (see Dashboard Spec)
5. Mark as Booked flow on conversation workspace

Read the files first, then make code changes directly and summarize what changed.
```
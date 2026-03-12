# Foreman — Project Plan & Status Tracker

> Share this file at the start of a new chat so work can resume with correct context.

---

## Product Vision

**Vision:** AI Operating System for Field Service Revenue
**Product:** AI Reactivation System for HVAC & Field Service Businesses
**Tagline:** Turn your past customers into booked jobs. Automatically.

**Target customer:** HVAC, plumbing, and electrical contractors. Owner-operated teams of 3–15. Not highly technical. May be using QuickBooks, Jobber, HousecallPro — or nothing beyond a phone. HVAC is the primary beachhead.

**Positioning:** Foreman is a revenue system, not a CRM or email tool. The core value proposition: identify which past customers are most likely to need service now, reach out in the operator's voice, convert responses to booked jobs, and show exactly how much revenue it generated. Priced below Jobber/HousecallPro, dramatically above them in AI-driven proactive outreach capability.

**Core loop:** Score → Prioritize → Outreach → Classify Response → Propose Time → Convert to Job → Track Revenue

---

## Current Status

- **Active Phase:** Phase 6 — Booking Conversion Flow + Google Calendar Integration
- **State:** Phase 5 complete. Revenue dashboard, customer scoring, priority grouping, and all-customers page all live. Phase 6 begins: classify inbound replies, detect booking intent, propose calendar slots, confirm bookings.
- **Last Updated:** 2026-03-11
- **Live URL:** https://web-production-3df3a.up.railway.app
- **Repo:** https://github.com/avelayud/foreman

---

## Recently Completed

### Phase 5 — Customer Scoring + Revenue Dashboard (✅ Complete)
- `core/scoring.py`: rules-based scoring engine (Recency 40 + LTV 20 + Frequency 15 + Job Type 15 + Engagement 10)
- Customer model migration: `score`, `score_breakdown`, `priority_tier`, `estimated_job_value`, `service_interval_days`, `predicted_next_service`
- OutreachLog model migration: `response_classification`, `classified_at`, `converted_to_job`, `converted_job_value`, `converted_at`
- Scoring runs at startup + daily via APScheduler
- Revenue dashboard: 8 metric cards (dormant identified, % contacted, responses, active convos, jobs booked, revenue generated, pipeline value, avg job value)
- Dashboard rebuilt with 4 priority groups: Upcoming Jobs / Active-Requires Attention / Ripe for Reactivation / On Hold
- Each group: top 5 shown with "Show more" (max 10) and "View all →" link
- New `/customers` page: full searchable + filterable customer list (search by name/email, filter by group)
- "Mark as Booked" flow: modal on dashboard + customer page, logs job value, updates OutreachLog
- Priority Scorer added to agents page with Run Now button and live stats
- Customer Analyzer now runs on startup + daily schedule for all customers with correspondence or no profile
- Score breakdown module on individual customer pages (5 signal bars)
- Nav: Conversations above Outreach Queue; All Customers link added
- Seed data: 200 customers, 5yr HVAC history, realistic dormancy/value distributions

### Phase 4 — Gmail + Conversations (✅ Complete)
- Gmail send path, thread ID persistence, reply detection
- Customer Analyzer, Follow-up Sequencer, Reply Detector agents
- Conversation workspace: AI timeline, context-aware draft, expandable messages
- UTC timestamps + EDT/EST display

---

## Build Phases Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| 1 | Foundation (models/config/DB) | ✅ Complete | Stable |
| 2 | Tone Profiler + Dashboard UI | ✅ Complete | Stable |
| 3 | Reactivation Analyzer + Approval Queue | ✅ Complete | Stable |
| 4 | Gmail Send + Follow-up Intelligence + Conversation UX | ✅ Complete | Fully operational |
| 5 | Customer Scoring + Revenue Dashboard | ✅ Complete | Live |
| 6 | Booking Conversion Flow + Google Calendar | 🔵 Active | See checklist below |
| 7 | Outreach Composer Redesign | ⬜ Planned | See backlog |
| 8 | SMS Channel (Twilio) | ⬜ Planned | |
| 9 | Service Interval Prediction | ⬜ Planned | |
| 10 | Jobber / HousecallPro Integration | ⬜ Planned | |
| 11 | QuickBooks Data Ingestion | ⬜ Planned | |
| 12 | ML-Trained Scoring Model (sklearn) | ⬜ Planned | Needs real conversion labels |

---

## Phase 6 — Booking Conversion Flow + Google Calendar

**Goal:** When a customer replies with booking intent, Foreman automatically detects it, proposes real available calendar slots, and closes the loop. The operator's job becomes reviewing and confirming — not managing scheduling back-and-forth manually.

### Response Classifier
- [ ] `agents/response_classifier.py`: Claude classifier, 5 categories:
  - `booking_intent` — "Yes, when can you come?"
  - `callback_request` — "Call me to discuss"
  - `price_inquiry` — "How much would that cost?"
  - `not_interested` — "Please remove me"
  - `unclear` — Ambiguous, surface to operator
- [ ] Wire classifier into reply detector pipeline (auto-runs on each new inbound reply)
- [ ] Store classification on `OutreachLog.response_classification` + `classified_at`
- [ ] Conversation workspace: show classification badge + recommended next action callout

### Google Calendar Integration
- [ ] Google Calendar OAuth flow (add `calendar.readonly` scope to existing OAuth)
- [ ] `integrations/calendar.py`: read operator's free/busy blocks for next 10 business days
- [ ] Operator availability preferences: working hours, buffer time between jobs
- [ ] Store availability template on Operator model (JSON: days, hours, job_duration_minutes)

### Booking Proposal Flow
- [ ] When `booking_intent` detected: auto-draft reply proposing 3 real available slots
- [ ] Slot proposal template in operator voice: "I have Tuesday the 18th at 10am, Wednesday the 19th at 2pm, or Thursday the 20th at 9am — any of those work for you?"
- [ ] Proposal draft lands in Outreach Queue for operator review before sending
- [ ] Customer confirmation reply → Reply Detector catches it → mark slot as tentatively booked

### Booking Confirmation + Job Creation
- [ ] Confirmation detection: Reply Detector + classifier identify "confirmed" replies
- [ ] On confirmation: create `Booking` record (date, time, customer_id, job_type)
- [ ] Update Customer.reactivation_status → `booked`, OutreachLog.converted_to_job = True
- [ ] Log estimated job value from Customer.estimated_job_value
- [ ] Confirmation summary on conversation workspace: "Job booked for [date]"
- [ ] Dashboard "Upcoming Jobs" group auto-populates from Booking records

### Calendar Write-back (optional, Phase 6b)
- [ ] Add `calendar.events` write scope
- [ ] Create Google Calendar event on booking confirmation
- [ ] Event includes: customer name, address, job type, contact info

---

## Backlog / TODOs

### Customer Analyzer — Debug + Data Quality (PRIORITY)
- Customer profiles not populating even for customers with known email history
- Need to verify: does `get_correspondence()` in `integrations/gmail.py` actually return messages for real email addresses in the DB?
- Add verbose logging to `_run_customer_analyzer_job()` to surface what's happening per customer
- Check: are real customer email addresses in the seed data matching actual Gmail senders?

### Email Traffic Simulation (for Analyzer Enrichment)
- Need richer email history to make Customer Analyzer profiles meaningful
- Simulate full realistic conversations: scheduling back-and-forth, pricing questions, multiple touchpoints, objections, confirmations
- Scenarios to cover:
  - Customer asks 3 questions before agreeing to schedule
  - Customer haggles on price then books
  - Customer requests callback, then schedules via email
  - Customer says "maybe next month" then re-engages
  - Customer books but then reschedules
- Will use a set of real email addresses owned by operator for actual Gmail correspondence
- **Separate program** (outside the main app): test environment email simulator
  - Uses Gmail API on owned accounts
  - Generates diverse, realistic inbound + outbound email threads
  - Populated threads then feed the Customer Analyzer with real Gmail data
  - Design: standalone script (`tools/email_simulator.py`) — not part of the production app

### Outreach Composer Redesign (Phase 7)
- "Draft Outreach" action button → dedicated composer page, not customer detail page
- Composer: customer context panel (left) + email editor (right), one-click send or queue
- Customer page becomes read-only CRM context — no inline draft widget
- Separate flow: cold-start (first outreach) vs reply/follow-up (thread continuation)

### Other Backlog
- **Durable scheduler**: move reply_detector + follow_up to cron/Celery (survive dyno restarts)
- **Email draft quality loop**: operator feedback signal, prompt A/B testing
- **Voice profiles from Gmail**: generate profiles from actual sent mail instead of manual seed
- **Voice profile config screen**: operator fine-tunes each voice's response style
- **Multi-tenant audit**: all queries filter by operator_id — audit before second user onboards

---

## Scoring Model Spec

Rules-based weighted scorer. Interpretable and replaceable with a trained model once real conversion data exists.

| Signal | Field | Max Points | Logic |
|---|---|---|---|
| Recency | days since last job | 40 | >365 days = 40, scales linearly below |
| Lifetime value | sum of job revenue | 20 | >$2000 = 20, >$500 = 10, else 5 |
| Job frequency | count of prior jobs | 15 | jobs × 3, capped at 15 |
| Job type | maintenance vs repair | 15 | Any maintenance = 15, repair-only = 8, single job = 4 |
| Prior engagement | response to past outreach | 10 | Positive response = 10, any reply = 5, none = 0 |

Priority tiers: high ≥70, medium 40–69, low <40.

**Phase 12 ML upgrade:** Once 3–6 months of real conversion outcomes exist, retrain using `converted_to_job` as label with sklearn RandomForest.

---

## Response Classification Spec

| Classification | Trigger Example | Next Action |
|---|---|---|
| `booking_intent` | "Yes, when can you come?" | Propose 3 calendar slots |
| `callback_request` | "Call me to discuss" | Flag for operator, show phone number |
| `price_inquiry` | "How much would that cost?" | Draft pricing response |
| `not_interested` | "Please remove me" | Unsubscribe, suppress all future outreach |
| `unclear` | Ambiguous reply | Surface to operator with full context |

---

## Known Risks / Watch-outs

- `reply_detector` + `follow_up` run as background threads (15-min poll); not backed by a durable scheduler — will miss cycles on dyno restart. Acceptable for now.
- Single-tenant: `OPERATOR_ID = 1` hardcoded throughout. Must audit before onboarding second operator.
- Customer Analyzer only finds Gmail threads where the email address matches exactly — synthetic seed data emails won't match real Gmail history.

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
| 2026-03-11 | Draft context | Follow-up drafts include full thread; reply drafts include job history + domain knowledge |
| 2026-03-11 | Product pivot | Repositioned as revenue system (not email assistant); scoring + revenue dashboard as Phase 5 |
| 2026-03-11 | Scoring approach | Rules-based weighted scorer first; ML model deferred to Phase 12 |
| 2026-03-11 | Phase 6 scope | Merged response classifier + booking conversion + Google Calendar into single phase |
| 2026-03-11 | Email simulation | Separate tool (`tools/email_simulator.py`) using real owned Gmail addresses — not part of production app |
| 2026-03-11 | Outreach composer | Deferred to Phase 7; "Draft Outreach" → dedicated composer page, not customer detail page |

---

## New Chat Resume Prompt

```text
I'm continuing work on Foreman — an AI reactivation system for HVAC & field service contractors.

Please read PROJECT_PLAN.md and README.md first to get full context.

Current state: Phases 1–5 complete. Now in Phase 6: Booking Conversion Flow + Google Calendar Integration.

Phase 6 priorities in order:
1. Response Classifier agent (classify inbound replies: booking_intent / callback_request / price_inquiry / not_interested / unclear)
2. Wire classifier into reply detector — auto-runs on each new inbound reply
3. Google Calendar OAuth (add calendar.readonly scope) + integrations/calendar.py
4. Booking proposal flow — when booking_intent detected, auto-draft reply with 3 real available slots
5. Booking confirmation detection + Booking record creation

Read the files first, then make code changes directly and summarize what changed.
```

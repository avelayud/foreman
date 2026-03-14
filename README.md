# Foreman

**AI Reactivation System for HVAC & Field Service Businesses**

> Turn your past customers into booked jobs. Automatically.

Foreman identifies dormant customers, scores them by rebooking probability, reaches out in the operator's voice, classifies responses, proposes real calendar slots, and tracks the revenue it generates — all without the operator managing a CRM.

**Live:** https://web-production-3df3a.up.railway.app
**Repo:** https://github.com/avelayud/foreman

---

## What It Does

1. Learns operator voice from sent Gmail (Tone Profiler)
2. Scores every past customer 0–100 by rebooking probability (Scoring Engine)
3. Finds dormant customers and drafts personalized outreach in the operator's voice (Reactivation Analyzer)
4. Builds customer context from Gmail correspondence and OutreachLog history (Customer Analyzer — runs daily)
5. Tracks replies by Gmail thread; feeds context-aware follow-up drafts (Reply Detector + Follow-up Sequencer)
6. Classifies inbound responses into 7 categories: booking intent → propose slots, not interested → answer their question conversationally, unsubscribe → suppress
7. Reads Google Calendar to propose real available slots; detects confirmation replies and creates bookings automatically
8. Tracks booked jobs and revenue attributed to Foreman outreach
9. Analytics page: customer base composition, outreach funnel, revenue ROI
10. Product analytics: internal event tracking, draft quality metrics, operator behavior

**Target customer:** HVAC, plumbing, and electrical contractors. Owner-operated teams of 3–15. Not highly technical. HVAC is the primary beachhead.

---

## Product State (2026-03-14)

> **Phases 1–7 + 6b complete. Jobs 11–23 complete.** Full booking flow live end-to-end: reply detected → classified → draft generated → operator approves → calendar invite sent → customer accepts → booking confirmed + GCal event created. Meeting approval gate, invite_sent status, accept/decline handling, appointment module on conversation page, draft revision notes, post-visit outcome tracking. Active: Phase 8 (Operator Config + Agent Quality).

## Feature Status

| Area | Status |
|---|---|
| Core models + DB (Operator, Customer, Job, Booking, OutreachLog) | ✅ |
| Tone Profiler agent | ✅ |
| Reactivation Analyzer agent | ✅ |
| Customer Analyzer agent (DB-first, Gmail fallback, --force flag) | ✅ |
| Reply Detector agent (background, 15-min poll) | ✅ |
| Follow-up Sequencer agent | ✅ |
| Priority Scorer agent (scheduled daily) | ✅ |
| Response Classifier agent (7 categories) | ✅ |
| Dry Run / Production mode toggle | ✅ |
| Outreach queue: Needs Approval + Send Pending sections | ✅ |
| Meetings Queue (booking proposals) | ✅ |
| One-click dashboard actions (Draft Outreach / Book Call / Draft Follow-up) | ✅ |
| Scheduled sender worker + smart queue refresh | ✅ |
| Revenue dashboard: 8 metric cards + 4 priority groups | ✅ |
| All Customers page (search by name/email, filter by group) | ✅ |
| Customer scoring engine (0–100, rules-based, 5 signals) | ✅ |
| Mark as Booked flow (modal, logs job value, tracks revenue) | ✅ |
| Active Conversations page (health state, attention badge, search) | ✅ |
| Conversation workspace (AI timeline, context-aware draft) | ✅ |
| Score breakdown on customer detail page | ✅ |
| Agents page with status + Run Now buttons for all agents | ✅ |
| Google Calendar OAuth + availability reading | ✅ |
| Booking proposal flow (booking_intent → auto-draft → Meetings Queue) | ✅ |
| Calendar view (agenda-style, color-coded by service type) | ✅ |
| Email thread continuity (In-Reply-To + References RFC headers) | ✅ |
| Dual-pass reply detection (thread scan + inbox address scan fallback) | ✅ |
| Updates inbox (`/updates`) — needs response, overdue follow-ups, recent replies, post-visit | ✅ |
| Per-page analytics in Internal Metrics | ✅ |
| Server-side action event tracking | ✅ |
| `unsubscribe_request` classifier category | ✅ |
| `NOT_INTERESTED_PROMPT` — conversational reply for declined-but-engaged customers | ✅ |
| Active Conversation banner on customer detail page | ✅ |
| Customer Analytics page (`/analytics`) — funnel, ROI, composition | ✅ |
| Product Analytics instrumentation + internal dashboard | ✅ |
| Error tracking log (all 500s captured, visible in Internal Metrics) | ✅ |
| Customer Analyzer DB-first (OutreachLog primary, Gmail fallback) | ✅ |
| Booking confirmation auto-detection (booking_confirmed → Booking + GCal event) | ✅ |
| Meeting approval gate — booking proposals queue for review before sending | ✅ |
| Calendar invite accept/decline handling (accept confirms booking, decline re-queues redraft) | ✅ |
| `invite_sent` conversation status — distinct state after calendar invite is sent | ✅ |
| Appointment confirmed module — schedule panel on conversation page when booking active | ✅ |
| Meetings Queue scoped to calendar invites only (booking_confirmed) | ✅ |
| Draft revision notes — operator influence box on all queue pages + conversation page | ✅ |
| Post-Visit Agent — daily, flags appointments needing outcome logged | ✅ |
| Post-visit outcome tracking — Quote Given, Job Won, No Show, conversation lock | ✅ |
| Nav badge live refresh after send/approve actions | ✅ |
| Operator Config page (`/settings`) — tone, salesy, job ranking, estimate ranges | ⬜ Phase 8 (Job 05) |
| Prompt Quality Sprint — HVAC-native agent voices using config values | ⬜ Phase 8 (Job 06) |
| SMS channel (Twilio) — send path + inbound webhook | ⬜ Phase 9 (Job 07) |
| SMS draft pipeline + UX (channel selector, timeline badges) | ⬜ Phase 9 (Job 08) |
| Jobber / HousecallPro integration | ⬜ Phase 10 |
| Service interval prediction | ⬜ Phase 11 |
| Outreach composer redesign | ⬜ Phase 12 |
| ML-trained scoring model (sklearn) | ⬜ Phase 13 |

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Web | FastAPI + Jinja2 |
| DB | SQLAlchemy + PostgreSQL (Railway) / SQLite (local) |
| AI | Anthropic Claude (`claude-sonnet-4-6`) |
| Email | Gmail API (OAuth2) |
| SMS | Twilio (Phase 9) |
| Calendar | Google Calendar API (OAuth2) |
| Deployment | Railway |

---

## Plans System

Feature work is tracked in `plans/` — one folder per job, each containing a `plan.md` and `tasks/` with individual task files. Plans are authored in Claude app and executed in Claude Code. Completed job folders are removed; context lives in `PROJECT_PLAN.md`.

```
plans/
├── README.md
├── job_05_operator_config_page/   # 🔵 Active — Phase 8
├── job_06_prompt_quality/         # ⬜ Phase 8 (depends on Job 05)
├── job_07_sms_send_path/          # ⬜ Phase 9
├── job_08_sms_ux/                 # ⬜ Phase 9 (depends on Job 07)
├── job_09_revenue_data_integrity/ # ⬜ Phase 8 (parallel to Jobs 05/06)
├── job_10_jobber_integration/     # ⬜ Phase 10
└── archive/                       # ✅ Completed jobs 11–23
```

---

## Project Structure

```
foreman/
├── api/
│   ├── app.py                    # FastAPI app (pages + JSON API)
│   └── run.py                    # Railway-safe launcher (reads PORT)
├── agents/
│   ├── tone_profiler.py
│   ├── reactivation.py
│   ├── customer_analyzer.py      # DB-first profile builder (daily)
│   ├── reply_detector.py
│   ├── response_classifier.py
│   ├── response_generator.py
│   ├── conversation_agent.py
│   ├── follow_up.py
│   └── post_visit.py             # Daily — flags past appointments needing outcome
├── core/
│   ├── config.py
│   ├── database.py               # SCHEMA_PATCHES, get_db(), init_db()
│   ├── models.py
│   ├── scoring.py
│   ├── operator_config.py        # Phase 8 — config getter/setter + agent context helper
│   ├── analytics.py
│   └── product_analytics.py
├── integrations/
│   ├── gmail.py
│   ├── calendar.py
│   └── sms.py                    # Phase 9 — Twilio send + inbound
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── customers.html
│   ├── customer.html
│   ├── conversations.html
│   ├── conversation_detail.html
│   ├── outreach.html
│   ├── meetings.html
│   ├── calendar.html
│   ├── agents.html
│   ├── analytics.html
│   ├── updates.html
│   ├── settings.html             # Phase 8 — operator config UI
│   └── internal_product.html
├── data/
│   ├── README.md
│   ├── reseed.py
│   └── archive/
├── tools/
│   └── email_simulator.py
├── plans/
├── Procfile
└── requirements.txt
```

---

## Key Pages

| URL | Description |
|---|---|
| `/` | Dashboard: revenue metrics, 4 priority groups, one-click Draft/Book/Follow-up actions |
| `/customers` | All customers: search by name/email, filter by group |
| `/customer/{id}` | Customer detail: account context, score breakdown, full history |
| `/conversations` | Active conversations: search, health state, attention indicators |
| `/conversations/{id}` | Conversation workspace: AI timeline, draft panel, recap |
| `/outreach` | Outreach queue: Needs Approval + Send Pending, search, regenerate |
| `/meetings` | Meetings queue: booking proposals, proposed slots panel, search |
| `/calendar` | Calendar view: agenda by month, color-coded by service type |
| `/agents` | Agent catalog: status, last run, Run Now buttons for all agents |
| `/analytics` | Analytics: customer base composition, outreach funnel, revenue ROI |
| `/updates` | Operator inbox: needs response, overdue follow-ups, recent replies, upcoming follow-ups |
| `/settings` | Operator config: tone, salesy, job priority, estimate ranges, business context *(Phase 8)* |
| `/internal/product` | Internal metrics: page views, draft behavior, per-page analytics, error log |

---

## Dashboard Priority Groups

| Group | Who | Primary Action |
|---|---|---|
| 📅 Upcoming Jobs | `booked` | Confirm details, prepare for service |
| 🔥 Active — Requires Attention | `replied`, `outreach_sent`, in-sequence | Book Call or Draft Follow-up |
| 🎯 Ripe for Reactivation | `never_contacted`, ranked by score | Draft Outreach |
| ⏸ On Hold / Declined | `sequence_complete`, `unsubscribed` | Monitor |

---

## Customer Scoring Model

| Signal | Max Points | Logic |
|---|---|---|
| Recency | 40 | Days since last job; >365 days = full 40, scales linearly below |
| Lifetime value | 20 | >$2000 = 20, >$500 = 10, else 5 |
| Job frequency | 15 | Count of jobs × 3, capped at 15 |
| Job type | 15 | Any maintenance job = 15, repair-only = 8, single job = 4 |
| Prior engagement | 10 | Prior positive response = 10, any reply = 5, none = 0 |

Priority tiers: **high** ≥70 · **medium** 40–69 · **low** <40.

---

## Response Classification

| Classification | Example | Next Action |
|---|---|---|
| `booking_intent` | "Yes, when can you come?" | Propose 3 real calendar slots |
| `booking_confirmed` | "Tuesday at 10am works for me" | Create Booking record + GCal event |
| `callback_request` | "Call me to discuss" | Flag for operator, surface phone number |
| `price_inquiry` | "How much would that cost?" | Draft pricing response |
| `not_interested` | "Not right now, but what does a tune-up include?" | Draft conversational reply |
| `unsubscribe_request` | "Please remove me from your list" | Mark unsubscribed, suppress all future outreach |
| `unclear` | Ambiguous reply | Surface to operator with full context |

---

## Local Setup

```bash
git clone https://github.com/avelayud/foreman
cd foreman

python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, DATABASE_URL

# Seed: 200 customers, rich HVAC histories + simulated conversations
DATABASE_URL=sqlite:///./foreman.db venv/bin/python -m data.reseed

# Run
DATABASE_URL=sqlite:///./foreman.db venv/bin/python -m api.run
# → http://localhost:8000
```

---

## Environment Variables

```bash
ANTHROPIC_API_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
DATABASE_URL
APP_ENV
APP_PORT
DRY_RUN
TWILIO_ACCOUNT_SID        # Phase 9
TWILIO_AUTH_TOKEN         # Phase 9
TWILIO_FROM_NUMBER        # Phase 9 — E.164 format
PYTHONUNBUFFERED=1        # required on Railway
```

---

## Railway

- `Procfile`: `web: python -m api.run`
- DB URL normalization handles `postgres://` → `postgresql://` automatically
- Startup retries handle transient DB boot races
- To connect to Postgres from local: `railway login` → `railway link` → `railway connect Postgres`

---

## Security

Rotate immediately if any of these are exposed:
- Anthropic API key
- Google OAuth client secret
- Railway Postgres credentials
- Twilio Auth Token (Phase 9)

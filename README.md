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
4. Builds customer context from Gmail correspondence (Customer Analyzer — runs daily)
5. Tracks replies by Gmail thread; feeds context-aware follow-up drafts (Reply Detector + Follow-up Sequencer)
6. Classifies inbound responses: booking intent → propose calendar slots, not interested → suppress
7. Reads Google Calendar to propose real available slots; detects confirmation replies and creates bookings automatically *(Phase 6b)*
8. Tracks booked jobs and revenue attributed to Foreman outreach
9. Analytics page: customer base composition, outreach funnel, revenue ROI *(Phase 7)*
10. Product analytics: internal event tracking, draft quality metrics, operator behavior *(Phase 7)*

**Target customer:** HVAC, plumbing, and electrical contractors. Owner-operated teams of 3–15. Not highly technical. HVAC is the primary beachhead.

---

## Product State (2026-03-12)

> **Open bugs:** stale customer profiles after reseed. See `PROJECT_PLAN.md` backlog for details.
> **Recently completed:** Analytics Dashboard (`/analytics`), Internal Metrics Dashboard (`/internal/product`), error tracking log (all 500s captured to DB), Schedule Appointment panel on conversation page, post-booking notes & revenue capture, email body line-break normalization fix, conversation page redesign (lazy timeline summaries), nav reorganization.

## Feature Status

| Area | Status |
|---|---|
| Core models + DB (Operator, Customer, Job, Booking, OutreachLog) | ✅ |
| Tone Profiler agent | ✅ |
| Reactivation Analyzer agent | ✅ |
| Customer Analyzer agent (scheduled daily) | ✅ |
| Reply Detector agent (background, 15-min poll) | ✅ |
| Follow-up Sequencer agent | ✅ |
| Priority Scorer agent (scheduled daily) | ✅ |
| Response Classifier agent (booking_intent / not_interested / etc.) | ✅ |
| Dry Run / Production mode toggle | ✅ |
| Outreach queue: Needs Approval + Send Pending sections | ✅ |
| Meetings Queue (booking proposals, separate from outreach) | ✅ |
| One-click dashboard actions (Draft Outreach / Book Call / Draft Follow-up) | ✅ |
| Scheduled sender worker + smart queue refresh (background, every 15 min) | ✅ |
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
| Email thread continuity (In-Reply-To + References RFC headers) | ✅ Fixed — In-Reply-To uses customer's own reply RFC Message-ID |
| Dual-pass reply detection (thread scan + inbox address scan fallback) | ✅ |
| Active Conversation banner on customer detail page | ✅ |
| Run Now buttons synchronous with auto-reload + last-run tracking | ✅ |
| Follow-up Sequencer added to daily APScheduler | ✅ |
| Plans scaffold (`plans/` — plan.md + tasks/ per job) | ✅ |
| Internal dev tools page (reseed DB, run all agents) | ✅ |
| Railway deploy with Postgres | ✅ |
| UTC timestamp storage + EDT/EST display | ✅ |
| Schedule Appointment panel on conversation page | ✅ |
| Post-booking notes + revenue capture on conversation page | ✅ |
| Email body line-break normalization (outbound Gmail) | ✅ Fixed |
| Customer Analytics page (`/analytics`) — funnel, ROI, composition | ✅ Phase 7 (Job 03) |
| Product Analytics instrumentation + internal dashboard | ✅ Phase 7 (Job 04) |
| Error tracking log (all 500s captured, visible in Internal Metrics) | ✅ |
| Lazy timeline summaries (conversation page loads without Claude block) | ✅ |
| **BUG: Stale customer profiles after reseed** | 🔴 Open |
| Booking confirmation detection + job record creation | ⬜ Phase 6b (Job 02) |
| Calendar write-back (create Google Calendar event on booking) | ⬜ Phase 6b (Job 02) |
| Outreach composer redesign (dedicated page, not customer detail) | ⬜ Phase 8 |
| SMS channel (Twilio) | ⬜ Phase 9 |
| Service interval prediction | ⬜ Phase 10 |
| Jobber / HousecallPro integration | ⬜ Phase 11 |
| ML-trained scoring model (sklearn) | ⬜ Phase 12 |

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Web | FastAPI + Jinja2 |
| DB | SQLAlchemy + PostgreSQL (Railway) / SQLite (local) |
| AI | Anthropic Claude (`claude-sonnet-4-6`) |
| Email | Gmail API (OAuth2) |
| Calendar | Google Calendar API (OAuth2) — Phase 6 |
| Deployment | Railway |

---

## Plans System

Feature work is tracked in `plans/` — one folder per job, each containing a `plan.md` and `tasks/` with individual task files. Plans are authored in Claude app and executed in Claude Code.

```
plans/
├── README.md                     # How to use the system
├── job_01_customer_analyzer/     # 🔵 Active
├── job_02_booking_confirmation/  # ⬜ Backlog (Phase 6b)
├── job_03_customer_analytics/    # ✅ Complete
└── job_04_product_analytics/     # ✅ Complete
```

**Execution order:** Job 01 → Job 04 → Job 03 (Job 02 is independent).

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
│   ├── customer_analyzer.py      # Builds profiles from Gmail history (daily)
│   ├── reply_detector.py
│   ├── follow_up.py
│   └── response_classifier.py   # Phase 6 — classify inbound replies
├── core/
│   ├── config.py
│   ├── database.py               # SCHEMA_PATCHES, get_db(), init_db()
│   ├── models.py
│   ├── scoring.py                # Rules-based 0–100 scorer, APScheduler job
│   ├── analytics.py              # Server-side aggregations for /analytics
│   └── product_analytics.py     # ProductEvent logging, session tracking
├── integrations/
│   ├── gmail.py                  # Send, read threads, search correspondence
│   └── calendar.py               # Phase 6 — Google Calendar read/write
├── templates/
│   ├── base.html
│   ├── dashboard.html            # Revenue metrics + 4 priority groups + one-click actions
│   ├── customers.html            # Full searchable customer list
│   ├── customer.html             # Customer detail + score breakdown
│   ├── conversations.html        # Active threads with search
│   ├── conversation_detail.html  # Workspace: draft + schedule + timeline
│   ├── outreach.html             # Needs Approval + Send Pending sections
│   ├── meetings.html             # Booking proposals queue
│   ├── calendar.html             # Agenda view, color-coded by service type
│   ├── agents.html               # All agents with Run Now buttons
│   ├── analytics.html            # Customer analytics: funnel, ROI, composition
│   └── internal_product.html     # Internal metrics: events, drafts, error log
├── data/
│   ├── README.md                 # Reseed docs: how to run, add emails, add scenarios
│   ├── reseed.py                 # Full wipe + reseed: 200 customers, rich conversations
│   ├── fix_inbound_timestamps.py # One-time UTC migration (2026-03-11)
│   └── archive/
│       └── seed_v1_legacy.py     # Original 40-customer seed (superseded)
├── tools/
│   └── email_simulator.py        # Planned — standalone Gmail conversation simulator
├── plans/                        # Feature work: plan.md + tasks/ per job
│   ├── README.md
│   ├── job_01_customer_analyzer/
│   ├── job_02_booking_confirmation/
│   ├── job_03_customer_analytics/
│   └── job_04_product_analytics/
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
| `/internal/product` | Internal metrics: page views, draft behavior, error log |

---

## Dashboard Priority Groups

The dashboard organizes customers into four actionable sections, each showing top 5 with expand-to-10:

| Group | Who | Primary Action |
|---|---|---|
| 📅 Upcoming Jobs | `booked` | Confirm details, prepare for service |
| 🔥 Active — Requires Attention | `replied`, `outreach_sent`, in-sequence | Book Call or Draft Follow-up |
| 🎯 Ripe for Reactivation | `never_contacted`, ranked by score | Draft Outreach |
| ⏸ On Hold / Declined | `sequence_complete`, `unsubscribed` | Monitor |

---

## Customer Scoring Model

Every customer receives a score 0–100 based on weighted signals:

| Signal | Max Points | Logic |
|---|---|---|
| Recency | 40 | Days since last job; >365 days = full 40, scales linearly below |
| Lifetime value | 20 | >$2000 = 20, >$500 = 10, else 5 |
| Job frequency | 15 | Count of jobs × 3, capped at 15 |
| Job type | 15 | Any maintenance job = 15, repair-only = 8, single job = 4 |
| Prior engagement | 10 | Prior positive response = 10, any reply = 5, none = 0 |

Priority tiers: **high** ≥70 · **medium** 40–69 · **low** <40. Score breakdown stored per customer and visible on their detail page.

---

## Response Classification (Phase 6)

When a reply is detected, a Claude agent classifies it and routes to the next action:

| Classification | Example | Next Action |
|---|---|---|
| `booking_intent` | "Yes, when can you come?" | Propose 3 real calendar slots |
| `callback_request` | "Call me to discuss" | Flag for operator, surface phone number |
| `price_inquiry` | "How much would that cost?" | Draft pricing response |
| `not_interested` | "Please remove me" | Unsubscribe, suppress all future outreach |
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

See **[data/README.md](data/README.md)** for full reseed documentation: Railway connection, adding live email addresses, adding scenario types, and augmenting bulk profiles.

---

## Environment Variables

```bash
ANTHROPIC_API_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
DATABASE_URL          # sqlite:///./foreman.db locally; internal Railway URL in prod
APP_ENV
APP_PORT
DRY_RUN
PYTHONUNBUFFERED=1    # required on Railway
```

---

## Railway

- `Procfile`: `web: python -m api.run`
- DB URL normalization handles `postgres://` → `postgresql://` automatically
- Startup retries handle transient DB boot races
- To connect to Postgres from local: `railway login` → `railway link` → `railway connect Postgres`
- Public networking must be enabled on the Postgres service for external psql access

---

## Security

Rotate immediately if any of these are exposed in logs or chat:
- Anthropic API key
- Google OAuth client secret
- Railway Postgres credentials (Postgres service → Settings → Regenerate)

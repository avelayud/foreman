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
6. Classifies inbound responses: booking intent → propose calendar slots, not interested → suppress *(Phase 6)*
7. Reads Google Calendar to propose real available slots and confirm bookings *(Phase 6)*
8. Tracks booked jobs and revenue attributed to Foreman outreach

**Target customer:** HVAC, plumbing, and electrical contractors. Owner-operated teams of 3–15. Not highly technical. HVAC is the primary beachhead.

---

## Product State (2026-03-11)

| Area | Status |
|---|---|
| Core models + DB (Operator, Customer, Job, Booking, OutreachLog) | ✅ |
| Tone Profiler agent | ✅ |
| Reactivation Analyzer agent | ✅ |
| Customer Analyzer agent (scheduled daily) | ✅ |
| Reply Detector agent (background, 15-min poll) | ✅ |
| Follow-up Sequencer agent | ✅ |
| Priority Scorer agent (scheduled daily) | ✅ |
| Dry Run / Production mode toggle | ✅ |
| Outreach queue (approve + schedule + send-now) | ✅ |
| Scheduled sender worker | ✅ |
| Revenue dashboard: 8 metric cards + 4 priority groups | ✅ |
| All Customers page (search + filter by group) | ✅ |
| Customer scoring engine (0–100, rules-based, 5 signals) | ✅ |
| Mark as Booked flow (modal, logs job value, tracks revenue) | ✅ |
| Active Conversations page (health state, attention badge) | ✅ |
| Conversation workspace (AI timeline, context-aware draft) | ✅ |
| Score breakdown on customer detail page | ✅ |
| Agents page with status + manual run | ✅ |
| Railway deploy with Postgres | ✅ |
| UTC timestamp storage + EDT/EST display | ✅ |
| Response classifier agent (booking_intent / not_interested / etc.) | 🔵 Phase 6 |
| Google Calendar OAuth + availability reading | 🔵 Phase 6 |
| Booking proposal flow (auto-draft slot proposals) | 🔵 Phase 6 |
| Booking confirmation + job creation | 🔵 Phase 6 |
| Outreach composer redesign (dedicated page, not customer detail) | ⬜ Phase 7 |
| SMS channel (Twilio) | ⬜ Phase 8 |
| Service interval prediction | ⬜ Phase 9 |
| Jobber / HousecallPro integration | ⬜ Phase 10 |
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
│   └── scoring.py                # Rules-based 0–100 scorer, APScheduler job
├── integrations/
│   ├── gmail.py                  # Send, read threads, search correspondence
│   └── calendar.py               # Phase 6 — Google Calendar read/write
├── templates/
│   ├── base.html
│   ├── dashboard.html            # Revenue metrics + 4 priority groups
│   ├── customers.html            # Full searchable customer list
│   ├── customer.html             # Customer detail + score breakdown
│   ├── conversations.html
│   ├── conversation_detail.html
│   ├── outreach.html
│   └── agents.html
├── data/
│   ├── seed.py                   # 200 customers, 5yr HVAC history
│   └── reseed.py                 # Full wipe + reseed (prod-safe)
├── tools/
│   └── email_simulator.py        # Planned — standalone Gmail conversation simulator
├── Procfile
└── requirements.txt
```

---

## Key Pages

| URL | Description |
|---|---|
| `/` | Dashboard: revenue metrics, 4 priority groups (Upcoming / Active / Ripe / On Hold) |
| `/customers` | All customers: search by name/email, filter by group |
| `/customer/{id}` | Customer detail: account context, score breakdown, full history |
| `/conversations` | Active conversations with health state and attention indicators |
| `/conversations/{id}` | Conversation workspace: AI timeline, draft panel, recap |
| `/outreach` | Outreach queue: review/edit/approve/schedule/send |
| `/agents` | Agent catalog: status, last run, manual trigger |

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

# Seed realistic HVAC data (200 customers, 5yr history)
venv/bin/python -m data.reseed

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

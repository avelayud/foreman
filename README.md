# Foreman

**AI Reactivation System for HVAC & Field Service Businesses**

> Turn your past customers into booked jobs. Automatically.

Foreman identifies dormant customers, scores them by rebooking probability, reaches out in the operator's voice, classifies responses, and tracks the revenue it generates — all without the operator managing a CRM.

**Live:** https://web-production-3df3a.up.railway.app
**Repo:** https://github.com/avelayud/foreman

---

## What It Does

1. Learns operator voice from sent Gmail (Tone Profiler)
2. Scores every past customer 0–100 by rebooking probability (Customer Scoring Engine)
3. Finds dormant customers and drafts personalized outreach in the operator's voice (Reactivation Analyzer)
4. Builds customer context from Gmail correspondence (Customer Analyzer)
5. Tracks replies by Gmail thread and feeds context-aware follow-up drafts (Reply Detector + Follow-up Sequencer)
6. Classifies inbound responses and routes them: booking intent → propose times, callback → flag, not interested → suppress
7. Tracks booked jobs and revenue attributed to Foreman outreach
8. Keeps the operator in control: review drafts, approve/schedule/send, manage conversations

**Target customer:** HVAC, plumbing, and electrical contractors. Owner-operated teams of 3–15. Not highly technical. May be using QuickBooks, Jobber, or HousecallPro — or nothing beyond a phone. HVAC is the primary beachhead.

---

## Product State (2026-03-11)

| Area | Status |
|---|---|
| Core models + DB (Operator, Customer, Job, Booking, OutreachLog) | ✅ |
| Tone Profiler agent | ✅ |
| Reactivation Analyzer agent | ✅ |
| Customer Analyzer agent | ✅ |
| Reply Detector agent (background, 15-min poll) | ✅ |
| Follow-up Sequencer agent | ✅ |
| Dry Run / Production mode toggle | ✅ |
| Outreach queue (approve + schedule + send-now) | ✅ |
| Scheduled sender worker | ✅ |
| Dashboard with segments, top prospects, browse-all + search | ✅ |
| Active Conversations page (health state, attention badge) | ✅ |
| Conversation workspace (AI timeline, context-aware draft, expandable messages) | ✅ |
| Agents page with status + manual run | ✅ |
| Railway deploy with Postgres | ✅ |
| UTC timestamp storage + EDT/EST display | ✅ |
| Customer scoring engine (0–100, rules-based) | ⬜ Phase 5 |
| Revenue dashboard (booked jobs, revenue generated, potential pipeline) | ⬜ Phase 5 |
| Response classifier agent | ⬜ Phase 6 |
| Booking conversion flow (mark as booked, log job value) | ⬜ Phase 6 |
| Google Calendar integration | ⬜ Phase 7 |
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
| AI | Anthropic Claude (`claude-sonnet-4-20250514`) |
| Email | Gmail API (OAuth2) |
| Deployment | Railway |

---

## Project Structure

```
foreman/
├── api/
│   ├── app.py                   # FastAPI app (pages + JSON API)
│   └── run.py                   # Railway-safe launcher (reads PORT)
├── agents/
│   ├── tone_profiler.py
│   ├── reactivation.py
│   ├── customer_analyzer.py
│   ├── reply_detector.py
│   ├── follow_up.py
│   └── response_classifier.py  # Phase 6
├── core/
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   └── scoring.py               # Phase 5
├── integrations/
│   └── gmail.py
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── customer.html
│   ├── conversations.html
│   ├── conversation_detail.html
│   ├── outreach.html
│   └── agents.html
├── data/
│   ├── seed.py
│   ├── reseed.py
│   └── fix_inbound_timestamps.py
├── Procfile
└── requirements.txt
```

---

## Key Pages

| URL | Description |
|---|---|
| `/` | Dashboard: revenue metrics row, priority customer queue, pipeline segments |
| `/customer/{id}` | Customer detail: account context, score breakdown, full history |
| `/conversations` | Active conversations with health state and attention indicators |
| `/conversations/{id}` | Conversation workspace: AI timeline, draft panel, recap |
| `/outreach` | Outreach queue: review/edit/approve/schedule/send |
| `/agents` | Agent catalog with status and manual run |

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

Score breakdown stored per customer so operators see exactly why someone is ranked where they are. Rules-based v1 is designed to be replaced by a trained sklearn model once real conversion outcome data accumulates.

---

## Response Classification

When a reply is detected, a Claude agent classifies it and routes to the next action:

| Classification | Trigger Example | Next Action |
|---|---|---|
| `booking_intent` | "Yes, when can you come?" | Propose calendar slots |
| `callback_request` | "Call me to discuss" | Flag for operator follow-up |
| `price_inquiry` | "How much would that cost?" | Draft pricing response |
| `not_interested` | "Please remove me" | Suppress all future outreach, log reason |
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
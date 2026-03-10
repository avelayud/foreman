# Foreman

AI-powered customer reengagement and scheduling workflow for small field service businesses (HVAC, plumbing, electrical, etc.).

**Live:** https://web-production-3df3a.up.railway.app  
**Repo:** https://github.com/avelayud/foreman

---

## What It Does

Foreman helps an operator run outbound reactivation with agent support:

1. Learns operator voice from sent Gmail (Tone Profiler)
2. Finds dormant customers and drafts personalized outreach (Reactivation Analyzer)
3. Builds customer context from correspondence (Customer Analyzer)
4. Tracks replies by Gmail thread and feeds follow-up logic (Reply Detector + Follow-up Sequencer)
5. Keeps the operator in control through approval, scheduling, and send actions

---

## Current Product State (as of 2026-03-10)

| Area | Status |
|---|---|
| Core models + DB (Operator, Customer, Job, Booking, OutreachLog) | ✅ |
| Tone Profiler agent (Gmail + Claude voice extraction) | ✅ |
| Reactivation Analyzer agent (dormant customer targeting + draft queueing) | ✅ |
| Customer Analyzer agent (relationship profile fields on customer) | ✅ |
| Reply Detector agent (thread-based reply capture) | ✅ |
| Follow-up Sequencer agent (context-aware follow-up drafts) | ✅ (manual run) |
| Dry Run / Production mode toggle in-app | ✅ |
| Outreach queue with approve + schedule + send-now flow | ✅ |
| Scheduled sender worker (sends due scheduled items in production mode) | ✅ |
| Active Conversations page (operator-friendly cards + health state) | ✅ |
| Individual Conversation page (operator recap + message timeline + selected message view) | ✅ |
| Agents page with status cards and CLI commands | ✅ |
| Railway deploy with Postgres | ✅ |
| Railway startup hardening (DB URL normalization, startup retries, robust port launcher) | ✅ |

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Web | FastAPI + Jinja2 |
| DB | SQLAlchemy + PostgreSQL (Railway) / SQLite (local) |
| AI | Anthropic Claude (`claude-sonnet-4-20250514`) |
| Email integration | Gmail API (OAuth2) |
| Scheduling | APScheduler + internal background polling worker |
| Deployment | Railway |

---

## Project Structure

```text
foreman/
├── api/
│   ├── app.py                 # FastAPI app (pages + JSON API)
│   └── run.py                 # Railway-safe launcher (reads PORT)
├── agents/
│   ├── tone_profiler.py
│   ├── reactivation.py
│   ├── customer_analyzer.py
│   ├── reply_detector.py
│   └── follow_up.py
├── core/
│   ├── config.py              # Env parsing / settings
│   ├── database.py            # Engine/session/init + schema patches
│   └── models.py              # ORM models
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
│   └── reseed.py
├── Procfile
├── requirements.txt
└── PROJECT_PLAN.md
```

---

## Key Pages

| URL | Description |
|---|---|
| `/` | Dashboard: pipeline metrics, segments, top prospects |
| `/customer/{id}` | Customer detail: account context + account timeline |
| `/conversations` | Active conversations with latest interaction + queue context |
| `/conversations/{id}` | Conversation workspace: recap, talking points, message timeline, selected email |
| `/outreach` | Outreach queue: review/edit drafts, approve/schedule, send now |
| `/agents` | Agent catalog with status/coverage and manual run cues |

---

## Local Setup

```bash
git clone https://github.com/avelayud/foreman
cd foreman

python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env
# Fill in at minimum:
# - ANTHROPIC_API_KEY
# - GOOGLE_CLIENT_ID
# - GOOGLE_CLIENT_SECRET
# - DATABASE_URL

# Seed data (optional)
venv/bin/python -m data.reseed

# Run app (same entrypoint shape used on Railway)
venv/bin/python -m api.run
# Opens on http://localhost:8000 by default
```

Alternative dev command:

```bash
venv/bin/uvicorn api.app:app --reload
```

---

## Important Environment Variables

```bash
ANTHROPIC_API_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI

DATABASE_URL
# Local machine: use sqlite or Railway public proxy URL
# Railway runtime: use Railway internal URL (postgres.railway.internal)

APP_ENV
APP_PORT
DRY_RUN

SENDGRID_API_KEY
SENDGRID_FROM_EMAIL
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_FROM_NUMBER
```

---

## Railway Notes

- `Procfile` uses `web: python -m api.run`
- `api/run.py` reads `PORT` safely from env and starts uvicorn
- Startup includes DB init retries to avoid transient boot race conditions
- DB URL normalization handles legacy `postgres://` inputs

Recommended Railway Web service vars:

```bash
DATABASE_URL=<internal Railway Postgres URL>
ANTHROPIC_API_KEY=<value>
GOOGLE_CLIENT_ID=<value>
GOOGLE_CLIENT_SECRET=<value>
```

---

## Security Note

If secrets are ever pasted in logs/chat or committed by accident, rotate them immediately:

- Anthropic API key
- Google OAuth client secret
- Postgres password/connection credentials

---

## Roadmap Snapshot

| Phase | Name | Status |
|---|---|---|
| 1 | Foundation | ✅ Complete |
| 2 | Tone Profiler + Core UI | ✅ Complete |
| 3 | Reactivation Analyzer + Queue | ✅ Complete |
| 4 | Gmail Send + Follow-up Intelligence | 🟡 In Progress (core built, scheduler polish/deploy stabilization) |
| 5 | SMS channel (Twilio) | ⬜ Not Started |
| 6+ | Booking, reminders, calendar sync, broader niche support | ⬜ Planned |

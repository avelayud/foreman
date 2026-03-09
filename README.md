# Foreman

AI-powered customer reengagement and scheduling platform for small field service contractors (HVAC, plumbing, etc.).

**Live:** https://web-production-3df3a.up.railway.app
**Repo:** https://github.com/avelayud/foreman

---

## What it does

Foreman helps field service business owners win back dormant customers by:
1. Reading the operator's sent Gmail to learn their natural writing voice
2. Identifying customers who are overdue for service (365+ days dormant)
3. Drafting personalized reactivation emails written in the operator's exact tone
4. Presenting emails for review and approval before sending

---

## Current State — Phase 2 Complete

| Feature | Status |
|---|---|
| Database models (Operator, Customer, Job, Booking, OutreachLog) | ✅ |
| Config and environment management | ✅ |
| Sample data seed (20 HVAC customers) | ✅ |
| Gmail OAuth + sent email reader | ✅ |
| Tone profiler agent (Claude-powered voice extraction) | ✅ |
| Dashboard UI (customer categories, metrics) | ✅ |
| Customer detail view (service history, outreach history) | ✅ |
| Outreach draft generation (Claude, inline approval) | ✅ |
| Outreach queue page | ✅ |
| Railway deployment (Postgres) | ✅ |

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| AI / LLM | Anthropic Claude (`claude-sonnet-4-20250514`) |
| Web framework | FastAPI + Jinja2 |
| Frontend | Tailwind CSS (CDN) |
| Database | SQLite (dev) → PostgreSQL (prod via Railway) |
| Email reading | Gmail API (OAuth2) |
| Email sending | SendGrid (Phase 3) |
| SMS | Twilio (Phase 5) |
| Scheduling | APScheduler (Phase 3) |
| Deployment | Railway |

---

## Project Structure

```
foreman/
├── api/
│   └── app.py              # FastAPI — web UI + JSON API
├── agents/
│   └── tone_profiler.py    # Gmail → Claude voice extraction
├── core/
│   ├── config.py           # Environment variable management
│   ├── database.py         # SQLAlchemy session management
│   └── models.py           # ORM models
├── data/
│   └── seed.py             # Sample HVAC data seed
├── integrations/
│   └── gmail.py            # Gmail OAuth + sent mail reader
├── templates/
│   ├── base.html           # Shared layout + sidebar
│   ├── dashboard.html      # Customer overview + categories
│   ├── customer.html       # Customer detail + draft generation
│   └── outreach.html       # Outreach queue
├── main.py                 # CLI entry point
├── Procfile                # Railway web process
└── requirements.txt
```

---

## Pages

| URL | Description |
|---|---|
| `/` | Dashboard — metrics + customers by reactivation category |
| `/customer/{id}` | Customer detail — service history, outreach log, draft email |
| `/outreach` | Outreach queue — drafted emails awaiting review/send |

---

## Local Setup

```bash
git clone https://github.com/avelayud/foreman
cd foreman
python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

venv/bin/python main.py --seed          # Seed sample data
venv/bin/uvicorn api.app:app --reload   # Start web server → http://localhost:8000
```

## CLI Agents

```bash
# Extract voice profile from Gmail (run once per operator)
venv/bin/python -m agents.tone_profiler --operator-id 1
```

---

## Environment Variables

```
ANTHROPIC_API_KEY       # Required — console.anthropic.com
DATABASE_URL            # Default: sqlite:///./foreman.db
APP_ENV                 # development | production
DRY_RUN                 # true = generate but don't send
GOOGLE_CLIENT_ID        # Gmail OAuth
GOOGLE_CLIENT_SECRET    # Gmail OAuth
```

---

## Core Philosophy

- **Operator voice** — AI learns how the operator writes. Emails sound like them, not a marketing agency.
- **SMS-native** — field operators live in text (Phase 5)
- **Prove ROI fast** — first win is a reactivated customer. Everything else is downstream.
- **Agnostic** — works with what the operator already has (Gmail, Google Cal)

---

## Roadmap

See `PROJECT_PLAN.md` for the full phase-by-phase breakdown.

| Phase | Name | Status |
|---|---|---|
| 1 | Foundation (models, DB, config) | ✅ Complete |
| 2 | Tone Profiler + Dashboard UI | ✅ Complete |
| 3 | Reactivation Outreach Agent | 🟡 Next |
| 4 | Follow-up Sequence Engine | ⬜ |
| 5 | SMS Channel (Twilio) | ⬜ |
| 6 | Booking Page + Slot Management | ⬜ |
| 7–12 | Confirmations, Cal sync, Dashboard, Onboarding | ⬜ |

# Foreman

AI-powered customer reengagement and scheduling workflow for small field service businesses (HVAC, plumbing, electrical, etc.).

**Live:** https://web-production-3df3a.up.railway.app
**Repo:** https://github.com/avelayud/foreman

---

## What It Does

Foreman helps an operator run outbound reactivation with agent support:

1. Learns operator voice from sent Gmail (Tone Profiler)
2. Finds dormant customers and drafts personalized outreach (Reactivation Analyzer)
3. Builds customer context from Gmail correspondence (Customer Analyzer)
4. Tracks replies by Gmail thread and feeds context-aware follow-up drafts (Reply Detector + Follow-up Sequencer)
5. Keeps the operator in control: review drafts, approve/schedule/send, manage conversations

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
│   ├── app.py                 # FastAPI app (pages + JSON API)
│   └── run.py                 # Railway-safe launcher (reads PORT)
├── agents/
│   ├── tone_profiler.py
│   ├── reactivation.py
│   ├── customer_analyzer.py
│   ├── reply_detector.py
│   └── follow_up.py
├── core/
│   ├── config.py
│   ├── database.py
│   └── models.py
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
| `/` | Dashboard: pipeline metrics, segments, top prospects, browse all customers |
| `/customer/{id}` | Customer detail: account context + full history |
| `/conversations` | Active conversations with health state and attention indicators |
| `/conversations/{id}` | Conversation workspace: AI timeline, draft panel, recap |
| `/outreach` | Outreach queue: review/edit/approve/schedule/send |
| `/agents` | Agent catalog with status and manual run |

---

## Local Setup

```bash
git clone https://github.com/avelayud/foreman
cd foreman

python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, DATABASE_URL

# Optional: seed synthetic data
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

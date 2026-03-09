# FieldAgent

**AI-powered reengagement and business operations platform for small field service contractors (HVAC, plumbing, electrical, etc.)**

---

## What This Is

FieldAgent is an agentic AI platform that helps small/solo field service operators (HVAC, plumbing, electrical) run their customer relationships and scheduling autonomously. It is designed for operators who may have nothing (no website, no CRM, no business email) or who already have basic tools (Gmail, Google Calendar) and want to layer AI on top.

The agent runs on a daily cycle. It decides who to contact, drafts personalized outreach in the operator's own voice, sends via email or SMS, handles replies, books appointments, and reminds customers — without the operator needing to manage any of it manually.

---

## Core Philosophy

- **Agnostic first** — works with what the operator has. No forced migrations.
- **SMS-native** — blue collar operators and their customers live in text, not email dashboards.
- **Single pane of glass** — one unified calendar, one activity log. No app-switching.
- **Operator voice** — AI learns how the operator writes and sounds like them, not a marketing agency.
- **Prove ROI fast** — the first win is a reactivated customer. Everything else is downstream.

---

## Two Products (Shared Infrastructure)

### Product A — AI Reactivation Agent *(build first)*
Plugs into what the operator already has. Runs outreach, follow-ups, and booking close automatically.
- Target user: Operator who has a customer list but isn't working it
- Core value: "That customer called back after 18 months"

### Product B — All-in-One for the Unequipped *(build second)*
Full lightweight operating system for operators with nothing. Provisions email, SMS number, booking page, calendar.
- Target user: Operator running everything from their personal phone
- Core value: "I have a real business presence now and it runs itself"

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| AI / LLM | Anthropic Claude API (`claude-sonnet-4-20250514`) |
| SMS | Twilio |
| Email sending | SendGrid |
| Email reading (tone) | Gmail API (OAuth) |
| Calendar sync | Google Calendar API (OAuth) |
| Database | SQLite (dev) → Postgres (prod) |
| Scheduling | APScheduler |
| API layer | FastAPI |
| Frontend (booking page) | React (later phase) |

---

## Project Structure

```
fieldagent/
├── agents/              # Autonomous agent logic
│   ├── reactivation.py  # Main outreach agent
│   ├── tone_profiler.py # Voice/tone learning from emails
│   ├── scheduler.py     # Booking and calendar agent
│   └── follow_up.py     # Sequence and follow-up agent
├── core/                # Shared business logic
│   ├── models.py        # Data models (Operator, Customer, Job, Booking)
│   ├── database.py      # DB connection and setup
│   └── config.py        # Environment/config management
├── integrations/        # External service connectors
│   ├── gmail.py         # Gmail OAuth + read/send
│   ├── gcal.py          # Google Calendar sync
│   ├── twilio_sms.py    # SMS send/receive
│   └── sendgrid.py      # Email sending fallback
├── api/                 # FastAPI routes (webhook receivers, booking API)
│   └── routes.py
├── data/                # Sample data, CSV imports, DB files
├── tests/               # Unit tests per module
├── docs/                # Additional documentation
├── README.md            # This file — always up to date
├── PROJECT_PLAN.md      # Detailed phase plan and current status
├── .env.example         # Environment variable template
├── requirements.txt     # Python dependencies
└── main.py              # Entry point / agent runner
```

---

## Quick Start (for new contributors or new chat sessions)

1. Clone the repo and create a virtual environment:
```bash
git clone <repo-url>
cd fieldagent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

3. Check `PROJECT_PLAN.md` to see current build status and what's next.

4. Run the agent:
```bash
python main.py
```

---

## Current Status

**Phase 1 — Complete** (project structure, data models, DB, seed data)  
**Phase 2 — Environment setup in progress**  
See `PROJECT_PLAN.md` for detailed task breakdown and current position.

### GitHub
https://github.com/avelayud/foreman

---

## Key Design Decisions (Log)

| Decision | Choice | Reason |
|---|---|---|
| Start niche | HVAC/plumbing | Tight ICP, predictable seasonal patterns, underserved |
| Outreach channel priority | SMS > Email | Higher open rates, operators live in texts |
| Tone learning approach | Scan sent Gmail → Claude analysis → stored system prompt prefix | Feels authentic, no manual config |
| Calendar conflict prevention | Write blocks immediately on booking, soft-confirm for AI-initiated | Prevents double booking without full takeover |
| Pricing target | $29-49/mo | Below Jobber, above "free trial" psychology |
| Build order | Reactivation agent first, then close the loop with booking | Ship value fast, validate before building infra |

# Foreman — Project Plan & Status Tracker

> **How to use this file:** At the start of every new chat session, share this file. It tells the AI assistant exactly where we are, what's built, what's next, and all relevant context so we can keep building without re-explaining.

---

## Current Status

**Active Phase:** Phase 3 🟡 In Progress — Reactivation Agent.
**Current Step:** Phase 2 fully complete (dashboard, voice profiles, segment engine, 40-customer synthetic data on Railway). Starting Phase 3: automated reactivation agent with approval queue.
**Last Updated:** 2026-03-10
**Live URL:** https://web-production-3df3a.up.railway.app
**GitHub:** https://github.com/avelayud/foreman

---

## Non-Code Setup Checklist (Complete Before Building)

- [ ] Regenerate Anthropic API key (previous one was exposed — do this at console.anthropic.com)
- [ ] Create `.env` from `.env.example` and paste new API key
- [ ] Run `pip install -r requirements.txt` inside activated venv
- [ ] Run `python main.py --seed` — confirm 20 customers load
- [ ] Run `python main.py` — confirm clean startup
- [ ] Google Cloud Console: create project `foreman-dev`, enable Gmail API, create OAuth credentials, download `credentials.json`
- [ ] Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`
- [ ] Railway: sign up at railway.app with GitHub, link to `avelayud/foreman`

---

## Build Phases Overview

| Phase | Name | Status | Est. Time |
|---|---|---|---|
| 1 | Foundation (models, config, DB) | ✅ Complete | Week 1 |
| 2 | Tone Profiler Agent | ✅ Complete | Week 1-2 |
| 3 | Reactivation Outreach Agent (Email) | 🟡 In Progress | Week 2 |
| 4 | Follow-up Sequence Engine | ⬜ Not Started | Week 2 |
| 5 | SMS Channel (Twilio) | ⬜ Not Started | Week 3 |
| 6 | Booking Page + Slot Management | ⬜ Not Started | Week 3-4 |
| 7 | Confirmation + Reminder Loop | ⬜ Not Started | Week 4 |
| 8 | Google Calendar OAuth Sync | ⬜ Not Started | Week 5 |
| 9 | Review Solicitation Agent | ⬜ Not Started | Week 5 |
| 10 | Operator Dashboard (basic) | ⬜ Not Started | Week 6-7 |
| 11 | Dynamic Onboarding Flow | ⬜ Not Started | Week 7-8 |
| 12 | Niche Config Layer (expansion) | ⬜ Not Started | Week 9+ |

**Status legend:** ✅ Done | 🟡 In Progress | ⬜ Not Started | 🔴 Blocked

---

## Phase 1 — Foundation ✅ COMPLETE

All core infrastructure is built and verified:
- Project directory structure
- SQLAlchemy models: Operator, Customer, Job, Booking, OutreachLog
- DB initialization and session management
- Config and environment variable management
- Sample data seed script (20 HVAC customers)
- Entry point (main.py) with --seed and --dry-run flags
- README.md, .env.example, .gitignore, requirements.txt

---

## Phase 2 — Tone Profiler + Dashboard UI ✅ COMPLETE

**Goal:** Extract operator voice from sent Gmail, build full dashboard UI with segment engine and reactivation workflow.

### Completed
- [x] `integrations/gmail.py` — Gmail OAuth + read sent mail
- [x] `agents/tone_profiler.py` — Claude voice extraction, stores tone_profile on Operator
- [x] Voice profiles — JSON array on Operator (assignable per customer at draft time)
- [x] Segment engine — classifies customers: high_value / end_of_life / new_lead / maintenance / referral
- [x] Priority scoring — `days_dormant × (total_spend / 1000 + 0.5)`
- [x] Dashboard — metric strip, segment shelf, top-6 prospects table, browse-all tabs
- [x] Customer detail — service history, voice picker, inline draft generation
- [x] Outreach queue page
- [x] Alembic migrations — voice_profiles (Operator) + assigned_voice_id (Customer)
- [x] 40-customer synthetic dataset (`data/reseed.py`) with varied statuses, jobs, logs
- [x] Railway Postgres live with Arjuna as operator + voice profile
- [x] Navy/gold design system (IBM Plex Sans/Mono + Playfair Display, CSS variables)

---

## Phase 3 — Reactivation Outreach Agent (Email) 🟡 IN PROGRESS

**Goal:** Agent autonomously scans for dormant customers, scores + ranks them, drafts personalized emails in the operator's voice, queues for approval.

**File:** `agents/reactivation.py`

### Design
- Targets customers: `reactivation_status == 'never_contacted'` AND `days_dormant >= 365`
- Ranks by priority_score (days_dormant × spend factor), picks top N per run
- Calls Claude with operator tone profile + customer segment context
- Saves drafts to OutreachLog with `dry_run=True` — operator reviews in /outreach queue
- Actual send triggered manually via "Mark Sent" in UI (or future Gmail integration)
- APScheduler for daily automation (or manual trigger via CLI)

### Tasks
- [ ] `agents/reactivation.py` — scan → rank → draft → save to OutreachLog
- [ ] CLI: `python -m agents.reactivation --operator-id 1 [--limit N] [--dry-run]`
- [ ] Reactivation prompt (uses existing DRAFT_SYSTEM/DRAFT_USER from app.py — extract to shared module)
- [ ] APScheduler daily trigger in `main.py`
- [ ] `/api/agent/run` POST endpoint to trigger from UI
- [ ] Dashboard "Run Agent" button (agent bar) wired to endpoint
- [ ] `integrations/sendgrid.py` — SendGrid fallback send (Phase 3b or Phase 4)

### Backlog (post-Phase 3)
- [ ] Voice profile config screen — operator fine-tunes each voice beyond sent-mail analysis
- [ ] Voice profiles generated from operator's actual sent Gmail (currently seeded manually)

---

## Phase 4 — Follow-up Sequence Engine

**File:** `agents/follow_up.py`

### Sequence
```
Day 0:   Initial outreach
Day 3:   Follow-up #1 — softer check-in
Day 7:   Follow-up #2 — light urgency
Day 14:  Close loop — "I'll leave you alone"
```

### Tasks
- [ ] State machine per customer (tracked via OutreachLog.sequence_step)
- [ ] Prompt variants per step
- [ ] Skip logic when reply is detected

---

## Phase 5 — SMS Channel (Twilio)

**Goal:** All outreach and replies work via SMS. Blue-collar operators live in text.

### Tasks
- [ ] `integrations/twilio_sms.py`
- [ ] `api/routes.py` — Twilio inbound webhook
- [ ] Two-way reply handling
- [ ] Operator alert SMS on key events

---

## Phase 6 — Booking Page + Slot Management

**Goal:** Customers can self-book from a hosted page. Agent sends booking links in outreach.

### Tasks
- [ ] Slot availability model
- [ ] Booking API endpoints
- [ ] Simple hosted booking page
- [ ] Conflict detection

---

## Phase 7 — Confirmation + Reminder Loop

### Sequence
```
On booking:      Confirmation SMS + email
24hrs before:    Reminder SMS with CONFIRM/RESCHEDULE option
2hrs before:     On-my-way trigger
After job:       Review request (24hrs post-complete)
```

---

## Phases 8-12 (Future — see earlier phases for detail)

- Phase 8: Google Calendar OAuth sync
- Phase 9: Review solicitation agent
- Phase 10: Operator dashboard (mobile-first)
- Phase 11: Dynamic onboarding flow
- Phase 12: Niche config layer (expand beyond HVAC)

---

## Decisions & Context Log

| Date | Topic | Decision |
|---|---|---|
| 2026-03-08 | Product name | Foreman |
| 2026-03-08 | Niche focus | HVAC/plumbing first. Infrastructure designed to expand. |
| 2026-03-08 | Build order | Reactivation agent (Product A) before full OS (Product B) |
| 2026-03-08 | SMS vs email | SMS is primary channel. Email is fallback/supplement. |
| 2026-03-08 | Calendar conflict | Soft-confirm for AI bookings. Hard block on any booking. |
| 2026-03-08 | Pricing target | $29-49/mo. Below Jobber. |
| 2026-03-08 | DB for dev | SQLite → Postgres for prod |
| 2026-03-09 | Deployment | Railway (Python-native) over Vercel for backend |
| 2026-03-09 | Frontend | Defer React dashboard. SMS + email summaries as UI substitute early. |
| 2026-03-10 | Dashboard | Full v4 redesign — navy/gold, segment shelf, top prospects, priority scoring |
| 2026-03-10 | Voice profiles | Each profile assignable per customer; generated from Gmail, not random |
| 2026-03-10 | Reactivation flow | Approval queue model confirmed: drafts land in /outreach, operator clicks "Send" |

---

## Environment Variables Required

```
ANTHROPIC_API_KEY        # Claude API — get from console.anthropic.com
SENDGRID_API_KEY         # Email sending — sendgrid.com (Phase 3)
TWILIO_ACCOUNT_SID       # SMS — twilio.com (Phase 5)
TWILIO_AUTH_TOKEN        # SMS
TWILIO_FROM_NUMBER       # Provisioned SMS number
GOOGLE_CLIENT_ID         # Gmail + Calendar OAuth
GOOGLE_CLIENT_SECRET     # Gmail + Calendar OAuth
DATABASE_URL             # Default: sqlite:///./foreman.db
```

---

## How to Resume in a New Chat

1. Share `PROJECT_PLAN.md` with the new session
2. Say: *"I'm continuing to build Foreman. Here's the project plan. Current step: [copy from Current Status above]. Let's work on [next task]."*
3. The assistant will have full context and can keep building.

---

## Starter Prompt for Claude Code

Once your environment is set up and you're in Claude Code, use this to kick off Phase 2:

```
I'm building Foreman — an AI reengagement platform for HVAC/plumbing contractors.
Phase 1 (foundation) is complete. Here is the PROJECT_PLAN.md: [paste file]

We are starting Phase 2: the Tone Profiler Agent.
The repo is at https://github.com/avelayud/foreman
Local path: /Users/arjunavelayudam/Desktop/Coding/foreman

Start by building integrations/gmail.py (Gmail OAuth + read sent emails),
then agents/tone_profiler.py (send emails to Claude, extract voice profile, store on Operator).
Use dry-run mode. I want to run this against my own Gmail and see my voice profile output.
```

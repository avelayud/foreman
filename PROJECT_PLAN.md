# Foreman — Project Plan & Status Tracker

> **How to use this file:** At the start of every new chat session, share this file. It tells the AI assistant exactly where we are, what's built, what's next, and all relevant context so we can keep building without re-explaining.

---

## Current Status

**Active Phase:** Phase 1 ✅ Complete. Phase 2 environment setup in progress.
**Current Step:** Files on disk + pushed to GitHub. Completing non-code setup (venv deps, .env, Google OAuth, Railway) before building tone profiler.
**Last Updated:** 2026-03-09
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
| 2 | Tone Profiler Agent | 🟡 In Progress | Week 1-2 |
| 3 | Reactivation Outreach Agent (Email) | ⬜ Not Started | Week 2 |
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

## Phase 2 — Tone Profiler Agent 🟡 IN PROGRESS

**Goal:** Read the operator's existing sent Gmail, extract their writing style, store a "voice profile" used by all future outreach.

**File:** `agents/tone_profiler.py`
**Depends on:** Gmail OAuth (`integrations/gmail.py`)

### What it does
1. Authenticates with Gmail via OAuth
2. Reads last 25-30 sent emails
3. Sends samples to Claude with a voice extraction prompt that identifies:
   - Formality level (casual / semi-formal / formal)
   - Greeting style ("Hey John" vs "Hi John," vs "Hello")
   - Sign-off style ("Thanks, Mike" vs "Best, Mike")
   - Sentence length and structure tendency
   - Use of humor or regional phrasing
   - Emoji usage
4. Stores voice profile as JSON on the Operator record
5. Generates 2-3 sample outreach messages using that profile for review

### Tasks
- [ ] `integrations/gmail.py` — OAuth flow + read sent mail
- [ ] `agents/tone_profiler.py` — core profiling logic
- [ ] Voice extraction prompt (system prompt for Claude)
- [ ] "Write in this voice" prefix prompt (reused by all agents)
- [ ] Store profile in Operator.tone_profile in DB
- [ ] CLI test: `python -m agents.tone_profiler --operator-id 1`

---

## Phase 3 — Reactivation Outreach Agent (Email)

**Goal:** Agent autonomously identifies dormant customers, drafts personalized reactivation emails in the operator's voice, sends on schedule.

**File:** `agents/reactivation.py`

### Logic
- Runs daily via APScheduler
- Targets customers where last_service_date > 365 days ago AND reactivation_status == 'never_contacted'
- Calls Claude with operator tone profile + customer service history
- Sends via Gmail (if connected) or SendGrid fallback
- Logs everything to OutreachLog

### Tasks
- [ ] `agents/reactivation.py`
- [ ] `integrations/sendgrid.py`
- [ ] Reactivation email generation prompt
- [ ] APScheduler daily trigger
- [ ] Dry-run mode (generate + print, don't send)

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

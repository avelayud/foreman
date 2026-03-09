# FieldAgent — Project Plan & Status Tracker

> **How to use this file:** At the start of every new chat session, share this file. It tells the AI assistant exactly where we are, what's built, what's next, and all relevant context so we can keep building without re-explaining.

---

## Current Status

**Active Phase:** Phase 1 — Foundation  
**Current Step:** Project scaffolding complete. Starting core data models.  
**Last Updated:** 2026-03-08  
**GitHub:** https://github.com/avelayud/foreman.git

---

## Build Phases Overview

| Phase | Name | Status | Est. Time |
|---|---|---|---|
| 1 | Foundation (models, config, DB) | 🟡 In Progress | Week 1 |
| 2 | Tone Profiler Agent | ⬜ Not Started | Week 1-2 |
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

## Phase 1 — Foundation

**Goal:** Get the data models, database, and config infrastructure in place so every agent has a clean foundation to build on.

**Why this first:** Every agent needs to read/write Operators, Customers, Jobs, and Bookings. Getting this right now prevents refactoring later.

### Tasks

- [x] Create project directory structure
- [x] Create README.md
- [x] Create PROJECT_PLAN.md
- [ ] `core/config.py` — env var loading, API key management
- [ ] `core/models.py` — SQLAlchemy models: Operator, Customer, Job, Booking, OutreachLog
- [ ] `core/database.py` — SQLite setup, session management, init script
- [ ] `requirements.txt` — all dependencies pinned
- [ ] `.env.example` — template with all required keys
- [ ] `main.py` — basic entry point that initializes DB and runs agent loop
- [ ] Load sample data — 20-30 fake HVAC customers with realistic service history
- [ ] Confirm DB initializes and sample data loads cleanly

### Data Models (design)

```
Operator
  - id, name, business_name, email, phone
  - tone_profile (JSON) ← output of tone profiler agent
  - niche (hvac | plumbing | electrical | ...)
  - onboarding_complete (bool)
  - integrations (JSON) ← which services are connected

Customer
  - id, operator_id (FK)
  - name, email, phone
  - last_service_date, last_service_type
  - total_jobs, total_spend
  - reactivation_status (never_contacted | outreach_sent | replied | booked | unsubscribed)
  - notes

Job
  - id, customer_id (FK), operator_id (FK)
  - service_type, scheduled_at, completed_at
  - status (scheduled | complete | cancelled | no_show)
  - amount, notes

Booking
  - id, customer_id (FK), operator_id (FK)
  - slot_start, slot_end
  - status (tentative | confirmed | cancelled)
  - source (ai_outreach | customer_initiated | manual)
  - created_at

OutreachLog
  - id, customer_id (FK), operator_id (FK)
  - channel (email | sms)
  - direction (outbound | inbound)
  - content, sent_at
  - opened (bool), replied (bool), reply_content
  - sequence_step (int) ← which step in follow-up sequence
```

---

## Phase 2 — Tone Profiler Agent

**Goal:** Read the operator's existing sent emails (via Gmail OAuth or pasted samples), extract their writing style, and store a "voice profile" used by all future outreach.

**File:** `agents/tone_profiler.py`

### What it does
1. Accepts either: Gmail OAuth (reads last 20-30 sent emails) OR pasted email samples
2. Sends samples to Claude with a prompt that extracts:
   - Formality level (casual / semi-formal / formal)
   - Greeting style ("Hey John" vs "Hi John," vs "Hello")
   - Sign-off style ("Thanks, Mike" vs "Best regards")
   - Sentence length tendency
   - Use of humor or regional phrasing
   - Emoji usage (yes/no)
3. Stores voice profile as JSON on the Operator record
4. Generates 2-3 sample reactivation messages using that profile for operator review

### Tasks
- [ ] `agents/tone_profiler.py` — core logic
- [ ] `integrations/gmail.py` — OAuth flow + read sent mail
- [ ] Prompt engineering: voice extraction system prompt
- [ ] Prompt engineering: "write in this voice" prefix prompt
- [ ] Store profile in Operator.tone_profile
- [ ] CLI test: run profiler on sample emails, review output

---

## Phase 3 — Reactivation Outreach Agent (Email)

**Goal:** Agent autonomously identifies dormant customers, drafts personalized reactivation emails in the operator's voice, and sends them on a schedule.

**File:** `agents/reactivation.py`

### What it does
1. Runs on schedule (daily, configurable)
2. Queries customers where:
   - `last_service_date` > 12 months ago (configurable threshold)
   - `reactivation_status` == `never_contacted`
3. For each candidate, calls Claude to draft a personalized email:
   - Uses operator tone profile
   - References actual service history ("last time we serviced your AC in June...")
   - Includes a soft call to action ("would love to get you on the schedule")
4. Sends via Gmail (if connected) or SendGrid
5. Logs to OutreachLog, updates Customer.reactivation_status

### Inputs to Claude (per customer)
```
- Operator name, business name, tone profile
- Customer name, last service date, last service type
- Season/month context
- Niche-specific templates (HVAC: seasonal tune-up angle)
```

### Tasks
- [ ] `agents/reactivation.py` — main agent logic
- [ ] `integrations/sendgrid.py` — email sending
- [ ] Prompt: reactivation email generation
- [ ] Scheduling: APScheduler daily trigger
- [ ] Dry-run mode: generate emails but don't send (for review)
- [ ] Test run on sample data, review output quality

---

## Phase 4 — Follow-up Sequence Engine

**Goal:** If a customer doesn't respond to the first outreach, the agent automatically sends follow-up messages on a cadence.

**File:** `agents/follow_up.py`

### Sequence logic
```
Day 0:  Initial outreach (Phase 3)
Day 3:  Follow-up #1 — softer, check-in tone
Day 7:  Follow-up #2 — create light urgency ("slots filling up for the season")
Day 14: Close loop — "I'll leave you alone, but reach out when ready"
        → Update reactivation_status = 'sequence_complete'
```

### Tasks
- [ ] `agents/follow_up.py` — state machine per customer
- [ ] Sequence step tracking in OutreachLog
- [ ] Prompt variants for each sequence step
- [ ] Skip logic: if reply detected at any step → exit sequence
- [ ] Test full sequence on sample data

---

## Phase 5 — SMS Channel (Twilio)

**Goal:** All outreach and replies can happen via SMS. Most blue-collar customers prefer text.

**File:** `agents/` (update reactivation + follow_up) + `integrations/twilio_sms.py`

### What it adds
- Operator gets a provisioned Twilio number (their "business SMS")
- All outreach can be sent via SMS instead of (or in addition to) email
- Inbound replies to that number are captured, logged, and trigger agent response
- Operator gets SMS alerts on their personal phone for key events (new reply, new booking)

### Tasks
- [ ] `integrations/twilio_sms.py` — send + webhook receive
- [ ] `api/routes.py` — Twilio webhook endpoint for inbound SMS
- [ ] Inbound reply handler: parse reply, update OutreachLog, trigger follow-up branch
- [ ] Operator notification: SMS to operator's personal number on key events
- [ ] Test two-way SMS flow end to end

---

## Phase 6 — Booking Page + Slot Management

**Goal:** Customers can see available slots and book directly without calling. Agent proposes booking links in outreach messages.

### What it adds
- Operator defines weekly availability (e.g., Mon-Fri 8am-5pm, 2hr slots)
- Booking page hosted at `{business}.fieldagent.app`
- Customer picks a slot, enters name/address, confirms
- Booking written to DB, calendar blocked, operator notified

### Tasks
- [ ] Slot availability model (operator sets weekly schedule)
- [ ] `api/routes.py` — booking API endpoints
- [ ] Simple React booking page (or server-rendered for MVP)
- [ ] Booking link generation (unique per outreach)
- [ ] Conflict detection: block slot on booking, prevent double-book

---

## Phase 7 — Confirmation + Reminder Loop

**Goal:** Once booked, the customer receives automated confirmations and reminders. No more no-shows.

### Sequence
```
Immediately after booking: Confirmation SMS + email
24 hours before:           Reminder SMS ("Mike from ABC HVAC tomorrow at 2pm. Reply CONFIRM or RESCHEDULE")
2 hours before:            "On my way" trigger (operator initiates, customer gets ETA)
After job:                 Thank you + review request (24hrs post-complete)
```

### Tasks
- [ ] APScheduler jobs for reminder timing
- [ ] RESCHEDULE reply handler → re-open slot, send new booking link
- [ ] Job status update: operator marks job complete via SMS command or simple UI
- [ ] Review solicitation trigger on job completion

---

## Phase 8 — Google Calendar OAuth Sync

**Goal:** If operator already uses Google Calendar, sync bi-directionally so there are never conflicts.

### Tasks
- [ ] `integrations/gcal.py` — OAuth flow + read/write
- [ ] On booking: write event to Google Cal
- [ ] On Google Cal event creation: block slot in FieldAgent
- [ ] Periodic sync job (every 15min) to catch manual calendar additions

---

## Phases 9-12 (Future)

Brief descriptions — will be expanded when we get there.

**Phase 9 — Review Solicitation Agent**
After job marked complete, agent sends personalized review request with Google Maps link. Tracks if review was left.

**Phase 10 — Basic Operator Dashboard**
Mobile-first web UI. Shows: today's jobs, AI activity log (what ran, what's pending approval), customer list, outreach stats. Replaces the "weekly email digest" placeholder.

**Phase 11 — Dynamic Onboarding Flow**
Conversational setup wizard. Detects what the operator has (Gmail? Google Cal? Nothing?) and configures integrations accordingly. Provisions what's missing.

**Phase 12 — Niche Config Layer**
Service-type templates for HVAC, plumbing, electrical, landscaping, cleaning. Different seasonal triggers, terminology, follow-up cadences. This is how we expand without rebuilding.

---

## Decisions & Open Questions Log

| Date | Topic | Decision / Status |
|---|---|---|
| 2026-03-08 | Niche focus | HVAC/plumbing first. Infrastructure designed to expand. |
| 2026-03-08 | Build order | Product A (reactivation agent) before Product B (full OS) |
| 2026-03-08 | SMS vs email | SMS is primary channel. Email is fallback/supplement. |
| 2026-03-08 | Calendar conflict strategy | Soft-confirm for AI bookings. Hard block on any booking. |
| 2026-03-08 | Pricing target | $29-49/mo. Below Jobber. |
| 2026-03-08 | DB for dev | SQLite → Postgres for prod |
| 2026-03-08 | Frontend timing | Defer React dashboard. Use SMS + email summaries as UI substitute early on. |
| TBD | Hosting | TBD — likely Railway or Render for easy Python deploy |
| TBD | Auth | TBD — simple API key for MVP, OAuth for operators later |

---

## Environment Variables Required

See `.env.example`. Keys needed:

```
ANTHROPIC_API_KEY        # Claude API
SENDGRID_API_KEY         # Email sending
TWILIO_ACCOUNT_SID       # SMS
TWILIO_AUTH_TOKEN        # SMS
TWILIO_FROM_NUMBER       # Provisioned SMS number
GOOGLE_CLIENT_ID         # Gmail + Calendar OAuth
GOOGLE_CLIENT_SECRET     # Gmail + Calendar OAuth
DATABASE_URL             # SQLite path or Postgres URL
```

---

## How to Resume in a New Chat

1. Share this file (`PROJECT_PLAN.md`) and `README.md` with the new session
2. Say: *"I'm continuing to build FieldAgent. Here's the project plan. We're currently on [phase]. Let's work on [next task]."*
3. The assistant should be able to pick up exactly where we left off.

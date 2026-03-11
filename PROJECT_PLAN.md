# Foreman — Project Plan & Status Tracker

> Share this file at the start of a new chat so work can resume with correct context.

---

## Current Status

- **Active Phase:** Phase 4 (Gmail send + intelligent follow-up + operator UX)  
- **State:** Core workflows are built and usable; deploy stability is being finalized on Railway.
- **Last Updated:** 2026-03-10
- **Live URL:** https://web-production-3df3a.up.railway.app
- **Repo:** https://github.com/avelayud/foreman

---

## Recently Completed (2026-03-10)

### Agent + workflow coverage
- Added/confirmed agent coverage in app + menu:
  - Tone Profiler
  - Reactivation Analyzer
  - Customer Analyzer
  - Reply Detector
  - Follow-up Sequencer
- Added `/agents` page status cards for each agent, with live stats and CLI commands.
- Added `/api/agent/status` for aggregate runtime/coverage metrics.

### Outreach operating model
- Added Dry Run vs Production mode toggle in app (`/api/operator/mode`).
- Built `approve + schedule` and `send now` flows for queue items (`/api/outreach/{log_id}/approve-send`).
- Queue behavior now supports:
  - pending approval
  - approved/scheduled waiting to send
  - sent
  - failed
- Added scheduled send default logic (business-hour aware) and due-message sender worker.
- Kept scheduled items in queue until actually sent.

### Conversation UX
- Reworked **Active Conversations** cards for operational triage:
  - color-coded by conversation health
  - last outbound snapshot
  - needs-response/follow-up signal
  - opportunity estimate and job type
- Built separate **Conversation Detail** page (`/conversations/{customer_id}`):
  - operator recap section in plain English
  - discussion summary + structured briefing fields
  - talking points + operator tips
  - conversation-only vertical timeline (message events only)
  - expandable selected-message panel
  - opportunity snapshot + auto next steps
- Moved account-life timeline concerns to customer context (not conversation timeline).

### Data model / DB alignment
- Added/used `customers.customer_profile` with fields:
  - `relationship_history`
  - `topics_discussed`
  - `customer_tone`
  - `prior_concerns`
  - `response_patterns`
  - `interest_signals`
  - `context_notes`
  - `analyzed_at`
- Added/used `outreach_logs.gmail_thread_id` for thread-based reply detection.
- Confirmed schema patching path in app startup.

### Deployment hardening
- Updated Procfile entrypoint to `python -m api.run`.
- Added `api/run.py` to resolve `PORT` robustly in Railway.
- Normalized DB URLs in `core/database.py` (supports `postgres://` → `postgresql://`).
- Added startup DB init retry loop in `api/app.py` for transient DB boot races.
- Added env trimming in config parser to reduce whitespace misconfiguration failures.

---

## Build Phases Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| 1 | Foundation (models/config/DB) | ✅ Complete | Stable |
| 2 | Tone Profiler + Dashboard UI | ✅ Complete | Stable |
| 3 | Reactivation Analyzer + Approval Queue | ✅ Complete | Stable |
| 4 | Gmail Send + Follow-up Intelligence | 🟡 In Progress | Core done, scheduler automation + deploy polish pending |
| 5 | SMS Channel (Twilio) | ⬜ Not Started | Planned |
| 6 | Booking + Slot Management | ⬜ Not Started | Planned |
| 7+ | Reminders, Calendar sync, onboarding expansion | ⬜ Planned | Future |

---

## Phase 4 Breakdown

### Implemented
- [x] Gmail send path on approval/send-now
- [x] Thread ID persistence on outbound logs
- [x] Customer Analyzer agent (`agents/customer_analyzer.py`)
- [x] Reply Detector agent (`agents/reply_detector.py`)
- [x] Follow-up Sequencer agent (`agents/follow_up.py`)
- [x] Reactivation agent integrated with analyzer context
- [x] Active Conversations page
- [x] Conversation Detail page (recap + timeline + opportunity/next steps)
- [x] Outreach queue redesign + action grouping
- [x] Production/dry-run toggle in UI
- [x] Scheduled send worker loop in app

### Remaining for Phase 4 closeout
- [ ] Add reliable recurring scheduler wiring for `reply_detector` + `follow_up` (currently manual/CLI)
- [ ] Add operator-facing run controls for non-reactivation agents (optional polish)
- [ ] Finish Railway deploy debugging and verify healthy boots + web responses after fresh deploy
- [ ] Rotate exposed secrets after successful deploy validation

---

## Deployment Debug Checklist (Current Priority)

1. Confirm Railway **Web** service variables:
   - `DATABASE_URL` = internal Railway URL (`postgres.railway.internal`)
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
2. Do not set a custom `PORT`; Railway injects it.
3. Confirm deploy includes:
   - `Procfile` using `python -m api.run`
   - `api/run.py`
   - DB URL normalization + startup retry code
4. If app still fails:
   - capture first traceback from Railway deploy/runtime logs
   - capture request ID from the Railway error page
   - verify DB connectivity from Railway runtime context

---

## Local Run Modes

### Local (SQLite)
```bash
DATABASE_URL=sqlite:///./foreman.db venv/bin/python -m api.run
```

### Local against Railway public DB
```bash
DATABASE_URL=postgresql://<user>:<pass>@hopper.proxy.rlwy.net:<port>/railway venv/bin/python -m api.run
```

### Manual agent runs
```bash
venv/bin/python -m agents.tone_profiler --operator-id 1
venv/bin/python -m agents.reactivation --operator-id 1 --limit 10
venv/bin/python -m agents.customer_analyzer --operator-id 1 --all
venv/bin/python -m agents.reply_detector --operator-id 1
venv/bin/python -m agents.follow_up --operator-id 1 --limit 20
```

---

## Environment Variables

```bash
ANTHROPIC_API_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
DATABASE_URL
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

## Decisions Log

| Date | Topic | Decision |
|---|---|---|
| 2026-03-08 | Product direction | Reactivation-first wedge before full FSM stack |
| 2026-03-09 | Deployment platform | Railway for Python + Postgres simplicity |
| 2026-03-10 | Agent naming | “Reactivation” renamed in UI to **Reactivation Analyzer** |
| 2026-03-10 | Operator safety | Added Dry Run / Production mode toggle |
| 2026-03-10 | Queue behavior | Approved but unsent drafts remain visible as scheduled/pending |
| 2026-03-10 | Conversation UX | Separate conversation page; conversation-only timeline |
| 2026-03-10 | Deploy hardening | Added startup retries, DB URL normalization, and Python launcher |

---

## To-Do / Backlog

- **Email draft fine-tuning**: The AI-generated draft quality (formatting, tone calibration, personalization depth) needs iterative improvement. Future work: prompt engineering, operator feedback loop, A/B testing different draft styles.

---

## Known Risks

- Secrets were exposed in chat/local env during troubleshooting and must be rotated.
- Railway app still reported “Application failed to respond” after one deploy; resolved via background DB init + deadlock fix.
- `reply_detector` runs in a background thread (every 15 min); not yet backed by a durable scheduler (e.g., cron/Celery) — will miss cycles if the dyno restarts mid-poll.

---

## New Chat Resume Prompt (General)

Use this when resuming build work:

```text
I’m continuing Foreman from PROJECT_PLAN.md (attached).
Current focus: Phase 4 closeout and deploy stabilization.

Please:
1) Read PROJECT_PLAN.md and README.md first.
2) Verify implemented features against code (agents, conversations UI, outreach queue workflow, dry-run/production mode).
3) Continue from the “Remaining for Phase 4 closeout” checklist.
4) Make code changes directly, run validation, and summarize exactly what changed.
```

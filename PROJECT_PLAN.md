# Foreman — Project Plan & Status Tracker

> Share this file at the start of a new chat so work can resume with correct context.

---

## Current Status

- **Active Phase:** Phase 4 (complete) → Phase 5 planning
- **State:** Core workflows fully operational. Conversations, drafts, reply detection, and follow-up all working end-to-end against real Gmail.
- **Last Updated:** 2026-03-11
- **Live URL:** https://web-production-3df3a.up.railway.app
- **Repo:** https://github.com/avelayud/foreman

---

## Recently Completed (2026-03-11)

### Conversation workspace
- Redesigned **Conversation Detail** page:
  - Two-column layout: timeline (left) + draft panel + expanded message (right)
  - Timeline sorted newest-first; each item shows AI-generated one-sentence summary
  - Click any timeline item to expand full email body on the right
  - Draft panel auto-loads on page open; context-aware (reply vs. follow-up)
  - Approve & Queue button moves draft directly to outreach queue
  - Full-width collapsible sections: Opportunity Snapshot + Conversation Recap & Talking Points
- Active Conversations list shows most recent message (inbound or outbound) with "Customer replied" signal

### Draft generation
- Reply drafts: read full conversation thread + customer job history; answer specific questions with real domain knowledge (HVAC filter lifespans, equipment ages, etc.)
- Follow-up drafts: include full previous outreach thread so draft explicitly references what was sent
- Body normalization: collapses single newlines within paragraphs to prevent broken email formatting
- Draft panel shows informative error if no sent emails exist for the customer

### Dashboard
- "View all →" now scrolls to browse section and activates tab via JS
- Live search box on browse card — filter any customer by name in real time

### Sidebar
- Attention badge on Conversations nav item (needs_response + needs_follow_up count)

### Timestamp handling
- All timestamps stored as UTC; display filter converts to Eastern (EDT/EST auto via `America/New_York`)
- Fixed Gmail inbound timestamp bug: was stripping timezone before UTC conversion, storing local EDT as naive datetime
- Migration script `data/fix_inbound_timestamps.py` corrects existing inbound logs (adds EDT offset)
- Railway Postgres: run `UPDATE outreach_logs SET sent_at = sent_at + INTERVAL '4 hours' WHERE direction = 'inbound' AND gmail_thread_id IS NOT NULL AND sent_at IS NOT NULL;` once to fix existing records

### Railway / infra
- Railway CLI workflow confirmed: `brew install railway` → `railway login` → `railway link` → `railway connect Postgres`
- Public networking must be enabled on Postgres service for external psql access

---

## Build Phases Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| 1 | Foundation (models/config/DB) | ✅ Complete | Stable |
| 2 | Tone Profiler + Dashboard UI | ✅ Complete | Stable |
| 3 | Reactivation Analyzer + Approval Queue | ✅ Complete | Stable |
| 4 | Gmail Send + Follow-up Intelligence + Conversation UX | ✅ Complete | Fully operational |
| 5 | SMS Channel (Twilio) | ⬜ Not Started | Planned |
| 6 | Booking + Slot Management | ⬜ Not Started | Planned |
| 7+ | Reminders, Calendar sync, onboarding expansion | ⬜ Planned | Future |

---

## Phase 4 — All Done

- [x] Gmail send path on approval/send-now
- [x] Thread ID persistence on outbound logs
- [x] Customer Analyzer agent
- [x] Reply Detector agent (background thread, every 15 min)
- [x] Follow-up Sequencer agent
- [x] Reactivation agent integrated with analyzer context
- [x] Active Conversations page (health state, attention badge)
- [x] Conversation Detail page (AI timeline summaries, draft panel, expandable messages)
- [x] Outreach queue redesign + approve/schedule/send-now flow
- [x] Production/dry-run toggle in UI
- [x] Scheduled send worker loop in app
- [x] Timestamp UTC normalization + EDT/EST display filter
- [x] Dashboard browse-all with search

---

## Known Risks / Watch-outs

- `reply_detector` + `follow_up` run as background threads (15-min poll); not backed by a durable scheduler — will miss cycles on dyno restart. Acceptable for now; move to cron/Celery if reliability becomes an issue.
- Postgres password was shared in a chat session — **rotate credentials** in Railway (Postgres → Settings → Regenerate).
- Single-tenant: `OPERATOR_ID = 1` hardcoded throughout.

---

## Backlog

- **Durable scheduler**: wire `reply_detector` and `follow_up` to a cron or task queue so they survive restarts
- **Email draft quality loop**: operator feedback signal, prompt A/B testing, tone calibration refinement
- **Voice profiles from Gmail**: generate profiles from actual sent mail instead of manual seed
- **Voice profile config screen**: let operator fine-tune each voice's response style
- **SMS channel**: Twilio integration (Phase 5)
- **Booking + slot management** (Phase 6)

---

## Local Run

```bash
# SQLite (default local dev)
DATABASE_URL=sqlite:///./foreman.db venv/bin/python -m api.run

# Against Railway Postgres (public proxy must be enabled)
DATABASE_URL=postgresql://<user>:<pass>@hopper.proxy.rlwy.net:26095/railway venv/bin/python -m api.run
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

## Decisions Log

| Date | Topic | Decision |
|---|---|---|
| 2026-03-08 | Product direction | Reactivation-first wedge before full FSM stack |
| 2026-03-09 | Deployment platform | Railway for Python + Postgres simplicity |
| 2026-03-10 | Agent naming | "Reactivation" renamed in UI to **Reactivation Analyzer** |
| 2026-03-10 | Operator safety | Added Dry Run / Production mode toggle |
| 2026-03-10 | Queue behavior | Approved but unsent drafts remain visible as scheduled/pending |
| 2026-03-10 | Conversation UX | Separate conversation page; conversation-only timeline |
| 2026-03-10 | Deploy hardening | Added startup retries, DB URL normalization, and Python launcher |
| 2026-03-11 | Timestamps | All stored as UTC; display via `America/New_York` zoneinfo filter |
| 2026-03-11 | Draft context | Follow-up drafts now include full thread; reply drafts include job history + domain knowledge |

---

## New Chat Resume Prompt

```text
I'm continuing Foreman from PROJECT_PLAN.md.
Phase 4 is complete. Next focus: backlog items or Phase 5 (SMS/Twilio).

Please:
1) Read PROJECT_PLAN.md and README.md first.
2) Check the Backlog section for current priorities.
3) Make code changes directly and summarize what changed.
```

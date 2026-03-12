# Foreman — Project Plan & Status Tracker

> Share this file at the start of a new chat so work can resume with correct context.

---

## Product Vision

**Vision:** AI Operating System for Field Service Revenue
**Product:** AI Reactivation System for HVAC & Field Service Businesses
**Tagline:** Turn your past customers into booked jobs. Automatically.

**Target customer:** HVAC, plumbing, and electrical contractors. Owner-operated teams of 3–15. Not highly technical. May be using QuickBooks, Jobber, HousecallPro — or nothing beyond a phone. HVAC is the primary beachhead.

**Positioning:** Foreman is a revenue system, not a CRM or email tool. The core value proposition: identify which past customers are most likely to need service now, reach out in the operator's voice, convert responses to booked jobs, and show exactly how much revenue it generated. Priced below Jobber/HousecallPro, dramatically above them in AI-driven proactive outreach capability.

**Core loop:** Score → Prioritize → Outreach → Classify Response → Propose Time → Convert to Job → Track Revenue

---

## Current Status

- **Active Phase:** Phase 6b — Booking Confirmation Detection + Calendar Write-back
- **State:** Phase 6 core complete. Response classifier live, booking proposals auto-drafted to Meetings Queue, Google Calendar reads available slots, one-click dashboard actions, email threading fixed, search added everywhere. Next: detect confirmation replies and create Booking records automatically. Phase 7 scoped: Customer Analytics page + Product Analytics instrumentation (see plans/).
- **Last Updated:** 2026-03-12
- **Live URL:** https://web-production-3df3a.up.railway.app
- **Repo:** https://github.com/avelayud/foreman

---

## Recently Completed

### Phase 6 — Booking Conversion Flow + Google Calendar (✅ Core Complete)
- `agents/response_classifier.py`: Claude classifier, 5 categories (booking_intent / callback_request / price_inquiry / not_interested / unclear)
- Classifier auto-runs in Reply Detector pipeline on every new inbound reply
- `integrations/calendar.py`: Google Calendar OAuth (calendar.readonly), reads free/busy blocks for slot proposals
- Booking proposal flow: booking_intent reply → auto-draft with 3 real calendar slots → routes to Meetings Queue
- `/meetings` page: booking proposal queue with proposed slots panel, search, regenerate button
- `/calendar` page: agenda view grouped by month, color-coded by service type (maintenance/install/repair)
- One-click dashboard actions: Draft Outreach / Draft Follow-up / Book Call — generates draft and redirects to correct queue
- Outreach Queue split: "Needs Approval" (amber) + "Send Pending" (blue) sections
- Badge counts only reflect pending-approval items (scheduled items excluded)
- Smart queue refresh: APScheduler background job every 15 min — auto-regenerates stale drafts when newer reply arrives
- Email threading fix: `send_email()` now sets `In-Reply-To` + `References` RFC 2822 headers so follow-ups land in the same thread on both sides
- Search added to Conversations, Outreach Queue, and Meetings Queue pages
- Run Now buttons added for all agents on Agents page (tone profiler, reply detector, follow-up sequencer)
- GMAIL_TOKEN_JSON base64 fallback: fixed Railway env var parse error affecting Send Now and Book Call
- `_fmt()` helper in conversation_agent: pre-escapes curly braces in values before str.format() to prevent crashes on email content with `{...}` patterns

### Phase 5 — Customer Scoring + Revenue Dashboard (✅ Complete)
- `core/scoring.py`: rules-based scoring engine (Recency 40 + LTV 20 + Frequency 15 + Job Type 15 + Engagement 10)
- Customer model migration: `score`, `score_breakdown`, `priority_tier`, `estimated_job_value`, `service_interval_days`, `predicted_next_service`
- OutreachLog model migration: `response_classification`, `classified_at`, `converted_to_job`, `converted_job_value`, `converted_at`
- Scoring runs at startup + daily via APScheduler
- Revenue dashboard: 8 metric cards (dormant identified, % contacted, responses, active convos, jobs booked, revenue generated, pipeline value, avg job value)
- Dashboard rebuilt with 4 priority groups: Upcoming Jobs / Active-Requires Attention / Ripe for Reactivation / On Hold
- Each group: top 5 shown with "Show more" (max 10) and "View all →" link
- New `/customers` page: full searchable + filterable customer list (search by name/email, filter by group)
- "Mark as Booked" flow: modal on dashboard + customer page, logs job value, updates OutreachLog
- Priority Scorer added to agents page with Run Now button and live stats
- Customer Analyzer now runs on startup + daily schedule for all customers with correspondence or no profile
- Score breakdown module on individual customer pages (5 signal bars)
- Nav: Conversations above Outreach Queue; All Customers link added
- Seed data: 200 customers, 5yr HVAC history, realistic dormancy/value distributions

### Phase 4 — Gmail + Conversations (✅ Complete)
- Gmail send path, thread ID persistence, reply detection
- Customer Analyzer, Follow-up Sequencer, Reply Detector agents
- Conversation workspace: AI timeline, context-aware draft, expandable messages
- UTC timestamps + EDT/EST display

---

## Build Phases Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| 1 | Foundation (models/config/DB) | ✅ Complete | Stable |
| 2 | Tone Profiler + Dashboard UI | ✅ Complete | Stable |
| 3 | Reactivation Analyzer + Approval Queue | ✅ Complete | Stable |
| 4 | Gmail Send + Follow-up Intelligence + Conversation UX | ✅ Complete | Fully operational |
| 5 | Customer Scoring + Revenue Dashboard | ✅ Complete | Live |
| 6 | Booking Conversion Flow + Google Calendar | ✅ Core complete | Classifier, calendar, meetings queue live |
| 6b | Booking Confirmation Detection + Calendar Write-back | 🔵 Active | Job 02 in plans/ |
| 7 | Customer Analytics Page + Product Analytics | ⬜ Planned | Jobs 03 + 04 in plans/; Job 04 before 03 |
| 8 | Outreach Composer Redesign | ⬜ Planned | See backlog |
| 9 | SMS Channel (Twilio) | ⬜ Planned | |
| 10 | Service Interval Prediction | ⬜ Planned | |
| 11 | Jobber / HousecallPro Integration | ⬜ Planned | |
| 12 | QuickBooks Data Ingestion | ⬜ Planned | |
| 13 | ML-Trained Scoring Model (sklearn) | ⬜ Planned | Needs real conversion labels |

---

## Phase 6 — Booking Conversion Flow + Google Calendar

**Goal:** When a customer replies with booking intent, Foreman automatically detects it, proposes real available calendar slots, and closes the loop. The operator's job becomes reviewing and confirming — not managing scheduling back-and-forth manually.

### Response Classifier (✅ Complete)
- [x] `agents/response_classifier.py`: Claude classifier, 5 categories (booking_intent / callback_request / price_inquiry / not_interested / unclear)
- [x] Wired into reply detector pipeline (auto-runs on each new inbound reply)
- [x] Stores classification on `OutreachLog.response_classification` + `classified_at`
- [x] Conversation workspace shows classification badge + recommended next action

### Google Calendar Integration (✅ Complete)
- [x] Google Calendar OAuth (calendar.readonly scope added to existing OAuth token)
- [x] `integrations/calendar.py`: reads operator free/busy for next 10 business days
- [x] GMAIL_TOKEN_JSON base64 fallback for Railway env var format

### Booking Proposal Flow (✅ Complete)
- [x] booking_intent detected → conversation_agent auto-drafts reply with 3 real slots
- [x] Proposal draft routes to `/meetings` (Meetings Queue) not Outreach Queue
- [x] `/meetings` page: proposed slots panel extracted from email body, search, regenerate
- [x] Operator reviews + approves → sends via Gmail in-thread

### One-Click Dashboard Actions (✅ Complete)
- [x] Draft Outreach: generates draft synchronously, redirects to /outreach
- [x] Book Call: reads calendar slots, generates booking proposal, redirects to /meetings
- [x] Draft Follow-up: generates context-aware follow-up draft, redirects to /outreach
- [x] Idempotent: checks for existing pending draft before generating new one

## Phase 6b — Booking Confirmation Detection + Calendar Write-back (🔵 Active)

### Booking Confirmation + Job Creation
- [ ] Confirmation detection: classifier identifies confirmed slot in customer reply
- [ ] On confirmation: create `Booking` record (date, time, customer_id, job_type)
- [ ] Update Customer.reactivation_status → `booked`, OutreachLog.converted_to_job = True
- [ ] Log estimated job value from Customer.estimated_job_value
- [ ] Confirmation summary on conversation workspace: "Job booked for [date]"

### Calendar Write-back
- [ ] Add `calendar.events` write scope to OAuth token
- [ ] Create Google Calendar event on booking confirmation
- [ ] Event includes: customer name, address, job type, contact info
- [ ] Link Google Calendar event ID on Booking record

---

---

## Phase 7 — Customer Analytics + Product Analytics

**Status:** ⬜ Planned. Full specs in `plans/job_03_customer_analytics/plan.md` and `plans/job_04_product_analytics/plan.md`.
**Execution order:** Job 04 (Product Analytics) → Job 03 (Customer Analytics) — so that `/analytics` itself is instrumented when built.

### Job 04 — Product Analytics Instrumentation
New `ProductEvent` model. `core/product_analytics.py` helpers (`log_event`, `get_session_id`, `log_page_view`). Session tracking via `foreman_session` cookie (UUID, 30-day expiry). Full event taxonomy: page views, draft events (with `edit_pct`), outreach, conversion, agent, navigation. `POST /api/events` (never returns 500). `trackEvent()` JS in `base.html`. Internal-only dashboard at `/internal/product` with 6 sections: Activity Overview, Page Popularity, Draft Behavior, Feature Engagement, Navigation Funnel, Recent Event Log.

Key metric: `edit_pct` = character diff / original length — reveals which draft types operators are rewriting vs. accepting.

### Job 03 — Customer Analytics Page (`/analytics`)
New read-only page, two tabs:
- **Customer Insights:** Value Tier Donut, Dormancy Distribution, Engagement by Segment, Job Type Breakdown, Response Classification Breakdown
- **Revenue & ROI:** Outreach Funnel, Activity Over Time (line chart), Revenue Over Time (bar + cumulative line), Recent Conversions table

All aggregations server-side in new `core/analytics.py`. Chart.js via CDN. Time-range toggle (`?range=30|90|all`) affects time-series only — composition data always all-time. Sidebar link between Conversations and Agents.

---

## Backlog / TODOs

### BUG — Stale Customer Analyzer Profiles After Reseed (PRIORITY)
- **Symptom:** After wiping + reseeding the DB and rerunning Customer Analyzer, a specific customer's profile still shows old/stale data from before the reseed.
- **Likely causes to investigate:**
  1. The reseed script deletes and recreates Customer rows but may not be clearing `_customer_profile` on the new rows if the column has a DB-level default that isn't null.
  2. Customer Analyzer reads from Gmail API (`get_correspondence()`) — Gmail still has the old real emails, so the profile is re-populated from real mail history not from seed data. This is correct behavior for live addresses but confusing in test context.
  3. The analyzer may be keying on email address rather than customer ID — so even a new Customer row for the same email address picks up the same old Gmail history.
- **Fix plan:** After reseed, Customer Analyzer should re-analyze and overwrite the profile. Verify `_customer_profile` is null on freshly seeded rows. Add `--force` flag to customer_analyzer to overwrite all profiles unconditionally. Consider displaying `analyzed_at` timestamp on the customer profile UI so staleness is visible.
- **Files:** `agents/customer_analyzer.py`, `data/reseed.py`, `core/models.py`

### BUG — Reply Detection Lag / Run Now Not Refreshing (PRIORITY)
- **Symptom:** Operator receives a real customer reply in Gmail. Even after manually pressing "Run Now" on the Agents page (reply detector), the reply does not appear on the site for some time. Unclear whether the agent is actually running, what it found, or whether a page refresh is needed after it completes.
- **Issues to investigate:**
  1. Run Now buttons fire agents in background threads and return immediately — the UI shows "started" but the page never refreshes. Operator has to manually reload.
  2. Reply Detector only checks threads that have a `gmail_thread_id` stored in `OutreachLog`. If the initial outreach email was sent but the thread ID wasn't persisted (e.g. dry_run records, or a bug at send time), the reply will never be detected.
  3. After reply is detected, classifier + draft generation also run sequentially in the same thread — total pipeline could take 15–30s. No feedback to operator.
- **Fix plan:**
  - Run Now button should poll for completion or at minimum auto-reload the page after a fixed delay (e.g. 5 seconds after click).
  - Add a "Last checked" timestamp to the Reply Detector card on Agents page so operator can see when it last ran.
  - Audit: verify `gmail_thread_id` is stored on all non-dry-run outbound OutreachLog records.
  - Log number of threads checked + number of replies found to the agent status output.
- **Files:** `agents/reply_detector.py`, `api/app.py`, `templates/agents.html`

### BUG — Email Body Line Breaks / Formatting on Recipient Side
- **Symptom:** Customer receives an email where the body has hard line breaks that look exactly like how the draft appeared in the site's text box — with visible enter/return characters creating a broken layout. The same email looks fine in the operator's Gmail inbox.
- **Root cause hypothesis:** The email body is stored and sent as plain text (`MIMEText(body, "plain", "utf-8")`). Claude's draft output contains literal `\n` newlines formatted for display in an HTML `<textarea>`. When sent as `text/plain`, some email clients (especially on mobile, or Gmail's web client when viewing on the recipient side) render each `\n` as a visible line break. The operator's Gmail view may be collapsing them. Alternatively, the body contains `\r\n` or double-newlines that format strangely.
- **Fix plan:**
  - Audit what the raw `body` string looks like before it's passed to `MIMEText` — print/log the first 500 chars at send time.
  - Normalize line endings: strip leading/trailing whitespace, collapse 3+ consecutive newlines to 2, ensure consistent `\n` (not `\r\n`).
  - Consider sending as `text/html` with `<br>` for line breaks and `<p>` for paragraphs — more consistent across clients.
  - Or: send multipart/alternative with both plain and HTML parts.
- **Files:** `integrations/gmail.py` (`send_email()`), `agents/conversation_agent.py` (where body is generated)

### BUG — Email Threading Still Creating New Thread on Second Reply (PRIORITY)
- **Symptom:** Same as before — when sending a second email in a conversation (e.g. a meeting proposal after an initial reply), the recipient sees it as a new separate email thread. The operator's inbox shows it correctly in the same thread.
- **Context:** A fix was applied (Phase 6) to use `format="minimal"` + per-message `messages().get(format="metadata", metadataHeaders=["Message-ID"])` to reliably fetch `Message-ID` headers and set `In-Reply-To` + `References`. The asymmetry (correct on sender, broken on recipient) persists.
- **Remaining hypotheses:**
  1. The `thread_id` being looked up may be from the first outbound message, but the customer's reply has a *different* Gmail thread ID on their side. When we fetch the thread by our `threadId`, we get our internal representation — not necessarily the RFC message IDs the recipient's client knows about.
  2. The `In-Reply-To` value may be the RFC Message-ID of *our* sent message, but the recipient's email client expects it to reference *their sent* message (i.e., the reply they sent us).
  3. The `References` chain may be incomplete — missing the customer's reply RFC Message-ID, so the recipient's client can't connect the chain.
- **Fix plan:**
  - At reply time, look up the inbound `OutreachLog` record for the customer's reply and retrieve its `rfc_message_id` (the Message-ID from the customer's email). Store this on the inbound log at detection time.
  - Set `In-Reply-To` = customer's reply RFC Message-ID (not just the last outbound).
  - Set `References` = full chain including both outbound and inbound RFC Message-IDs in order.
  - Add logging to print the exact `In-Reply-To` and `References` headers being set before each send.
- **Files:** `integrations/gmail.py`, `agents/reply_detector.py` (store `rfc_message_id` on inbound logs), `api/app.py` (`_deliver_outreach_log`)

### IMPROVEMENT — Agent Orchestration & Run-Order Documentation
- **Problem:** It's unclear when each agent runs, what order they run in, what triggers them, and what the expected lag is between an event (e.g. customer replies) and the system reacting to it. This causes confusion about whether something is broken or just delayed.
- **Current state (best known):**
  - Tone Profiler: manual only
  - Reactivation Analyzer: manual only
  - Priority Scorer: startup + daily (APScheduler)
  - Customer Analyzer: startup + daily (APScheduler)
  - Reply Detector: every 15 min (APScheduler background thread)
  - Follow-up Sequencer: manual only (should be daily)
  - Response Classifier: auto-triggered inside reply detector pipeline on each new reply
  - Conversation Agent: auto-triggered inside reply detector pipeline after classification
- **Fix plan:**
  - Document the full pipeline on the Agents page: show trigger type (manual / scheduled / auto), frequency, and what it produces.
  - Add a pipeline diagram or ordered list showing: Reply comes in → Reply Detector picks it up (up to 15 min) → Classifier runs → Draft generated → appears in queue.
  - Add `last_run_at` + `next_run_at` to scheduled agents on the Agents page so operator knows when the next automatic run is.
  - Consider adding Follow-up Sequencer to the daily schedule so it doesn't require manual runs.
- **Files:** `api/app.py`, `templates/agents.html`

### Customer Analyzer — Read from OutreachLog (PRIORITY)
- **Current problem:** Customer Analyzer calls `get_correspondence()` which searches Gmail API by email address. Synthetic seed emails (e.g. `patsimm@email.com`) don't exist in Gmail so profiles never populate.
- **Fix:** Teach the analyzer to fall back to (or prefer) the existing `OutreachLog` records in the DB. For each customer, query `OutreachLog` for all inbound + outbound messages, format them as a conversation thread, and send to Claude for profile analysis — no Gmail API call needed.
- This makes the analyzer work for 100% of customers immediately, including all 40 scenario customers who have rich simulated conversation data.
- Gmail `get_correspondence()` can remain as a secondary enrichment path for customers where real Gmail threads exist (the 8 live email addresses).
- Implementation notes:
  - In `agents/customer_analyzer.py`, add `_get_thread_from_db(customer, db)` that fetches OutreachLog rows ordered by `sent_at`
  - Format as: `[OUTBOUND] Subject: ...\n<body>` / `[INBOUND] <body>` — same structure as Gmail thread formatting
  - Use this as the primary source; call Gmail `get_correspondence()` only if OutreachLog returns fewer than 2 messages
  - Store result in `Customer._customer_profile` as before

### Email Traffic Simulation (for Live Email Enrichment)
- For the 8 live email addresses, we need real Gmail threads so `get_correspondence()` returns actual data
- Use owned Gmail accounts to simulate realistic back-and-forth conversations with the operator Gmail
- Design: standalone script (`tools/email_simulator.py`) — not part of production app
- Lower priority now that OutreachLog-based analysis will work for all scenario customers

### Outreach Composer Redesign (Phase 7)
- "Draft Outreach" action button → dedicated composer page, not customer detail page
- Composer: customer context panel (left) + email editor (right), one-click send or queue
- Customer page becomes read-only CRM context — no inline draft widget
- Separate flow: cold-start (first outreach) vs reply/follow-up (thread continuation)

### Other Backlog
- **Durable scheduler**: move reply_detector + follow_up to cron/Celery (survive dyno restarts)
- **Email draft quality loop**: operator feedback signal, prompt A/B testing
- **Voice profiles from Gmail**: generate profiles from actual sent mail instead of manual seed
- **Voice profile config screen**: operator fine-tunes each voice's response style
- **Multi-tenant audit**: all queries filter by operator_id — audit before second user onboards

---

## Scoring Model Spec

Rules-based weighted scorer. Interpretable and replaceable with a trained model once real conversion data exists.

| Signal | Field | Max Points | Logic |
|---|---|---|---|
| Recency | days since last job | 40 | >365 days = 40, scales linearly below |
| Lifetime value | sum of job revenue | 20 | >$2000 = 20, >$500 = 10, else 5 |
| Job frequency | count of prior jobs | 15 | jobs × 3, capped at 15 |
| Job type | maintenance vs repair | 15 | Any maintenance = 15, repair-only = 8, single job = 4 |
| Prior engagement | response to past outreach | 10 | Positive response = 10, any reply = 5, none = 0 |

Priority tiers: high ≥70, medium 40–69, low <40.

**Phase 12 ML upgrade:** Once 3–6 months of real conversion outcomes exist, retrain using `converted_to_job` as label with sklearn RandomForest.

---

## Response Classification Spec

| Classification | Trigger Example | Next Action |
|---|---|---|
| `booking_intent` | "Yes, when can you come?" | Propose 3 calendar slots |
| `callback_request` | "Call me to discuss" | Flag for operator, show phone number |
| `price_inquiry` | "How much would that cost?" | Draft pricing response |
| `not_interested` | "Please remove me" | Unsubscribe, suppress all future outreach |
| `unclear` | Ambiguous reply | Surface to operator with full context |

---

## Known Risks / Watch-outs

- `reply_detector` + `follow_up` run as background threads (15-min poll); not backed by a durable scheduler — will miss cycles on dyno restart. Acceptable for now.
- Single-tenant: `OPERATOR_ID = 1` hardcoded throughout. Must audit before onboarding second operator.
- Customer Analyzer currently calls `get_correspondence()` which searches Gmail API by email address — synthetic seed emails don't exist in Gmail so profiles don't populate. **Fix planned:** fall back to OutreachLog records in DB as primary source (see Backlog).
- **Email threading (recipient side):** Second email to a customer still arrives as a new thread on the recipient's side despite `In-Reply-To` + `References` fix. Root cause still under investigation — likely the `References` chain is missing the customer's own reply RFC Message-ID. See Backlog for fix plan.
- **Run Now buttons are fire-and-forget:** Agents start in background threads; UI shows "started" but never confirms completion. Operator must manually refresh to see results. Reply Detector in particular may take 15–30s for full classify + draft pipeline.
- **Stale customer profiles after reseed:** Customer Analyzer re-reads from Gmail API which still has real email history — so profiles for live email addresses repopulate with old Gmail data even after a DB wipe. See Backlog for fix plan.

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
| 2026-03-11 | Draft context | Follow-up drafts include full thread; reply drafts include job history + domain knowledge |
| 2026-03-11 | Product pivot | Repositioned as revenue system (not email assistant); scoring + revenue dashboard as Phase 5 |
| 2026-03-11 | Scoring approach | Rules-based weighted scorer first; ML model deferred to Phase 12 |
| 2026-03-11 | Phase 6 scope | Merged response classifier + booking conversion + Google Calendar into single phase |
| 2026-03-11 | Email simulation | Separate tool (`tools/email_simulator.py`) using real owned Gmail addresses — not part of production app |
| 2026-03-11 | Outreach composer | Deferred to Phase 7; "Draft Outreach" → dedicated composer page, not customer detail page |
| 2026-03-12 | Queue routing | booking_intent drafts → /meetings; everything else → /outreach. Discriminator: OutreachLog.response_classification |
| 2026-03-12 | One-click actions | Dashboard action buttons POST to /api/action/* which generate synchronously then redirect — eliminates multi-step generate → move → re-edit flow |
| 2026-03-12 | Email threading | send_email() now sets In-Reply-To + References MIME headers; _deliver_outreach_log() looks up existing thread_id — ensures replies land in same thread for both sender and recipient |
| 2026-03-12 | Queue badge count | Only counts approval_status="pending" items — scheduled/approved items no longer inflate sidebar badge |
| 2026-03-12 | Reseed data | 200 customers: 8 live email addresses (never_contacted), 40 scenario customers (rich multi-turn conversations), 152 bulk generated |
| 2026-03-12 | Analytics page scope | `/analytics` is read-only insight page (not a work queue); no customer filtering, no actions — that's the dashboard |
| 2026-03-12 | Product analytics privacy | `edit_pct` is computed metric (never draft text). No PII in event properties. Session IDs are random UUIDs. |
| 2026-03-12 | Phase 7 execution order | Job 04 (product analytics) before Job 03 (analytics page) — so /analytics is instrumented from day one |
| 2026-03-12 | `booking_confirmed` vs `booking_intent` | `booking_intent` = wants to book, no slot confirmed; `booking_confirmed` = specific time accepted. Only `booking_confirmed` triggers auto-Booking creation. |
| 2026-03-12 | Plans scaffold | Feature work tracked in `plans/` — one folder per job, `plan.md` + `tasks/` with individual task files. Authored in Claude app, executed in Claude Code. |

---

## New Chat Resume Prompt

**Files to attach:** `PROJECT_PLAN.md`, `README.md`, and whichever code files are relevant to the specific task (see per-task file lists below).

```text
I'm continuing work on Foreman — an AI reactivation system for HVAC & field service contractors.

Read PROJECT_PLAN.md and README.md first for full context, then look at any code files attached.

Current state (2026-03-12): Phases 1–6 core complete. Phase 6b active.
Live: https://web-production-3df3a.up.railway.app

Completed recently:
- Response classifier agent (auto-runs on every inbound reply)
- Google Calendar OAuth + slot reading (integrations/calendar.py)
- Booking proposals route to /meetings queue (separate from /outreach)
- One-click dashboard actions: Draft Outreach / Draft Follow-up / Book Call
- Email threading fix attempt (In-Reply-To + References headers) — still not fully working
- Search on Conversations, Outreach Queue, Meetings Queue
- Run Now buttons + /internal dev tools page (reseed + run all agents)
- DB reseeded: 200 customers (8 live emails, 40 scenario conversations, 152 bulk)

Open bugs (see Backlog in PROJECT_PLAN.md for full details + fix plans):
1. Email threading STILL broken: second email to recipient arrives as new thread despite In-Reply-To/References fix. Root cause: References chain missing customer's own reply RFC Message-ID.
2. Reply detection lag: Run Now buttons fire-and-forget, no page refresh, operator can't tell if agent ran or found anything.
3. Email body line breaks: Claude drafts sent as plain text have hard line breaks that render badly on recipient side.
4. Stale customer profiles after reseed: Customer Analyzer re-reads Gmail API which still has old real emails — profile repopulates with stale data.
5. Agent run order / orchestration unclear: needs documentation + scheduling audit.

Next priorities:
1. Fix email threading (see Backlog — store rfc_message_id on inbound OutreachLog, use it for In-Reply-To)
2. Fix email body line breaks (normalize body before MIMEText, or send as HTML)
3. Customer Analyzer: fall back to OutreachLog records as primary source
4. Reply Detector: auto-refresh UI after Run Now, add last-checked timestamp
5. Booking confirmation detection → create Booking record automatically (Phase 6b)

Make code changes directly and summarize what changed.
```

---

### Per-task file lists (attach these to Claude app)

**Email threading fix:**
- `PROJECT_PLAN.md`
- `integrations/gmail.py`
- `agents/reply_detector.py`
- `api/app.py` (lines ~2300–2420, the `_deliver_outreach_log` function)

**Email body formatting fix:**
- `integrations/gmail.py` (`send_email()`)
- `agents/conversation_agent.py`

**Customer Analyzer fix (OutreachLog as source):**
- `PROJECT_PLAN.md`
- `agents/customer_analyzer.py`
- `core/models.py`
- `integrations/gmail.py`

**Reply Detector / Run Now UX:**
- `agents/reply_detector.py`
- `api/app.py`
- `templates/agents.html`

**Booking confirmation detection:**
- `PROJECT_PLAN.md`
- `agents/reply_detector.py`
- `agents/response_classifier.py`
- `agents/conversation_agent.py`
- `core/models.py`

**Any API / UI work:**
- `PROJECT_PLAN.md`
- `api/app.py`
- whichever `templates/*.html` file is relevant

**Data / reseed work:**
- `data/README.md`
- `data/reseed.py`
- `core/models.py`

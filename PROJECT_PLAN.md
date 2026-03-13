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

- **Active Phase:** Phase 8 — Outreach Composer Redesign
- **State:** Phases 1–7 and 6b all complete. Customer Analyzer reads from OutreachLog (DB-first, Gmail fallback). Booking confirmation auto-detection live. Email formatting fixed. Conversation agent context-awareness fixed. Next: Phase 8.
- **Last Updated:** 2026-03-13
- **Live URL:** https://web-production-3df3a.up.railway.app
- **Repo:** https://github.com/avelayud/foreman

---

## Recently Completed

### 2026-03-13 — Job 01 (Customer Analyzer) + Phase 6b (Booking Confirmation)

- **Customer Analyzer DB-first (Job 01):** Added `_get_thread_from_db()` to `agents/customer_analyzer.py` — reads OutreachLog records (all directions, all dry_run states) as the primary data source, formatted as `[OUTBOUND date] Subject: ...` / `[INBOUND date]` thread strings. `analyze_customer()` now uses DB as primary source when ≥ 2 messages exist; falls back to Gmail API for thin/empty threads (covers 8 live email customers with no OutreachLog). Added skip logic (don't re-analyze if profile exists) and `--force` CLI flag to overwrite all profiles unconditionally. Reply detector passes `force=True` on post-reply profile refresh so new reply context is always incorporated.
- **Booking confirmation auto-detection (Phase 6b):** `_auto_create_booking()` in `reply_detector.py` fires when classifier returns `booking_confirmed`. Reads extracted `booking_slot_start/end` from the queued confirmation draft (set by `conversation_agent._generate_booking_confirmation`), creates `Booking` record (`source=ai_outreach`, `status=confirmed`), flips `Customer.reactivation_status → booked`, marks `OutreachLog.converted_to_job = True`, and creates a Google Calendar event. GCal step has graceful fallback — booking is always saved even if calendar scope is unavailable. Conversation workspace already displays the booked state when `active_booking` exists — no UI changes needed.

### 2026-03-13 — Email Formatting Fix, Conversation Agent Improvements, Regenerate Draft Fix

- **Email line-break fix (multipart/alternative):** root cause was Python's `MIMEText` with `charset="utf-8"` applying quoted-printable encoding, wrapping lines at 76 chars with `=\r\n` soft breaks. Gmail on the recipient side stripped `=` but kept `\r\n`, causing hard line breaks. Fix: `send_email()` now sends `multipart/alternative` (plain text + HTML). HTML part converts paragraphs to `<p>` tags via `_plain_to_html()` so text reflows naturally. Plain text part retained as fallback.
- **Conversation agent context-awareness:** `AGENT_SYSTEM` now scopes "respect their decision" rule to the *current* message only. Agent explicitly grants requests when customer previously declined something (e.g. a call) but asks for it again later. `NOT_INTERESTED_PROMPT` removed hardcoded "no proposed times" ban — now only skips if customer didn't ask. `PRICE_RESPONSE_PROMPT` gives ballpark ranges and offers alternatives without hard-pushing.
- **Regenerate draft context-aware:** `POST /api/outreach/{id}/regenerate` now reads `response_classification` from the existing draft. If it's a conversation reply, routes to `conversation_agent.generate_response` with the correct classification and latest inbound message as context. Falls back to cold reactivation draft only when no classification is set.
- **Signoff formatting:** `AGENT_SYSTEM` now instructs agent to put the name on its own line (`Best,\nArjuna` not `Best, Arjuna`).

### 2026-03-13 — Conversation State Fixes, Classifier Overhaul, Updates Inbox, Internal Metrics Improvements
- **Updates inbox (`/updates`):** new operator inbox page with four sections — Needs Response (red, unread inbound awaiting reply), Follow-ups Overdue (amber, past-due sequences), Inbound Replies Last 7 Days (blue, full classified feed), Follow-ups Coming Up (green, next 3 days). Sidebar link with amber attention badge showing count of conversations needing response.
- **Reply detector all-customer scan:** removed `ACTIVE_STATUSES` and `SCAN_STATUSES` filters from both Pass 1 (thread scan) and Pass 2 (inbox scan). All customers with outbound threads are now scanned regardless of `reactivation_status` — fixes missed replies from customers previously marked closed/unsubscribed.
- **`unsubscribe_request` classifier category:** added as a separate 7th category distinct from `not_interested`. `reactivation_status = "unsubscribed"` and draft-skip now only triggered by explicit permanent opt-out language ("remove me from your list", "stop emailing me"). `not_interested` (soft decline) no longer marks unsubscribed.
- **`NOT_INTERESTED_PROMPT` in conversation agent:** instead of skipping draft for `not_interested`, agent now generates a conversational reply that respects the customer's position and directly answers any question they asked. No proposed times, no rebooking push.
- **Booking_intent / callback_request guardrails:** classifier now explicitly requires affirmative intent for both categories. "I don't think I need a call just yet" + question → `not_interested`. Declining + asking a question is never `booking_intent` or `callback_request`.
- **`AGENT_SYSTEM` strengthened:** rules added prohibiting re-proposing something the customer already declined. Agent must respond to what the customer actually said rather than following a pipeline script toward booking.
- **Per-page analytics in Internal Metrics:** new "Per-page Analytics" section (Section 4b) with expandable `<details>` elements for 10 key pages. Shows page view count + action event bar chart per page. `conversations_detail` aggregates all `/conversations/{id}` page events server-side.
- **Server-side action event tracking:** `log_event` calls added after draft generation, draft queue, and approve-send so Internal Metrics shows draft behavior without requiring frontend tracking.
- **Action event naming:** sidebar nav events renamed from generic `nav_click` to descriptive `nav_to_{page}` names. `"unknown"` entries and `page_view`/`error` types excluded from Feature Engagement display.
- **Email CRLF normalization:** `_normalize_email_body()` now strips `\r\n` and `\r` before splitting on `\n{2,}` — fixes paragraph detection failing on textarea submissions from browsers that send CRLF line endings.

### 2026-03-12 — Phase 7 (Analytics + Internal Metrics), Conversation Page, Error Tracking
- Analytics Dashboard (`/analytics`): customer base composition, outreach funnel, revenue ROI, time-range filter (30d/90d/All), `core/analytics.py` with 7 server-side aggregation functions
- Internal Metrics Dashboard (`/internal/product`): page views, draft behavior, feature engagement, navigation funnel, recent events log, **Error Log** section showing all captured 500s with traceback viewer
- Error tracking: global `@app.exception_handler(Exception)` logs all unhandled errors to `ProductEvent` table (`event_type="error"`) — visible in Internal Metrics. Returns friendly retry page instead of blank 500.
- Schedule Appointment panel on conversation page: mirrors Draft Message UX, creates Booking + GCal event + sends email in-thread without queue log (`POST /api/customer/{id}/book-and-invite`)
- Post-booking notes capture: green confirmation state after booking, notes + estimated job value saved to Booking, propagated to OutreachLog for revenue attribution (`POST /api/booking/{id}/notes`)
- Conversation page lazy timeline summaries: `_generate_timeline_summaries()` moved off render critical path to `GET /api/conversation/{id}/summaries`, fetched by JS after page load — fixes Railway 500s from 30s request timeout
- Email body normalization: `_normalize_email_body()` strips Claude's hard line-breaks at Gmail send boundary — outbound emails render as natural paragraphs on recipient side
- Nav reorganization: Workspace section (dashboard, analytics, customers, conversations, calendar), Queues section (outreach, meetings), Agents section (all agents only), Internal section (dev tools, internal metrics)
- Timeline badges extended to outbound messages: `booking_confirmed` → "Calendar Invite", `booking_intent` → "Booking Inquiry"
- `ProductEvent` model + `core/product_analytics.py`: session tracking, page view logging, event ingestion (`POST /api/events`)
- `POST /api/customer/{id}/booking-draft`: Claude Haiku generates confirmation email subject+body given slot + service type

### 2026-03-12 — Email Threading, Reply Detection, Agent UX Fixes
- Email threading (recipient side): `OutreachLog.rfc_message_id` now stored at reply detection time; `send_email()` accepts explicit `in_reply_to` param and uses it as `In-Reply-To`, overriding the last-message-in-thread heuristic — so follow-ups land in the correct thread on the recipient's client
- Schema auto-migrated: `SCHEMA_PATCHES` adds `rfc_message_id VARCHAR` to `outreach_logs` on startup
- Dual-pass reply detection: Pass 1 = thread-based scan (stored `gmail_thread_id`); Pass 2 = email-address inbox scan (`search_inbox_by_sender()`) catches orphaned replies on different threads
- Reply detection dedup: `_already_logged_rfc_ids()` per-message dedup replaces the broken "any inbound ever?" check — future replies from the same customer no longer get skipped
- `"replied"` status added to `ACTIVE_STATUSES` scan set — customers who already replied were previously invisible to the detector
- Active Conversation banner on `/customer/{id}`: shows reply count, thread count, amber warning if `unique_threads > 1`, link to conversation workspace
- Run Now buttons now synchronous: all agent run endpoints block until completion, JS auto-reloads page on success with 120s AbortController timeout
- `_agent_last_run` in-memory dict: all agents (manual + scheduled) update this on completion; agents page shows accurate last-run timestamps
- Follow-up Sequencer added to APScheduler daily schedule (was manual-only)
- Conversation page draft UX: removed auto-draft on page load — draft only generated on explicit user click. Three states: pending draft notice → generate button → draft form
- Queued drafts shown in conversation timeline as dashed-blue entries with "View in Queue →" link
- Plans scaffold: `plans/` directory created with `README.md`, job folders for Jobs 01–04, each with `plan.md` + `tasks/` subfolder

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
| 6b | Booking Confirmation Detection + Calendar Write-back | ✅ Complete | Auto-booking on confirmed reply; GCal write-back |
| 7 | Customer Analytics Page + Product Analytics | ✅ Complete | Jobs 03 + 04 done; per-page analytics + error tracking added 2026-03-13 |
| 8 | Outreach Composer Redesign | 🔵 Active | See backlog / plans/ |
| 9 | SMS Channel (Twilio) | ⬜ Planned | |
| 10 | Service Interval Prediction | ⬜ Planned | |
| 11 | Jobber / HousecallPro Integration | ⬜ Planned | |
| 12 | QuickBooks Data Ingestion | ⬜ Planned | |
| 13 | ML-Trained Scoring Model (sklearn) | ⬜ Planned | Needs real conversion labels |

---

## Phase 6 — Booking Conversion Flow + Google Calendar

**Goal:** When a customer replies with booking intent, Foreman automatically detects it, proposes real available calendar slots, and closes the loop. The operator's job becomes reviewing and confirming — not managing scheduling back-and-forth manually.

### Response Classifier (✅ Complete)
- [x] `agents/response_classifier.py`: Claude classifier, 7 categories (booking_intent / booking_confirmed / callback_request / price_inquiry / not_interested / unsubscribe_request / unclear)
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

## Phase 6b — Booking Confirmation Detection + Calendar Write-back (✅ Complete)

- [x] `booking_confirmed` classifier category (distinct from `booking_intent`)
- [x] `_auto_create_booking()` in reply_detector: fires on `booking_confirmed`
- [x] Creates `Booking` record (`source=ai_outreach`, `status=confirmed`) with slot times extracted by conversation_agent
- [x] `Customer.reactivation_status → booked`, `OutreachLog.converted_to_job = True`
- [x] Google Calendar event created via `integrations/calendar.create_calendar_event()` — customer added as attendee, GCal sends .ics invite automatically
- [x] `Booking.google_cal_event_id` stored on success; graceful fallback if calendar scope unavailable
- [x] Conversation workspace shows booked state (existing `active_booking` UI path)

---

---

## Phase 7 — Customer Analytics + Product Analytics

**Status:** ✅ Complete. Extended 2026-03-13 with per-page analytics breakdown and server-side action event tracking.
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

### ~~BUG — Email Body CRLF / Formatting on Recipient Side~~ ✅ Fixed (2026-03-13)
- Root cause: browser textarea submissions use `\r\n` line endings; `_normalize_email_body()` only split on `\n{2,}` so `\r\n\r\n` paragraph breaks were not detected
- Fix: strip `\r\n` → `\n` and `\r` → `\n` before the regex split. Outbound emails now render as clean paragraphs on recipient side.

### BUG — Stale Customer Analyzer Profiles After Reseed (PRIORITY)
- **Symptom:** After wiping + reseeding the DB and rerunning Customer Analyzer, a specific customer's profile still shows old/stale data from before the reseed.
- **Likely causes to investigate:**
  1. The reseed script deletes and recreates Customer rows but may not be clearing `_customer_profile` on the new rows if the column has a DB-level default that isn't null.
  2. Customer Analyzer reads from Gmail API (`get_correspondence()`) — Gmail still has the old real emails, so the profile is re-populated from real mail history not from seed data. This is correct behavior for live addresses but confusing in test context.
  3. The analyzer may be keying on email address rather than customer ID — so even a new Customer row for the same email address picks up the same old Gmail history.
- **Fix plan:** After reseed, Customer Analyzer should re-analyze and overwrite the profile. Verify `_customer_profile` is null on freshly seeded rows. Add `--force` flag to customer_analyzer to overwrite all profiles unconditionally. Consider displaying `analyzed_at` timestamp on the customer profile UI so staleness is visible.
- **Files:** `agents/customer_analyzer.py`, `data/reseed.py`, `core/models.py`

### ~~BUG — Reply Detection Lag / Run Now Not Refreshing~~ ✅ Fixed (2026-03-12)
- Run Now buttons are now synchronous (no background threading) — HTTP response returns only after agent completes
- JS auto-reloads page on success with 120s AbortController timeout
- `_agent_last_run` dict updated after every run (manual + scheduled) — agents page shows accurate last-run timestamps
- Reply Detector dual-pass: Pass 1 thread scan + Pass 2 inbox address scan; per-message RFC dedup; `"replied"` status included

### ~~BUG — Email Body Line Breaks / Formatting on Recipient Side~~ ✅ Fixed (2026-03-13)
- Root cause confirmed: browser textarea uses `\r\n`; `_normalize_email_body()` only matched `\n{2,}` so paragraph breaks weren't detected and the body was sent as a wall of text
- Fix: `body.replace('\r\n', '\n').replace('\r', '\n')` before regex split in `api/app.py`
- **Files:** `api/app.py` (`_normalize_email_body()`)

### ~~BUG — Email Threading Still Creating New Thread on Second Reply~~ ✅ Fixed (2026-03-12)
- Root cause confirmed: `In-Reply-To` was referencing our last outbound RFC Message-ID, not the customer's reply — recipient's client couldn't connect the chain
- Fix: `rfc_message_id` stored on inbound `OutreachLog` at detection time; `send_email()` accepts explicit `in_reply_to` param; `_deliver_outreach_log()` looks up `_get_customer_inbound_rfc_id()` and passes it through
- `OutreachLog.rfc_message_id` column added via `SCHEMA_PATCHES` (auto-migrates on startup)

### IMPROVEMENT — Agent Orchestration & Run-Order Documentation (Partially Fixed)
- **Current state (as of 2026-03-12):**
  - Tone Profiler: manual only
  - Reactivation Analyzer: manual only
  - Priority Scorer: startup + daily (APScheduler)
  - Customer Analyzer: startup + daily (APScheduler)
  - Reply Detector: every 15 min (APScheduler background thread) + Run Now
  - Follow-up Sequencer: ✅ now daily (APScheduler) + Run Now
  - Response Classifier: auto-triggered inside reply detector pipeline
  - Conversation Agent: auto-triggered inside reply detector pipeline after classification
- **Remaining:** Agents page doesn't yet show trigger type or `next_run_at`. Pipeline timing not documented in UI. Durable scheduler (survive dyno restart) not yet implemented.

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
| `booking_intent` | "Yes, when can you come?" | Propose 3 calendar slots — requires affirmative explicit intent |
| `booking_confirmed` | "Tuesday at 10am works for me" | Create Booking record |
| `callback_request` | "Call me to discuss" | Flag for operator, show phone number — requires affirmative call request |
| `price_inquiry` | "How much would that cost?" | Draft pricing response |
| `not_interested` | "Not right now, but what does a tune-up include?" | Draft conversational reply answering question; do NOT re-propose booking |
| `unsubscribe_request` | "Remove me from your list" | Mark unsubscribed, suppress all outreach, skip draft |
| `unclear` | Ambiguous reply | Surface to operator with full context |

**Key rules (2026-03-13):**
- Decline + question → `not_interested` (never `booking_intent` or `callback_request`)
- "I don't need a call just yet" → `not_interested` even if they also ask a question
- `unsubscribe_request` requires final, unambiguous language — soft declines always land on `not_interested`
- `not_interested` does NOT set `reactivation_status = "unsubscribed"` — customer stays active

---

## Known Risks / Watch-outs

- `reply_detector` + `follow_up` run as APScheduler background threads; not backed by a durable scheduler — will miss cycles on dyno restart. Acceptable for now.
- Single-tenant: `OPERATOR_ID = 1` hardcoded throughout. Must audit before onboarding second operator.
- Customer Analyzer currently calls `get_correspondence()` which searches Gmail API by email address — synthetic seed emails don't exist in Gmail so profiles don't populate. **Fix planned (Job 01):** fall back to OutreachLog records in DB as primary source (see Backlog).
- **Stale customer profiles after reseed:** Customer Analyzer re-reads from Gmail API which still has real email history — so profiles for live email addresses repopulate with old Gmail data even after a DB wipe. See Backlog for fix plan.
- ~~Email threading broken on recipient side~~ — ✅ Fixed 2026-03-12
- ~~Run Now buttons fire-and-forget~~ — ✅ Fixed 2026-03-12 (synchronous + auto-reload)

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
| 2026-03-12 | RFC threading fix | `In-Reply-To` must reference customer's reply RFC Message-ID (not our outbound) — stored as `rfc_message_id` on inbound OutreachLog at detection time; passed explicitly to `send_email()` |
| 2026-03-12 | Dual-pass reply detection | Pass 1 = stored gmail_thread_id scan; Pass 2 = `search_inbox_by_sender()` email-address inbox scan catches orphaned threads. Per-message RFC dedup prevents double-logging. |
| 2026-03-12 | Run Now synchronous | Agent run endpoints block until completion; JS auto-reloads. `_agent_last_run` dict updated by all agents for accurate last-run display. |
| 2026-03-12 | Conversation draft on demand | Draft only generated on explicit user click — not on page load. Pending draft in queue shows notice + link to prevent duplicate drafts. |
| 2026-03-12 | Active Conversation banner | Customer detail page shows conversation state (reply count, thread count, amber warning for orphaned threads) with link to workspace. |
| 2026-03-13 | unsubscribe_request split | `not_interested` = soft decline, conversation stays active, draft generated. `unsubscribe_request` = explicit permanent opt-out only — triggers unsubscribed status + draft skip. Root cause: Samuel Keller declined service + asked a question, system auto-unsubscribed him and hid the conversation. |
| 2026-03-13 | Reply detector all-customer scan | Removed ACTIVE_STATUSES/SCAN_STATUSES filters from Pass 1 and Pass 2. All customers with outbound gmail_thread_id are scanned. A customer marked unsubscribed or booked can still reply and that reply must be logged. |
| 2026-03-13 | not_interested draft behavior | Instead of skipping draft on not_interested, conversation_agent now uses NOT_INTERESTED_PROMPT — answers the customer's actual question, respects their position, no rebooking push. Better matches real business behavior (decliner who asked a question deserves an answer). |
| 2026-03-13 | booking_intent guardrails | Added explicit IMPORTANT rules to classifier: decline + question → not_interested (not booking_intent). Affirmative, explicit booking desire required. "I don't think I need a call just yet" is not callback_request. |
| 2026-03-13 | Updates inbox | New /updates page consolidates operator action items: needs response (highest priority), overdue follow-ups, recent inbound replies, upcoming follow-ups. Sidebar amber badge shows count of conversations awaiting reply. |
| 2026-03-13 | Per-page analytics | Internal Metrics Section 4b: expandable breakdown per page using server-side page_event_data dict. conversations_detail aggregates all /conversations/{id} events into one synthetic key. |
| 2026-03-13 | Server-side event tracking | draft_generated, draft_queued, outreach_sent logged via log_event() in API endpoints — not dependent on frontend JS. Ensures Internal Metrics populates even if client-side tracking is blocked. |
| 2026-03-13 | Email formatting (multipart/alternative) | MIMEText + charset="utf-8" uses QP encoding which wraps at 76 chars; Gmail recipient strips = but keeps \r\n → hard line breaks. Fix: send_email() now sends multipart/alternative. HTML part via _plain_to_html() uses <p> tags for natural reflow. Plain text retained as fallback. |
| 2026-03-13 | Conversation agent temporal awareness | AGENT_SYSTEM "respect their decision" rule scoped to current message only. If customer previously declined but now asks for it, grant the request. NOT_INTERESTED_PROMPT hard "no proposed times" ban removed — only skip if customer didn't ask. |
| 2026-03-13 | Regenerate draft context routing | /api/outreach/{id}/regenerate reads response_classification from existing draft. If set, routes to conversation_agent.generate_response with latest inbound_log_id. Falls back to cold reactivation only when no classification. |
| 2026-03-13 | Signoff formatting | AGENT_SYSTEM instructs agent to put name on its own line: "Best,\nArjuna" not "Best, Arjuna". |
| 2026-03-13 | Customer Analyzer DB-first | OutreachLog is primary source (all dry_run states included so scenario customers work). Gmail fallback when DB has < 2 messages. Skip existing profiles unless force=True. reply_detector always passes force=True so new replies update the profile. |
| 2026-03-13 | booking_confirmed auto-booking | _auto_create_booking() in reply_detector reads booking_slot_start/end from the queued confirmation draft, creates Booking (source=ai_outreach), flips customer to booked, marks converted_to_job=True, creates GCal event. GCal failure is non-fatal — booking always saved. |

---

## New Chat Resume Prompt

**Files to attach:** `PROJECT_PLAN.md`, `README.md`, and whichever code files are relevant to the specific task (see per-task file lists below).

```text
I'm continuing work on Foreman — an AI reactivation system for HVAC & field service contractors.

Read PROJECT_PLAN.md and README.md first for full context, then look at any code files attached.

Current state (2026-03-13): Phases 1–7 + 6b all complete. Active: Phase 8.
Live: https://web-production-3df3a.up.railway.app

Completed recently (2026-03-13 session):
- Customer Analyzer (Job 01): _get_thread_from_db() reads OutreachLog as primary source. DB-first
  (>=2 messages), Gmail fallback for thin threads. Skip logic + --force flag. reply_detector passes
  force=True on post-reply refresh. Profiles now populate for all 200 customers.
- Booking confirmation (Phase 6b): _auto_create_booking() in reply_detector fires on booking_confirmed.
  Creates Booking record (source=ai_outreach), flips customer to booked, sets converted_to_job=True,
  creates Google Calendar event. GCal graceful fallback if scope unavailable.
- Email formatting: send_email() sends multipart/alternative (plain + HTML). _plain_to_html() converts
  paragraphs to <p> tags. Root cause: Python MIMEText QP encoding wrapped at 76 chars.
- Conversation agent: AGENT_SYSTEM scoped to current message. Agent grants requests even if customer
  previously declined. NOT_INTERESTED_PROMPT allows calls/times if customer asks. PRICE_RESPONSE_PROMPT
  gives ballpark ranges. Signoff: name on own line.
- Regenerate draft: routes to conversation_agent for reply drafts (uses response_classification).

Next priorities:
1. Phase 8 — Outreach Composer redesign: dedicated composer page, separate cold vs reply flow
   (design notes: plans/backlog_conversation_queue_design.md)

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

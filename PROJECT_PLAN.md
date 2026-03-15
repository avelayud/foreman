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

- **Active Phase:** Phase 8 — Operator Config + Agent Quality
- **State:** Phases 1–7 and 6b all complete. Jobs 05, 09, 11–31 complete. Latest: UI polish sprint 2 — Conversations job type badge (call/on-site), Outreach Queue type-based filters (Send Pending first), Command Center read/unread state, booking invite queues to Meetings Queue, booking_intent routing fix. Next: Job 06 (Prompt Quality Sprint). Job 32 (Analytics — backlog).
- **Last Updated:** 2026-03-14
- **Live URL:** https://web-production-3df3a.up.railway.app
- **Repo:** https://github.com/avelayud/foreman

---

## Recently Completed

### 2026-03-14 — UI Polish Sprint 2 (Job Type, Queue Filters, Read/Unread, Booking Flow Fixes)

- **Conversations page:** Job type + call/on-site badge added to info row. Status pill moved from header to inline with opportunity. Info row order: Job Type | Messages | Last Interaction | Status · Opportunity. Legend updated.
- **Outreach Queue:** Filter buttons changed from approval-status (Needs Approval/Send Pending) to outreach type (sequence_label). Send Pending section now renders first (if any), Needs Approval below. `data-type` attribute on cards enables type filtering.
- **Command Center:** Time and Customer columns widened (110→130px, 140→160px). "Category" column renamed "Status". "What To Do" renamed "What Happened · Next Step". Read/unread state: unread rows get subtle bg tint; first click marks as read in localStorage, row goes white.
- **Booking flow fix:** "Set Up Appointment" → "Queue for Review →" — now calls new `POST /api/customer/{id}/queue-booking-invite` endpoint (creates tentative Booking + GCal event + queues confirmation email to Meetings Queue as pending review). No longer sends directly.
- **booking_intent routing fix:** `pending_draft_queue` now uses `_MEETINGS_CLASSIFICATIONS = ("booking_confirmed",)` only — `booking_intent` drafts correctly route to Outreach Queue, not Meetings Queue. Action banner text updated accordingly.
- **Nav icons:** Agents → 🤖, Settings → ⚙️, Dev Tools → 🛠️ (removed `font-size:11px` wrappers for consistent vertical alignment).
- **New backlog plans:** `plans/backlog_draft_learning_agent.md` (learns operator edits, improves future drafts). `plans/backlog_conversation_page_redesign.md` (opportunity snapshot, recap/talking points, operator prep for upcoming jobs).

### 2026-03-14 — UI Polish Sprint (Conversations, Queue, Dashboard, Command Center)

- **Conversations page:** Status/health chips now inline with customer name (same row, with divider); faded grey separator between name row and body; info section (Last Interaction | Opportunity | Messages) now horizontal with vertical dividers. In/out counts moved from header to info row. Legend block explaining health chip vs status pill added above cards.
- **Outreach Queue:** Regenerate button moved inline to right of revision notes textarea. Customer Page + Open Conversation moved into 3-dot menu (⋮) in card header. Quick Links section removed. Filter bar added at top: All / Needs Approval / Send Pending filters with mini donut SVG.
- **Priority Dashboard:** Revenue Pipeline (Uncontacted / In-Flight / Booked / Converted) grouped in left half; Outreach Health (Reply Rate / Booking Rate / Needs Attention / Total Outreach) grouped in right half. Section labels added.
- **Command Center:** By Category section moved before Recent Activity. Quadrant rows show detail sub-line (classification context, days overdue, appointment date). Feed_items enriched with action-specific descriptions. Quadrant max rows increased to 5. Recent Activity has column headers (Time / Customer / What To Do / Category). Count badge added to Recent Activity header.
- **base.html:** `s-booked` CSS class added (purple, for invite_sent state). Nav "All Agents" renamed to "Agents".
- **Jobs archived:** 05, 09, 24–31 moved to plans/archive.

### 2026-03-14 — Jobs 24–30 + Deploy Fixes + UI Polish

- **Job 24 (Conversation State Agent):** `agents/state_reconciler.py` — 5 idempotent reconciliation rules run at startup + every 15 min via APScheduler. Fixes orphaned states (e.g. customer replied but still marked in-sequence).
- **Job 25 (GCal Sync Agent):** `agents/gcal_sync.py` — 5-case sync: detects deleted/rescheduled calendar events, sets `orphaned`/`time_changed` flags on Booking, runs at startup + every 6 hours. `integrations/calendar.py` added `update_calendar_event()` via `events().patch()`.
- **Job 26 (Edit Meeting Invite):** Edit appointment toggle on conversation page — inline form with date/time/duration/service/notes/email fields. `POST /api/booking/{id}/edit` endpoint + `EditBookingRequest` Pydantic model. Patches GCal event if `google_cal_event_id` present.
- **Job 27 (Agents Page Polish):** All 13 agents grouped into 5 labelled sections (Listening & Classification, Outreach & Drafting, Booking & Calendar, Maintenance & Data, Internal Ops). Group headers with descriptions. `last_run_at` via `est` filter.
- **Job 28 (Meeting Queue Status):** Fixed status tags on Meetings Queue to show invite_sent/booking_intent correctly. `health_override` on Customer model with `dismissHealth()` + `clearHealthOverride()` JS. Auto-expires on new genuine inbound.
- **Job 29 (Conversations Layout):** Donut chart added to conversations page. Compact filter tabs with counts. `_compute_donut_arcs()` + `HEALTH_COLORS` in app.py. `health_key`, `health_color`, `last_contact_display` on each conversation item.
- **Job 30 (Command Center Redesign):** `/updates` fully redesigned: Section A = chronological notification feed (filled dot = unread/seen via `last_updates_viewed` cookie, hollow = seen), Section B = 2×2 quadrant grid (Needs Response / Needs Follow-up / Invite Sent / Calendar). `feed_items` + `quadrant_data` built in app.py.
- **Deploy bug fixes:** `google_cal_event_id` added to SCHEMA_PATCHES["bookings"]; `invite_sent` added to `reactivation_status` Enum; `/updates` route column-projection query expanded with `response_classification`; Command Center crash fixed (`qdata['items']` subscript vs `qdata.items` method ambiguity in Jinja2).
- **Conversation detail UI polish:** Action banner moved above appointment panel; panel renamed "Appointment"; opportunity value range moved above job notes with inline Update Value button; first-open opportunity value popup (modal) — fixed endpoint URL (`/notes` not `/update-notes`) and sessionStorage debounce.
- **Navbar reorganization:** Dashboard → Priority Dashboard; Updates → Command Center; All Customers / Calendar / Analytics moved to new "Explore" section; All Agents moved under Internal.
- **Conversations page:** Reverted from compact row list to card-based detail layout (`.conv-card` with colored left border, 2-col layout with message preview and action buttons), made ~30% more compact. Donut integrated inline with filter bar instead of standalone block.

### 2026-03-14 — Jobs 11–23: Meetings Queue, Conversation UX, Booking Flow

- **Job 11 (Agent run timeout):** AbortController 120s safety valve on all Run Now buttons; "Still running — reload when ready" amber state so operators aren't stranded.
- **Job 12 (Gmail thread split fix):** `send_email()` sets `In-Reply-To` + `References` headers referencing the customer's reply RFC Message-ID, so Foreman replies land in the same thread on the customer side.
- **Job 13 (Meeting approval gate):** Booking proposals no longer auto-send — all `booking_intent` drafts queue to Meetings Queue for operator review before sending.
- **Job 14 (Calendar acceptance false positive):** Fixed bug where a customer accepting a Google Calendar invite was re-classified as a new reply triggering a redundant redraft.
- **Job 15 (Reply detector trigger chain):** Reply detector polls every 5 minutes; runs response generator inline immediately when new replies are found (no independent poll). Nav badge updates live.
- **Job 16 (invite_sent status):** New `reactivation_status = invite_sent` — set when a calendar invite is sent from Meetings Queue. Surfaces correctly in conversations and dashboard groups.
- **Job 17 (Calendar invite accept/decline handling):** Accept → confirm booking + success toast on conversation page. Decline → delete booking + queue redraft in Meetings Queue.
- **Job 18 (Meetings queue UI overhaul):** Cleaner card layout, slot display, approve/decline actions. Revision notes field. Regenerate button wired to conversation agent.
- **Job 19 (Appointment confirmed module):** Conversation page shows confirmed appointment panel above draft panel when booking is active. Schedule panel bubbles to top via CSS `order:-1`.
- **Job 20 (Status refresh triggers):** Nav badge counts refresh after every approve/send action via `refreshNavCounts()` in base.html. Conversation page reloads 900ms after approve.
- **Job 21 (Meetings queue scope):** Meetings Queue now shows only `booking_confirmed` calendar invites. `booking_intent` (day-window proposals) routes to Outreach Queue.
- **Job 22 (Updates page improvements):** `needs_response` and `recent_replies` sorted by `created_at` desc. Post-visit update section added. Attention counts accurate.
- **Job 23 (Draft revision notes):** Operator influence box (textarea) on Outreach Queue, Meetings Queue, and Conversation page. Notes appended to Claude prompt at generation time via `revision_notes` param on all draft endpoints.

### 2026-03-13 — Job 01 (Customer Analyzer) + Phase 6b (Booking Confirmation)

- **Customer Analyzer DB-first (Job 01):** Added `_get_thread_from_db()` to `agents/customer_analyzer.py` — reads OutreachLog records (all directions, all dry_run states) as the primary data source, formatted as `[OUTBOUND date] Subject: ...` / `[INBOUND date]` thread strings. `analyze_customer()` now uses DB as primary source when ≥ 2 messages exist; falls back to Gmail API for thin/empty threads (covers 8 live email customers with no OutreachLog). Added skip logic (don't re-analyze if profile exists) and `--force` CLI flag to overwrite all profiles unconditionally. Reply detector passes `force=True` on post-reply profile refresh so new reply context is always incorporated.
- **Booking confirmation auto-detection (Phase 6b):** `_auto_create_booking()` in `reply_detector.py` fires when classifier returns `booking_confirmed`. Reads extracted `booking_slot_start/end` from the queued confirmation draft (set by `conversation_agent._generate_booking_confirmation`), creates `Booking` record (`source=ai_outreach`, `status=confirmed`), flips `Customer.reactivation_status → booked`, marks `OutreachLog.converted_to_job = True`, and creates a Google Calendar event. GCal step has graceful fallback — booking is always saved even if calendar scope is unavailable. Conversation workspace already displays the booked state when `active_booking` exists — no UI changes needed.

### 2026-03-13 — Email Formatting Fix, Conversation Agent Improvements, Regenerate Draft Fix

- **Email line-break fix (multipart/alternative):** root cause was Python's `MIMEText` with `charset="utf-8"` applying quoted-printable encoding, wrapping lines at 76 chars with `=\r\n` soft breaks. Gmail on the recipient side stripped `=` but kept `\r\n`, causing hard line breaks. Fix: `send_email()` now sends `multipart/alternative` (plain text + HTML). HTML part converts paragraphs to `<p>` tags via `_plain_to_html()` so text reflows naturally. Plain text part retained as fallback.
- **Conversation agent context-awareness:** `AGENT_SYSTEM` now scopes "respect their decision" rule to the *current* message only. Agent explicitly grants requests when customer previously declined something (e.g. a call) but asks for it again later. `NOT_INTERESTED_PROMPT` removed hardcoded "no proposed times" ban — now only skips if customer didn't ask. `PRICE_RESPONSE_PROMPT` gives ballpark ranges and offers alternatives without hard-pushing.
- **Regenerate draft context-aware:** `POST /api/outreach/{id}/regenerate` now reads `response_classification` from the existing draft. If it's a conversation reply, routes to `conversation_agent.generate_response` with the correct classification and latest inbound message as context. Falls back to cold reactivation draft only when no classification is set.
- **Signoff formatting:** `AGENT_SYSTEM` now instructs agent to put the name on its own line (`Best,\nArjuna` not `Best, Arjuna`).

### 2026-03-13 — Conversation State Fixes, Classifier Overhaul, Updates Inbox, Internal Metrics
- Updates inbox, reply detector all-customer scan, unsubscribe_request classifier category, NOT_INTERESTED_PROMPT, booking_intent guardrails, per-page analytics, server-side event tracking, email CRLF normalization. See full history in git.

---

## Build Phases Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| 1 | Foundation (models/config/DB) | ✅ Complete | Stable |
| 2 | Tone Profiler + Dashboard UI | ✅ Complete | Stable |
| 3 | Reactivation Analyzer + Approval Queue | ✅ Complete | Stable |
| 4 | Gmail Send + Follow-up Intelligence + Conversation UX | ✅ Complete | Fully operational |
| 5 | Customer Scoring + Revenue Dashboard | ✅ Complete | Live |
| 6 | Booking Conversion Flow + Google Calendar | ✅ Complete | Classifier, calendar, meetings queue live |
| 6b | Booking Confirmation Detection + Calendar Write-back | ✅ Complete | Auto-booking on confirmed reply; GCal write-back |
| 7 | Customer Analytics Page + Product Analytics | ✅ Complete | Jobs 03 + 04 done; per-page analytics + error tracking |
| 8 | Operator Config + Agent Quality | 🔵 Active | Jobs 05 ✅, 09 ✅, 31 ✅ done — Job 06 (Prompt Quality) remaining |
| 9 | SMS Channel (Twilio) | ⬜ Planned | Operator-driven channel selection |
| 10 | Jobber / HousecallPro Integration | ⬜ Planned | After SMS channel complete |
| 11 | Service Interval Prediction | ⬜ Planned | |
| 12 | Outreach Composer Redesign | ⬜ Planned | Dedicated composer page, cold vs reply flow |
| 13 | ML-Trained Scoring Model (sklearn) | ⬜ Planned | Needs real conversion labels |

---

## Phase 8 — Operator Config + Agent Quality (🔵 Active)

**Goal:** Give the operator a configuration page that feeds directly into every agent prompt. Makes Foreman feel like it understands their specific business — not a generic AI tool. Two jobs: build the config UI + storage, then do a focused prompt quality pass using those config values.

**Strategic rationale:** Before SMS and integrations, the email/conversation quality needs to be tight. A seasoned HVAC operator receiving these drafts will immediately know if they sound like AI. Config page unlocks dynamic, business-specific prompts. Prompt sprint makes the underlying drafts sound like a 15-year trade veteran.

### Job 05 — Operator Config Page

**New page:** `/settings` (or `/config`) — operator-facing configuration panel.

**Config fields and how they feed agents:**

| Setting | Type | Feeds Into |
|---|---|---|
| Tone dial | Slider 1–5 (consultative ↔ direct) | All agent system prompts |
| Salesy-ness | Slider 1–5 (low-key ↔ confident push) | Reactivation + follow-up prompts |
| Job type priority ranking | Drag-to-rank list | Scoring engine + reactivation targeting |
| Estimate ranges per job type | Min/max $ per type | Pricing response prompt |
| Seasonal focus months | Multi-select per job type | Reactivation timing logic |
| Business context blurb | Free text (200 char) | All agent prompts as injected context |

**Storage:** New JSON column `operator_config` on `Operator` model (SCHEMA_PATCHES migration). Default values pre-populated so agents always have something to work with.

**Agent injection:** New `core/operator_config.py` helper — `get_agent_context(operator_id, db)` returns a formatted string block injected at the top of every agent system prompt.

**Tasks:**
- [ ] `core/models.py` — add `operator_config JSON` to Operator
- [ ] `core/database.py` — SCHEMA_PATCHES migration for new column
- [ ] `core/operator_config.py` — `get_agent_context()`, `get_config()`, `save_config()`, default values
- [ ] `api/app.py` — `GET /settings` page route + `POST /api/settings` save endpoint
- [ ] `templates/settings.html` — config UI: sliders, drag-rank, min/max inputs, free text, save button
- [ ] `agents/reactivation.py` — inject operator context block into system prompt
- [ ] `agents/conversation_agent.py` — inject operator context block into all prompts
- [ ] `agents/follow_up.py` — inject operator context block
- [ ] `core/scoring.py` — read job type priority ranking for scoring weight adjustment
- [ ] `templates/base.html` — add Settings link to sidebar nav

### Job 06 — Prompt Quality Sprint

**Goal:** Make every agent draft sound like it came from a skilled, professional trade operator — not AI-generated outreach. Blue-collar competence: direct, specific, no fluff, confident on pricing.

**Scope:** Rewrite/refine prompts in `agents/reactivation.py`, `agents/conversation_agent.py`, `agents/follow_up.py`. Use operator config values as dynamic inputs. Test against 10 real scenario customers.

**Prompt targets by agent:**

*Reactivation Analyzer (cold outreach):*
- Reference the actual job in the subject line, not generic "check in"
- Specific to job type (tune-up vs repair vs install)
- Short — operators write short emails
- No corporate language ("I wanted to reach out", "I hope this finds you well")

*Conversation Agent — not_interested:*
- Answer the customer's actual question with real trade knowledge
- Don't hedge on pricing — give a real range with confidence
- No re-pitching in the same message

*Conversation Agent — booking_intent:*
- Propose slots like a busy contractor would ("I have Tuesday morning or Thursday after 2")
- Not "I would be happy to schedule a time that works for both of us"

*Conversation Agent — price_inquiry:*
- HVAC-specific ranges by job type (pulled from operator config estimate ranges)
- Acknowledge variability without being wishy-washy

*Follow-up Sequencer:*
- First follow-up: shorter, warmer ("Just wanted to make sure this didn't get buried")
- Second follow-up: close the loop gracefully ("No worries if the timing isn't right")
- No guilt-trip language

**Tasks:**
- [ ] Pull 10 real draft examples from live app / seed scenarios
- [ ] Rewrite `REACTIVATION_PROMPT` in `agents/reactivation.py`
- [ ] Rewrite `AGENT_SYSTEM`, `NOT_INTERESTED_PROMPT`, `PRICE_RESPONSE_PROMPT`, `BOOKING_INTENT_PROMPT` in `agents/conversation_agent.py`
- [ ] Rewrite follow-up sequence prompts in `agents/follow_up.py`
- [ ] Add operator config injection to all three agents (depends on Job 05)
- [ ] Test: run Reactivation Analyzer against 5 customers, review drafts, iterate

### Job 09 — Revenue Data Integrity

**Goal:** Enforce three data capture checkpoints so revenue metrics are actually reliable. Operators cannot close a post-visit conversation without logging what happened. Surface pending items in the Updates inbox. In-app only — no external nudges. ERP/CRM integration will retroactively backfill gaps later.

**Execution:** Independent of Jobs 05/06 — can run in parallel or after. Independent of SMS (Jobs 07/08).

**Three checkpoints:**

1. **Booking creation** — `estimated_value` is required (or explicit "Value Unknown") before a booking can be confirmed. Enforced on both auto-detected (`booking_confirmed`) and manually scheduled bookings.
2. **Post-visit outcome** — new `PostVisitAgent` runs daily, finds all bookings where `scheduled_at` has passed and `visit_outcome = "pending"`. Sets `Customer.needs_post_visit_update = True`. Conversation is API-locked (403) until operator logs outcome. Customer surfaced in `/updates` under "Needs Post-Visit Update" section.
3. **Quote + close** — three outcome buttons in conversation workspace: **Quote Given** (captures `quote_given` amount) → **Job Won** (captures `final_invoice_value`, sets `job_won = True`) / **No Show** (clears lock, no further capture).

**New `Booking` fields:**
```
visit_outcome         VARCHAR   DEFAULT 'pending'   # pending / confirmed / no_show
quote_given           FLOAT     nullable
quote_given_at        TIMESTAMP nullable
job_won               BOOLEAN   DEFAULT False
final_invoice_value   FLOAT     nullable
closed_at             TIMESTAMP nullable
```

**New `Customer` field:** `needs_post_visit_update BOOLEAN DEFAULT False`

**New agent:** `agents/post_visit.py` — startup + daily APScheduler.

**New API routes:** `/api/booking/{id}/estimate`, `/api/booking/{id}/quote`, `/api/booking/{id}/close`, `/api/booking/{id}/no-show`, `/api/updates/post-visit`

**Updates inbox:** New "📋 Needs Post-Visit Update" section at top of `/updates` — red/urgent, counts toward sidebar badge.

**Analytics addition:** Revenue Pipeline card on `/analytics` showing Booked → Visit Confirmed → Quote Given → Job Won with conversion rates and dollar amounts at each stage.

**Tasks:**
- [ ] `core/models.py` — new Booking fields + Customer.needs_post_visit_update
- [ ] `core/database.py` — SCHEMA_PATCHES for all new columns
- [ ] `agents/post_visit.py` — PostVisitAgent + APScheduler registration
- [ ] `api/app.py` — 5 new booking endpoints + 403 lock enforcement
- [ ] `templates/updates.html` — "Needs Post-Visit Update" section
- [ ] `templates/conversation_detail.html` — post-visit banner + outcome modals
- [ ] `templates/meetings.html` / booking creation — mandatory estimate enforcement
- [ ] `core/analytics.py` — `get_revenue_pipeline()` function
- [ ] `templates/analytics.html` — Revenue Pipeline card

---

## Phase 9 — SMS Channel (Twilio) (⬜ Planned)

**Goal:** Add SMS as a parallel outreach and conversation channel alongside email. Operator selects the channel per customer before drafting. Same agent pipeline (classify, draft, follow-up) — different transport.

**Strategic rationale:** HVAC operators live in their phones. Customers respond to SMS faster and at higher rates than email, especially for service businesses. This is the biggest single unlock for conversion rates after the core loop is solid.

**Design decisions:**
- Channel is **operator-driven** — operator selects Email or SMS per customer before drafting (not auto-selected)
- SMS conversations fold into the existing conversation workspace — channel indicator per message in timeline
- Two-way SMS: Twilio webhook receives replies → same reply detector pipeline → classifier → draft
- SMS drafts are shorter (160–320 char target), no subject line, more conversational
- `OutreachLog.channel` field: `email` (default, existing) or `sms` (new)

### Job 07 — Twilio Integration + SMS Send Path

**Tasks:**
- [ ] `requirements.txt` — add `twilio`
- [ ] `.env.example` — add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- [ ] `core/config.py` — add Twilio env vars
- [ ] `integrations/sms.py` — `send_sms(to_number, body, operator_id)`, returns `sms_sid`
- [ ] `core/models.py` — add `channel VARCHAR DEFAULT 'email'` to `OutreachLog`, `phone_number VARCHAR` to `Customer`
- [ ] `core/database.py` — SCHEMA_PATCHES for new columns
- [ ] `api/app.py` — `POST /webhook/twilio/inbound` — Twilio inbound SMS webhook handler
- [ ] `agents/reply_detector.py` — Pass 3: scan for unlogged inbound SMS (via Twilio API or webhook state)
- [ ] `api/app.py` — update draft send endpoints to route to `send_sms()` when `channel=sms`

### Job 08 — SMS Draft Pipeline + UX

**Tasks:**
- [ ] `agents/conversation_agent.py` — `SMS_SYSTEM` prompt variant: short, no subject, conversational
- [ ] `agents/reactivation.py` — SMS draft mode: shorter body, no subject line
- [ ] `agents/follow_up.py` — SMS follow-up variant
- [ ] `templates/customer.html` — channel selector (Email / SMS toggle) before Draft Outreach action
- [ ] `templates/conversation_detail.html` — channel badge per message in timeline (📧 / 💬)
- [ ] `templates/outreach.html` — SMS drafts shown with channel badge, char count indicator
- [ ] `api/app.py` — draft generation endpoints accept `channel` param; pass to agent

---

## Phase 10 — Jobber / HousecallPro Integration (⬜ Planned)

**Goal:** Pull customer + job history directly from the operator's existing FSM tool. Removes the manual import problem entirely — onboarding goes from "export a CSV" to "connect your Jobber account."

**Design decisions:**
- Read-only integration first: pull customers + job history, no write-back
- Jobber first (larger market share in target segment), HousecallPro second
- Syncs run on a schedule (daily) + on-demand via Agents page
- Imported customers merge with existing records by email address (dedup key)
- `Customer.source` field: `manual`, `jobber`, `housecallpro`

**Tasks (high level — detailed plan TBD):**
- [ ] Jobber OAuth integration (`integrations/jobber.py`)
- [ ] Pull clients + job history from Jobber API
- [ ] Map Jobber job types → Foreman job type taxonomy
- [ ] Scheduled daily sync + Run Now button on Agents page
- [ ] Customer merge/dedup logic by email
- [ ] HousecallPro integration (parallel structure to Jobber)
- [ ] Sync status visible on customer detail page (`source`, `last_synced_at`)

---

## Backlog / TODOs

### BUG — Stale Customer Analyzer Profiles After Reseed
- **Symptom:** After wiping + reseeding the DB and rerunning Customer Analyzer, a specific customer's profile still shows old/stale data from before the reseed.
- **Likely cause:** Customer Analyzer reads from Gmail API (`get_correspondence()`) — Gmail still has the old real emails. Correct behavior for live addresses but confusing in test context.
- **Fix plan:** Add `analyzed_at` timestamp to customer profile UI so staleness is visible. Consider `--force` flag behavior in reseed script.
- **Files:** `agents/customer_analyzer.py`, `data/reseed.py`

### IMPROVEMENT — Agent Orchestration & Run-Order Documentation
- Agents page doesn't yet show trigger type or `next_run_at`
- Pipeline timing not documented in UI
- Durable scheduler (survive dyno restart) not yet implemented — acceptable for now

### Other Backlog
- **Durable scheduler**: move reply_detector + follow_up to cron/Celery (survive dyno restarts)
- **Email draft quality loop**: operator feedback signal, prompt A/B testing
- **Voice profiles from Gmail**: generate profiles from actual sent mail instead of manual seed
- **Multi-tenant audit**: all queries filter by operator_id — audit before second user onboards
- **Outreach composer redesign** (Phase 12): dedicated composer page, cold vs reply flow

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

**Phase 13 ML upgrade:** Once 3–6 months of real conversion outcomes exist, retrain using `converted_to_job` as label with sklearn RandomForest.

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

**Key rules:**
- Decline + question → `not_interested` (never `booking_intent` or `callback_request`)
- `unsubscribe_request` requires final, unambiguous language — soft declines always land on `not_interested`
- `not_interested` does NOT set `reactivation_status = "unsubscribed"` — customer stays active

---

## Known Risks / Watch-outs

- `reply_detector` + `follow_up` run as APScheduler background threads — will miss cycles on dyno restart. Acceptable for now.
- Single-tenant: `OPERATOR_ID = 1` hardcoded throughout. Must audit before onboarding second operator.
- Stale customer profiles after reseed: Customer Analyzer re-reads Gmail API which has old real emails. See Backlog.

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
| 2026-03-11 | Scoring approach | Rules-based weighted scorer first; ML model deferred to Phase 13 |
| 2026-03-11 | Phase 6 scope | Merged response classifier + booking conversion + Google Calendar into single phase |
| 2026-03-11 | Email simulation | Separate tool (`tools/email_simulator.py`) using real owned Gmail addresses — not part of production app |
| 2026-03-12 | Queue routing | booking_intent drafts → /meetings; everything else → /outreach. Discriminator: OutreachLog.response_classification |
| 2026-03-12 | One-click actions | Dashboard action buttons POST to /api/action/* which generate synchronously then redirect |
| 2026-03-12 | Email threading | send_email() sets In-Reply-To + References MIME headers; ensures replies land in same thread |
| 2026-03-12 | Queue badge count | Only counts approval_status="pending" items |
| 2026-03-12 | Reseed data | 200 customers: 8 live email addresses, 40 scenario customers, 152 bulk generated |
| 2026-03-12 | Analytics page scope | `/analytics` is read-only insight page — no actions, that's the dashboard |
| 2026-03-12 | Product analytics privacy | `edit_pct` is computed metric. No PII in event properties. Session IDs are random UUIDs. |
| 2026-03-12 | `booking_confirmed` vs `booking_intent` | `booking_intent` = wants to book; `booking_confirmed` = specific time accepted. Only confirmed triggers auto-Booking. |
| 2026-03-12 | Plans scaffold | Feature work tracked in `plans/` — one folder per job, `plan.md` + `tasks/`. Authored in Claude app, executed in Claude Code. |
| 2026-03-12 | RFC threading fix | `In-Reply-To` must reference customer's reply RFC Message-ID — stored as `rfc_message_id` on inbound OutreachLog |
| 2026-03-12 | Dual-pass reply detection | Pass 1 = stored gmail_thread_id scan; Pass 2 = email-address inbox scan. Per-message RFC dedup. |
| 2026-03-12 | Run Now synchronous | Agent run endpoints block until completion; JS auto-reloads. |
| 2026-03-12 | Conversation draft on demand | Draft only generated on explicit user click — not on page load. |
| 2026-03-13 | unsubscribe_request split | `not_interested` = soft decline, stays active. `unsubscribe_request` = explicit permanent opt-out only. |
| 2026-03-13 | Reply detector all-customer scan | Removed ACTIVE_STATUSES/SCAN_STATUSES filters. All customers with outbound threads scanned. |
| 2026-03-13 | not_interested draft behavior | Conversation agent answers customer's question; no rebooking push. |
| 2026-03-13 | booking_intent guardrails | Decline + question → not_interested. Affirmative explicit desire required for booking_intent. |
| 2026-03-13 | Updates inbox | /updates consolidates: needs response, overdue follow-ups, recent inbound, upcoming follow-ups. |
| 2026-03-13 | Email formatting (multipart/alternative) | send_email() sends multipart/alternative. HTML part via _plain_to_html() uses <p> tags. |
| 2026-03-13 | Conversation agent temporal awareness | "Respect their decision" rule scoped to current message only. |
| 2026-03-13 | Regenerate draft context routing | Routes to conversation_agent for reply drafts using stored response_classification. |
| 2026-03-13 | Customer Analyzer DB-first | OutreachLog primary source (>=2 messages), Gmail fallback for thin threads. --force flag. |
| 2026-03-13 | booking_confirmed auto-booking | _auto_create_booking() in reply_detector creates Booking + GCal event. GCal failure non-fatal. |
| 2026-03-13 | Roadmap resequenced | Phase 8 = Operator Config + Prompt Quality. Phase 9 = SMS (Twilio, operator-driven channel). Phase 10 = Jobber/HousecallPro integration. ML scoring deferred to Phase 13. |
| 2026-03-13 | SMS channel design | Operator-driven (not auto-selected). Same conversation workspace, channel badge per message. OutreachLog.channel field. SMS drafts shorter, no subject line. |
| 2026-03-13 | Revenue data integrity | Three enforced checkpoints: booking creation (mandatory estimate), post-visit outcome (conversation lock), quote + close capture. In-app only — no external nudges. ERP integration will backfill retroactively. |
| 2026-03-13 | Post-visit lock | Customers with pending visit_outcome are API-locked — archive/close endpoints return 403. Cleared only when operator logs Quote Given, Job Won, or No Show. |
| 2026-03-13 | Post-visit surface location | Needs Post-Visit Update customers surfaced in /updates inbox (not a 5th dashboard group) — keeps dashboard clean, /updates is already the operator's attention page. |

---

## New Chat Resume Prompt

**Files to attach:** `PROJECT_PLAN.md`, `README.md`, and whichever code files are relevant to the specific task.

```text
I'm continuing work on Foreman — an AI reactivation system for HVAC & field service contractors.

Read PROJECT_PLAN.md and README.md first for full context, then look at any code files attached.

Current state (2026-03-14): Phases 1–7 + 6b all complete. Jobs 11–30 complete.
Live: https://web-production-3df3a.up.railway.app

Completed recently (Jobs 24–30):
- Job 24: state_reconciler.py — 5 idempotent rules, runs every 15 min.
- Job 25: gcal_sync.py — detects deleted/rescheduled GCal events, orphaned/time_changed flags, every 6 hrs.
- Job 26: Edit appointment form on conversation page. POST /api/booking/{id}/edit, patches GCal.
- Job 27: Agents page grouped into 5 sections with labels + descriptions.
- Job 28: Meeting queue status tags fixed. health_override + dismissHealth/clearHealthOverride.
- Job 29: Conversations page: donut chart inline with filter bar, health_key/health_color/last_contact_display.
- Job 30: Command Center redesign — chronological feed (seen/unread cookie) + 2×2 quadrant grid.
- Deploy fixes: google_cal_event_id in SCHEMA_PATCHES, invite_sent in Enum, Command Center crash fix.
- Conversations page: restored card layout (compact), donut inline with filters.
- Opportunity value popup fix: wrong endpoint URL (/update-notes → /notes), sessionStorage debounce.

Active: Phase 8 — Operator Config + Agent Quality + Revenue Data Integrity
- Job 05: Operator Config page (/settings) — sliders, job ranking, estimate ranges, business context
- Job 06: Prompt Quality Sprint — rewrite reactivation/conversation/follow-up prompts using config values
- Job 09: Revenue Data Integrity — mandatory booking estimates, post-visit lock, quote/close capture, PostVisitAgent
- Job 31: Priority Dashboard Redesign — overview section, metric cards
- Job 32: Analytics Overhaul — backlog (product discussion first)

Next after Phase 8: Phase 9 (SMS via Twilio, operator-driven), Phase 10 (Jobber integration).

Make code changes directly and summarize what changed.
```

---

### Per-task file lists

**Phase 8 — Operator Config (Job 05):**
- `PROJECT_PLAN.md`
- `core/models.py`
- `core/database.py`
- `api/app.py`
- `templates/base.html`

**Phase 8 — Prompt Quality Sprint (Job 06):**
- `PROJECT_PLAN.md`
- `agents/reactivation.py`
- `agents/conversation_agent.py`
- `agents/follow_up.py`
- `core/operator_config.py` (new — from Job 05)

**Phase 8 — Revenue Data Integrity (Job 09):**
- `PROJECT_PLAN.md`
- `core/models.py`
- `core/database.py`
- `agents/reply_detector.py`
- `api/app.py`
- `templates/conversation_detail.html`
- `templates/updates.html`
- `core/analytics.py`

**Phase 9 — SMS Send Path (Job 07):**
- `PROJECT_PLAN.md`
- `core/models.py`
- `core/database.py`
- `integrations/sms.py` (new)
- `api/app.py`

**Phase 9 — SMS Draft Pipeline + UX (Job 08):**
- `PROJECT_PLAN.md`
- `agents/conversation_agent.py`
- `agents/reactivation.py`
- `agents/follow_up.py`
- `agents/reply_detector.py`
- `templates/conversation_detail.html`
- `templates/outreach.html`
- `templates/customer.html`

**Any API / UI work:**
- `PROJECT_PLAN.md`
- `api/app.py`
- whichever `templates/*.html` file is relevant

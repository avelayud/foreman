# Job 24 — Conversation State Agent + Health Override

**Phase:** 8 (quality + reliability — parallel with Jobs 05/06/09)
**Status:** ✅ Complete
**Depends on:** Nothing — fully independent
**Goal:** A proactive background agent that continuously reconciles drifted conversation state, plus a manual health override so operators can dismiss false-positive alerts. Together these eliminate the class of bugs where the app shows "Needs Response" or "Action Required" for situations that are already resolved.

---

## Background

Right now, status and health chips are updated exclusively by operator actions (approve, send, mark booked) and the reply detector (new inbound reply). If anything changes outside those two paths — a booking gets cancelled, a draft gets deleted, a GCal acceptance comes in via a different thread — nothing catches it. The conversation gets stuck in a misleading state until the operator manually notices and intervenes.

The Sam Keller bug is the canonical example: invite was sent, booking was confirmed in GCal, but the conversation still showed "Action Required — Pending Scheduling" because `latest_classification = booking_confirmed` and the booking record wasn't linked. The template fix (Job 14) patched the display, but the underlying state was still wrong.

This job makes state self-healing. The agent runs every 15 minutes and applies a deterministic set of reconciliation rules. It also introduces `health_override` — a lightweight operator escape hatch to dismiss false-positive health chips without corrupting the underlying status.

---

## The Reconciliation Rules

The state reconciler runs 5 rules on every active conversation in sequence. Rules are applied in priority order — stop at the first rule that fires for each customer.

### Rule 1 — Orphaned `invite_sent`
**Condition:** `reactivation_status == "invite_sent"` AND no active booking (status in `tentative`, `confirmed`, `complete`) exists
**Action:** Reset `reactivation_status → "replied"`
**Why:** The invite was sent but the booking record is gone (deleted, cancelled, or never auto-created because no slot was extracted). Customer needs re-engagement.

### Rule 2 — Orphaned `booked`
**Condition:** `reactivation_status == "booked"` AND no active booking exists
**Action:** Reset `reactivation_status → "replied"`
**Why:** Booking was removed (operator deleted it, or it was cancelled). Customer is effectively back in an active conversation state.

### Rule 3 — Calendar acceptance confirms booking
**Condition:** Any inbound OutreachLog for this customer has `response_classification == "calendar_accepted"` AND an active booking exists with status `tentative` or `confirmed` AND `reactivation_status in ("invite_sent", "replied")`
**Action:** Set booking `status = "confirmed"`, set `reactivation_status = "booked"`
**Why:** This is the fix for cases where reply_detector correctly logged the acceptance (from the same Gmail thread) but didn't flip the booking/status — covering pre-existing data and any edge cases where the inline handler in reply_detector missed it.

### Rule 4 — Stale `draft_queued=True` with deleted draft
**Condition:** Inbound OutreachLog has `draft_queued = True` AND `response_classification` is set (not `calendar_accepted`, not `unsubscribe_request`) AND there is NO corresponding outbound dry_run draft for this customer with a `created_at` after the inbound log
**Action:** Reset `draft_queued = False` on the inbound log
**Why:** Operator deleted the draft from the queue. The response generator will not re-draft because it filters `draft_queued = True`. Resetting this flag allows regeneration when the operator wants a new draft.

### Rule 5 — Health override expiry
**Condition:** `health_override` is set on Customer AND a new actionable inbound log exists with `created_at` AFTER `health_override_set_at`
**Action:** Clear `health_override = None`, clear `health_override_set_at = None`
**Why:** A health override is a temporary operator dismissal ("I know about this, not urgent"). When a new genuine reply arrives, the dismissal must expire so the operator sees the new activity.

---

## Health Override

A new lightweight mechanism for operators to dismiss health chip alerts without changing the underlying status.

### New `Customer` fields
```python
health_override         = Column(String, nullable=True)      # awaiting_reply | invite_sent | closed
health_override_set_at  = Column(DateTime, nullable=True)    # when operator set it
```

Valid override values match health chip keys: `awaiting_reply`, `invite_sent`, `closed`.

SCHEMA_PATCHES entries for both columns.

### How it works in `_conversation_health()`
When `customer.health_override` is set, the function returns the override state instead of computing from timestamps + status. The override has `needs_response=False` and `needs_follow_up=False` to suppress all banners.

Since `_conversation_health()` currently takes `(status, last_outbound_at, last_inbound_at)` and has no access to customer fields, there are two options:
- Option A: Pass `health_override` as a 4th parameter (preferred — minimal change)
- Option B: Compute override check at every call site before calling `_conversation_health()`

**Use Option A.** Add `health_override: str | None = None` as the 4th param. When set, return the override health dict immediately before any other logic.

```python
def _conversation_health(status, last_outbound_at, last_inbound_at, health_override=None):
    if health_override:
        meta = CONVERSATION_HEALTH_META.get(health_override, CONVERSATION_HEALTH_META["awaiting_reply"])
        return {"key": health_override, "label": meta["label"], "chip_cls": meta["chip_cls"],
                "rank": meta["rank"], "needs_response": False, "needs_follow_up": False}
    # ... rest of existing logic unchanged
```

All existing call sites pass no 4th argument so they're unaffected. The conversation detail page is the only one that passes `health_override` — it reads it from the customer record.

### UI — Dismiss button on health chip
In `templates/conversation_detail.html`, add a "✕" dismiss button next to the "Needs Response" or "Needs Follow-up" health chip. Clicking it calls `POST /api/conversation/{id}/dismiss-health` which sets `health_override = "awaiting_reply"` and `health_override_set_at = now()`.

When an override is active, show a small `◎ Auto` link next to the chip that calls `POST /api/conversation/{id}/clear-health-override` to restore computed health.

The dismiss button ONLY shows for `needs_response` and `needs_follow_up` chips — not for `awaiting_reply`, `invite_sent`, or `closed` (those are already calm states).

---

## New Agent — `agents/state_reconciler.py`

```python
"""
agents/state_reconciler.py
Conversation State Reconciler.

Scans all active customers and applies 5 deterministic reconciliation rules
to fix drifted conversation state. Safe to run frequently — each rule is
idempotent. Returns count of customers whose state was corrected.

Usage:
    python -m agents.state_reconciler --operator-id 1
"""

def run(operator_id: int) -> int:
    """Apply reconciliation rules to all active conversations.
    Returns total number of state corrections made."""
```

Rules are applied in a single DB pass per customer. Each correction is logged to stdout with customer_id + what changed (for debugging). No LLM calls — this is pure DB state reconciliation.

**Schedule:** Startup + every 15 minutes via APScheduler (same scheduler instance as other agents).

---

## New API Routes

| Method | Path | Description |
|---|---|---|
| POST | `/api/conversation/{id}/dismiss-health` | Set `health_override = "awaiting_reply"`, `health_override_set_at = now()` |
| POST | `/api/conversation/{id}/clear-health-override` | Clear `health_override` and `health_override_set_at` |
| POST | `/api/agent/run-state-reconciler` | Run state reconciler synchronously (for Agents page Run Now) |

---

## Agents Page

Add to the agents list in `api/app.py`:

```python
{
    "key": "state_reconciler",
    "name": "Conversation State Reconciler",
    "icon": "🔄",
    "description": "Runs every 15 minutes. Scans all active conversations and fixes drifted state: orphaned invite_sent/booked statuses, stale draft_queued flags, calendar acceptances that weren't processed. The safety net that keeps health chips accurate without operator intervention.",
    "status": "active",
    "status_label": "Active (every 15 min)",
    "last_run_at": _agent_last_run.get("state_reconciler"),
    "stat_label": "Corrections made",
    "stat_value": str(state_corrections_today),  # new counter
    "cli": "python -m agents.state_reconciler --operator-id 1",
    "phase": "Phase 8",
}
```

Add `Run Now` button. Add to `_agent_last_run` dict.

---

## Tasks

- [ ] `task_01_model_fields.md` — `Customer.health_override` + `Customer.health_override_set_at` + SCHEMA_PATCHES
- [ ] `task_02_state_reconciler_agent.md` — `agents/state_reconciler.py` (5 rules, idempotent)
- [ ] `task_03_health_override_param.md` — `_conversation_health()` 4th param + all call sites pass customer's override
- [ ] `task_04_api_routes.md` — dismiss + clear-override endpoints + run-state-reconciler endpoint
- [ ] `task_05_scheduler.md` — register state_reconciler in APScheduler (every 15 min) + startup run
- [ ] `task_06_agents_page.md` — add state_reconciler to agents list + Run Now button
- [ ] `task_07_conversation_ui.md` — dismiss button on health chip + auto restore link in conversation_detail.html

---

## Files to Attach in Claude Code

```
PROJECT_PLAN.md
core/models.py
core/database.py
agents/state_reconciler.py  (new — won't exist yet)
api/app.py
templates/conversation_detail.html
```

---

## Key Constraints

- All 5 rules must be **idempotent** — running 10 times in a row changes nothing after the first application
- No LLM calls — this is pure state reconciliation, must be fast (< 2s for 200 customers)
- Corrections are logged to stdout but not exposed in the UI beyond the stat counter — keeps the operator UI clean
- `health_override` is scoped to one session of inactivity — expires on the next genuine inbound reply (Rule 5)
- The override does NOT change `reactivation_status` — it only affects the computed health chip

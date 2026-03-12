# Backlog: Conversation Page ↔ Queue Relationship Design

**Added:** 2026-03-12
**Priority:** Medium — affects core outreach UX before Phase 7

---

## The Question

When a customer has an active conversation and there is a message in the Outreach or Meetings Queue for them, the Conversation page could in theory show a draft. Should it? If so, is it the same draft as what's in the queue? What happens when the operator acts on it?

Three unresolved scenarios:

---

## Scenario A — Queue draft IS the same as the conversation page draft

The conversation page shows the pending queue draft inline (read-only or editable). Acting on it from the conversation page is equivalent to acting on it from the queue.

**Problems:**
- Two entry points to the same draft creates confusion about which is canonical.
- If operator edits on the conversation page, does it update the queue draft or create a new one?

**Resolution idea:** Conversation page shows the pending draft in read-only preview form. The only action is "Edit in Queue →" which navigates to the queue entry where the full edit/approve flow lives.

---

## Scenario B — Conversation page can generate a SEPARATE draft from the queue

The operator can generate a one-off message from the conversation page that is independent of any queued draft. They can send it directly from the conversation, bypassing the queue entirely.

**Problems:**
- Bypassing the queue means no approval step and no outreach log tracking before send.
- Inconsistent with the principle that everything goes through the queue first.
- "Just send from conversation" is lower friction but removes the safety net.

**Current state:** The conversation page (after our fix) generates a draft that goes to the queue via "Approve & Queue →". Direct send is NOT possible — this is correct.

---

## Scenario C — Conversation page generates a NEW draft that REPLACES the queued one

If there's already a draft in the queue and the operator generates a new one from the conversation page, the new one replaces the queued one.

**Problems:**
- Implicit replacement could delete work the agent already generated.
- Should be explicit: "Replace queued draft with this one?"

---

## Current Behavior (post-fix, 2026-03-12)

- If a pending draft exists in the queue, conversation page shows a notice and a link to the queue.
- "Generate different draft" button is available, generates a NEW draft and routes it to the queue via "Approve & Queue →".
- Two pending drafts for the same customer can now exist. This is messy.

---

## Recommended Resolution (to implement in Phase 7)

1. **One pending draft per customer at a time.** Before generating a new one, check for an existing pending draft. If one exists, offer: "Replace queued draft?" (destructive, requires confirmation) or "View in Queue →" (non-destructive).
2. **Conversation page never sends directly.** Everything goes through the queue. The conversation page is for reading context and optionally triggering a new draft.
3. **Queue is the canonical action surface.** Conversation page is read + context + draft trigger only.
4. **Clear queue draft on reply.** When a new inbound reply is detected, any existing pending draft for that customer should be auto-discarded (it's now stale). The reply_detector's conversation_agent will generate a fresh one.

---

## Files to Touch (when implementing)

- `api/app.py` — `/api/conversation/{id}/queue` endpoint: check for existing pending draft, accept `force=True` flag to replace
- `templates/conversation_detail.html` — "Generate different draft" → confirmation modal
- `agents/reply_detector.py` — discard stale pending draft on new inbound reply before generating fresh one

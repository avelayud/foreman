# Job 28 — Fix Meeting Queue Status Tag

**Phase:** 8
**Status:** ⬜ Not started
**Depends on:** Nothing — fully independent
**Goal:** Remove the misleading "Meeting Confirmed" status tag from draft meeting invites in the queue that have not been sent yet. A draft is not a confirmation — it's a proposed invite awaiting operator review.

---

## Background

When the response generator creates a `booking_confirmed` draft for the Meetings Queue, the timeline in the conversation shows a queued card with a "Meeting Confirmed" tag. This is wrong — the invite has not been sent, so the customer has not been confirmed. It looks like a sent confirmation when it's just a draft.

Similarly, any status chip or label associated with a queued (unsent, `dry_run=True`) booking_confirmed OutreachLog should not say "confirmed" — it should indicate pending review.

---

## Affected Locations

### 1. Timeline card in `templates/conversation_detail.html`

Current (line ~155):
```html
{% if event.response_classification == 'booking_confirmed' %}📅 Meeting Invite · In Queue{% else %}⏳ Queued Draft{% endif %}
```
This label is already correct ("Meeting Invite · In Queue"). But the `cls-calendar` badge shown for `outbound` + `booking_confirmed` classification says "📅 Calendar Invite" — this shows on SENT outbound logs, which is fine. Check that queued drafts don't also get this badge.

Currently the badge logic (line ~185-191):
```html
{% elif event.type == 'outbound' %}
  {% if event.response_classification == 'booking_confirmed' %}
    <span class="cls-badge cls-calendar">📅 Calendar Invite</span>
```
This fires for ALL outbound `booking_confirmed` logs, including queued drafts that were never sent. A queued event's type would be `queued`, not `outbound`, so the badge doesn't actually show. **Verify this in the template logic — if queued events don't show the outbound badge, no change is needed here.**

### 2. Meetings Queue page — `templates/meetings.html`

The meetings queue shows each draft with a status indicator. Check if any tag or chip says "Confirmed" or "Meeting Confirmed" on a dry_run draft. If so, change it to "Pending Review" or "Draft Ready".

### 3. Conversations list — status pills

On `/conversations`, if a customer's conversation card shows a "Meeting Confirmed" chip/label for a customer who only has a queued draft (not yet sent), change that chip to something accurate like "Invite Queued" or "Draft Ready".

Check `api/app.py` GET /conversations route — look for where `reactivation_status` or `latest_classification` gets turned into a display label. If `booking_confirmed` maps to "Meeting Confirmed" label, add a check: only show "Meeting Confirmed" when `dry_run=False` (actually sent).

### 4. Conversation detail — action banner

The action banner already correctly says "Meeting Invite Queued for Review" when `pending_booking_log_id` is set. This is correct. No change needed.

---

## Specific Changes

### `templates/meetings.html`
Read the file. Find any status badge or label that says "Confirmed" on a card that is a dry_run draft. Change to "Draft — Pending Review" or similar neutral label.

### `api/app.py` — GET /conversations
Find where conversation items get their `latest_classification_label` or status display text. If `booking_confirmed` produces "Meeting Confirmed" text, gate it:
- If the latest booking_confirmed log is `dry_run=True` → label: "Invite Queued"
- If `dry_run=False` and booking exists → label: "Meeting Confirmed"

### `templates/conversation_detail.html`
The `queued` event type in the timeline correctly shows "📅 Meeting Invite · In Queue" — verify the outbound badge (`📅 Calendar Invite`) does NOT appear for queued events (it shouldn't since type != 'outbound'). If it does appear, add a `dry_run` check.

---

## Tasks

- [ ] `task_01_audit.md` — read meetings.html, conversations template/route, conversation_detail — document every place where "Meeting Confirmed" or similar text appears for unsent drafts
- [ ] `task_02_fix.md` — apply targeted fixes to each affected location based on audit findings

---

## Files to Read First

```
templates/meetings.html
templates/conversations.html (or equivalent)
api/app.py  (GET /conversations route, conversations detail route)
templates/conversation_detail.html
```

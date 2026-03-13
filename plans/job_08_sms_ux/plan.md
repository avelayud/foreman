# Job 08 — SMS Draft Pipeline + UX

**Phase:** 9
**Status:** ⬜ Not started
**Depends on:** Job 07 (Twilio send path must be wired first)
**Goal:** Teach every agent to draft for SMS (shorter, no subject, conversational). Add channel selection to the operator UX. Show SMS vs email clearly in conversation timeline and queues.

---

## Background

Job 07 built the transport layer — outbound sending and inbound webhook. Job 08 makes the product actually usable for SMS: agents produce appropriate SMS drafts, the operator can choose the channel before drafting, and the UI clearly distinguishes email from SMS throughout.

---

## Agent Changes

### SMS Draft Mode

All three draft agents need a SMS variant. Key differences from email:

| | Email | SMS |
|---|---|---|
| Length | 3–5 paragraphs | 1–3 sentences, 160–320 chars target |
| Subject | Required | None |
| Salutation | "Hi [name]," | Often no salutation, or just "[name]," |
| Signoff | "Best,\n[Name]" | Just "[Name]" or nothing |
| Tone | Professional but warm | More conversational, like a text from a contractor |
| Links | Acceptable | Avoid |

### `agents/reactivation.py`

Add `SMS_REACTIVATION_PROMPT` — same intent as `REACTIVATION_PROMPT` but:
- No subject line generated
- Body max 2 sentences
- Example: "Hey [first name], it's [operator] from [business]. It's been about a year — want to get your system checked before summer? I have openings next week."

`generate_draft()` accepts `channel: str = "email"` param. When `channel == "sms"`, uses SMS prompt and skips subject generation.

### `agents/conversation_agent.py`

Add `SMS_SYSTEM` — base system prompt for SMS replies:
- "You are replying via text message. Keep responses to 1–2 sentences."
- "No subject line. No formal salutation. Sign off with just your first name."

`generate_response()` accepts `channel: str = "email"` param. When `channel == "sms"`, prepend `SMS_SYSTEM` constraints.

### `agents/follow_up.py`

Add SMS variants for follow-up 1 and 2:
- Follow-up 1 SMS: "Hey [name], just following up on my message from last week. Still happy to come take a look — [Name]"
- Follow-up 2 SMS: "No worries if the timing's not right. We're here when you need us. — [Name]"

`generate_follow_up()` accepts `channel: str = "email"` param.

---

## UX Changes

### Customer Detail Page (`templates/customer.html`)

Add **channel selector** before the Draft Outreach action button:

```
[ Email ]  [ SMS ]   →   Draft Outreach
```

- Defaults to Email
- SMS option is grayed out if `customer.phone_number` is null (show tooltip: "No phone number on file")
- Selected channel passed to draft generation endpoint as `channel` param
- Persists selection in the page state (not in DB — stateless UI choice)

Add **phone number field** to the customer info panel:
- Editable inline (click to edit, save inline)
- `PATCH /api/customer/{id}` — add `phone_number` to patchable fields

### Conversation Workspace (`templates/conversation_detail.html`)

**Channel badge on each message in timeline:**
- Email messages: 📧 or subtle "Email" label
- SMS messages: 💬 or subtle "SMS" label
- Color-coded: email stays existing blue/gold; SMS gets a distinct color (e.g. teal/green)

**Draft panel:**
- Show char count for SMS drafts (target: under 320 chars, warn at 300+)
- "Send via SMS" vs "Send via Email" on the send button — based on the draft's channel

### Outreach Queue (`templates/outreach.html`)

- Add channel badge to each draft card (📧 Email / 💬 SMS)
- SMS drafts show char count inline

### Dashboard Actions

One-click "Draft Outreach" and "Draft Follow-up" buttons default to email. For now, SMS drafting goes through the customer detail page channel selector (not dashboard one-click — keeps dashboard simple).

---

## API Changes

### Draft generation endpoints
All draft endpoints that currently take `customer_id` should also accept optional `channel: str = "email"` body param. Pass through to agent.

### `PATCH /api/customer/{id}`
Add `phone_number` to patchable fields.

### `POST /api/action/draft-outreach`, `POST /api/action/draft-follow-up`
These one-click dashboard endpoints default to `channel=email` — no change needed for Phase 9. Can be extended later.

---

## Tasks

- [ ] task_01_sms_reactivation_prompt.md — SMS_REACTIVATION_PROMPT + channel param in generate_draft()
- [ ] task_02_sms_conversation_prompt.md — SMS_SYSTEM + channel param in generate_response()
- [ ] task_03_sms_follow_up_prompt.md — SMS follow-up variants + channel param in generate_follow_up()
- [ ] task_04_channel_selector_ui.md — Email/SMS toggle on customer.html + phone_number field
- [ ] task_05_timeline_channel_badges.md — channel badges in conversation_detail.html timeline
- [ ] task_06_outreach_queue_badges.md — channel badges in outreach.html
- [ ] task_07_api_channel_param.md — thread channel param through all draft endpoints
- [ ] task_08_customer_phone_patch.md — PATCH /api/customer/{id} phone_number field

---

## Files to Attach in Claude Code

```
PROJECT_PLAN.md
agents/reactivation.py
agents/conversation_agent.py
agents/follow_up.py
api/app.py
templates/customer.html
templates/conversation_detail.html
templates/outreach.html
```

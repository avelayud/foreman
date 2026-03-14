# Job 12 — Fix Gmail Thread Splitting

**Status:** ⬜ Not started
**Goal:** Replies sent from the app are landing in the customer's inbox as new threads instead of continuing the existing conversation thread. Fix all outbound send paths to correctly thread into the original Gmail conversation.

---

## Background

Gmail threads messages by `In-Reply-To` and `References` headers, NOT by subject line. When we send a reply without the correct `In-Reply-To` header matching the customer's last inbound message RFC ID, Gmail creates a new thread in the recipient's inbox — even though our own inbox shows it as the same thread (because we have the thread_id).

Observed: Sam Keller's inbox received the second outbound as a new thread. A third thread was created later. Subject line changes also contribute — changing the subject while replying causes Gmail to start a new conversation on the recipient's end.

There are two separate send paths that both need fixing:
1. `POST /api/outreach/{log_id}/approve-send` — follow-up replies in existing thread
2. `POST /api/outreach/{log_id}/confirm-booking` — meeting confirmation email

---

## Deliverables

1. `api/app.py` — In `approve_and_send`, always fetch and pass `in_reply_to` (the RFC Message-ID of the customer's last inbound) when sending into an existing thread
2. `api/app.py` — In `confirm_booking`, same fix
3. `api/app.py` — Do NOT allow subject line mutation on replies; if a thread_id exists, keep the subject as `Re: {original_subject}` or pass the original subject unchanged
4. `integrations/gmail.py` — Verify `send_email` correctly sets `In-Reply-To` and `References` headers when `in_reply_to` is provided; add `References` header if missing
5. `api/app.py` — Helper `_get_customer_inbound_rfc_id(customer_id)` — verify it returns the correct RFC ID of the most recent inbound message (not just any message)

---

## Tasks

- [ ] Read `integrations/gmail.py` send_email implementation — check if References header is set
- [ ] Read `_get_customer_inbound_rfc_id` — verify it gets the right message
- [ ] Read approve-send endpoint — trace exactly what thread_id and in_reply_to values are passed
- [ ] Read confirm-booking send path — same trace
- [ ] Fix: ensure both send paths pass `in_reply_to=<last inbound RFC ID>` and `thread_id=<existing thread>`
- [ ] Fix: prevent subject line mutation on replies (strip day/time from subject for booking confirmations)
- [ ] Fix gmail.py to set both `In-Reply-To` and `References` headers

---

## Key Invariant

When replying to an existing conversation:
- `thread_id` = the Gmail thread ID (keeps it in OUR thread view)
- `in_reply_to` = RFC Message-ID of the customer's last message (keeps it in THEIR thread view)
- Subject = unchanged from the original thread (do not inject date/time)

---

## Files to Attach

```
integrations/gmail.py
api/app.py          (search: approve_and_send, confirm_booking, _get_customer_inbound_rfc_id, _gmail_send_message)
```

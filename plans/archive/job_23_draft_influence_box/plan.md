# Job 23 — Draft Message: Operator Influence / Revision Notes

**Status:** ⬜ Not started
**Goal:** Add a "Revision Notes" text box next to the draft body where the operator can describe what to change. When they hit Regenerate, those notes are passed to the agent as additional instructions and incorporated into the new draft.

---

## Background

Currently, the draft panel shows the AI-generated email body. The operator can edit it manually, or click Regenerate to get a completely fresh draft. There's no way to say "make it shorter" or "mention the seasonal tune-up discount" without manually editing the draft.

The Revision Notes box gives the operator a way to influence the regenerated output without rewriting the draft themselves.

---

## Deliverables

### Outreach Queue (`templates/outreach.html`)
1. Add "Revision Notes" textarea next to the body field (smaller, ~3 rows, placeholder: "E.g. Make it shorter, mention the seasonal discount…")
2. Move Regenerate button to below the Revision Notes box (out of the right action panel)
3. Update `regenerateDraft()` JS: include `revision_notes` in the POST body

### Meetings Queue (`templates/meetings.html`)
4. Same change for booking_confirmed card: add Revision Notes next to the Calendar Invite Email body
5. Move Regenerate button below Revision Notes

### Conversation Detail (`templates/conversation_detail.html`)
6. Add Revision Notes textarea above or next to the draft body (when in draft-form state)
7. Move Regenerate button below Revision Notes
8. Update `loadDraft()` / `regenerateDraft()` to pass revision notes

### Backend
9. `api/app.py` — `/api/outreach/{log_id}/regenerate`: accept `revision_notes: str` in request body; pass to `generate_response(revision_notes=...)`
10. `api/app.py` — `/api/meetings/{log_id}/regenerate`: same
11. `api/app.py` — `/api/conversation/{customer_id}/draft`: accept `revision_notes` in POST body
12. `agents/conversation_agent.py` — `generate_response()`: accept `revision_notes` param; if provided, append to system or user prompt: "Operator revision notes: {revision_notes}. Incorporate these changes in the draft."
13. `agents/reactivation.py` — Same for cold outreach regeneration

---

## Tasks

- [ ] Read outreach.html — find the draft body field and regenerate button
- [ ] Read meetings.html — same
- [ ] Read conversation_detail.html — same
- [ ] Read /api/outreach/{log_id}/regenerate endpoint
- [ ] Read conversation_agent.generate_response() signature
- [ ] Add revision_notes textarea to outreach.html
- [ ] Add revision_notes textarea to meetings.html
- [ ] Add revision_notes textarea to conversation_detail.html
- [ ] Move regenerate buttons below revision notes in all three
- [ ] Update JS to include revision_notes in regenerate calls
- [ ] Update regenerate endpoints to accept + pass revision_notes
- [ ] Update generate_response() to incorporate revision_notes

---

## Files to Attach

```
templates/outreach.html
templates/meetings.html
templates/conversation_detail.html
api/app.py          (search: regenerate, /api/outreach/.*/regenerate, /api/meetings/.*/regenerate, /api/conversation/.*/draft)
agents/conversation_agent.py
agents/reactivation.py
```

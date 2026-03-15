# Backlog: Conversation Page Redesign — Opportunity Snapshot, Recap & Operator Prep

**Phase:** Backlog (design discussion first)
**Affects:** `/conversations/{id}` — the individual conversation workspace

---

## Problems to solve

### 1. Opportunity Snapshot

The current opportunity estimate is a static number derived from the scoring engine. It doesn't tell the operator *why* this customer is valuable or what the realistic job scope looks like.

**Goal:** Replace the static dollar figure with a richer opportunity card:
- Estimated job value range (low/high from config ranges)
- Most likely service type (from job history)
- Last service date + what was done
- Why this customer scores high (1-2 sentence rationale)
- Risk flags (e.g., "only replied once before, lukewarm response")

### 2. Conversation Recap & Talking Points

The AI timeline is good for browsing history but doesn't give the operator a quick briefing before engaging. There's no "here's what you need to know before you respond" surface.

**Goal:** A compact recap module above the draft panel:
- Summary of conversation so far (1-3 bullets, updated after each event)
- What the customer last said / their tone
- Suggested talking points for the next message (2-3 bullets Claude generates)
- Whether there are any open questions the operator should address

### 3. Operator Prep for Upcoming Calls / Jobs

When a booking is confirmed and the appointment date is approaching, the operator needs to be prepped — not just reminded. There's no flow for this today.

**Goal:** An "Upcoming Job Prep" module that surfaces when appointment is within 48h:
- Job scope and notes
- Customer preferences and history (from CustomerProfile)
- Suggested things to bring / check before arrival
- Quick link to log the outcome after the visit

This should also be surfaced in the Command Center as a prep prompt ("Appointment tomorrow with Mike Chen — review notes →").

---

## Design questions to resolve

1. Where does the recap live? Above the draft, or in a collapsible sidebar panel?
2. Is the recap auto-generated on page load, or triggered on demand (to avoid excess API calls)?
3. Should talking points be part of the draft generation prompt, or a separate UI element?
4. Operator prep: push notification / Command Center item, or only visible on the conversation page?
5. Should the opportunity snapshot replace the score breakdown, or complement it?

---

## Relevant files

- `templates/conversation_detail.html` — main workspace template
- `agents/conversation_agent.py` — conversation draft + context
- `agents/customer_analyzer.py` — builds CustomerProfile
- `api/app.py` — conversation_detail route (passes context)
- `templates/updates.html` — Command Center (add prep item)

# Job 22 — Updates Page Improvements

**Status:** ⬜ Not started
**Goal:** Each update entry needs a timestamp, the list should sort most-recent-first, and clicking an update should navigate to the individual conversation page (not just the conversations list).

---

## Background

The updates page currently shows recent inbound replies and activity. Issues:
- No timestamp shown on entries — operator can't tell when something happened
- Order is unclear (not guaranteed to be most-recent-first)
- The "Reply" or action link goes to the conversations list, not the specific conversation

---

## Deliverables

1. `api/app.py` — GET /updates route: ensure items are sorted by `created_at DESC` (most recent first)
2. `api/app.py` — Include `created_at` timestamp in each update item dict
3. `templates/updates.html` (or wherever the updates page renders) — Display timestamp on each entry in a compact format (e.g., "Mar 14 · 2:35 PM" or relative "2 hours ago" for recent items)
4. `templates/updates.html` — Change action link from `/conversations` to `/conversations/{customer_id}` — link directly to the individual conversation

---

## Tasks

- [ ] Find the updates page route in app.py (search for GET /updates or similar)
- [ ] Find the updates.html template
- [ ] Add `created_at` to the items dict
- [ ] Sort DESC by created_at
- [ ] Update template to display timestamp
- [ ] Update link to point to individual conversation

---

## Files to Attach

```
api/app.py          (search: /updates, updates route)
templates/          (find updates.html or the template used for the updates page)
```

# Job 30 — Command Center Redesign (formerly Updates Page)

**Phase:** 8
**Status:** ⬜ Not started
**Depends on:** Nothing — fully independent
**Note:** The page has been renamed from "Updates" to "Command Center" in the nav and page header (done 2026-03-14). This job redesigns the content layout.
**Goal:** Redesign the Command Center so it communicates urgency effectively. Replace the oversized grouped sections with: (1) a chronological notification feed at the top showing all updates in time order, and (2) a compact four-quadrant grid below that surfaces each category at a glance with reduced visual footprint.

---

## Background

The current Updates page groups updates into sections (Needs Response, Needs Follow-up, Calendar Updates, etc.). This structure hides urgency — an item that arrived 3 minutes ago sits in the same visual weight as something from last week. Operators scan for the most urgent item, not the most recent in a category.

Two problems with the current layout:
1. **No chronological signal.** Updates in the same section aren't sorted by recency in a way that communicates urgency.
2. **Sections are too large.** Each module occupies roughly a third of the viewport. An operator with 4 active sections has to scroll through a full page of content just to get the overview.

---

## New Layout

### Section 1 — Notification Feed (top, full-width)

A running list of all updates in reverse chronological order, with a timestamp. Think of it like a simple activity feed or inbox.

```
[●] Mar 14, 10:42 AM   Sam Keller replied — "Monday works for me"              Needs Response  [→]
[●] Mar 14, 9:15 AM    Jane Davis appointment time changed in calendar           Calendar        [→]
[○] Mar 13, 4:00 PM    Bob Chen follow-up overdue — 7 days since last outreach  Follow-up       [→]
[○] Mar 12, 11:30 AM   Mike Torres invite sent — awaiting response              Invite Sent     [→]
```

**Each row:**
- Colored dot (filled = unread/active, hollow = seen) — `●` vs `○`
- Timestamp (local time via `est` filter)
- Customer name (bold, links to conversation)
- Short description of the trigger event
- Category badge (colored chip — matches health chip colors)
- View arrow →

**"Unread" definition:** Any item that arrived after the operator's last visit to /updates. Store `last_updates_viewed_at` on the Operator model (or in a session cookie — cookie is simpler, no DB change). When the operator opens /updates, all items older than the last visit are shown as "seen" (hollow dot).

**Limit:** Show last 50 items. Add "Show more →" if count > 50.

---

### Section 2 — Four-Quadrant Summary (below feed)

A 2x2 grid of compact category panels, each roughly half the current module height.

```
┌─────────────────────┬─────────────────────┐
│  Needs Response  4  │  Needs Follow-up  7  │
│  Sam Keller         │  Bob Chen (7d)        │
│  Mike Torres        │  Lisa Park (14d)      │
│  + 2 more →         │  + 5 more →           │
├─────────────────────┼─────────────────────┤
│  Invite Sent  3     │  Calendar Updates  1  │
│  Jane Davis         │  Sam Keller           │
│  + 2 more →         │  Event deleted        │
└─────────────────────┴─────────────────────┘
```

**Each quadrant:**
- Header: category name + count badge
- Up to 2–3 customer rows (name + brief context)
- "View all →" link if count > 3 (filters the feed above, or links to a filtered /conversations view)
- Quadrant uses ~200px height max

**Quadrant categories:**
1. Needs Response (red header) — customers with `health.needs_response = True`
2. Needs Follow-up (amber header) — customers with `health.needs_follow_up = True`
3. Invite Sent (purple header) — customers with `reactivation_status = "invite_sent"`
4. Calendar Updates (blue header) — bookings with `orphaned=True` or `time_changed=True`

---

## "Unread" Tracking

Use a session cookie `last_updates_viewed` with a UTC timestamp. On GET /updates:
1. Read `last_updates_viewed` cookie
2. Mark each feed item as `seen = (item.timestamp < last_viewed)`
3. Set the cookie to `datetime.utcnow()` in the response

No DB change. Cookie expires after 30 days.

---

## Notification Feed — Data Sources

Aggregate from:
- **Inbound OutreachLogs** (`direction=inbound`, `dry_run=False`, created_at desc): customer replied
- **Bookings with `orphaned=True`**: GCal event deleted
- **Bookings with `time_changed=True`**: appointment time changed
- **Customers with overdue follow-up** (computed from health): follow-up overdue

Each item in the feed has:
```python
{
    "ts": datetime,            # for sorting
    "customer_id": int,
    "customer_name": str,
    "category": str,           # needs_response | needs_follow_up | invite_sent | calendar
    "description": str,        # human-readable trigger description
    "seen": bool,              # based on last_updates_viewed cookie
}
```

Sort by `ts` desc. Items without a precise timestamp (e.g. follow-up overdue) get a synthetic timestamp = last_outbound_at + follow_up_due_days.

---

## Backend Changes — `api/app.py` GET /updates

Build `feed_items` list (all updates combined, sorted by ts desc).
Build `quadrant_data` dict (keyed by category, each with count + top 3 customers).

New template context:
```python
{
    "feed_items": [...],          # sorted combined feed, max 50
    "feed_total": int,
    "quadrant_data": {
        "needs_response": {"count": N, "items": [...]},
        "needs_follow_up": {"count": N, "items": [...]},
        "invite_sent": {"count": N, "items": [...]},
        "calendar": {"count": N, "items": [...]},
    },
    "last_viewed": datetime | None,  # from cookie
}
```

Set response cookie `last_updates_viewed` to utcnow().

---

## CSS Strategy

Current modules are ~`padding:20px` with large fonts. New targets:
- Feed rows: 44px height, compact fonts (12px body, 10px mono labels)
- Quadrant panels: max-height ~220px, 2x2 CSS grid
- Remove all full-width section dividers (they create visual weight that implies equal importance)

---

## Tasks

- [ ] `task_01_backend.md` — `api/app.py` GET /updates — build `feed_items` + `quadrant_data`, set cookie
- [ ] `task_02_template.md` — `templates/updates.html` — full redesign: feed + 2x2 quadrant grid

---

## Files to Read First

```
api/app.py  (GET /updates route — existing data queries)
templates/updates.html
```

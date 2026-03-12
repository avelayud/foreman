# Job 04 — Product Analytics Instrumentation + Internal Dashboard

**Status:** ⬜ Backlog
**Depends On:** Nothing (build before Job 03 so /analytics itself is instrumented)
**Goal:** Lightweight event tracking so you (Arjuna) can understand how operators use Foreman — which pages they visit, how much they edit AI drafts, which features drive engagement, and where they drop off. Internal-only, never visible to operators.

---

## New Model — `ProductEvent`

```python
class ProductEvent(Base):
    id: int (PK)
    operator_id: int (nullable, FK)
    session_id: str  # UUID from cookie
    event_type: str  # "page_view" | "draft" | "outreach" | "conversion" | "agent" | "navigation"
    event_name: str
    page: str
    properties: str  # JSON
    created_at: datetime (UTC)
```

Session ID stored in `foreman_session` cookie. Set on every page response, 30-day expiry.

---

## Event Taxonomy

### Page Views (`event_type = "page_view"`)
Fired server-side on every route. Properties: queue_depth, customer_score, pending_count (where relevant).

### Draft Events (`event_type = "draft"`) — highest signal
- `draft_generated`: `{customer_id, draft_type, char_count}`
- `draft_approved_unchanged`: `{customer_id, draft_type}`
- `draft_edited_then_approved`: `{customer_id, draft_type, edit_distance, edit_pct}`
- `draft_discarded`: `{customer_id, draft_type}`
- `draft_regenerated`: `{customer_id, draft_type, attempt_number}`

`edit_pct` = character diff / original length. Store original draft length in `data-original-length` on the textarea at load time; compute on submit in JS.

### Outreach Events
- `outreach_sent`: `{customer_id, was_edited, edit_pct}`
- `outreach_scheduled`: `{customer_id}`
- `one_click_action_used`: `{action_type, customer_id}`

### Conversion Events
- `booking_marked_manual`: `{customer_id, job_value, days_since_outreach}`
- `booking_confirmed_auto`: `{customer_id, days_since_outreach}`

### Agent Events
- `agent_run_manual`: `{agent_name}`
- `agent_run_scheduled`: `{agent_name, records_processed}`

### Navigation Events (client-side via JS)
- `tab_switched`: `{tab_name}`
- `search_used`: `{query_length}` (not the query itself)
- `filter_applied`: `{filter_name, filter_value}`
- `show_more_clicked`: `{group_name}`
- `conversation_timeline_item_clicked`: `{item_index}`

---

## Server-side Helpers (`core/product_analytics.py`)

```python
log_event(db, session_id, event_type, event_name, page, properties, operator_id)
get_session_id(request)     # reads cookie or generates new UUID
log_page_view(db, request, page, operator_id, properties)  # convenience wrapper
```

**Always wrapped in try/except** — analytics must never crash the app.

## Client-side (`base.html`)

Small JS block at bottom of `<body>`:
```javascript
function trackEvent(eventName, properties) {
    fetch('/api/events', { method: 'POST', body: JSON.stringify({event_name: eventName, ...properties}) })
        .catch(() => {});  // always silent-fail
}
```

Wire to: tab switches, search inputs (debounced 500ms), filter changes, show-more buttons, timeline item clicks.

## New Route

`POST /api/events` — reads session cookie, calls `log_event`, always returns `{"ok": true}`, never returns 500.

---

## Internal Dashboard (`/internal/product`) — 6 Sections

1. **Activity Overview** (4 cards): total page views, unique sessions, total events, avg events/session — time-range filtered
2. **Page Popularity** (bar chart): most visited pages by page_view count
3. **Draft Behavior** (most important):
   - Stat row: total generated, % unchanged, % edited, avg edit_pct
   - Bar chart: edit rate by draft type
   - Histogram: edit_pct distribution (0–10% / 10–30% / 30–60% / 60%+)
4. **Feature Engagement** (horizontal bar): usage count per tracked feature, sorted descending
5. **Navigation Funnel**: Dashboard → Customer Detail → Outreach Queue → Conversation → Booked — distinct session counts at each step
6. **Recent Event Log** (table): last 100 events — Time / Page / Event Type / Event Name / Properties (first 80 chars, expandable on click)

Time range toggle: `?range=7|30|all` — affects all sections.

---

## Privacy Principles

- No PII in event properties (customer IDs are fine, names are not)
- `edit_pct` is a computed metric, never the draft text
- Session IDs are random UUIDs — not linked to operator login

---

## Files to Create

- `core/product_analytics.py` — `log_event`, `get_session_id`, `log_page_view`
- `templates/internal_analytics.html` — 6-section internal dashboard

## Files to Modify

- `core/models.py` — add `ProductEvent` model
- `api/app.py` — instrument all routes + add `POST /api/events` + add `GET /internal/product`
- `templates/base.html` — add `trackEvent()` JS + wire to nav events
- `data/reseed.py` — ensure `ProductEvent` table is wiped on reseed (don't accumulate test events)

## Tasks (to be detailed)

| Task | Description | Status |
|------|-------------|--------|
| task_01 | `ProductEvent` model + `core/product_analytics.py` | todo |
| task_02 | Server-side instrumentation in `api/app.py` (all routes) | todo |
| task_03 | Client-side `trackEvent()` in `base.html` + wire to nav events | todo |
| task_04 | `POST /api/events` endpoint + `GET /internal/product` dashboard | todo |

## Acceptance Criteria

- [ ] Visit `/` → `ProductEvent` row created with `event_type="page_view"`, `page="dashboard"`
- [ ] Generate a draft → `draft_generated` event logged with `char_count`
- [ ] Edit draft text and approve → `draft_edited_then_approved` with non-zero `edit_pct`
- [ ] `POST /api/events` returns `{"ok": true}` even if DB write fails
- [ ] `/internal/product` loads and shows draft behavior section with correct counts
- [ ] No crash anywhere in the app if `ProductEvent` table is missing or `log_event` throws

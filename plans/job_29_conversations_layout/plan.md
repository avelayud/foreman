# Job 29 — Conversations Page: Compact Layout + Distribution Donut

**Phase:** 8
**Status:** ✅ Complete
**Depends on:** Nothing — fully independent
**Goal:** Make the conversations list more information-dense (show 4–6 cards at once instead of 2) and add a donut chart showing the distribution of conversation health states so operators can assess the overall pipeline at a glance before diving into individual conversations.

---

## Background

The current conversations list renders each conversation as a tall card that takes up ~40% of the viewport. Operators can only see 2–3 conversations before scrolling, which makes it feel more like a gallery than a list. The fix is a compact table-like row layout that fits 6–8 conversations on screen.

The page also lacks any summary signal — there's no quick answer to "how many conversations need my attention right now?" A donut chart above the list fills that gap.

---

## New Layout — Compact Row Cards

Replace the current card grid with a compact list. Each row contains:

```
[Health chip] [Customer name]  [Last contact: Mar 14]  [Stage]  [Score]  [→]
```

**Row height:** ~48px (vs. current ~120px)
**Columns:**
1. Health chip (colored dot or small badge) — `needs_response` (red), `needs_follow_up` (amber), `awaiting_reply` (blue), `invite_sent` (purple), `closed` (green)
2. Customer name (bold, 14px)
3. Last contact date (mono, 11px, right of name or separate column)
4. Reactivation status pill (small, same as current)
5. Score badge (if available)
6. Chevron → links to conversation detail

**Hover:** row highlights, cursor pointer
**Active state:** no modal — just navigates to `/conversations/{id}` on click

### CSS approach
```css
.conv-row { display:flex; align-items:center; gap:12px; padding:10px 16px; border-bottom:1px solid var(--border); cursor:pointer; transition:background 0.1s; }
.conv-row:hover { background:var(--navy-soft); }
.conv-row:last-child { border-bottom:none; }
.conv-name { font-size:13.5px; font-weight:600; color:var(--navy); flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.conv-meta { font-size:10.5px; font-family:'IBM Plex Mono',monospace; color:var(--text-3); white-space:nowrap; }
.conv-health-dot { width:9px; height:9px; border-radius:50%; flex-shrink:0; }
```

### Health dot colors
- `needs_response`: `var(--red)` + pulse animation
- `needs_follow_up`: `var(--amber)`
- `awaiting_reply`: `var(--blue)`
- `invite_sent`: `#7c3aed`
- `closed`: `var(--green)`
- `booked`: `var(--green)`

---

## Donut Chart — Conversation Distribution

Display above the conversations list, spanning the full width (or right-aligned within the page header).

**Chart:** SVG donut, 120px diameter
**Segments:** one per health state, sized by count
**Legend:** inline next to the donut — label + count for each segment

```
[donut]   ● Needs Response   4
          ● Needs Follow-up  7
          ● Awaiting Reply  12
          ● Invite Sent      3
          ● Closed           8
```

**Implementation:** Pure SVG — no chart library dependency. Compute arc paths in the template using the counts. Pre-compute in Python and pass as `donut_segments = [{label, key, count, color}]` from the route.

The donut only shows states with count > 0.

---

## Filter Tabs

Keep the existing filter tabs (All | Needs Response | Follow-up | Awaiting Reply | Invite Sent | etc.) — they stay above the list. The donut is above the tabs.

If a filter is active, the donut still shows full distribution (not filtered). This gives operators context about the whole pipeline even while focusing on one segment.

---

## Search Bar

Keep the existing search bar. Place it inline with the filter tabs.

---

## Backend Changes — `api/app.py` GET /conversations

Add `donut_segments` to the template context:
```python
from collections import Counter
health_counts = Counter(c["health_key"] for c in conversations_list)
donut_segments = [
    {"key": "needs_response", "label": "Needs Response", "color": "#ef4444", "count": health_counts.get("needs_response", 0)},
    {"key": "needs_follow_up", "label": "Needs Follow-up", "color": "#f59e0b", "count": health_counts.get("needs_follow_up", 0)},
    {"key": "awaiting_reply", "label": "Awaiting Reply", "color": "#3b82f6", "count": health_counts.get("awaiting_reply", 0)},
    {"key": "invite_sent", "label": "Invite Sent", "color": "#7c3aed", "count": health_counts.get("invite_sent", 0)},
    {"key": "closed", "label": "Closed", "color": "#10b981", "count": health_counts.get("closed", 0)},
]
donut_segments = [s for s in donut_segments if s["count"] > 0]
```

Each conversation dict in `conversations_list` needs a `health_key` field (the health chip key, not the label). Verify this is already present — if not, add it.

---

## SVG Donut Generation

Compute in Jinja or pass pre-computed arc data from Python. Since Jinja2 doesn't have math for arc paths, compute the arcs in Python and pass `donut_arcs` to the template:

```python
import math

def compute_donut_arcs(segments, cx=60, cy=60, r=46, stroke_width=14):
    total = sum(s["count"] for s in segments)
    if total == 0:
        return []
    arcs = []
    angle = -90  # start at top
    for seg in segments:
        pct = seg["count"] / total
        sweep = 360 * pct
        # Convert to radians for x/y
        start_rad = math.radians(angle)
        end_rad = math.radians(angle + sweep)
        x1 = cx + r * math.cos(start_rad)
        y1 = cy + r * math.sin(start_rad)
        x2 = cx + r * math.cos(end_rad)
        y2 = cy + r * math.sin(end_rad)
        large_arc = 1 if sweep > 180 else 0
        arcs.append({**seg, "d": f"M {x1:.1f} {y1:.1f} A {r} {r} 0 {large_arc} 1 {x2:.1f} {y2:.1f}", "stroke_width": stroke_width})
        angle += sweep
    return arcs
```

Pass `donut_arcs` and `donut_total` to the template.

---

## Tasks

- [ ] `task_01_backend.md` — add `donut_segments`, `donut_arcs`, `donut_total`, `health_key` to conversations route context
- [ ] `task_02_template.md` — `templates/conversations.html` — replace card grid with compact rows + add donut SVG + legend

---

## Files to Read First

```
api/app.py  (GET /conversations route)
templates/conversations.html
```

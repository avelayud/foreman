# Job 27 — Agents Page: Grouping + Local Timezone Timestamps

**Phase:** 8
**Status:** ✅ Complete
**Depends on:** Nothing — fully independent
**Goal:** Group agents into logical pipeline stages so the page is easier to scan, and fix "Last Run" timestamps to display in the operator's local timezone instead of UTC.

---

## Background

The Agents page currently shows agents in a flat list with no clear grouping. As the number of agents grows (now at 9+), it's hard to understand the pipeline at a glance. Two quick wins:
1. Group agents by pipeline phase with labeled section headers
2. Fix timestamps — `last_run_at` is stored and displayed as UTC, which shows confusing times like "3:14 AM" when the agent ran at 10:14 PM local time.

---

## Agent Groups

### Group 1 — Intake & Scoring
*Run first to profile and rank customers before any outreach*
- `customer_analyzer` — Customer Analyzer
- `tone_profiler` — Tone Profiler
- `scoring` — Scoring Engine

### Group 2 — Outreach
*Core outreach generation — run after intake*
- `reactivation` — Reactivation Agent

### Group 3 — Conversation
*Post-send: detect replies, classify intent, generate responses*
Run in order if triggering manually:
- `reply_detector` — Reply Detector
- `response_classifier` — Response Classifier *(auto-triggered)*
- `response_generator` — Response Generator
- `conversation_agent` — Conversation Agent *(auto-triggered)*
- `follow_up` — Follow-up Agent

### Group 4 — Scheduling
*Calendar and appointment management*
- `gcal_sync` — Google Calendar Sync
- `post_visit` — Post-Visit Agent

### Group 5 — Maintenance
*Background health checks — run independently*
- `state_reconciler` — Conversation State Reconciler

---

## UI Changes — `templates/agents.html`

Replace the flat `agents-grid` with grouped sections:

```html
<div class="agent-group">
  <div class="agent-group-header">
    <span class="agent-group-title">Intake &amp; Scoring</span>
    <span class="agent-group-desc">Run first — profile and rank customers before outreach</span>
  </div>
  <div class="agents-grid">
    <!-- agent cards for this group -->
  </div>
</div>
```

Add CSS:
```css
.agent-group { margin-bottom: 28px; }
.agent-group-header { display:flex; align-items:baseline; gap:12px; margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid var(--border); }
.agent-group-title { font-size:12px; font-weight:700; color:var(--navy); font-family:'IBM Plex Mono',monospace; letter-spacing:0.8px; text-transform:uppercase; }
.agent-group-desc { font-size:11.5px; color:var(--text-3); }
```

---

## Backend Changes — `api/app.py`

In the GET /agents route, add a `group` key to each agent dict and return agents in the correct order within each group.

The template iterates over groups (ordered list of `{name, desc, agents[]}` dicts) instead of a flat agents list.

Alternatively (simpler): keep the flat agents list but add `group` and `group_order` keys — the template uses Jinja `groupby` filter.

**Use the flat list + `group` key approach** — minimal backend change, template handles display.

Add to each agent dict:
```python
"group": "intake_scoring",       # or "outreach", "conversation", "scheduling", "maintenance"
"group_label": "Intake & Scoring",
"group_desc": "Run first — profile and rank customers before outreach",
"group_order": 1,                # 1-5
"agent_order": 1,                # position within group
```

---

## Timestamp Fix — Local Timezone

**Problem:** `_agent_last_run` stores `datetime.utcnow()` and the template calls `{{ agent.last_run_at.strftime('%b %-d, %Y at %-I:%M %p') }}` — this displays raw UTC.

**Fix:** In the Jinja2 template, use the existing `est` filter (already defined in `api/app.py` for the timeline) instead of strftime:

Change in `templates/agents.html`:
```html
{{ agent.last_run_at.strftime('%b %-d, %Y at %-I:%M %p') }}
```
to:
```html
{{ agent.last_run_at | est }}
```

The `est` filter converts UTC → Eastern time (already handles DST). If the operator is in a different timezone, this is a separate config issue — for now EST matches the operator.

If `est` filter is only registered for specific routes, verify it's registered on the app-level Jinja env in `api/app.py`. If not, register it globally.

---

## Tasks

- [ ] `task_01_backend_groups.md` — add `group`, `group_label`, `group_desc`, `group_order`, `agent_order` to all agent dicts in GET /agents
- [ ] `task_02_template.md` — `templates/agents.html` — grouped display, section headers, timestamp filter fix

---

## Files to Read First

```
api/app.py   (GET /agents route — agents list)
templates/agents.html
```

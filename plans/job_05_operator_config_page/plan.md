# Job 05 — Operator Config Page

**Phase:** 8
**Status:** ⬜ Not started
**Goal:** Build a `/settings` config page where the operator sets business-specific parameters that feed directly into every agent prompt. Makes Foreman's drafts specific to this shop — not generic AI outreach.

---

## Background

Right now, agent prompts have no knowledge of the operator's business beyond what's in the customer record and tone profile. The config page adds a layer of operator-specific intelligence:
- How direct vs consultative should the tone be?
- Which job types does this shop prioritize?
- What are real price ranges for this market?
- What's the business context agents should know?

These values are stored on the `Operator` model and injected into every agent system prompt at generation time via a shared helper.

---

## Deliverables

1. `core/operator_config.py` — config getter/setter + `get_agent_context()` prompt injection helper
2. `core/models.py` — `operator_config JSON` column on Operator
3. `core/database.py` — SCHEMA_PATCHES migration
4. `api/app.py` — `GET /settings` + `POST /api/settings`
5. `templates/settings.html` — config UI
6. Agent prompt injection in `reactivation.py`, `conversation_agent.py`, `follow_up.py`
7. Scoring weight adjustment in `core/scoring.py` for job type priority
8. Sidebar nav update in `templates/base.html`

---

## Config Fields Spec

| Field | Type | Default | Description |
|---|---|---|---|
| `tone` | int 1–5 | 3 | 1 = consultative/warm, 5 = direct/no-frills |
| `salesy` | int 1–5 | 2 | 1 = low-key, 5 = confident push |
| `job_priority` | list[str] | ["maintenance", "repair", "install", "inspection", "other"] | Drag-to-rank order |
| `estimate_ranges` | dict[str, {min, max}] | see defaults below | $ ranges per job type |
| `seasonal_focus` | dict[str, list[int]] | {} | job_type → list of months (1–12) |
| `business_context` | str | "" | Free text injected into all prompts (200 char max) |

**Default estimate ranges:**
```json
{
  "maintenance": {"min": 89, "max": 199},
  "repair": {"min": 150, "max": 800},
  "install": {"min": 3500, "max": 12000},
  "inspection": {"min": 79, "max": 149},
  "other": {"min": 100, "max": 500}
}
```

---

## `get_agent_context()` Output Format

The helper returns a string block prepended to every agent system prompt:

```
BUSINESS CONTEXT:
- Tone: [Direct and no-frills / Balanced / Consultative and warm] (x/5)
- Sales approach: [Low-key, relationship-first / Balanced / Confident, push for the booking] (x/5)
- Job priority (highest first): Maintenance > Repair > Install > Inspection > Other
- Estimate ranges: Maintenance $89–199 | Repair $150–800 | Install $3,500–12,000
- Seasonal focus: Push maintenance in April, May, June
- Context: [operator's free text]
```

---

## UI Design Notes

- Page at `/settings` — sidebar link in Internal or a new top-level "Settings" section
- Tone + Salesy: HTML range sliders with live label updates ("Direct", "Balanced", "Consultative")
- Job priority: simple ordered list with up/down arrow buttons (no drag-drop dependency needed)
- Estimate ranges: two number inputs (min/max) per job type, dollar-formatted
- Seasonal focus: checkbox grid (job types × months)
- Business context: textarea with 200-char counter
- Save button POSTs to `/api/settings`, returns 200, shows "Saved" confirmation inline
- Pre-populate with current config on page load (or defaults if never set)

---

## Tasks

See `tasks/` folder for individual task files.

- [ ] task_01_model_migration.md — add operator_config column
- [ ] task_02_operator_config_module.md — core/operator_config.py
- [ ] task_03_api_routes.md — GET /settings + POST /api/settings
- [ ] task_04_settings_template.md — templates/settings.html
- [ ] task_05_agent_injection.md — inject context into reactivation, conversation_agent, follow_up
- [ ] task_06_scoring_priority.md — job_priority feeds scoring weight
- [ ] task_07_nav_update.md — sidebar link

---

## Files to Attach in Claude Code

```
PROJECT_PLAN.md
core/models.py
core/database.py
core/config.py
api/app.py
templates/base.html
agents/reactivation.py
agents/conversation_agent.py
agents/follow_up.py
core/scoring.py
```

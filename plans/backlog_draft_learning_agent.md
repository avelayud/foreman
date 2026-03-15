# Backlog: Draft Learning Agent

**Phase:** Backlog (design discussion first)
**Depends on:** Outreach queue, Gmail send path

---

## Problem

Claude generates drafts based on tone profile + customer context, but operators routinely edit them before sending. Those edits represent real signal — the gap between the AI draft and the approved/sent version reveals exactly what the operator wants to change. Currently that signal is discarded.

## Goal

Build an agent that:
1. Compares the generated draft (stored at log creation) with the final approved/sent version
2. Extracts the edit pattern — what was shortened, removed, reworded, or added
3. Accumulates patterns across multiple edits into an operator-specific "edit profile"
4. Injects the edit profile into future draft prompts so Claude proactively mimics the operator's edits

## Iterative improvement loop

```
Generate draft (v0)
    ↓
Operator edits in queue
    ↓
Operator approves → sent version logged (v1)
    ↓
Learning Agent: diff(v0, v1) → extract edit patterns
    ↓
Edit profile updated on Operator record
    ↓
Next draft: inject edit profile into prompt
    ↓
Generated draft closer to v1 (fewer edits needed)
```

## Data needed

- `OutreachLog.generated_content` — new column to snapshot the AI-generated draft at creation time (before operator edits)
- `OutreachLog.content` — already stores final approved content
- `Operator._edit_profile` — new JSON column: `{patterns: [...], sample_count: int, last_updated: ...}`

## Edit pattern schema

```json
{
  "patterns": [
    {
      "type": "shorten",
      "description": "Operator consistently removes the last paragraph",
      "frequency": 8
    },
    {
      "type": "rephrase_opener",
      "description": "Replaces 'I wanted to reach out' with 'Just checking in'",
      "frequency": 5
    },
    {
      "type": "remove_cta",
      "description": "Removes explicit call-to-action in closing",
      "frequency": 6
    }
  ],
  "sample_count": 14,
  "last_updated": "2026-03-14T..."
}
```

## Agent design

- **Trigger:** Daily or after each new approval event
- **Minimum samples:** Don't generate a profile until 5+ edit pairs available
- **Prompt:** Feed diff pairs to Claude, ask for pattern extraction
- **Injection:** Append edit profile summary to system prompt in `reactivation.py`, `follow_up.py`, `response_generator.py`

## Schema changes needed

1. `OutreachLog.generated_content TEXT` — snapshot at draft creation
2. `Operator._edit_profile TEXT` — JSON edit profile

## Files to touch

- `core/models.py` — add columns
- `core/database.py` — SCHEMA_PATCHES
- `agents/draft_learner.py` — new agent
- `agents/reactivation.py`, `follow_up.py`, `response_generator.py` — inject edit profile into prompts
- `api/app.py` — expose Run Now button on Agents page; snapshot `generated_content` at draft creation

## Open questions

- How many edit pairs before patterns are reliable? (Suggest: 5 minimum, meaningful at 10+)
- Should edit profile be global (all drafts) or per sequence type (initial vs follow-up)?
- Does the operator see the profile / can they override it?

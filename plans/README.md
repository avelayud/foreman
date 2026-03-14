# Foreman — Plans System

Plans are authored in Claude app and executed in Claude Code.

## Workflow

1. **Author** a plan in Claude app (use the job template below)
2. **Drop** the `plan.md` + `tasks/` folder into `plans/` under the correct job folder
3. **Open Claude Code**, say: _"execute plans/job_XX_name"_ — Claude reads `plan.md` first, then works through tasks in order

## Folder Structure

```
plans/
├── README.md
├── job_05_operator_config_page/         # Phase 8 — active
│   └── plan.md
├── job_06_prompt_quality/               # Phase 8 — depends on 05
│   └── plan.md
├── job_07_sms_send_path/                # Phase 9
│   └── plan.md
├── job_08_sms_ux/                       # Phase 9 — depends on 07
│   └── plan.md
├── job_09_revenue_data_integrity/       # Phase 8 — parallel with 05
│   └── plan.md
├── job_10_jobber_integration/           # Phase 10
│   └── plan.md
├── job_24_conversation_state_agent/     # Phase 8 — state reconciler + health override ✅ Done
│   └── plan.md
├── job_25_gcal_sync_agent/              # Phase 8 — depends on 24 ✅ Done
│   └── plan.md
├── job_26_edit_meeting_invite/          # Phase 8 — edit/reschedule confirmed appointment
│   └── plan.md
├── job_27_agents_page_polish/           # Phase 8 — group agents + fix UTC timestamps
│   └── plan.md
├── job_28_meeting_queue_status/         # Phase 8 — fix "Meeting Confirmed" on drafts
│   └── plan.md
├── job_29_conversations_layout/         # Phase 8 — compact rows + distribution donut
│   └── plan.md
└── job_30_updates_page_redesign/        # Phase 8 — notification feed + compact quadrants
    └── plan.md
```

Delete a job folder when all tasks are complete. Context is preserved in PROJECT_PLAN.md.

---

## Task File Format

Every task file uses this frontmatter + body:

```markdown
---
job: job_01_customer_analyzer
task: task_01_db_thread_reader
status: todo           # todo | in_progress | done | blocked
depends_on: []         # list of task IDs that must be done first
files:
  - agents/customer_analyzer.py
  - core/models.py
---

# Task: [Short Name]

## Goal
One paragraph — what this task produces and why.

## Steps
1. ...
2. ...

## Files to Read First
- `path/to/file.py` — why you're reading it

## Acceptance Criteria
- [ ] criterion
- [ ] criterion

## Notes
Any gotchas, design decisions, or watch-outs.
```

---

## Job Execution Order

| Job | Name | Phase | Status | Depends On |
|-----|------|-------|--------|------------|
| 24 | Conversation State Agent + Health Override | 8 | ✅ Done | — |
| 25 | Google Calendar Sync Agent | 8 | ✅ Done | Job 24 |
| 26 | Edit / Reschedule Meeting Invite | 8 | ⬜ Not started | — |
| 27 | Agents Page: Grouping + Timezone Fix | 8 | ⬜ Not started | — |
| 28 | Fix Meeting Queue Status Tag | 8 | ⬜ Not started | — |
| 29 | Conversations Page: Compact Layout + Donut | 8 | ⬜ Not started | — |
| 30 | Updates Page Redesign | 8 | ⬜ Not started | — |
| 05 | Operator Config Page | 8 | ⬜ Not started | — |
| 09 | Revenue Data Integrity | 8 | ⬜ Not started | — *(parallel with 05)* |
| 06 | Prompt Quality Sprint | 8 | ⬜ Not started | Job 05 |
| 07 | Twilio SMS Send Path | 9 | ⬜ Not started | — |
| 08 | SMS Draft Pipeline + UX | 9 | ⬜ Not started | Job 07 |
| 10 | Jobber / HousecallPro Integration | 10 | ⬜ Not started | Phases 8+9 stable |

> Jobs 26–30 are fully independent — any can run in parallel.
> Jobs 05 and 09 are independent of each other and of 26–30.
> Job 06 requires Job 05 (`core/operator_config.py`) to exist first.
> Job 07 and 08 are sequential. Job 10 is standalone once Phases 8+9 are done.

---

## How to Tell Claude Code to Execute a Plan

```
Execute plans/job_01_customer_analyzer — read plan.md first for context, then work through tasks in order. Mark each task status as "in_progress" when you start it and "done" when complete.
```

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
├── job_01_customer_analyzer/       # active
│   ├── plan.md
│   └── tasks/
│       ├── task_01_*.md
│       └── task_02_*.md
├── job_02_booking_confirmation/    # backlog
├── job_03_customer_analytics/      # backlog
└── job_04_product_analytics/       # backlog
```

Move a job folder to `plans/done/` when all tasks are complete.

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

| Job | Name | Status | Depends On |
|-----|------|--------|------------|
| 01 | Customer Analyzer Fix | 🔵 Active | — |
| 02 | Booking Confirmation + Calendar Write-back | ⬜ Backlog | — |
| 04 | Product Analytics Instrumentation | ⬜ Backlog | — |
| 03 | Customer Analytics Page | ⬜ Backlog | 01, 04 |

> Job 04 runs before Job 03 so that the `/analytics` page itself is instrumented when built.

---

## How to Tell Claude Code to Execute a Plan

```
Execute plans/job_01_customer_analyzer — read plan.md first for context, then work through tasks in order. Mark each task status as "in_progress" when you start it and "done" when complete.
```

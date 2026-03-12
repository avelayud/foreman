---
job: job_01_customer_analyzer
task: task_01_db_thread_reader
status: todo
depends_on: []
files:
  - agents/customer_analyzer.py
  - core/models.py
---

# Task 01 — Add `_get_thread_from_db()`

## Goal
Add a new private function `_get_thread_from_db(customer, db)` to `agents/customer_analyzer.py` that reads OutreachLog records from the database and returns a formatted conversation thread string — the same format as `get_correspondence()` from Gmail.

## Files to Read First
- `agents/customer_analyzer.py` — understand existing `get_correspondence()` call and how the thread string is currently used in the Claude prompt
- `core/models.py` — OutreachLog model fields: `sent_at`, `email_body`, `inbound`, `subject`, `dry_run`

## Steps
1. Read `customer_analyzer.py` fully — find where `get_correspondence()` is called and how the result is passed to Claude
2. Read `OutreachLog` model in `core/models.py` — note field names for `inbound`, `email_body`, `subject`, `sent_at`
3. Add function `_get_thread_from_db(customer, db)`:
   - Query `OutreachLog` where `customer_id == customer.id`, ordered by `sent_at ASC`
   - Exclude `dry_run=True` records (or include them if no non-dry records exist — your call, document the decision)
   - For each record: if `inbound=False` → `[OUTBOUND] Subject: {subject}\n{email_body}`, if `inbound=True` → `[INBOUND] {email_body}`
   - Join with double newline separator
   - Return the string, or `None` if no records found

## Acceptance Criteria
- [ ] Function exists and is importable
- [ ] Returns `None` (not empty string) when no OutreachLog records exist for a customer
- [ ] Outbound records show `[OUTBOUND] Subject: ...` prefix
- [ ] Inbound records show `[INBOUND]` prefix
- [ ] Records are ordered chronologically (oldest first)
- [ ] Function does not crash on a customer with no logs

## Notes
- Keep function private (`_get_thread_from_db`) — it's only used within the analyzer
- Don't modify the Claude prompt in this task — that's task 02
- `OutreachLog.inbound` is a Boolean column: `True` = customer reply, `False` = operator-sent outbound

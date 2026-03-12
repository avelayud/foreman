---
job: job_01_customer_analyzer
task: task_02_analyzer_integration
status: todo
depends_on: [task_01_db_thread_reader]
files:
  - agents/customer_analyzer.py
  - integrations/gmail.py
---

# Task 02 — Wire DB-First Logic + --force Flag

## Goal
Update the main analyze loop in `customer_analyzer.py` to use `_get_thread_from_db()` as the primary source. Fall back to `get_correspondence()` (Gmail API) only if DB returns fewer than 2 messages. Add `--force` CLI flag to overwrite existing profiles unconditionally.

## Files to Read First
- `agents/customer_analyzer.py` — the main `analyze_customers()` / `run()` function and where profile skip logic lives (e.g. `if customer._customer_profile: continue`)
- `integrations/gmail.py` — `get_correspondence()` signature

## Steps
1. Find the skip logic that bypasses already-profiled customers — this is where `--force` hooks in
2. Add `--force` argument to the `argparse` block (if one exists) or to the `if __name__ == "__main__"` block
3. Update skip logic: if `--force` is set, do NOT skip customers with existing profiles
4. In the analysis function, replace (or wrap) the `get_correspondence()` call:
   ```python
   thread = _get_thread_from_db(customer, db)
   if not thread or thread.count('\n') < 4:  # fewer than ~2 messages
       thread = get_correspondence(customer.email)  # Gmail fallback
   ```
5. If both return nothing (new customer, no history, no Gmail), skip profiling with a log message — don't crash
6. Verify the thread string variable is passed to Claude in the same way as before — no prompt changes needed

## Acceptance Criteria
- [ ] `python -m agents.customer_analyzer --operator-id 1 --all` profiles all 40 scenario customers
- [ ] `--force` flag causes all profiles to be overwritten, not just missing ones
- [ ] Without `--force`, customers with existing profiles are still skipped (no regression)
- [ ] Gmail fallback is attempted when DB thread is thin (< 2 messages)
- [ ] Customers with zero history (no jobs, no OutreachLog, no Gmail) are skipped gracefully with a log line
- [ ] `analyzed_at` is updated on every successful profile write

## Notes
- The 8 live email address customers (`never_contacted` status) may have no OutreachLog records — they should fall through to the Gmail fallback
- Do not remove `get_correspondence()` — keep it as the secondary path
- After this task, run `python -m agents.customer_analyzer --operator-id 1 --all --force` and verify profiles appear on the site for scenario customers

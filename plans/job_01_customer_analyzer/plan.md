# Job 01 — Customer Analyzer Fix

**Status:** 🔵 Active
**Phase:** 5 backlog / unblocks Job 03
**Goal:** Make Customer Analyzer populate profiles for all customers using OutreachLog records as the primary data source — not Gmail API. This unblocks profile display for all 40 scenario customers with rich simulated conversations.

---

## Problem

`agents/customer_analyzer.py` calls `integrations/gmail.get_correspondence()` which searches Gmail API by customer email address. Synthetic seed emails (e.g. `patsimm@email.com`) don't exist in Gmail, so profiles never populate for ~192 of 200 customers.

## Solution

Add `_get_thread_from_db(customer, db)` to the analyzer that:
1. Queries `OutreachLog` for all inbound + outbound messages for the customer, ordered by `sent_at`
2. Formats them as `[OUTBOUND] Subject: ...\n<body>` / `[INBOUND] <body>` thread strings
3. Returns this as the primary conversation source for Claude profile analysis

Gmail `get_correspondence()` stays as **secondary enrichment only** — used when fewer than 2 DB messages exist.

## Key Design Decisions

- DB-first, Gmail-fallback — not the other way around
- Same `CustomerProfile` JSON schema, same storage on `Customer._customer_profile`
- Add `--force` flag to overwrite existing profiles unconditionally (useful after reseed)
- Display `analyzed_at` timestamp in UI so staleness is visible

## Files Involved

- `agents/customer_analyzer.py` — primary change
- `core/models.py` — OutreachLog fields reference
- `integrations/gmail.py` — `get_correspondence()` for fallback reference

## Tasks

| Task | File | Status |
|------|------|--------|
| task_01 | Add `_get_thread_from_db()` to customer_analyzer | todo |
| task_02 | Wire DB-first logic + --force flag + fallback | todo |

## Acceptance Criteria

- [ ] Run `python -m agents.customer_analyzer --operator-id 1 --all` and all scenario customers get profiles
- [ ] `analyzed_at` is updated on each run
- [ ] `--force` flag overwrites existing profiles
- [ ] Gmail fallback still works for the 8 live email address customers
- [ ] No crash when OutreachLog is empty (new customer, no history)

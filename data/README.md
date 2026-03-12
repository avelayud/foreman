# Foreman — Data Layer

This folder contains all database seeding, migration, and maintenance scripts.

---

## Files

| File | Purpose |
|---|---|
| `reseed.py` | **Canonical reseed script** — full wipe + 200-customer dataset. Run this to reset. |
| `fix_inbound_timestamps.py` | One-time UTC migration for inbound Gmail logs (2026-03-11). Keep for reference. |
| `archive/seed_v1_legacy.py` | Original 40-customer seed (2026-03-10). Superseded by reseed.py. |

---

## How to Reseed

### Railway (production)

```bash
# Get the public proxy URL from Railway Postgres service vars
# DATABASE_PUBLIC_URL = postgresql://postgres:<pass>@hopper.proxy.rlwy.net:26095/railway

DATABASE_URL="postgresql://postgres:<pass>@hopper.proxy.rlwy.net:26095/railway" \
  venv/bin/python -m data.reseed

# Then restart the web service so scoring + analyzer run on fresh data
railway up --service web
```

> **Important:** `DATABASE_URL` must be set as an environment variable *before* Python starts.
> Setting it inside the script is too late — `core.config` reads it at import time.
> Never use the internal Railway URL (`postgres.railway.internal`) from your local machine.

### Local SQLite

```bash
DATABASE_URL=sqlite:///./foreman.db venv/bin/python -m data.reseed
```

### Quick verification after reseed

```bash
# Check customer count
DATABASE_URL="postgresql://..." venv/bin/python -c "
from core.database import init_db, get_db
from core.models import Customer, OutreachLog, Booking
init_db()
with get_db() as db:
    print('Customers:', db.query(Customer).count())
    print('OutreachLogs:', db.query(OutreachLog).count())
    print('Bookings:', db.query(Booking).count())
"
```

---

## Dataset Overview (200 customers)

| Segment | Count | Details |
|---|---|---|
| Live email customers | 8 | Real addresses, never_contacted, clean slate for live simulation |
| Scenario conversations | 40 | Named customers with rich multi-turn email histories |
| Bulk generated | 152 | Procedural from name/profile pools, full job histories |

### Customer status distribution (approximate)

| Status | Count |
|---|---|
| `never_contacted` | ~148 (prime + warming + recent + new leads + end-of-life) |
| `outreach_sent` / `sequence_step_2` / `sequence_step_3` | ~20 |
| `replied` | ~5 |
| `booked` | ~22 |
| `unsubscribed` | ~5 |

---

## Live Email Addresses

These 8 addresses are assigned to dormant, never-contacted customers. Use them for
real end-to-end simulation — they will receive actual Gmail outreach from the
reactivation agent.

| Email | Customer Name | Days Dormant | Total Spend | Notes |
|---|---|---|---|---|
| `velayudamarjuna@gmail.com` | AV Test | 430 | $1,720 | Primary test account |
| `hsimmons921@gmail.com` | Harold Simmons | 520 | $2,340 | High-value, 4 jobs |
| `sparsons313@gmail.com` | Sarah Parsons | 475 | $2,680 | High-value, 5 jobs, AC install history |
| `arjun.velayudam99@gmail.com` | Arjun Velayudam | 410 | $1,890 | Mid-value |
| `christuck769@gmail.com` | Chris Tucker | 395 | $1,540 | Furnace + emergency repair history |
| `samkeller716@gmail.com` | Sam Keller | 445 | $1,960 | Heat pump + maintenance history |
| `velayudam.arj@gmail.com` | Arjuna Velayudam | 380 | $980 | Boiler + heating history |
| `kated.kitkat@gmail.com` | Kate Dawson | 500 | $2,150 | Mini-split install history |

**To add a new live address:** Add an entry to `LIVE_CUSTOMERS` in `reseed.py` and re-run.

---

## Scenario Conversation Types

The 40 scenario customers cover the full range of realistic outreach responses.
Each is defined in `SCENARIO_CUSTOMERS` with `"scenario": "<type>"`.

| Scenario | Count | What happens | Final status |
|---|---|---|---|
| `price_haggler` | 6 | Initial outreach → customer asks price → we answer → they haggle → we counter → they accept → slot proposal → confirms | `booked` |
| `scheduling_negotiation` | 6 | Outreach → yes interested → propose slots → none work → re-propose → confirm | `booked` |
| `callback_then_email` | 4 | Outreach → "call me at 555-X" → we offer call or email → they pick email → slot proposal → confirm | `booked` |
| `maybe_next_month` | 5 | Outreach → "too busy, try next month" → follow-up 1 (day 10) → follow-up 2 (day 28) → customer re-engages → slot proposal pending | `replied` |
| `multiple_questions` | 5 | Outreach → Q1 (what's included) → A → Q2 (duct cleaning?) → A → Q3 (how long?) → A → "OK let's schedule" → slots → confirm | `booked` |
| `reschedule` | 4 | Outreach → yes → slots → books Mon 10am → "sorry, move to Wed?" → reschedule confirmed | `booked` |
| `not_interested` | 5 | Outreach → "not interested / remove me" | `unsubscribed` |
| `straightforward_book` | 5 | Outreach → "yes great timing, when are you free?" → slots → confirms | `booked` |

### To add a new scenario type

1. Add entries to `SCENARIO_CUSTOMERS` with the new `scenario` key
2. Add a new `elif scenario == "your_type":` branch in `_add_scenario_logs()`
3. Return the correct final status from that branch
4. Re-run reseed

---

## Bulk Customer Profiles

The 152 bulk customers are generated from `BULK_PROFILES` (a list of tuples):

```python
(days_min, days_max, jobs_min, jobs_max, spend_min, spend_max, status, pool_key)
```

**Pool keys** (`JOB_TYPE_POOLS`):
- `maintenance` — tune-ups, inspections, filter replacements
- `repair` — furnace repair, refrigerant, emergency, thermostat
- `install` — AC install, mini-split, zone control, heat pump
- `mixed` — all service types

The bulk list cycles through `BULK_PROFILES` entries in order. To change the
distribution, reorder or duplicate entries in the list before the desired customer #.

### To add more bulk customers

Change `target = 200` in `reseed()` to the desired total. The bulk fill loop
automatically generates `target - len(LIVE_CUSTOMERS) - len(SCENARIO_CUSTOMERS)` customers.

---

## Email Content Templates

All email body helpers are at the top of `reseed.py`:

| Function | Used for |
|---|---|
| `_initial_outreach(first)` | First touch — seasonal check-in |
| `_pricing_response(first, price, service)` | Price haggle scenario |
| `_haggle_response(first, price)` | Counter-offer in price haggle |
| `_slot_proposal(first, s1, s2, s3)` | Propose 3 calendar slots |
| `_booking_confirm(first, slot)` | Confirm a booked appointment |
| `_reschedule_confirm(first, slot)` | Acknowledge reschedule |
| `_followup_1(first)` | Day 10 follow-up |
| `_followup_2(first)` | Day 28 follow-up |
| `_callback_offer(first)` | "Happy to call or email" |
| `_service_detail(first)` | What's included in a tune-up |
| `_duct_info(first)` | Duct cleaning upsell info |
| `_duration_response(first)` | How long does a service take |

To change the operator voice across all seeded emails, edit these functions.

---

## Known Limitations

- Slot strings in scenario emails use fixed day names ("Tuesday the 18th") not computed
  from the current date — this is intentional for readability and doesn't affect app logic
- `random.seed(42)` means bulk customer names/profiles are reproducible but will
  regenerate different IDs each time (auto-increment in Postgres)
- Live email customer IDs will change on each reseed — if you've hardcoded an ID anywhere, re-check it
- Scoring engine (APScheduler) runs at startup after reseed — scores populate within ~60s of Railway restart

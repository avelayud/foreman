# Job 10 — Jobber / HousecallPro Integration

**Phase:** 10
**Status:** ⬜ Not started
**Depends on:** Phase 9 (SMS) complete — not a hard dependency, but don't start until Phases 8+9 are stable
**Goal:** Pull customer and job history directly from the operator's existing FSM tool. Removes the manual import problem entirely — onboarding goes from "export a CSV" to "connect your Jobber account."

---

## Background

Every HVAC operator in Foreman's target segment already uses a field service management (FSM) tool. Jobber has the largest market share in the 3–15 person contractor space. HousecallPro is the second major player.

Right now Foreman gets customer data via CSV import or manual entry, which is a significant onboarding friction point. This integration makes onboarding instant and keeps Foreman's customer list in sync with the operator's real job history.

**Read-only first.** No write-back to Jobber/HCP in this phase — Foreman is a revenue layer on top of, not a replacement for, their FSM tool. Write-back (creating jobs, updating customer records) is a future phase.

---

## Design Decisions

- **Jobber first** — larger market share in target segment. HousecallPro second (parallel structure, different API).
- **Daily sync + on-demand** — runs daily at startup via APScheduler. Operator can also trigger via Agents page "Run Now" button.
- **Merge by email** — imported customers matched to existing records by email address (primary dedup key). If match found, update job history; if no match, create new Customer record.
- **`Customer.source`** field: `manual` (existing default), `jobber`, `housecallpro`.
- **Jobber job type → Foreman taxonomy** — Jobber uses free-form work order titles; map to Foreman's `last_service_type` categories (tune-up, repair, install, maintenance, inspection).
- **OAuth 2.0** — Jobber uses standard OAuth with access + refresh tokens. Store tokens on Operator model (same pattern as Gmail).
- **Sync idempotent** — re-running sync never creates duplicate records. Use external IDs (`jobber_client_id`, `jobber_job_id`) as dedup keys.

---

## Deliverables

1. `integrations/jobber.py` — OAuth flow, client fetch, job history fetch
2. `integrations/housecallpro.py` — parallel structure to Jobber
3. `core/models.py` — new fields on Customer + Job + Operator
4. `core/database.py` — SCHEMA_PATCHES for new columns
5. `agents/jobber_sync.py` — sync agent (maps Jobber data → Foreman models, handles dedup)
6. `agents/housecallpro_sync.py` — parallel sync agent
7. `api/app.py` — OAuth callback routes + sync trigger endpoints
8. `templates/agents.html` — Jobber Sync + HCP Sync agents with status + Run Now
9. `templates/customer.html` — source badge (`Jobber` / `HousecallPro` / `Manual`) + `last_synced_at`

---

## Data Model Changes

### Customer (new fields)
```
source                VARCHAR   DEFAULT 'manual'   # manual | jobber | housecallpro
jobber_client_id      VARCHAR   nullable            # Jobber's internal client ID
hcp_client_id         VARCHAR   nullable            # HousecallPro's internal client ID
last_synced_at        TIMESTAMP nullable
```

### Job (new fields)
```
jobber_job_id         VARCHAR   nullable
hcp_job_id            VARCHAR   nullable
```

### Operator (new fields)
```
jobber_access_token   TEXT      nullable
jobber_refresh_token  TEXT      nullable
jobber_token_expiry   TIMESTAMP nullable
hcp_access_token      TEXT      nullable
hcp_refresh_token     TEXT      nullable
hcp_token_expiry      TIMESTAMP nullable
```

---

## Tasks

### Task 01 — Data model + schema patches
**Files:** `core/models.py`, `core/database.py`
- Add new fields to Customer, Job, Operator (see above)
- Add SCHEMA_PATCHES entries for all new columns
- Acceptance: `init_db()` applies patches cleanly on both SQLite and Postgres

### Task 02 — Jobber OAuth + API client
**Files:** `integrations/jobber.py`
- Implement OAuth 2.0 authorization URL generation
- Implement token exchange (auth code → access + refresh tokens)
- Implement token refresh on expiry
- Implement `get_clients(operator_id)` — paginated fetch of all Jobber clients
- Implement `get_jobs(operator_id, client_id=None)` — paginated job history
- Store tokens on Operator model
- Notes: Jobber API docs at https://developer.getjobber.com. GraphQL API, not REST.

### Task 03 — Jobber sync agent
**Files:** `agents/jobber_sync.py`
- `sync_jobber(operator_id, verbose=False)` — main entry point
- For each client returned: find existing Customer by email (or `jobber_client_id`) → update or create
- For each job: find existing Job by `jobber_job_id` → update or create
- Map Jobber `workType` / title → Foreman `last_service_type` (tune-up / repair / install / maintenance / inspection / other)
- Set `Customer.source = 'jobber'` on upserted records
- Update `last_synced_at` on each synced customer
- APScheduler registration in `api/app.py` (daily, same pattern as priority scorer)
- `__main__` block: `python -m agents.jobber_sync --operator-id 1`

### Task 04 — Jobber OAuth web flow
**Files:** `api/app.py`, `templates/settings.html`
- `GET /integrations/jobber/connect` — redirect to Jobber OAuth authorization URL
- `GET /integrations/jobber/callback` — exchange code for tokens, store on Operator, redirect to /settings
- Add "Connect Jobber" button to `/settings` page (shows green "Connected" state if tokens exist)

### Task 05 — Agents page integration
**Files:** `templates/agents.html`, `api/app.py`
- Add Jobber Sync and HCP Sync as agent cards with last-run timestamp and Run Now button
- `POST /api/agents/jobber-sync/run` endpoint
- Show sync status: last run, customers synced count

### Task 06 — Customer detail source badge
**Files:** `templates/customer.html`
- Show source badge next to customer name: `Jobber`, `HousecallPro`, `Manual`
- Show `last_synced_at` if source is not manual
- Small indicator only — don't clutter the existing layout

### Task 07 — HousecallPro integration (parallel to Jobber)
**Files:** `integrations/housecallpro.py`, `agents/housecallpro_sync.py`
- HCP uses REST API with OAuth 2.0 (different API shape than Jobber's GraphQL)
- `get_customers(operator_id)`, `get_jobs(operator_id)`
- Sync agent mirrors jobber_sync.py structure
- Add HCP OAuth flow to `/settings` (same pattern as Jobber)
- Notes: tackle after Jobber is working end-to-end

---

## API Reference Notes

**Jobber:**
- GraphQL API: `https://api.getjobber.com/api/graphql`
- OAuth endpoints: `https://api.getjobber.com/api/oauth/authorize`, `https://api.getjobber.com/api/oauth/token`
- Scopes needed: `read_clients`, `read_jobs`
- Pagination: cursor-based via `pageInfo.endCursor`

**HousecallPro:**
- REST API: `https://api.housecallpro.com/v1/`
- OAuth: standard authorization code flow
- Scopes: `customers:read`, `jobs:read`

---

## Watch-outs

- Jobber uses GraphQL (not REST) — queries need to be defined, not just endpoints called
- Token refresh must be automatic — Jobber access tokens expire, refresh tokens need storing
- Dedup by email is imperfect (some customers may have multiple emails) — flag mismatches but don't crash
- Job type mapping from free-form Jobber titles is fuzzy — use Claude to classify if regex fails (log low-confidence mappings)
- Don't run sync if OAuth tokens don't exist — graceful skip with log message
- HCP API rate limits more aggressively than Jobber — add retry with backoff

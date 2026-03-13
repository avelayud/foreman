# Job 07 — Twilio Integration + SMS Send Path

**Phase:** 9
**Status:** ⬜ Not started
**Goal:** Add SMS as a parallel outreach channel. Wire Twilio for outbound sending and inbound webhook handling. SMS conversations use the same agent pipeline — different transport.

---

## Background

HVAC operators live in their phones. Customers respond to SMS faster and at higher rates than email for service businesses. Phase 9 adds SMS as a first-class channel alongside email.

**Design decisions:**
- Channel is **operator-driven** — operator selects Email or SMS per customer before drafting (not auto-selected by Foreman)
- `OutreachLog.channel` field: `email` (existing default) or `sms` (new)
- `Customer.phone_number` stored for SMS delivery
- Inbound SMS handled via Twilio webhook → same reply detector + classifier pipeline as email
- Twilio MessagingServiceSid preferred over a raw From number (better deliverability)

---

## New Environment Variables

```bash
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_FROM_NUMBER      # E.164 format: +15551234567
```

---

## New Files

### `integrations/sms.py`

```python
def send_sms(to_number: str, body: str, operator_id: int) -> dict:
    """Send SMS via Twilio. Returns {sms_sid, status, to, body}."""

def get_inbound_messages(since: datetime) -> list[dict]:
    """Pull inbound SMS from Twilio API since a given timestamp.
    Returns list of {from_number, body, sms_sid, received_at}."""
```

Error handling: Twilio exceptions caught and logged; never crash the main pipeline.

### `core/operator_config.py` addition (from Job 05)
No new file — `sms` channel config can live here if needed (e.g. SMS opt-in language).

---

## Model Changes

### `OutreachLog`
```python
channel = Column(String, default="email")   # "email" | "sms"
sms_sid = Column(String, nullable=True)     # Twilio SID for sent/received SMS
```

### `Customer`
```python
phone_number = Column(String, nullable=True)   # E.164 format
```

---

## SCHEMA_PATCHES

```python
("outreach_logs", "channel", "ALTER TABLE outreach_logs ADD COLUMN channel VARCHAR DEFAULT 'email'"),
("outreach_logs", "sms_sid", "ALTER TABLE outreach_logs ADD COLUMN sms_sid VARCHAR"),
("customers", "phone_number", "ALTER TABLE customers ADD COLUMN phone_number VARCHAR"),
```

---

## API Routes

### `POST /webhook/twilio/inbound`
Twilio inbound SMS webhook. Validates Twilio signature (use `twilio.request_validator`). Finds customer by `from_number`. Creates inbound `OutreachLog` with `channel=sms`. Triggers classifier pipeline (same as email reply detection). Returns TwiML `<Response/>` (empty — no auto-reply).

```python
@app.post("/webhook/twilio/inbound")
async def twilio_inbound_webhook(request: Request):
    ...
```

**Important:** Twilio webhook must be publicly accessible. Railway deployment URL is fine. Register in Twilio console: `https://web-production-3df3a.up.railway.app/webhook/twilio/inbound`

### Send path changes
Existing `POST /api/outreach/{id}/send` and `POST /api/action/send-now` routes check `OutreachLog.channel`:
- `channel == "email"` → existing `send_email()` path
- `channel == "sms"` → new `send_sms()` path, store `sms_sid`

---

## Reply Detector — Pass 3 (SMS)

Add a third pass to `agents/reply_detector.py`:

```python
def _scan_twilio_inbound(operator, db):
    """Pass 3: Pull inbound SMS from Twilio API since last scan.
    Match by from_number to Customer.phone_number.
    Create inbound OutreachLog (channel=sms) if not already logged (dedup by sms_sid).
    Trigger classifier pipeline same as email path."""
```

Dedup key: `OutreachLog.sms_sid` — skip if already logged.

---

## Seed Data Updates

Add phone numbers to existing seed customers so SMS can be tested locally. Format: E.164.

```python
# In data/reseed.py — add phone_number to customer seed dict
{"name": "...", "email": "...", "phone_number": "+15551234567", ...}
```

---

## Tasks

- [ ] task_01_env_and_deps.md — requirements.txt + .env.example + config.py
- [ ] task_02_model_migration.md — OutreachLog.channel, OutreachLog.sms_sid, Customer.phone_number
- [ ] task_03_sms_integration.md — integrations/sms.py (send + inbound fetch)
- [ ] task_04_webhook.md — POST /webhook/twilio/inbound + TwiML response
- [ ] task_05_send_path.md — route outgoing drafts to sms.send_sms() when channel=sms
- [ ] task_06_reply_detector_pass3.md — Pass 3 Twilio inbound scan
- [ ] task_07_seed_phone_numbers.md — add phone_number to reseed.py

---

## Files to Attach in Claude Code

```
PROJECT_PLAN.md
core/models.py
core/database.py
core/config.py
integrations/gmail.py       ← reference for send pattern
agents/reply_detector.py
api/app.py
requirements.txt
data/reseed.py
```

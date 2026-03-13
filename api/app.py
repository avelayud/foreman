"""
api/app.py
FastAPI application — serves the Foreman web UI and JSON API.

Web pages:
  GET /               → Dashboard (metrics + customer categories)
  GET /customer/{id}  → Customer detail (history + draft outreach)
  GET /outreach       → Outreach queue (drafts pending approval/sending)

JSON API:
  GET  /health
  GET  /api/operator/{id}
  GET  /api/operator/{id}/customers
  GET  /api/operator/{id}/stats
  POST /api/draft/{customer_id}          → generate draft via Claude
  POST /api/draft/{customer_id}/approve  → log draft, mark customer contacted
"""

import json
import os
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

import anthropic
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.config import config
from core.database import get_db, init_db
from core.models import Booking, Customer, Job, Operator, OutreachLog

app = FastAPI(title="Foreman", version="0.2.0")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

from zoneinfo import ZoneInfo as _ZoneInfo
from datetime import timezone as _tz

_EASTERN = _ZoneInfo("America/New_York")

def _jinja_est(dt, fmt="%-m/%-d/%y %-I:%M %p %Z"):
    """Format a naive UTC datetime as Eastern time for display."""
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz.utc)
    return dt.astimezone(_EASTERN).strftime(fmt)

templates.env.filters["est"] = _jinja_est

OPERATOR_ID = 1  # Single-tenant for now
SCHEDULE_POLL_SECONDS = 60
DB_STARTUP_MAX_ATTEMPTS = max(1, int(os.getenv("DB_STARTUP_MAX_ATTEMPTS", "8")))
DB_STARTUP_RETRY_SECONDS = max(1, int(os.getenv("DB_STARTUP_RETRY_SECONDS", "3")))
_scheduled_sender_started = False
_scheduled_sender_lock = threading.Lock()
_reply_detector_started = False
_reply_detector_lock = threading.Lock()
_db_ready = False
_db_init_error: Exception | None = None

REPLY_POLL_SECONDS = 900  # 15 minutes
_scoring_scheduler: BackgroundScheduler | None = None
_last_analyzer_run: datetime | None = None

# In-memory last-run tracker — updated after every agent run (manual or scheduled).
# Reset on process restart, but Run Now endpoints are now synchronous so the page
# reloads immediately after and the value is fresh.
_agent_last_run: dict[str, datetime | None] = {
    "tone_profiler": None,
    "reactivation": None,
    "scoring": None,
    "customer_analyzer": None,
    "reply_detector": None,
    "follow_up": None,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _operator_data(op) -> dict:
    """Serialize operator ORM object to a template-safe dict."""
    if not op:
        return {
            "id": None,
            "name": "Operator",
            "business_name": "Foreman",
            "niche": "hvac",
            "onboarding_complete": False,
            "voice_profiles": [],
            "tone_profile_set": False,
            "outreach_mode": "dry_run",
            "is_production_mode": False,
        }

    outreach_mode = (op.outreach_mode or "dry_run").strip().lower()
    if outreach_mode not in ("dry_run", "production"):
        outreach_mode = "dry_run"

    return {
        "id": op.id,
        "name": op.name,
        "business_name": op.business_name,
        "niche": op.niche,
        "onboarding_complete": op.onboarding_complete,
        "voice_profiles": op.voice_profiles,
        "tone_profile_set": bool(op.tone_profile),
        "outreach_mode": outreach_mode,
        "is_production_mode": outreach_mode == "production",
    }


_MEETINGS_CLASSIFICATIONS = ("booking_intent", "booking_confirmed")


def _get_queue_count(db) -> int:
    """Count items needing operator approval (pending only) for the sidebar badge."""
    return (
        db.query(OutreachLog)
        .filter(
            OutreachLog.operator_id == OPERATOR_ID,
            OutreachLog.dry_run == True,
            OutreachLog.approval_status == "pending",
            ~OutreachLog.response_classification.in_(_MEETINGS_CLASSIFICATIONS)
            | OutreachLog.response_classification.is_(None),
        )
        .count()
    )


def _get_meetings_queue_count(db) -> int:
    """Count pending meeting proposals and booking confirmations for the Meetings Queue badge."""
    return (
        db.query(OutreachLog)
        .filter(
            OutreachLog.operator_id == OPERATOR_ID,
            OutreachLog.dry_run == True,
            OutreachLog.response_classification.in_(_MEETINGS_CLASSIFICATIONS),
        )
        .count()
    )


def _get_conversations_attention_count(db) -> int:
    """Count conversation threads needing action (needs_response + needs_follow_up) for sidebar badge.
    Uses two efficient queries instead of N+1 per customer."""
    active_statuses = set(FOLLOW_UP_DUE_DAYS.keys()) | {"replied"}
    customers = (
        db.query(Customer.id, Customer.reactivation_status)
        .filter(
            Customer.operator_id == OPERATOR_ID,
            Customer.reactivation_status.in_(active_statuses),
        )
        .all()
    )
    if not customers:
        return 0
    customer_ids = [c.id for c in customers]
    status_by_id = {c.id: c.reactivation_status for c in customers}
    logs = (
        db.query(
            OutreachLog.customer_id,
            OutreachLog.direction,
            OutreachLog.sent_at,
            OutreachLog.created_at,
        )
        .filter(
            OutreachLog.operator_id == OPERATOR_ID,
            OutreachLog.customer_id.in_(customer_ids),
            OutreachLog.dry_run == False,
        )
        .all()
    )
    logs_by_customer = defaultdict(list)
    for log in logs:
        logs_by_customer[log.customer_id].append(log)
    count = 0
    for cid, status in status_by_id.items():
        clogs = logs_by_customer.get(cid, [])
        outbound = [l for l in clogs if l.direction == "outbound"]
        inbound = [l for l in clogs if l.direction == "inbound"]
        last_outbound_at = max((l.sent_at or l.created_at for l in outbound), default=None)
        last_inbound_at = max((l.sent_at or l.created_at for l in inbound), default=None)
        # Override status if inbound logs exist but status wasn't updated yet
        effective = status
        if inbound and effective not in ("booked", "sequence_complete", "unsubscribed", "replied"):
            effective = "replied"
        health = _conversation_health(effective, last_outbound_at, last_inbound_at)
        if health["needs_response"] or health["needs_follow_up"]:
            count += 1
    return count


def _parse_iso_datetime(value: str):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        return None


def _format_datetime_local(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%Y-%m-%dT%H:%M")


def _next_business_send_time(now: datetime | None = None) -> datetime:
    """
    Choose a default send window during business hours.
    - Weekdays only
    - 9:00 AM to 5:00 PM local time
    - Rounded to the next quarter hour
    """
    now = now or datetime.now()
    candidate = now + timedelta(minutes=30)
    candidate = candidate.replace(second=0, microsecond=0)

    remainder = candidate.minute % 15
    if remainder:
        candidate += timedelta(minutes=(15 - remainder))

    if candidate.hour < 9:
        candidate = candidate.replace(hour=9, minute=0, second=0, microsecond=0)
    elif candidate.hour >= 17:
        candidate = (candidate + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )

    while candidate.weekday() >= 5:
        candidate = (candidate + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )

    return candidate


def _gmail_send_message(to: str, subject: str, body: str, thread_id: str = None, in_reply_to: str = None) -> str:
    """Send a message through Gmail and return thread ID."""
    from integrations.gmail import send_email as gmail_send

    _, returned_thread_id = gmail_send(
        to=to, subject=subject, body=body, thread_id=thread_id, in_reply_to=in_reply_to
    )
    return returned_thread_id


def _get_customer_inbound_rfc_id(customer_id: int) -> str | None:
    """Return the RFC 2822 Message-ID of the customer's most recent inbound reply.
    Used to set In-Reply-To so the recipient's email client threads our response
    correctly under their sent message."""
    with get_db() as db:
        row = (
            db.query(OutreachLog.rfc_message_id)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.direction == "inbound",
                OutreachLog.rfc_message_id != None,
                OutreachLog.rfc_message_id != "",
            )
            .order_by(OutreachLog.sent_at.desc(), OutreachLog.created_at.desc())
            .first()
        )
        return row[0] if row and row[0] else None


def _get_customer_thread_id(log_id: int) -> str | None:
    """
    Return the gmail_thread_id to use when replying to a customer.

    MUST filter to outbound-only. Inbound logs (customer replies detected via
    Pass 2 inbox scan) may carry a different thread_id — one that lives in the
    customer's mailbox, not ours. Passing that thread_id to Gmail send() causes
    the reply to appear as a new thread on the recipient's side.
    """
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
        if not log:
            return None
        customer_id = log.customer_id
        existing_thread = (
            db.query(OutreachLog.gmail_thread_id)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.gmail_thread_id != None,
                OutreachLog.direction == "outbound",   # ← critical: never use inbound thread_id
                OutreachLog.dry_run == False,
            )
            .order_by(OutreachLog.sent_at.desc())
            .first()
        )
        return existing_thread[0] if existing_thread else None


def _deliver_outreach_log(
    log_id: int,
    *,
    subject: str,
    body: str,
    customer_email: str | None,
    scheduled_send_at: datetime | None = None,
) -> tuple[str | None, str | None]:
    """
    Attempt to deliver an outreach message via Gmail and persist delivery status.
    Returns (thread_id, send_error).
    """
    thread_id = None
    send_error = None

    if customer_email:
        try:
            existing_thread_id = _get_customer_thread_id(log_id)
            # Look up customer_id from the log so we can fetch the inbound RFC ID
            with get_db() as _db:
                _log_row = _db.query(OutreachLog.customer_id).filter_by(
                    id=log_id, operator_id=OPERATOR_ID
                ).first()
                _cid = _log_row[0] if _log_row else None
            inbound_rfc_id = _get_customer_inbound_rfc_id(_cid) if _cid else None
            thread_id = _gmail_send_message(
                to=customer_email,
                subject=subject,
                body=body,
                thread_id=existing_thread_id,
                in_reply_to=inbound_rfc_id,
            )
        except Exception as exc:
            send_error = str(exc)
    else:
        send_error = "Customer has no email address on file"

    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
        if not log:
            return None, "Log entry not found"

        now_utc = datetime.utcnow()
        log.approved_at = log.approved_at or now_utc

        if thread_id:
            log.dry_run = False
            log.approval_status = "sent"
            log.sent_at = now_utc
            log.send_error = None
            log.gmail_thread_id = thread_id
        else:
            log.dry_run = True
            log.approval_status = "failed"
            log.send_error = send_error or "Unknown send failure"

        if scheduled_send_at is not None:
            log.scheduled_send_at = scheduled_send_at

    return thread_id, send_error


def _process_scheduled_outreach_once():
    """Send due scheduled outreach logs (production mode only)."""
    now_utc = datetime.utcnow()
    with get_db() as db:
        due_rows = (
            db.query(
                OutreachLog.id,
                OutreachLog.subject,
                OutreachLog.content,
                OutreachLog.scheduled_send_at,
                Customer.email.label("customer_email"),
            )
            .join(Customer, OutreachLog.customer_id == Customer.id)
            .join(Operator, OutreachLog.operator_id == Operator.id)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                OutreachLog.approval_status == "scheduled",
                OutreachLog.scheduled_send_at != None,
                OutreachLog.scheduled_send_at <= now_utc,
                Operator.outreach_mode == "production",
            )
            .order_by(OutreachLog.scheduled_send_at.asc(), OutreachLog.id.asc())
            .limit(25)
            .all()
        )

    for row in due_rows:
        thread_id, send_error = _deliver_outreach_log(
            log_id=row.id,
            subject=row.subject or "",
            body=row.content or "",
            customer_email=row.customer_email,
            scheduled_send_at=row.scheduled_send_at,
        )
        if thread_id:
            print(f"[scheduled_sender] Sent outreach log {row.id}")
        else:
            print(f"[scheduled_sender] Failed outreach log {row.id}: {send_error}")


def _scheduled_sender_loop():
    while True:
        try:
            _process_scheduled_outreach_once()
        except Exception as exc:
            print(f"[scheduled_sender] loop error: {exc}")
        time.sleep(SCHEDULE_POLL_SECONDS)


def _start_scheduled_sender():
    global _scheduled_sender_started
    with _scheduled_sender_lock:
        if _scheduled_sender_started:
            return
        worker = threading.Thread(
            target=_scheduled_sender_loop,
            daemon=True,
            name="scheduled-outreach-sender",
        )
        worker.start()
        _scheduled_sender_started = True
        print(f"✅ Scheduled outreach sender started (poll: {SCHEDULE_POLL_SECONDS}s)")


def _reply_detector_loop():
    """Poll Gmail for customer replies every REPLY_POLL_SECONDS."""
    global _agent_last_run
    # Delay first run by 30s to let the app fully settle
    time.sleep(30)
    while True:
        try:
            from agents.reply_detector import run as run_reply_detector
            count = run_reply_detector(operator_id=OPERATOR_ID)
            _agent_last_run["reply_detector"] = datetime.utcnow()
            if count:
                print(f"[reply_detector] {count} new reply(s) detected", flush=True)
        except Exception as exc:
            print(f"[reply_detector] loop error: {exc}", flush=True)
        time.sleep(REPLY_POLL_SECONDS)


def _start_reply_detector():
    global _reply_detector_started
    with _reply_detector_lock:
        if _reply_detector_started:
            return
        worker = threading.Thread(
            target=_reply_detector_loop,
            daemon=True,
            name="reply-detector",
        )
        worker.start()
        _reply_detector_started = True
        print(f"✅ Reply detector started (poll: {REPLY_POLL_SECONDS}s / 15 min)", flush=True)


def _run_scoring_job():
    """Score all customers — called at startup and daily by APScheduler."""
    global _agent_last_run
    try:
        from core.scoring import score_all_customers
        with get_db() as db:
            count = score_all_customers(db, operator_id=OPERATOR_ID)
        _agent_last_run["scoring"] = datetime.utcnow()
        print(f"[scoring] Scored {count} customers.", flush=True)
    except Exception as exc:
        print(f"[scoring] error: {exc}", flush=True)


def _run_customer_analyzer_job():
    """Run customer analyzer on all customers with correspondence or no profile yet."""
    global _last_analyzer_run
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    try:
        from agents.customer_analyzer import analyze_customer
        with get_db() as db:
            customer_ids_with_logs = {
                row[0] for row in
                db.query(OutreachLog.customer_id)
                .filter_by(operator_id=OPERATOR_ID)
                .distinct()
                .all()
            }
            customers = db.query(Customer).filter_by(operator_id=OPERATOR_ID).all()
            to_analyze = []
            for c in customers:
                if not c.email:
                    continue
                raw = c.customer_profile
                profile = {}
                if isinstance(raw, dict):
                    profile = raw
                elif isinstance(raw, str):
                    try:
                        profile = _json.loads(raw)
                    except Exception:
                        profile = {}
                not_analyzed = not profile or not profile.get("analyzed_at")
                has_history = c.id in customer_ids_with_logs
                if not_analyzed or has_history:
                    to_analyze.append(c.id)
        for cid in to_analyze:
            try:
                analyze_customer(OPERATOR_ID, cid, verbose=False)
            except Exception as exc:
                print(f"[customer_analyzer] error on customer {cid}: {exc}", flush=True)
        _last_analyzer_run = _dt.now(_tz.utc).replace(tzinfo=None)
        _agent_last_run["customer_analyzer"] = _last_analyzer_run
        print(f"[customer_analyzer] Analyzed {len(to_analyze)} customers.", flush=True)
        return len(to_analyze)
    except Exception as exc:
        print(f"[customer_analyzer] job error: {exc}", flush=True)
        return 0


def _run_follow_up_job():
    """Run follow-up sequencer — called daily by APScheduler and on manual Run Now."""
    global _agent_last_run
    try:
        from agents.follow_up import run as run_follow_up
        run_follow_up(operator_id=OPERATOR_ID)
        _agent_last_run["follow_up"] = datetime.utcnow()
        print("[follow_up] Daily run complete.", flush=True)
    except Exception as exc:
        print(f"[follow_up] error: {exc}", flush=True)


def _refresh_queued_drafts():
    """
    Scans pending queue drafts. If a customer replied after a draft was created,
    regenerates the draft with updated context so it reflects the latest message.
    Runs every 15 minutes alongside reply_detector.
    """
    print("[queue_refresh] Scanning pending drafts for stale context...", flush=True)
    try:
        with get_db() as db:
            pending = (
                db.query(OutreachLog)
                .filter(
                    OutreachLog.operator_id == OPERATOR_ID,
                    OutreachLog.dry_run == True,
                    OutreachLog.direction == "outbound",
                )
                .all()
            )
            to_refresh = []
            for draft in pending:
                newer_inbound = (
                    db.query(OutreachLog)
                    .filter(
                        OutreachLog.customer_id == draft.customer_id,
                        OutreachLog.operator_id == OPERATOR_ID,
                        OutreachLog.direction == "inbound",
                        OutreachLog.dry_run == False,
                        OutreachLog.created_at > draft.created_at,
                    )
                    .first()
                )
                if newer_inbound:
                    to_refresh.append({
                        "draft_id": draft.id,
                        "customer_id": draft.customer_id,
                        "classification": draft.response_classification or "unclear",
                        "inbound_log_id": newer_inbound.id,
                    })

        for item in to_refresh:
            print(f"  [queue_refresh] Refreshing draft {item['draft_id']} for customer {item['customer_id']}", flush=True)
            try:
                with get_db() as db:
                    old = db.query(OutreachLog).filter_by(id=item["draft_id"]).first()
                    if old:
                        db.delete(old)
                from agents.conversation_agent import generate_response
                generate_response(
                    operator_id=OPERATOR_ID,
                    customer_id=item["customer_id"],
                    classification=item["classification"],
                    inbound_log_id=item["inbound_log_id"],
                    verbose=False,
                )
            except Exception as e:
                print(f"  [queue_refresh] Error refreshing draft {item['draft_id']}: {e}", flush=True)

        print(f"[queue_refresh] Done. {len(to_refresh)} draft(s) refreshed.", flush=True)
    except Exception as e:
        print(f"[queue_refresh] Error: {e}", flush=True)


def _start_scoring_scheduler():
    global _scoring_scheduler
    if _scoring_scheduler is not None:
        return
    _run_scoring_job()  # run once immediately
    _run_customer_analyzer_job()
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(_run_scoring_job, "interval", hours=24, id="daily_scoring")
    scheduler.add_job(_run_customer_analyzer_job, "interval", hours=24, id="daily_analyzer")
    scheduler.add_job(_run_follow_up_job, "interval", hours=24, id="daily_follow_up")
    scheduler.add_job(_refresh_queued_drafts, "interval", minutes=15, id="queue_refresh")
    scheduler.start()
    _scoring_scheduler = scheduler
    print("✅ Scoring scheduler started (daily).", flush=True)


def _normalize_customer_profile(profile: dict | None) -> dict:
    profile = profile or {}
    topics = profile.get("topics_discussed")
    concerns = profile.get("prior_concerns")
    try:
        email_count = int(profile.get("email_count") or 0)
    except (TypeError, ValueError):
        email_count = 0

    return {
        "relationship_history": profile.get("relationship_history") or "",
        "topics_discussed": topics if isinstance(topics, list) else [],
        "customer_tone": profile.get("customer_tone") or "unknown",
        "prior_concerns": concerns if isinstance(concerns, list) else [],
        "response_patterns": profile.get("response_patterns") or "",
        "interest_signals": profile.get("interest_signals") or "",
        "context_notes": profile.get("context_notes") or "",
        "analyzed_at": _parse_iso_datetime(profile.get("analyzed_at")),
        "email_count": email_count,
    }


def days_since(dt) -> int:
    if not dt:
        return 0
    return (datetime.utcnow() - dt).days


def categorize_from_dict(cd: dict, days: int, status: str) -> str:
    """Categorize using a pre-serialized customer dict."""
    if status == "unsubscribed":
        return "unsubscribed"
    if status in ("outreach_sent", "sequence_step_2", "sequence_step_3"):
        return "in_sequence"
    if status in ("replied", "booked", "sequence_complete"):
        return "converted"
    if days >= 365:
        return "prime"
    if days >= 180:
        return "warming"
    return "recent"


def categorize(customer) -> str:
    days = days_since(customer.last_service_date)
    status = customer.reactivation_status
    if status == "unsubscribed":
        return "unsubscribed"
    if status in ("outreach_sent", "sequence_step_2", "sequence_step_3"):
        return "in_sequence"
    if status in ("replied", "booked", "sequence_complete"):
        return "converted"
    if days >= 365:
        return "prime"
    if days >= 180:
        return "warming"
    return "recent"


def enrich(c) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "last_service_date": c.last_service_date,
        "last_service_type": c.last_service_type,
        "total_jobs": c.total_jobs,
        "total_spend": c.total_spend,
        "reactivation_status": c.reactivation_status,
        "days_dormant": days_since(c.last_service_date),
        "category": categorize(c),
    }


SEGMENT_INFO = {
    'referral':    ('👥 Referral Ready', 'pill-ref'),
    'high_value':  ('🔥 High Value',     'pill-hv'),
    'end_of_life': ('⚠️ End-of-Life',    'pill-eol'),
    'new_lead':    ('🆕 New Lead',        'pill-new'),
    'maintenance': ('🔧 Maintenance Due', 'pill-maint'),
}

def get_segment_key(c: dict) -> str:
    if c['reactivation_status'] in ('replied', 'booked'):
        return 'referral'
    if c['total_spend'] >= 1500:
        return 'high_value'
    if c['days_dormant'] >= 730:
        return 'end_of_life'
    svc = (c.get('last_service_type') or '').lower()
    if c['total_jobs'] == 1 or 'install' in svc:
        return 'new_lead'
    return 'maintenance'

def add_segment(c: dict) -> dict:
    key = get_segment_key(c)
    label, cls = SEGMENT_INFO[key]
    avg_job = c['total_spend'] / max(c['total_jobs'], 1)
    opp_map = {
        'end_of_life': (avg_job * 3.5, 'system replacement'),
        'high_value':  (avg_job,        'seasonal service'),
        'new_lead':    (avg_job * 0.6,  'maintenance plan'),
        'referral':    (400,            'referral value'),
        'maintenance': (avg_job * 0.75, 'tune-up'),
    }
    opp_val, opp_label = opp_map[key]
    c['segment_key']    = key
    c['segment_label']  = label
    c['segment_cls']    = cls
    c['opp_est']        = f"~${opp_val:,.0f}"
    c['opp_label']      = opp_label
    c['priority_score'] = c['days_dormant'] * (c['total_spend'] / 1000 + 0.5)
    return c


CONVERSATION_STAGE_META = {
    "never_contacted": {"label": "Not Started", "progress_pct": 0, "status_cls": "s-none"},
    "outreach_sent": {"label": "Initial Outreach Sent", "progress_pct": 25, "status_cls": "s-sent"},
    "sequence_step_2": {"label": "Follow-up 1 Sent", "progress_pct": 50, "status_cls": "s-warm"},
    "sequence_step_3": {"label": "Follow-up 2 Sent", "progress_pct": 75, "status_cls": "s-warm"},
    "replied": {"label": "Customer Replied", "progress_pct": 100, "status_cls": "s-ok"},
    "booked": {"label": "Booked", "progress_pct": 100, "status_cls": "s-ok"},
    "sequence_complete": {"label": "Sequence Complete", "progress_pct": 100, "status_cls": "s-none"},
    "unsubscribed": {"label": "Unsubscribed", "progress_pct": 0, "status_cls": "s-none"},
}


CONVERSATION_HEALTH_META = {
    "needs_response": {"label": "Needs Response", "chip_cls": "needs-response", "rank": 0},
    "needs_follow_up": {"label": "Needs Follow-up", "chip_cls": "needs-follow-up", "rank": 1},
    "awaiting_reply": {"label": "Awaiting Reply", "chip_cls": "awaiting-reply", "rank": 2},
    "closed": {"label": "Closed", "chip_cls": "closed", "rank": 3},
}


FOLLOW_UP_DUE_DAYS = {
    "outreach_sent": 3,
    "sequence_step_2": 7,
    "sequence_step_3": 14,
}


OUTREACH_STATUS_META = {
    "pending": {"label": "Pending approval", "chip_cls": "pending", "rank": 1},
    "approved": {"label": "Approved · waiting to send", "chip_cls": "approved", "rank": 2},
    "scheduled": {"label": "Scheduled to send", "chip_cls": "scheduled", "rank": 3},
    "failed": {"label": "Send failed · retry required", "chip_cls": "failed", "rank": 0},
    "sent": {"label": "Sent", "chip_cls": "sent", "rank": 4},
}


def _outreach_status(log: OutreachLog) -> str:
    status = (log.approval_status or "").strip().lower()
    if status in OUTREACH_STATUS_META:
        return status
    return "pending" if log.dry_run else "sent"


def _outreach_sequence_label(sequence_step: int | None, response_classification: str | None = None) -> str:
    if response_classification == "booking_intent":
        return "Booking proposal"
    if response_classification == "price_inquiry":
        return "Price response"
    if response_classification == "callback_request":
        return "Callback acknowledgement"
    if response_classification == "unclear":
        return "Clarifying reply"
    step = int(sequence_step or 0)
    if step <= 0:
        return "Initial outreach"
    return f"Follow-up {step}"


def _conversation_stage(status: str) -> dict:
    return CONVERSATION_STAGE_META.get(
        status,
        {"label": status.replace("_", " ").title(), "progress_pct": 0, "status_cls": "s-none"},
    )


def _conversation_health(status: str, last_outbound_at, last_inbound_at):
    if status in ("booked", "sequence_complete", "unsubscribed"):
        key = "closed"
        meta = CONVERSATION_HEALTH_META[key]
        return {
            "key": key,
            "label": meta["label"],
            "chip_cls": meta["chip_cls"],
            "rank": meta["rank"],
            "needs_response": False,
            "needs_follow_up": False,
        }

    if last_inbound_at and (not last_outbound_at or last_inbound_at > last_outbound_at):
        key = "needs_response"
        meta = CONVERSATION_HEALTH_META[key]
        return {
            "key": key,
            "label": meta["label"],
            "chip_cls": meta["chip_cls"],
            "rank": meta["rank"],
            "needs_response": True,
            "needs_follow_up": False,
        }

    # "replied" always means the customer is waiting for our response
    if status == "replied":
        key = "needs_response"
        meta = CONVERSATION_HEALTH_META[key]
        return {
            "key": key,
            "label": meta["label"],
            "chip_cls": meta["chip_cls"],
            "rank": meta["rank"],
            "needs_response": True,
            "needs_follow_up": False,
        }

    due_days = FOLLOW_UP_DUE_DAYS.get(status)
    if due_days and last_outbound_at and days_since(last_outbound_at) >= due_days:
        key = "needs_follow_up"
        meta = CONVERSATION_HEALTH_META[key]
        return {
            "key": key,
            "label": meta["label"],
            "chip_cls": meta["chip_cls"],
            "rank": meta["rank"],
            "needs_response": False,
            "needs_follow_up": True,
        }

    key = "awaiting_reply"
    meta = CONVERSATION_HEALTH_META[key]
    return {
        "key": key,
        "label": meta["label"],
        "chip_cls": meta["chip_cls"],
        "rank": meta["rank"],
        "needs_response": False,
        "needs_follow_up": False,
    }


def _log_timestamp(log) -> datetime | None:
    if not log:
        return None
    return log.sent_at or log.created_at


def _timeline_date_key(item: dict) -> datetime:
    return item.get("at") or datetime.min


def _compact_summary(content: str, max_len: int = 140) -> str:
    text = (content or "").strip().replace("\n", " ")
    if not text:
        return "No message content."
    text = " ".join(text.split())

    for sep in (". ", "? ", "! "):
        if sep in text:
            first_sentence = text.split(sep, 1)[0].strip()
            if len(first_sentence) >= 32:
                return first_sentence[:max_len] + ("..." if len(first_sentence) > max_len else "")

    return text[:max_len] + ("..." if len(text) > max_len else "")


def _generate_timeline_summaries(log_entries: list[dict]) -> dict[int, str]:
    """One Claude call to produce a one-sentence snapshot for each timeline event.
    Returns {log_id: summary}. Falls back to {} on any error."""
    if not log_entries:
        return {}
    try:
        items = []
        for entry in log_entries:
            direction = "Customer reply" if entry["direction"] == "inbound" else "Outbound email"
            body = (entry.get("content") or "")[:500].strip().replace("\n", " ")
            items.append(
                f'ID:{entry["id"]} [{direction}] Subject:"{entry["subject"]}"\n{body}'
            )
        prompt = (
            "For each email below, write ONE concise sentence (max 18 words) summarising "
            "the specific content — what was said, asked, or offered. Be concrete, not generic.\n\n"
            + "\n\n---\n\n".join(items)
            + '\n\nReturn a JSON array only: [{"id": <int>, "summary": "<sentence>"}]'
        )
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:]).rstrip("`").strip()
        return {item["id"]: item["summary"] for item in json.loads(raw)}
    except Exception as exc:
        print(f"[timeline_summaries] failed: {exc}")
        return {}


def _auto_next_steps(status: str, last_outbound_at, last_inbound_at):
    if last_inbound_at and (not last_outbound_at or last_inbound_at > last_outbound_at):
        return [
            {"title": "Reply to customer", "timing": "Within 12 hours", "owner": "Human"},
            {"title": "Capture intent + booking notes", "timing": "After reply", "owner": "Agent"},
        ]

    if status == "outreach_sent":
        elapsed = days_since(last_outbound_at) if last_outbound_at else 0
        if elapsed >= 3:
            return [
                {"title": "Generate Follow-up 1 draft", "timing": "Due now", "owner": "Agent"},
                {"title": "Review + send follow-up", "timing": "Today", "owner": "Human"},
            ]
        return [
            {"title": "Monitor for inbound response", "timing": f"In {max(3 - elapsed, 0)} day(s)", "owner": "Agent"},
            {"title": "Keep queue clear for new sends", "timing": "Daily", "owner": "Human"},
        ]

    if status == "sequence_step_2":
        elapsed = days_since(last_outbound_at) if last_outbound_at else 0
        if elapsed >= 7:
            return [
                {"title": "Generate Follow-up 2 draft", "timing": "Due now", "owner": "Agent"},
                {"title": "Send follow-up if approved", "timing": "Today", "owner": "Human"},
            ]
        return [
            {"title": "Wait for response before step 3", "timing": f"In {max(7 - elapsed, 0)} day(s)", "owner": "Agent"},
        ]

    if status == "sequence_step_3":
        elapsed = days_since(last_outbound_at) if last_outbound_at else 0
        if elapsed >= 14:
            return [
                {"title": "Close-loop this sequence", "timing": "Due now", "owner": "Agent"},
            ]
        return [
            {"title": "Final wait window", "timing": f"In {max(14 - elapsed, 0)} day(s)", "owner": "Agent"},
        ]

    if status == "replied":
        return [
            {"title": "Move toward booking", "timing": "Today", "owner": "Human"},
            {"title": "Tag conversation as warm opportunity", "timing": "After response", "owner": "Agent"},
        ]

    if status == "booked":
        return [
            {"title": "Confirm appointment details", "timing": "Now", "owner": "Human"},
            {"title": "Trigger reminder sequence", "timing": "24h before visit", "owner": "Agent"},
        ]

    return [
        {"title": "No immediate action required", "timing": "Monitor", "owner": "Agent"},
    ]


def _conversation_recap(customer: dict, stage: dict, health: dict, logs: list[dict], next_steps: list[dict]) -> dict:
    """
    Build an operator-ready briefing:
    - What this thread has covered
    - Known issues or sensitivities
    - Current situation and immediate objective
    - Practical talking points based on profile + pipeline analytics
    """
    profile = customer.get("customer_profile") or {}
    outbound_logs = [entry for entry in logs if entry["direction"] == "outbound"]
    inbound_logs = [entry for entry in logs if entry["direction"] == "inbound"]
    latest = logs[0] if logs else None

    topics = profile.get("topics_discussed") or []
    concerns = profile.get("prior_concerns") or []
    response_patterns = (profile.get("response_patterns") or "").strip()
    context_notes = (profile.get("context_notes") or "").strip()
    relationship_history = (profile.get("relationship_history") or "").strip()
    tone = (profile.get("customer_tone") or "").strip()
    interest_signals = (profile.get("interest_signals") or "").strip()

    outbound_sample = [entry["summary"] for entry in outbound_logs[:2] if entry.get("summary")]
    inbound_sample = [entry["summary"] for entry in inbound_logs[:2] if entry.get("summary")]

    correspondence_bits = []
    if isinstance(topics, list) and topics:
        correspondence_bits.append(", ".join(str(topic) for topic in topics[:4]))
    if inbound_sample:
        correspondence_bits.append(f"customer replies mention: {' | '.join(inbound_sample[:2])}")
    if outbound_sample:
        correspondence_bits.append(f"outreach so far: {' | '.join(outbound_sample[:2])}")
    if not correspondence_bits and logs:
        correspondence_bits.append("message history exists, but no structured topic tags are available yet")
    if not correspondence_bits:
        correspondence_bits.append("no active correspondence has been logged yet")

    issue_bits = []
    if isinstance(concerns, list) and concerns:
        issue_bits.extend(str(concern) for concern in concerns[:3])
    if response_patterns:
        issue_bits.append(response_patterns)
    if context_notes:
        issue_bits.append(context_notes)
    if not issue_bits:
        issue_bits.append("No explicit concerns captured yet.")

    latest_actor = "customer" if latest and latest["direction"] == "inbound" else "agent"
    latest_at = latest.get("at") if latest else None
    latest_date = latest_at.strftime("%b %-d at %-I:%M %p") if latest_at else "no recent touch logged"
    current_position = (
        f"Stage: {stage['label']}. Health: {health['label']}. "
        f"Thread currently has {len(outbound_logs)} outbound and {len(inbound_logs)} inbound message(s). "
        f"Most recent touch was by {latest_actor} ({latest_date})."
    )

    primary_objective = next_steps[0]["title"] if next_steps else "Keep momentum and move toward booking."

    briefing_rows = [
        {
            "label": "Correspondence So Far",
            "value": "; ".join(correspondence_bits),
        },
        {
            "label": "Known Issues / Sensitivities",
            "value": "; ".join(issue_bits[:4]),
        },
        {
            "label": "Current Situation",
            "value": current_position,
        },
        {
            "label": "Primary Objective For Next Touch",
            "value": primary_objective,
        },
    ]

    talking_points: list[str] = []
    if health.get("needs_response"):
        talking_points.append("Open by acknowledging their latest reply and answer the unresolved point first.")
    elif health.get("needs_follow_up"):
        talking_points.append("Lead with a short follow-up recap, then make one concrete ask for next action.")
    else:
        talking_points.append("Start with a concise recap of prior outreach and confirm if timing is right to proceed.")

    opp_est = customer.get("opp_est")
    opp_label = customer.get("opp_label")
    if opp_est and opp_label:
        talking_points.append(f"Anchor value: this looks like a {opp_est} {opp_label} opportunity.")

    total_spend = float(customer.get("total_spend") or 0)
    if total_spend >= 1500:
        talking_points.append("Reference their strong history with your team and position this as proactive support.")

    dormant_days = int(customer.get("days_dormant") or 0)
    if dormant_days >= 365:
        talking_points.append(f"Acknowledge that it has been {dormant_days} days since last service and re-establish urgency.")

    if isinstance(concerns, list):
        for concern in concerns[:2]:
            talking_points.append(f"Proactively address concern: {concern}.")

    if isinstance(topics, list) and topics:
        talking_points.append(f"Use topic continuity: reconnect on {topics[0]}.")

    if tone and tone.lower() != "unknown":
        talking_points.append(f"Match customer tone ({tone}) to keep the call aligned.")

    if relationship_history:
        talking_points.append("Use relationship context to personalize: " + relationship_history[:120] + ("..." if len(relationship_history) > 120 else ""))

    if interest_signals:
        talking_points.append("Highlight interest signal: " + interest_signals[:120] + ("..." if len(interest_signals) > 120 else ""))

    deduped_talking_points = []
    seen = set()
    for point in talking_points:
        key = point.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped_talking_points.append(point)

    return {
        "operator_summary": (
            f"This thread is currently {health['label'].lower()} and the next operator action is: "
            f"{primary_objective}."
        ),
        "briefing_rows": briefing_rows,
        "talking_points": deduped_talking_points[:7],
    }


# ── Startup ───────────────────────────────────────────────────────────────────

def _try_init_db_once(timeout_seconds: float = 8.0) -> None:
    """Run init_db() in a sub-thread with a hard wall-clock timeout.

    psycopg2's connect_timeout only covers the TCP handshake; DNS hangs are
    not covered and can block indefinitely. This wrapper enforces a true
    deadline regardless of where the hang occurs.
    """
    done = threading.Event()
    error_holder: list[Exception | None] = [None]

    def _worker():
        try:
            init_db()
        except Exception as exc:
            error_holder[0] = exc
        finally:
            done.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    if not done.wait(timeout_seconds):
        raise RuntimeError(
            f"DB init timed out after {timeout_seconds}s "
            f"(DATABASE_URL={os.getenv('DATABASE_URL', 'not set')[:40]}…)"
        )
    if error_holder[0]:
        raise error_holder[0]


def _init_db_background():
    """
    Initialise the database in a background thread so uvicorn can bind to PORT
    immediately. Railway starts Postgres and the web service in parallel, so a
    transient connection failure at boot time must not crash the process.
    """
    global _db_ready, _db_init_error
    print("[db-init] starting background DB init…", flush=True, file=sys.stderr)
    for attempt in range(1, DB_STARTUP_MAX_ATTEMPTS + 1):
        try:
            _try_init_db_once(timeout_seconds=20.0)
            _db_ready = True
            _db_init_error = None
            print("✅ Database ready.", flush=True, file=sys.stderr)
            _start_scheduled_sender()
            _start_reply_detector()
            _start_scoring_scheduler()
            return
        except Exception as exc:
            _db_init_error = exc
            print(
                f"[db-init] attempt {attempt}/{DB_STARTUP_MAX_ATTEMPTS} failed: {exc}",
                flush=True, file=sys.stderr,
            )
            if attempt < DB_STARTUP_MAX_ATTEMPTS:
                time.sleep(DB_STARTUP_RETRY_SECONDS)
    print(
        f"[db-init] FATAL: all retries exhausted. Last error: {_db_init_error}",
        flush=True, file=sys.stderr,
    )


@app.on_event("startup")
def startup():
    t = threading.Thread(target=_init_db_background, daemon=True, name="db-init")
    t.start()


_STARTING_UP_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="4">
<title>Foreman — Starting up</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;background:#f9fafb;}}
.box{{text-align:center;color:#374151;}}
h2{{font-size:1.5rem;margin-bottom:.5rem;}}
p{{color:#6b7280;font-size:.95rem;}}
</style></head>
<body><div class="box">
<h2>Foreman is starting up&hellip;</h2>
<p>Connecting to the database. This page will refresh automatically.</p>
{error_line}
</div></body></html>"""


def _db_starting_response() -> HTMLResponse | None:
    """Return a fast holding page if the DB is not yet ready, else None."""
    if _db_ready:
        return None
    error_line = (
        f'<p style="color:#ef4444;font-size:.85rem;">DB error: {_db_init_error}</p>'
        if _db_init_error else ""
    )
    return HTMLResponse(
        _STARTING_UP_HTML.format(error_line=error_line),
        status_code=503,
    )


# ── Web pages ─────────────────────────────────────────────────────────────────

def _get_enriched_customers(operator_id: int) -> list[dict]:
    """Fetch and enrich all customers. Returns plain dicts, safe to use outside DB session."""
    with get_db() as db:
        raw_customers = db.query(Customer).filter_by(operator_id=operator_id).all()
        last_interaction_rows = (
            db.query(OutreachLog.customer_id, OutreachLog.sent_at, OutreachLog.direction)
            .filter(OutreachLog.operator_id == operator_id, OutreachLog.dry_run == False)
            .order_by(OutreachLog.sent_at.desc())
            .all()
        )
        last_interaction: dict[int, dict] = {}
        for row in last_interaction_rows:
            if row.customer_id not in last_interaction:
                last_interaction[row.customer_id] = {
                    "date": row.sent_at,
                    "direction": row.direction,
                }
        customers_raw = []
        for c in raw_customers:
            score_bd = {}
            try:
                score_bd = json.loads(c.score_breakdown or "{}")
            except Exception:
                pass
            customers_raw.append({
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "address": c.address,
                "last_service_date": c.last_service_date,
                "last_service_type": c.last_service_type,
                "total_jobs": c.total_jobs,
                "total_spend": c.total_spend,
                "reactivation_status": c.reactivation_status,
                "score": c.score or 0,
                "score_breakdown": score_bd,
                "priority_tier": c.priority_tier or "low",
                "estimated_job_value": c.estimated_job_value or 0.0,
                "service_interval_days": c.service_interval_days,
                "predicted_next_service": c.predicted_next_service,
                "last_interaction": last_interaction.get(c.id),
            })

    enriched = []
    for cd in customers_raw:
        days = days_since(cd["last_service_date"])
        status = cd["reactivation_status"]
        cat = categorize_from_dict(cd, days, status)
        cd["days_dormant"] = days
        cd["category"] = cat
        if status == "booked":
            cd["outreach_status"] = "Booked"
            cd["outreach_status_cls"] = "s-booked"
        elif status == "replied":
            cd["outreach_status"] = "Replied"
            cd["outreach_status_cls"] = "s-replied"
        elif status in ("outreach_sent", "sequence_step_2", "sequence_step_3"):
            cd["outreach_status"] = "Contacted"
            cd["outreach_status_cls"] = "s-contacted"
        elif status == "unsubscribed":
            cd["outreach_status"] = "Unsubscribed"
            cd["outreach_status_cls"] = "s-unsub"
        else:
            cd["outreach_status"] = "Not Contacted"
            cd["outreach_status_cls"] = "s-none"
        score = cd["score"]
        if score >= 70:
            cd["score_cls"] = "score-high"
        elif score >= 40:
            cd["score_cls"] = "score-med"
        else:
            cd["score_cls"] = "score-low"
        enriched.append(cd)
    return enriched


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if (guard := _db_starting_response()):
        return guard

    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        queue_count = db.query(OutreachLog).filter_by(
            operator_id=OPERATOR_ID, dry_run=True
        ).count()
        conversations_attention_count = _get_conversations_attention_count(db)
        operator_data = _operator_data(operator)

        # ── Phase 5 metrics ────────────────────────────────────────────────
        # Responses received (inbound outreach logs)
        responses_received = db.query(OutreachLog).filter_by(
            operator_id=OPERATOR_ID, direction="inbound"
        ).count()

        # Active conversations: customers with outbound sent but not booked/unsubscribed
        active_statuses = ("outreach_sent", "sequence_step_2", "sequence_step_3", "replied")
        active_conversations = db.query(Customer).filter(
            Customer.operator_id == OPERATOR_ID,
            Customer.reactivation_status.in_(active_statuses),
        ).count()

        # Jobs booked via Foreman (converted_to_job = True)
        booked_logs = db.query(OutreachLog).filter_by(
            operator_id=OPERATOR_ID, converted_to_job=True
        ).all()
        jobs_booked = len(booked_logs)
        revenue_generated = sum(
            (l.converted_job_value or 0.0) for l in booked_logs
        )

    enriched = _get_enriched_customers(OPERATOR_ID)

    # Partition into 4 groups
    group_upcoming = sorted(
        [c for c in enriched if c["reactivation_status"] == "booked"],
        key=lambda x: -x["score"],
    )
    group_attention = sorted(
        [c for c in enriched if c["reactivation_status"] in ("replied", "outreach_sent", "sequence_step_2", "sequence_step_3")],
        key=lambda x: (0 if x["reactivation_status"] == "replied" else 1, -x["score"]),
    )
    group_ripe = sorted(
        [c for c in enriched if c["reactivation_status"] == "never_contacted"],
        key=lambda x: -x["score"],
    )
    group_declined = sorted(
        [c for c in enriched if c["reactivation_status"] in ("sequence_complete", "unsubscribed")],
        key=lambda x: -x["score"],
    )

    # ── 8 dashboard metric cards ───────────────────────────────────────────
    dormant_customers = [
        c for c in enriched
        if c["score"] > 40
        and c["reactivation_status"] == "never_contacted"
    ]
    dormant_count = len(dormant_customers)

    # "contacted in last 90 days" = outreach_sent/replied/etc.
    total_dormant_eligible = [
        c for c in enriched
        if c["score"] > 40
        and c["reactivation_status"] != "unsubscribed"
    ]
    contacted_dormant = sum(
        1 for c in total_dormant_eligible
        if c["reactivation_status"] not in ("never_contacted",)
    )
    pct_contacted = (
        round(contacted_dormant * 100 / len(total_dormant_eligible))
        if total_dormant_eligible else 0
    )

    # Potential revenue: uncontacted priority customers (score > 40, never_contacted)
    potential_revenue = sum(
        c["estimated_job_value"]
        for c in dormant_customers
        if c["estimated_job_value"]
    )

    # Avg job value across all customers with spend
    all_spend = [c["total_spend"] for c in enriched if c["total_spend"] and c["total_jobs"]]
    all_jobs = [c["total_jobs"] for c in enriched if c["total_spend"] and c["total_jobs"]]
    avg_job_value = (
        round(sum(all_spend) / sum(all_jobs), 2) if all_jobs else 0
    )

    metrics = {
        "dormant_identified": dormant_count,
        "pct_contacted": pct_contacted,
        "responses_received": responses_received,
        "active_conversations": active_conversations,
        "jobs_booked": jobs_booked,
        "revenue_generated": revenue_generated,
        "potential_revenue": potential_revenue,
        "avg_job_value": avg_job_value,
    }

    today_str = datetime.utcnow().strftime('%A, %B %-d, %Y')

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active": "dashboard",
        "operator": operator_data,
        "metrics": metrics,
        "group_upcoming": group_upcoming,
        "group_attention": group_attention,
        "group_ripe": group_ripe,
        "group_declined": group_declined,
        "queue_count": queue_count,
        "conversations_attention_count": conversations_attention_count,
        "today_str": today_str,
    })


@app.get("/customers", response_class=HTMLResponse)
def customers_list(request: Request, search: str = "", group: str = "all"):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        op = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        operator_data = _operator_data(op)
        queue_count = db.query(OutreachLog).filter_by(operator_id=OPERATOR_ID, dry_run=True).count()
        conversations_attention_count = _get_conversations_attention_count(db)

    enriched = _get_enriched_customers(OPERATOR_ID)
    all_customers = sorted(enriched, key=lambda x: -x["score"])

    return templates.TemplateResponse("customers.html", {
        "request": request,
        "active": "customers",
        "operator": operator_data,
        "queue_count": queue_count,
        "conversations_attention_count": conversations_attention_count,
        "all_customers": all_customers,
        "search": search,
        "group_filter": group,
    })


@app.get("/customer/{customer_id}", response_class=HTMLResponse)
def customer_detail(request: Request, customer_id: int):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        jobs_raw = db.query(Job).filter_by(customer_id=customer_id).order_by(Job.completed_at.desc()).all()
        logs_raw = db.query(OutreachLog).filter_by(customer_id=customer_id).order_by(OutreachLog.sent_at.desc()).all()

        operator_data = _operator_data(operator)
        queue_count = _get_queue_count(db)
        conversations_attention_count = _get_conversations_attention_count(db)
        customer_data = enrich(customer)
        customer_data = add_segment(customer_data)
        customer_data["assigned_voice_id"] = customer.assigned_voice_id
        customer_data["customer_profile"] = _normalize_customer_profile(customer.customer_profile)
        # Score data for breakdown module
        try:
            score_bd = json.loads(customer.score_breakdown or "{}")
        except Exception:
            score_bd = {}
        customer_data["score"] = customer.score or 0
        customer_data["score_breakdown"] = score_bd
        customer_data["priority_tier"] = customer.priority_tier or "low"
        customer_data["estimated_job_value"] = customer.estimated_job_value or 0.0
        customer_data["predicted_next_service"] = customer.predicted_next_service
        jobs = [{"service_type": j.service_type, "completed_at": j.completed_at,
                 "status": j.status, "amount": j.amount} for j in jobs_raw]
        logs = [{"id": l.id, "subject": l.subject, "content": l.content,
                 "sent_at": l.sent_at, "dry_run": l.dry_run, "sequence_step": l.sequence_step,
                 "direction": l.direction, "channel": l.channel}
                for l in logs_raw]

        # Active conversation state for the CTA card
        sent_logs = [l for l in logs_raw if not l.dry_run]
        has_active_conversation = bool(sent_logs)
        last_sent_log = sent_logs[0] if sent_logs else None  # already desc by sent_at
        inbound_logs = [l for l in sent_logs if l.direction == "inbound"]
        last_inbound_log = inbound_logs[0] if inbound_logs else None
        active_conv_last_at = _log_timestamp(last_sent_log) if last_sent_log else None
        active_conv_last_direction = last_sent_log.direction if last_sent_log else None
        active_conv_reply_count = len(inbound_logs)
        unique_threads = len({l.gmail_thread_id for l in sent_logs if l.gmail_thread_id})

        account_events = []
        for j in jobs_raw:
            event_at = j.completed_at or j.scheduled_at or j.created_at
            account_events.append({
                "type": "service",
                "title": f"{j.service_type}",
                "detail": f"${j.amount:,.0f} · {j.status.replace('_', ' ')}",
                "at": event_at,
            })
        for l in logs_raw:
            event_at = l.sent_at or l.created_at
            if l.direction == "inbound":
                title = f"Inbound {l.channel} reply"
                event_type = "reply"
            elif l.dry_run:
                title = f"Queued {l.channel} draft"
                event_type = "queued"
            else:
                title = f"Outbound {l.channel}"
                event_type = "outreach"
            account_events.append({
                "type": event_type,
                "title": title,
                "detail": (l.subject or "(no subject)")[:120],
                "at": event_at,
            })

    account_events.sort(key=lambda item: item["at"] or datetime.min, reverse=True)

    return templates.TemplateResponse("customer.html", {
        "request": request,
        "active": "customers",
        "operator": operator_data,
        "queue_count": queue_count,
        "conversations_attention_count": conversations_attention_count,
        "customer": customer_data,
        "jobs": jobs,
        "logs": logs,
        "account_events": account_events,
        "has_active_conversation": has_active_conversation,
        "active_conv_last_at": active_conv_last_at,
        "active_conv_last_direction": active_conv_last_direction,
        "active_conv_reply_count": active_conv_reply_count,
        "unique_threads": unique_threads,
    })


def _outreach_row(log, customer) -> dict:
    queue_status = _outreach_status(log)
    status_meta = OUTREACH_STATUS_META[queue_status]
    conversation_stage = _conversation_stage(customer.reactivation_status)
    suggested_send_at = _next_business_send_time()
    scheduled_send_at = log.scheduled_send_at

    return {
        "log_id": log.id,
        "customer_id": customer.id,
        "customer_name": customer.name,
        "customer_email": customer.email or "",
        "subject": log.subject,
        "content": log.content,
        "created_at": log.created_at,
        "sent_at": log.sent_at,
        "dry_run": log.dry_run,
        "sequence_step": log.sequence_step,
        "sequence_label": _outreach_sequence_label(log.sequence_step, log.response_classification),
        "response_classification": log.response_classification or "",
        "approval_status": queue_status,
        "approval_status_label": status_meta["label"],
        "approval_chip_cls": status_meta["chip_cls"],
        "approval_rank": status_meta["rank"],
        "approved_at": log.approved_at,
        "scheduled_send_at": scheduled_send_at,
        "scheduled_send_input": _format_datetime_local(scheduled_send_at or suggested_send_at),
        "send_error": log.send_error,
        "conversation_stage_label": conversation_stage["label"],
        "conversation_stage_cls": conversation_stage["status_cls"],
        "booking_slot_start": getattr(log, "booking_slot_start", None),
        "booking_slot_end": getattr(log, "booking_slot_end", None),
        "booking_slot_start_input": _format_datetime_local(getattr(log, "booking_slot_start", None)),
        "booking_slot_end_input": _format_datetime_local(getattr(log, "booking_slot_end", None)),
        "customer_last_service_type": getattr(customer, "last_service_type", None) or "Service",
    }


@app.get("/outreach", response_class=HTMLResponse)
def outreach_queue(request: Request):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        rows = (
            db.query(OutreachLog, Customer)
            .join(Customer, OutreachLog.customer_id == Customer.id)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                ~OutreachLog.response_classification.in_(_MEETINGS_CLASSIFICATIONS)
            | OutreachLog.response_classification.is_(None),
            )
            .order_by(OutreachLog.created_at.desc())
            .all()
        )
        operator_data = _operator_data(operator)
        pending = [_outreach_row(l, c) for l, c in rows]
        pending.sort(
            key=lambda item: (
                item["approval_rank"],
                item["scheduled_send_at"] or datetime.max,
                -(item["created_at"].timestamp() if item["created_at"] else 0),
            )
        )
        queue_count = len(pending)
        meetings_queue_count = _get_meetings_queue_count(db)
        conversations_attention_count = _get_conversations_attention_count(db)

    return templates.TemplateResponse("outreach.html", {
        "request": request,
        "active": "outreach",
        "operator": operator_data,
        "queue_count": queue_count,
        "meetings_queue_count": meetings_queue_count,
        "conversations_attention_count": conversations_attention_count,
        "pending": pending,
    })


@app.get("/meetings", response_class=HTMLResponse)
def meetings_queue(request: Request):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        rows = (
            db.query(OutreachLog, Customer)
            .join(Customer, OutreachLog.customer_id == Customer.id)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                OutreachLog.response_classification.in_(_MEETINGS_CLASSIFICATIONS),
            )
            .order_by(OutreachLog.created_at.desc())
            .all()
        )
        operator_data = _operator_data(operator)
        pending = [_outreach_row(l, c) for l, c in rows]
        queue_count = _get_queue_count(db)
        meetings_queue_count = len(pending)
        conversations_attention_count = _get_conversations_attention_count(db)

    return templates.TemplateResponse("meetings.html", {
        "request": request,
        "active": "meetings",
        "operator": operator_data,
        "queue_count": queue_count,
        "meetings_queue_count": meetings_queue_count,
        "conversations_attention_count": conversations_attention_count,
        "pending": pending,
    })


@app.get("/calendar", response_class=HTMLResponse)
def calendar_view(request: Request):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        operator_data = _operator_data(operator)
        queue_count = _get_queue_count(db)
        meetings_queue_count = _get_meetings_queue_count(db)
        conversations_attention_count = _get_conversations_attention_count(db)

        bookings = (
            db.query(Booking, Customer)
            .join(Customer, Booking.customer_id == Customer.id)
            .filter(Booking.operator_id == OPERATOR_ID)
            .order_by(Booking.slot_start)
            .all()
        )
        bookings_data = []
        for b, c in bookings:
            bookings_data.append({
                "id": b.id,
                "customer_name": c.name,
                "customer_email": c.email,
                "customer_id": c.id,
                "slot_start": b.slot_start,
                "slot_end": b.slot_end,
                "status": b.status,
                "service_type": b.service_type or "Service",
                "notes": b.notes or "",
                "source": b.source,
            })

    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "active": "calendar",
        "operator": operator_data,
        "queue_count": queue_count,
        "meetings_queue_count": meetings_queue_count,
        "conversations_attention_count": conversations_attention_count,
        "bookings": bookings_data,
    })


@app.get("/conversations", response_class=HTMLResponse)
def conversations(request: Request):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        operator_data = _operator_data(operator)
        queue_count = _get_queue_count(db)
        customers = db.query(Customer).filter_by(operator_id=OPERATOR_ID).all()

        conversations_data = []
        health_counts = {key: 0 for key in CONVERSATION_HEALTH_META}
        for customer in customers:
            logs = (
                db.query(OutreachLog)
                .filter_by(
                    operator_id=OPERATOR_ID,
                    customer_id=customer.id,
                    dry_run=False,
                )
                .order_by(OutreachLog.sent_at.desc(), OutreachLog.created_at.desc())
                .all()
            )
            if not logs:
                continue

            logs_sorted = sorted(logs, key=lambda log: _log_timestamp(log) or datetime.min, reverse=True)
            outbound_logs = [log for log in logs_sorted if log.direction == "outbound"]
            inbound_logs = [log for log in logs_sorted if log.direction == "inbound"]
            last_touch_log = logs_sorted[0]
            latest_outbound = outbound_logs[0] if outbound_logs else None
            latest_inbound = inbound_logs[0] if inbound_logs else None
            last_outbound_at = _log_timestamp(latest_outbound)
            last_inbound_at = _log_timestamp(latest_inbound)
            # Derive effective status from actual log activity — handles race where
            # reply_detector logged the inbound message but didn't yet update reactivation_status
            effective_status = customer.reactivation_status
            if inbound_logs and effective_status not in ("booked", "sequence_complete", "unsubscribed", "replied"):
                effective_status = "replied"
            stage = _conversation_stage(effective_status)
            health = _conversation_health(effective_status, last_outbound_at, last_inbound_at)
            summary = add_segment(enrich(customer))
            health_counts[health["key"]] += 1

            # Preview: show most recent message (could be inbound reply)
            last_message_is_inbound = last_touch_log.direction == "inbound"

            conversations_data.append({
                "customer_id": customer.id,
                "customer_name": customer.name,
                "customer_email": customer.email,
                "status_label": stage["label"],
                "last_interaction_label": "Customer reply" if last_message_is_inbound else "Agent outreach",
                "health_label": health["label"],
                "health_chip_cls": health["chip_cls"],
                "health_rank": health["rank"],
                "reactivation_status": effective_status,
                "outbound_count": len(outbound_logs),
                "inbound_count": len(inbound_logs),
                "last_touch_at": _log_timestamp(last_touch_log),
                "last_touch_direction": last_touch_log.direction,
                "last_outbound_at": last_outbound_at,
                # Latest message preview (inbound reply if most recent, else last outbound)
                "last_message_is_inbound": last_message_is_inbound,
                "last_message_at": _log_timestamp(last_touch_log),
                "last_message_subject": (last_touch_log.subject or "(no subject)") if last_touch_log else "(no subject)",
                "last_message_preview": _compact_summary(last_touch_log.content or "", 180) if last_touch_log else "",
                "needs_response": health["needs_response"],
                "needs_follow_up": health["needs_follow_up"],
                "opp_est": summary.get("opp_est"),
                "opp_label": summary.get("opp_label"),
                "days_dormant": summary.get("days_dormant"),
                "total_spend": summary.get("total_spend"),
            })

    conversations_data.sort(key=lambda row: row["last_touch_at"] or datetime.min, reverse=True)
    conversations_data.sort(key=lambda row: row["health_rank"])

    conversations_attention_count = sum(
        1 for item in conversations_data if item["needs_response"] or item["needs_follow_up"]
    )

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "active": "conversations",
        "operator": operator_data,
        "queue_count": queue_count,
        "conversations_attention_count": conversations_attention_count,
        "conversations": conversations_data,
        "awaiting_reply_count": health_counts["awaiting_reply"],
        "needs_response_count": health_counts["needs_response"],
        "needs_follow_up_count": health_counts["needs_follow_up"],
    })


@app.get("/conversations/{customer_id}", response_class=HTMLResponse)
def conversation_detail(request: Request, customer_id: int):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        logs = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, customer_id=customer_id, dry_run=False)
            .order_by(OutreachLog.sent_at.desc(), OutreachLog.created_at.desc())
            .all()
        )
        # Check for any pending draft in the queue for this customer
        pending_draft_log = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                OutreachLog.approval_status == "pending",
                OutreachLog.direction == "outbound",
            )
            .order_by(OutreachLog.created_at.desc())
            .first()
        )
        has_pending_draft = pending_draft_log is not None
        pending_draft_queue = (
            "meetings"
            if pending_draft_log and pending_draft_log.response_classification == "booking_intent"
            else "outreach"
        )
        pending_draft_summary = _compact_summary(pending_draft_log.content or "", 120) if pending_draft_log else ""
        pending_draft_created_at = _log_timestamp(pending_draft_log) if pending_draft_log else None
        operator_data = _operator_data(operator)
        queue_count = _get_queue_count(db)
        conversations_attention_count = _get_conversations_attention_count(db)
        customer_data = add_segment(enrich(customer))
        customer_data["customer_profile"] = _normalize_customer_profile(customer.customer_profile)

        log_entries = []
        for log in logs:
            logged_at = _log_timestamp(log)
            sender_key = "human" if log.direction == "inbound" else "agent"
            log_entries.append({
                "id": log.id,
                "direction": log.direction,
                "channel": log.channel,
                "subject": log.subject or "(no subject)",
                "content": log.content or "",
                "summary": _compact_summary(log.content or "", 170),
                "sender_key": sender_key,
                "sender_label": "Human" if sender_key == "human" else "Agent",
                "sequence_step": (log.sequence_step or 0) + 1,
                "at": logged_at,
                "gmail_thread_id": log.gmail_thread_id,
                "response_classification": log.response_classification,
            })

        latest_outbound = next((log for log in logs if log.direction == "outbound"), None)
        latest_inbound = next((log for log in logs if log.direction == "inbound"), None)
        last_outbound_at = _log_timestamp(latest_outbound)
        last_inbound_at = _log_timestamp(latest_inbound)
        # Derive effective status from actual log activity so chips stay consistent
        # with the timeline even if reactivation_status wasn't updated yet
        effective_status = customer.reactivation_status
        if latest_inbound and effective_status not in ("booked", "sequence_complete", "unsubscribed", "replied"):
            effective_status = "replied"
        stage = _conversation_stage(effective_status)
        health = _conversation_health(effective_status, last_outbound_at, last_inbound_at)
        next_steps = _auto_next_steps(effective_status, last_outbound_at, last_inbound_at)

        timeline_events = []
        for entry in log_entries:
            direction_label = "Inbound reply" if entry["direction"] == "inbound" else "Outbound email"
            timeline_events.append({
                "id": entry["id"],
                "type": "inbound" if entry["direction"] == "inbound" else "outbound",
                "title": direction_label,
                "detail": f"{entry['sender_label']} · Step {entry['sequence_step']}",
                "subject": entry["subject"],
                "summary": entry["summary"],
                "content": entry["content"],
                "sender_label": entry["sender_label"],
                "sequence_step": entry["sequence_step"],
                "gmail_thread_id": entry["gmail_thread_id"],
                "at": entry["at"],
                "response_classification": entry.get("response_classification"),
            })

    # Add pending draft as a "queued" timeline entry (visually distinct from sent messages)
    if has_pending_draft and pending_draft_log:
        timeline_events.append({
            "id": pending_draft_log.id,
            "type": "queued",
            "title": "Draft in Queue",
            "detail": f"Awaiting approval · {'Meetings Queue' if pending_draft_queue == 'meetings' else 'Outreach Queue'}",
            "subject": pending_draft_log.subject or "(draft)",
            "summary": pending_draft_summary,
            "content": pending_draft_log.content or "",
            "sender_label": "Queued Draft",
            "sequence_step": (pending_draft_log.sequence_step or 0) + 1,
            "gmail_thread_id": None,
            "at": pending_draft_created_at,
            "response_classification": None,
            "queued_to": pending_draft_queue,
        })

    timeline_events.sort(key=_timeline_date_key, reverse=True)

    # AI summaries are loaded lazily via /api/conversation/{id}/summaries
    # to avoid blocking the page render with a Claude call.

    timeline_events_json = [
        {
            **event,
            "at": event["at"].isoformat() + "Z" if event.get("at") else None,
        }
        for event in timeline_events
    ]

    outbound_count = sum(1 for entry in log_entries if entry["direction"] == "outbound")
    inbound_count = sum(1 for entry in log_entries if entry["direction"] == "inbound")
    latest_classification = next(
        (
            entry["response_classification"]
            for entry in log_entries
            if entry["direction"] == "inbound" and entry.get("response_classification")
        ),
        "none",
    )
    opportunity_signals = []
    if customer_data["days_dormant"] >= 365:
        opportunity_signals.append(f"Dormant for {customer_data['days_dormant']} days")
    if customer_data["total_spend"] >= 1500:
        opportunity_signals.append(f"High historical value (${customer_data['total_spend']:,.0f})")
    if customer_data["customer_profile"]["interest_signals"]:
        opportunity_signals.append(customer_data["customer_profile"]["interest_signals"])
    if inbound_count > 0:
        opportunity_signals.append("Customer has already replied")
    if not opportunity_signals:
        opportunity_signals.append("No explicit intent signals yet")

    recap = _conversation_recap(
        customer=customer_data,
        stage=stage,
        health=health,
        logs=log_entries,
        next_steps=next_steps,
    )

    return templates.TemplateResponse("conversation_detail.html", {
        "request": request,
        "active": "conversations",
        "operator": operator_data,
        "queue_count": queue_count,
        "conversations_attention_count": conversations_attention_count,
        "customer": customer_data,
        "stage": stage,
        "health": health,
        "next_steps": next_steps,
        "logs": log_entries,
        "timeline_events": timeline_events,
        "timeline_events_json": timeline_events_json,
        "outbound_count": outbound_count,
        "inbound_count": inbound_count,
        "opportunity_signals": opportunity_signals,
        "conversation_recap": recap,
        "latest_classification": latest_classification,
        "has_pending_draft": has_pending_draft,
        "pending_draft_queue": pending_draft_queue,
        "pending_draft_summary": pending_draft_summary,
        "pending_draft_created_at": pending_draft_created_at,
    })


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.delete("/api/outreach/{log_id}")
def delete_outreach(log_id: int):
    """Remove a draft from the outreach queue. Only pending/failed drafts can be deleted."""
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
        if not log:
            raise HTTPException(status_code=404, detail="Draft not found")
        if log.approval_status not in ("pending", "failed"):
            raise HTTPException(status_code=400, detail="Only pending or failed drafts can be removed")
        db.delete(log)
    return {"status": "deleted"}


class MarkBookedRequest(BaseModel):
    job_value: float
    notes: str = ""
    customer_id: int | None = None


@app.post("/api/outreach/{log_id}/mark-booked")
def mark_booked(log_id: int, req: MarkBookedRequest):
    """
    Mark an outreach thread as converted to a booked job.
    Sets converted_to_job=True, records job value, updates customer status.
    """
    now_utc = datetime.utcnow()
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
        if not log:
            raise HTTPException(status_code=404, detail="Outreach log not found")
        log.converted_to_job = True
        log.converted_job_value = req.job_value
        log.converted_at = now_utc

        customer = db.query(Customer).filter_by(
            id=log.customer_id, operator_id=OPERATOR_ID
        ).first()
        if customer:
            customer.reactivation_status = "booked"
            if req.notes:
                customer.notes = (customer.notes or "") + f"\n[Booked {now_utc.strftime('%Y-%m-%d')}] {req.notes}"

    return {"status": "booked", "log_id": log_id, "job_value": req.job_value}


@app.post("/api/customer/{customer_id}/mark-booked")
def mark_booked_by_customer(customer_id: int, req: MarkBookedRequest):
    """
    Mark a customer as booked from the dashboard (no specific log_id).
    Finds the most recent outbound log and marks it converted.
    """
    now_utc = datetime.utcnow()
    with get_db() as db:
        customer = db.query(Customer).filter_by(
            id=customer_id, operator_id=OPERATOR_ID
        ).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Find most recent outbound log (dry_run=False preferred, else any)
        log = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, customer_id=customer_id, direction="outbound")
            .order_by(OutreachLog.sent_at.desc(), OutreachLog.created_at.desc())
            .first()
        )
        if log:
            log.converted_to_job = True
            log.converted_job_value = req.job_value
            log.converted_at = now_utc

        customer.reactivation_status = "booked"
        if req.notes:
            customer.notes = (customer.notes or "") + f"\n[Booked {now_utc.strftime('%Y-%m-%d')}] {req.notes}"

    return {"status": "booked", "customer_id": customer_id, "job_value": req.job_value}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "db_ready": _db_ready,
        "db_error": str(_db_init_error) if _db_init_error else None,
        "database_url_prefix": os.getenv("DATABASE_URL", "not set")[:40],
    }


@app.get("/debug-db")
def debug_db():
    """Synchronously attempt a DB connection and return the result. Temp diagnostics only."""
    db_url = os.getenv("DATABASE_URL", "not set")
    try:
        _try_init_db_once(timeout_seconds=20.0)
        return {"result": "ok", "db_url_prefix": db_url[:40]}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"result": "error", "error": str(exc), "db_url_prefix": db_url[:40]},
        )


@app.get("/api/operator/{operator_id}")
def get_operator(operator_id: int):
    with get_db() as db:
        op = db.query(Operator).filter_by(id=operator_id).first()
        if not op:
            raise HTTPException(status_code=404, detail="Operator not found")
        return {
            "id": op.id,
            "name": op.name,
            "business_name": op.business_name,
            "email": op.email,
            "niche": op.niche,
            "onboarding_complete": op.onboarding_complete,
            "tone_profile": op.tone_profile,
        }


@app.get("/api/operator/{operator_id}/customers")
def get_customers(operator_id: int, status: str = None):
    with get_db() as db:
        q = db.query(Customer).filter_by(operator_id=operator_id)
        if status:
            q = q.filter_by(reactivation_status=status)
        customers = q.order_by(Customer.last_service_date.asc()).all()
    return {"total": len(customers), "customers": [enrich(c) for c in customers]}


@app.get("/api/operator/{operator_id}/stats")
def get_stats(operator_id: int):
    with get_db() as db:
        customers = db.query(Customer).filter_by(operator_id=operator_id).all()
        if not customers:
            raise HTTPException(status_code=404, detail="No customers found")
        status_counts = {}
        for c in customers:
            status_counts[c.reactivation_status] = status_counts.get(c.reactivation_status, 0) + 1
    return {
        "total_customers": len(customers),
        "status_breakdown": status_counts,
        "total_revenue": round(sum(c.total_spend for c in customers), 2),
    }


# ── Voice assignment ──────────────────────────────────────────────────────────

@app.post("/api/customer/{customer_id}/assign-voice")
def assign_voice(customer_id: int, body: dict):
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer.assigned_voice_id = body.get("voice_id")
    return {"ok": True}


# ── Draft generation ──────────────────────────────────────────────────────────

DRAFT_SYSTEM = """You are a ghostwriter for a small field service business owner.
Write a single reactivation email in the owner's exact voice — their tone, greeting style, signoff, and characteristic phrases.
The email should feel personal and genuine, never salesy. Keep it short: 3–5 sentences. End with a soft call to action.
Formatting rules: use plain text only, no markdown. Separate paragraphs with a single blank line (\\n\\n). Do not add extra blank lines. Do not use bullet points or headers.
Return ONLY a JSON object with keys "subject" and "body". No markdown, no code fences."""

DRAFT_USER = """Tone profile:
{tone}

{voice_section}Write a reactivation email for past customer {name}.
Last service: "{service_type}" about {days} days ago ({months:.0f} months).
History: {jobs} jobs, ${spend:.0f} total spent."""


CONVO_DRAFT_SYSTEM = """You are a ghostwriter for a small field service contractor (HVAC, plumbing, appliance repair).
Write a short, natural email in the owner's exact voice — their tone, greeting style, signoff, and characteristic phrases.

You have real domain expertise. Use it when customers ask questions:
- AC filters: 1" filters every 1-3 months, 4-5" media filters every 6-12 months, HEPA every 12-18 months. Actual lifespan depends on pets, dust, and run time.
- Furnaces last 15-20 years, AC units 10-15 years, water heaters 8-12 years.
- Common jobs: tune-ups, filter swaps, refrigerant checks, coil cleaning, duct inspection, capacitor/contactor replacement.
- If a customer says something was just serviced, accept it and pivot to what IS needed — never push work that isn't warranted.

CRITICAL FORMATTING RULES (violations will break the email client):
- Plain text only — no markdown, no asterisks, no headers
- Inside a paragraph: ZERO line breaks. Every sentence in the same paragraph must be on one continuous line.
- Between paragraphs: exactly one blank line (two newline characters). No more.
- No leading or trailing blank lines in the body.
- No bullet points or lists.

Return ONLY valid JSON: {"subject": "...", "body": "..."}. No code fences, no extra text."""

CONVO_REPLY_USER = """Operator tone profile:
{tone}

{voice_section}--- Customer account context ---
Name: {name}
Last service: {service_type} ({days} days ago)
Full service history: {job_history}
Total: {total_jobs} jobs, ${total_spend:,.0f} lifetime spend
---

--- Full conversation thread (oldest first) ---
{thread}
---

The customer has replied. Steps:
1. Read their most recent message carefully. Identify every question they asked and every concern or piece of information they shared.
2. Answer each question with real, specific information. If they asked about filter life, give actual numbers. If they mentioned the type or size of their system, factor that in.
3. If they mentioned something was already handled (e.g., furnace was just serviced), acknowledge it — do not push for work they don't need.
4. Where there is a genuine next step (filter replacement, estimate, scheduling a visit), offer it concretely with a timeframe.
5. Close with one clear call to action.

Write 3-5 sentences. Be genuinely helpful first, commercial second. Match the operator's tone exactly."""

CONVO_FOLLOWUP_USER = """Operator tone profile:
{tone}

{voice_section}--- Customer account context ---
Name: {name}
Last service: {service_type} ({days} days ago)
Full service history: {job_history}
Total: {total_jobs} jobs, ${total_spend:,.0f} lifetime spend
---

--- Previous outreach thread (oldest first) ---
{thread}
---

The customer has not replied yet. Write a brief follow-up (2–3 sentences) that:
1. Acknowledges the previous email — reference something specific from it (the subject or a detail mentioned), so it reads as a continuation, not a fresh outreach.
2. Takes a slightly different angle — bring in their service history, mention a seasonal reason to act now, or ask a direct question they can answer easily.
3. Ends with one simple call to action.

Do not repeat the first email word-for-word. Be natural, not pushy. Match the operator's tone exactly."""


class DraftRequest(BaseModel):
    voice_id: str = None


@app.post("/api/conversation/{customer_id}/draft")
def generate_conversation_draft(customer_id: int):
    """Generate a context-aware reply (if customer replied) or follow-up (if overdue) draft."""
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        logs = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, customer_id=customer_id, dry_run=False)
            .order_by(OutreachLog.sent_at.asc(), OutreachLog.created_at.asc())
            .all()
        )
        voice_id = customer.assigned_voice_id
        profiles = operator.voice_profiles or []
        voice = next((p for p in profiles if p["id"] == voice_id), profiles[0] if profiles else None)
        tone = json.dumps(operator.tone_profile, indent=2)
        cust_name = customer.name
        cust_service_type = customer.last_service_type or "service"
        cust_last_service_date = customer.last_service_date
        cust_total_jobs = customer.total_jobs or 0
        cust_total_spend = customer.total_spend or 0.0
        # Fetch full job history for context
        jobs = (
            db.query(Job)
            .filter_by(customer_id=customer_id)
            .order_by(Job.completed_at.desc())
            .limit(8)
            .all()
        )
        job_history_parts = []
        for j in jobs:
            date_str = j.completed_at.strftime("%b %Y") if j.completed_at else "unknown date"
            job_history_parts.append(f"{j.service_type} ({date_str}, ${j.amount:,.0f})" if j.amount else f"{j.service_type} ({date_str})")
        job_history = "; ".join(job_history_parts) if job_history_parts else "No prior jobs on record"
        inbound_logs = [l for l in logs if l.direction == "inbound"]
        outbound_logs = [l for l in logs if l.direction == "outbound"]
        last_outbound = outbound_logs[-1] if outbound_logs else None
        last_inbound = inbound_logs[-1] if inbound_logs else None
        last_outbound_at = _log_timestamp(last_outbound)
        last_inbound_at = _log_timestamp(last_inbound)
        # Build thread context (up to last 6 messages)
        thread_lines = []
        for l in logs[-6:]:
            direction = "Customer" if l.direction == "inbound" else "You"
            body = " ".join((l.content or "").split())[:500]  # flatten + truncate
            thread_lines.append(f"[{direction}] Subject: {l.subject or '(no subject)'}\n{body}")
        thread = "\n\n".join(thread_lines)
        has_thread = bool(thread_lines)
        effective_status = customer.reactivation_status
        if inbound_logs and effective_status not in ("booked", "sequence_complete", "unsubscribed", "replied"):
            effective_status = "replied"
        is_reply = bool(last_inbound and (not last_outbound_at or last_inbound_at > last_outbound_at))
        # Serialize ORM attributes before session closes to avoid DetachedInstanceError
        last_outbound_subject = (last_outbound.subject or "our previous email") if last_outbound else "our previous email"

    if not has_thread:
        raise HTTPException(
            status_code=400,
            detail="No sent emails on record for this customer. Use the customer page to generate initial outreach."
        )

    voice_section = (
        f"Write in the voice of {voice['name']} ({voice.get('role', 'team member')}).\n\n"
        if voice else ""
    )
    days = days_since(cust_last_service_date)

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        if is_reply:
            user_content = CONVO_REPLY_USER.format(
                tone=tone,
                voice_section=voice_section,
                name=cust_name,
                service_type=cust_service_type,
                days=days,
                job_history=job_history,
                total_jobs=cust_total_jobs,
                total_spend=cust_total_spend,
                thread=thread,
            )
        else:
            user_content = CONVO_FOLLOWUP_USER.format(
                tone=tone,
                voice_section=voice_section,
                name=cust_name,
                service_type=cust_service_type,
                days=days,
                job_history=job_history,
                total_jobs=cust_total_jobs,
                total_spend=cust_total_spend,
                thread=thread,
            )
        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=800,
            system=CONVO_DRAFT_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")

    import re as _re
    raw = message.content[0].text.strip()
    try:
        draft = json.loads(raw)
    except json.JSONDecodeError:
        draft = {"subject": "Following up", "body": raw}
    if draft.get("body"):
        _body = draft["body"].strip()
        _paras = _re.split(r'\n\n+', _body)
        _paras = [' '.join(p.split('\n')) for p in _paras if p.strip()]
        draft["body"] = '\n\n'.join(_paras)
    draft["draft_type"] = "reply" if is_reply else "follow_up"
    return draft


class QueueDraftRequest(BaseModel):
    body: str
    subject: str = ""   # optional — auto-derived from thread if omitted
    sequence_step: int = 0


@app.post("/api/conversation/{customer_id}/queue")
def queue_conversation_draft(customer_id: int, req: QueueDraftRequest):
    """Queue a conversation reply/follow-up draft for operator review before sending."""
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        # Derive subject from existing thread if not supplied
        subject = req.subject.strip() if req.subject.strip() else None
        if not subject:
            last_out = (
                db.query(OutreachLog)
                .filter_by(operator_id=OPERATOR_ID, customer_id=customer_id, dry_run=False, direction="outbound")
                .order_by(OutreachLog.sent_at.desc(), OutreachLog.created_at.desc())
                .first()
            )
            thread_subject = (last_out.subject or "") if last_out else ""
            subject = f"Re: {thread_subject}" if thread_subject else "Following up"
        log = OutreachLog(
            operator_id=OPERATOR_ID,
            customer_id=customer_id,
            channel="email",
            direction="outbound",
            subject=subject,
            content=req.body,
            dry_run=True,
            approval_status="pending",
            approved_at=None,
            scheduled_send_at=None,
            send_error=None,
            sequence_step=req.sequence_step,
        )
        db.add(log)
    return {"status": "queued", "customer_id": customer_id}


@app.get("/api/conversation/{customer_id}/summaries")
def get_conversation_summaries(customer_id: int):
    """
    Lazy-load one-sentence AI summaries for timeline events.
    Called by the conversation page after render to avoid blocking page load.
    Returns {log_id: summary_string}.
    """
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        logs = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, customer_id=customer_id, dry_run=False)
            .order_by(OutreachLog.sent_at.desc(), OutreachLog.created_at.desc())
            .all()
        )
        log_entries = [
            {
                "id": log.id,
                "direction": log.direction,
                "subject": log.subject or "(no subject)",
                "content": log.content or "",
                "summary": _compact_summary(log.content or "", 170),
            }
            for log in logs
        ]
    summaries = _generate_timeline_summaries(log_entries)
    return {"summaries": summaries}


def _generate_reactivation_draft(customer_id: int, voice_id: str = None) -> dict:
    """Core reactivation draft logic. Returns a dict with 'subject' and 'body'."""
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()

        # Resolve voice profile: use requested voice_id, fall back to customer's assigned, then first profile
        resolved_voice_id = voice_id or customer.assigned_voice_id
        profiles = operator.voice_profiles
        voice = next((p for p in profiles if p["id"] == resolved_voice_id), profiles[0] if profiles else None)

        # Serialize everything we need before session closes
        cust_name = customer.name
        cust_service_type = customer.last_service_type or "service"
        cust_last_service_date = customer.last_service_date
        cust_total_jobs = customer.total_jobs
        cust_total_spend = customer.total_spend
        tone = json.dumps(operator.tone_profile, indent=2)

    days = days_since(cust_last_service_date)
    voice_section = (
        f"Write in the voice of {voice['name']} ({voice.get('role', 'team member')}).\n\n"
        if voice else ""
    )

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=512,
            system=DRAFT_SYSTEM,
            messages=[{
                "role": "user",
                "content": DRAFT_USER.format(
                    tone=tone,
                    voice_section=voice_section,
                    name=cust_name,
                    service_type=cust_service_type,
                    days=days,
                    months=days / 30,
                    jobs=cust_total_jobs,
                    spend=cust_total_spend,
                )
            }]
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {e}")

    import re as _re
    raw = message.content[0].text.strip()
    try:
        draft = json.loads(raw)
    except json.JSONDecodeError:
        draft = {"subject": "Checking in", "body": raw}

    # Normalize body: collapse single newlines within paragraphs, keep double between
    if draft.get("body"):
        _body = draft["body"].strip()
        _paras = _re.split(r'\n\n+', _body)
        _paras = [' '.join(p.split('\n')) for p in _paras if p.strip()]
        draft["body"] = '\n\n'.join(_paras)

    if voice:
        draft["voice_name"] = voice["name"]
    return draft


@app.post("/api/draft/{customer_id}")
def generate_draft(customer_id: int, req: DraftRequest = None):
    req = req or DraftRequest()
    return _generate_reactivation_draft(customer_id, voice_id=req.voice_id)


class ApproveSendRequest(BaseModel):
    subject: str
    body: str
    send_now: bool = False
    scheduled_send_at: str | None = None


@app.post("/api/outreach/{log_id}/approve-send")
def approve_send(log_id: int, req: ApproveSendRequest):
    """
    Save outreach edits and either:
    - approve/schedule for later send, or
    - send immediately (production mode only).
    """
    now_utc = datetime.utcnow()
    parsed_schedule = _parse_iso_datetime(req.scheduled_send_at)
    if req.scheduled_send_at and parsed_schedule is None:
        raise HTTPException(status_code=400, detail="Invalid scheduled_send_at datetime")

    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
        if not log:
            raise HTTPException(status_code=404, detail="Log entry not found")

        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        mode = (operator.outreach_mode or "dry_run").strip().lower() if operator else "dry_run"
        if mode not in ("dry_run", "production"):
            mode = "dry_run"

        customer = db.query(Customer).filter_by(id=log.customer_id).first()
        customer_email = customer.email if customer else None
        log.subject = req.subject
        log.content = req.body

    if not req.send_now:
        scheduled_send_at = parsed_schedule or _next_business_send_time()
        with get_db() as db:
            log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
            log.approved_at = log.approved_at or now_utc
            log.approval_status = "scheduled"
            log.scheduled_send_at = scheduled_send_at
            log.send_error = None
            log.dry_run = True

        return {
            "status": "scheduled",
            "log_id": log_id,
            "scheduled_send_at": scheduled_send_at.isoformat(),
            "mode": mode,
        }

    if mode != "production":
        scheduled_send_at = parsed_schedule or _next_business_send_time()
        with get_db() as db:
            log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
            log.approved_at = log.approved_at or now_utc
            log.approval_status = "scheduled"
            log.scheduled_send_at = scheduled_send_at
            log.send_error = "Blocked by dry run mode"
            log.dry_run = True

        return JSONResponse(
            status_code=409,
            content={
                "status": "dry_run_mode",
                "detail": "Cannot send while Dry Run mode is active. Toggle to Production mode to send.",
                "scheduled_send_at": scheduled_send_at.isoformat(),
                "mode": mode,
            },
        )

    thread_id, send_error = _deliver_outreach_log(
        log_id=log_id,
        subject=req.subject,
        body=req.body,
        customer_email=customer_email,
        scheduled_send_at=parsed_schedule,
    )

    if not thread_id:
        return JSONResponse(
            status_code=502,
            content={
                "status": "failed",
                "log_id": log_id,
                "detail": send_error or "Send failed",
                "mode": mode,
            },
        )

    result = {"status": "sent", "log_id": log_id, "mode": mode}
    if thread_id:
        result["gmail_thread_id"] = thread_id
    return result


class ConfirmBookingRequest(BaseModel):
    slot_start: str           # ISO datetime, Eastern time
    slot_end: str             # ISO datetime, Eastern time
    service_type: str = "Service"
    notes: str = ""
    email_subject: str = ""
    email_body: str = ""


@app.post("/api/outreach/{log_id}/confirm-booking")
def confirm_booking(log_id: int, req: ConfirmBookingRequest):
    """
    Confirm a booking from a booking_confirmed draft:
    1. Create a Booking record (confirmed, source=ai_outreach)
    2. Create a Google Calendar event — GCal auto-sends .ics invite to customer
    3. Send confirmation email via Gmail (production mode) or queue it (dry run)
    4. Update customer.reactivation_status → booked
    """
    try:
        slot_start = datetime.fromisoformat(req.slot_start)
        slot_end = datetime.fromisoformat(req.slot_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slot_start or slot_end — expected ISO datetime")

    # Load log + customer
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
        if not log:
            raise HTTPException(status_code=404, detail="Log entry not found")
        customer = db.query(Customer).filter_by(id=log.customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        mode = (operator.outreach_mode or "dry_run").strip().lower() if operator else "dry_run"

        customer_email = customer.email
        customer_name = customer.name
        customer_id = customer.id
        email_subject = req.email_subject or log.subject or f"Your appointment confirmation"
        email_body = req.email_body or log.content or ""
        existing_thread_id = _get_customer_thread_id(log_id)

    # Create Booking record
    with get_db() as db:
        booking = Booking(
            operator_id=OPERATOR_ID,
            customer_id=customer_id,
            slot_start=slot_start,
            slot_end=slot_end,
            status="confirmed",
            source="ai_outreach",
            service_type=req.service_type,
            notes=req.notes,
        )
        db.add(booking)
        db.flush()
        booking_id = booking.id
        c = db.query(Customer).filter_by(id=customer_id).first()
        if c:
            c.reactivation_status = "booked"

    # Create Google Calendar event
    gcal_event_id = None
    gcal_error = None
    try:
        from integrations.calendar import create_calendar_event
        event = create_calendar_event(
            summary=f"{req.service_type} — {customer_name}",
            start_dt=slot_start,
            end_dt=slot_end,
            customer_email=customer_email,
            description=(
                f"Booked via Foreman reactivation outreach.\n"
                f"Customer: {customer_name}"
                + (f"\nNotes: {req.notes}" if req.notes else "")
            ),
        )
        gcal_event_id = event.get("id")
        if gcal_event_id:
            with get_db() as db:
                b = db.query(Booking).filter_by(id=booking_id).first()
                if b:
                    b.google_cal_event_id = gcal_event_id
    except Exception as e:
        gcal_error = str(e)
        print(f"[confirm_booking] GCal event creation failed: {e}")

    # Send confirmation email
    email_sent = False
    send_error = None
    if mode == "production" and customer_email:
        try:
            inbound_rfc_id = _get_customer_inbound_rfc_id(customer_id)
            thread_id = _gmail_send_message(
                to=customer_email,
                subject=email_subject,
                body=email_body,
                thread_id=existing_thread_id,
                in_reply_to=inbound_rfc_id,
            )
            email_sent = bool(thread_id)
            with get_db() as db:
                log = db.query(OutreachLog).filter_by(id=log_id).first()
                if log:
                    log.dry_run = False
                    log.approval_status = "sent"
                    log.sent_at = datetime.utcnow()
                    if thread_id:
                        log.gmail_thread_id = thread_id
        except Exception as e:
            send_error = str(e)
    else:
        # Dry run mode — mark as scheduled (operator can send later)
        with get_db() as db:
            log = db.query(OutreachLog).filter_by(id=log_id).first()
            if log:
                log.approval_status = "scheduled"
                log.scheduled_send_at = _next_business_send_time()

    return {
        "status": "confirmed",
        "booking_id": booking_id,
        "gcal_event_id": gcal_event_id,
        "gcal_error": gcal_error,
        "email_sent": email_sent,
        "send_error": send_error,
        "mode": mode,
    }


class BookingDraftRequest(BaseModel):
    slot_start: str = ""
    service_type: str = "Service"


@app.post("/api/customer/{customer_id}/booking-draft")
def generate_booking_draft(customer_id: int, req: BookingDraftRequest):
    """Generate a confirmation email subject + body for the booking panel."""
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        tone = operator.tone_profile or "" if operator else ""
        customer_name = customer.name

    slot_label = ""
    if req.slot_start:
        try:
            dt = datetime.fromisoformat(req.slot_start)
            slot_label = dt.strftime("%A, %B %-d at %-I:%M %p")
        except ValueError:
            slot_label = req.slot_start

    prompt = (
        f"Write a short, warm booking confirmation email.\n"
        f"Customer name: {customer_name}\n"
        f"Service: {req.service_type}\n"
        f"Time: {slot_label or 'TBD'}\n"
        f"Tone notes: {tone}\n\n"
        f"Return JSON: {{\"subject\": \"...\", \"body\": \"...\"}}\n"
        f"The body should be 3–5 sentences max. No fluff. Use the operator's tone."
    )
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        import json as _json
        raw = msg.content[0].text.strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = _json.loads(raw.strip())
        return {"subject": data.get("subject", ""), "body": data.get("body", "")}
    except Exception as e:
        # Fallback to a plain default
        subject = f"Your appointment is confirmed — {req.service_type}"
        body = f"Hi {customer_name},\n\nJust confirming your {req.service_type} appointment{' on ' + slot_label if slot_label else ''}.\n\nLet me know if you need to reschedule.\n\nBest,\nArjuna"
        return {"subject": subject, "body": body}


@app.post("/api/customer/{customer_id}/book-and-invite")
def book_and_invite(customer_id: int, req: ConfirmBookingRequest):
    """
    Create a booking + GCal event + send confirmation email directly from the
    conversation page — no outreach queue log required.
    """
    try:
        slot_start = datetime.fromisoformat(req.slot_start)
        slot_end = datetime.fromisoformat(req.slot_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slot_start or slot_end — expected ISO datetime")

    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        mode = (operator.outreach_mode or "dry_run").strip().lower() if operator else "dry_run"
        customer_email = customer.email
        customer_name = customer.name
        # Find outbound thread to reply in-thread
        existing_thread = (
            db.query(OutreachLog.gmail_thread_id)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.gmail_thread_id != None,
                OutreachLog.direction == "outbound",
                OutreachLog.dry_run == False,
            )
            .order_by(OutreachLog.sent_at.desc())
            .first()
        )
        existing_thread_id = existing_thread[0] if existing_thread else None

    # Create Booking record
    with get_db() as db:
        booking = Booking(
            operator_id=OPERATOR_ID,
            customer_id=customer_id,
            slot_start=slot_start,
            slot_end=slot_end,
            status="confirmed",
            source="ai_outreach",
            service_type=req.service_type,
            notes=req.notes,
        )
        db.add(booking)
        db.flush()
        booking_id = booking.id
        c = db.query(Customer).filter_by(id=customer_id).first()
        if c:
            c.reactivation_status = "booked"

    # Create Google Calendar event
    gcal_event_id = None
    gcal_error = None
    try:
        from integrations.calendar import create_calendar_event
        event = create_calendar_event(
            summary=f"{req.service_type} — {customer_name}",
            start_dt=slot_start,
            end_dt=slot_end,
            customer_email=customer_email,
            description=(
                f"Booked via Foreman reactivation outreach.\n"
                f"Customer: {customer_name}"
                + (f"\nNotes: {req.notes}" if req.notes else "")
            ),
        )
        gcal_event_id = event.get("id")
        if gcal_event_id:
            with get_db() as db:
                b = db.query(Booking).filter_by(id=booking_id).first()
                if b:
                    b.google_cal_event_id = gcal_event_id
    except Exception as e:
        gcal_error = str(e)
        print(f"[book_and_invite] GCal event creation failed: {e}")

    # Send confirmation email
    email_sent = False
    send_error = None
    email_subject = req.email_subject or f"Your appointment is confirmed — {req.service_type}"
    email_body = req.email_body or f"Hi {customer_name},\n\nJust confirming your appointment for {req.service_type} on {slot_start.strftime('%A, %B %-d at %-I:%M %p')}.\n\nLet me know if you need to reschedule.\n\nBest,\nArjuna"
    if mode == "production" and customer_email:
        try:
            inbound_rfc_id = _get_customer_inbound_rfc_id(customer_id)
            thread_id = _gmail_send_message(
                to=customer_email,
                subject=email_subject,
                body=email_body,
                thread_id=existing_thread_id,
                in_reply_to=inbound_rfc_id,
            )
            email_sent = bool(thread_id)
            # Log the confirmation email
            with get_db() as db:
                log = OutreachLog(
                    operator_id=OPERATOR_ID,
                    customer_id=customer_id,
                    channel="email",
                    direction="outbound",
                    subject=email_subject,
                    content=email_body,
                    sent_at=datetime.utcnow(),
                    dry_run=False,
                    approval_status="sent",
                    sequence_step=0,
                    gmail_thread_id=thread_id,
                    response_classification="booking_confirmed",
                )
                db.add(log)
        except Exception as e:
            send_error = str(e)
    else:
        email_sent = False  # dry run — booking still created, GCal still fires

    return {
        "status": "confirmed",
        "booking_id": booking_id,
        "gcal_event_id": gcal_event_id,
        "gcal_error": gcal_error,
        "email_sent": email_sent,
        "send_error": send_error,
        "mode": mode,
    }


class ApproveRequest(BaseModel):
    subject: str
    body: str


@app.post("/api/draft/{customer_id}/approve")
def approve_draft(customer_id: int, req: ApproveRequest):
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        log = OutreachLog(
            operator_id=OPERATOR_ID,
            customer_id=customer_id,
            channel="email",
            direction="outbound",
            subject=req.subject,
            content=req.body,
            dry_run=True,
            approval_status="pending",
            approved_at=None,
            scheduled_send_at=None,
            send_error=None,
            sequence_step=0,
        )
        db.add(log)
        customer.reactivation_status = "outreach_sent"

    return {"status": "approved", "customer_id": customer_id}


class OutreachModeRequest(BaseModel):
    mode: str


@app.post("/api/operator/mode")
def set_outreach_mode(req: OutreachModeRequest):
    mode = (req.mode or "").strip().lower()
    if mode not in ("dry_run", "production"):
        raise HTTPException(status_code=400, detail="Mode must be 'dry_run' or 'production'")

    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        if not operator:
            raise HTTPException(status_code=404, detail="Operator not found")
        operator.outreach_mode = mode

    return {
        "status": "ok",
        "mode": mode,
        "mode_label": "Production" if mode == "production" else "Dry Run",
    }


# ── Reactivation agent trigger ────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    limit: int = 10
    threshold_days: int = None


@app.post("/api/agent/run")
def run_agent(req: AgentRunRequest = None):
    """Run reactivation agent synchronously — blocks until complete."""
    global _agent_last_run
    req = req or AgentRunRequest()
    from agents.reactivation import run as run_reactivation
    count = run_reactivation(
        operator_id=OPERATOR_ID,
        limit=req.limit,
        threshold_days=req.threshold_days,
    )
    _agent_last_run["reactivation"] = datetime.utcnow()
    return {"status": "ok", "drafts_queued": count or 0}


@app.post("/api/agent/run-customer-analyzer")
def run_agent_customer_analyzer():
    """Run customer analyzer synchronously — blocks until complete."""
    count = _run_customer_analyzer_job()
    return {"status": "ok", "analyzed": count or 0}


@app.post("/api/agent/run-scoring")
def run_agent_scoring():
    """Run priority scorer synchronously — blocks until complete."""
    _run_scoring_job()
    return {"status": "ok"}


@app.post("/api/agent/run-tone-profiler")
def run_agent_tone_profiler():
    """Run tone profiler synchronously — blocks until complete."""
    global _agent_last_run
    from agents.tone_profiler import run as run_tone_profiler
    run_tone_profiler(operator_id=OPERATOR_ID)
    _agent_last_run["tone_profiler"] = datetime.utcnow()
    return {"status": "ok"}


@app.post("/api/agent/run-reply-detector")
def run_agent_reply_detector():
    """Run reply detector synchronously — blocks until complete (may take 30–60s)."""
    global _agent_last_run
    from agents.reply_detector import run as run_reply_detector
    count = run_reply_detector(operator_id=OPERATOR_ID)
    _agent_last_run["reply_detector"] = datetime.utcnow()
    return {"status": "ok", "replies_detected": count or 0}


@app.post("/api/agent/run-follow-up")
def run_agent_follow_up():
    """Run follow-up sequencer synchronously — blocks until complete."""
    _run_follow_up_job()
    return {"status": "ok"}


@app.post("/api/classify/{log_id}")
def classify_log(log_id: int):
    """Manually trigger classification on an inbound OutreachLog."""
    try:
        from agents.response_classifier import classify_reply
        result = classify_reply(operator_id=OPERATOR_ID, inbound_log_id=log_id, verbose=True)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/draft-response/{customer_id}")
def draft_response(customer_id: int, req: dict = Body({})):
    """Manually trigger conversation agent for a customer."""
    classification = req.get("classification", "unclear")
    inbound_log_id = req.get("inbound_log_id")
    import threading
    result = {}
    def _run():
        from agents.conversation_agent import generate_response
        draft_id = generate_response(
            operator_id=OPERATOR_ID,
            customer_id=customer_id,
            classification=classification,
            inbound_log_id=inbound_log_id,
            verbose=True,
        )
        result["draft_id"] = draft_id
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)
    return {"status": "queued", "draft_id": result.get("draft_id")}


@app.post("/api/action/draft-outreach/{customer_id}")
def action_draft_outreach(customer_id: int):
    """One-click: generate reactivation draft and queue it. Returns draft_id."""
    with get_db() as db:
        # Idempotent: return existing pending draft if already queued
        existing = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                OutreachLog.direction == "outbound",
                OutreachLog.response_classification.is_(None),
            )
            .first()
        )
        if existing:
            return {"status": "exists", "draft_id": existing.id}

    # Generate a fresh reactivation draft for this customer synchronously
    draft = _generate_reactivation_draft(customer_id)

    # Persist to queue
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        new_log = OutreachLog(
            operator_id=OPERATOR_ID,
            customer_id=customer_id,
            channel="email",
            direction="outbound",
            subject=draft.get("subject", "Checking in"),
            content=draft.get("body", ""),
            dry_run=True,
            sequence_step=0,
            approval_status="pending",
        )
        db.add(new_log)
        db.flush()
        draft_id = new_log.id
    return {"status": "generated", "draft_id": draft_id}


@app.post("/api/action/draft-followup/{customer_id}")
def action_draft_followup(customer_id: int):
    """One-click: generate follow-up draft for a customer mid-sequence."""
    with get_db() as db:
        # Idempotent check
        existing = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                OutreachLog.direction == "outbound",
            )
            .first()
        )
        if existing:
            return {"status": "exists", "draft_id": existing.id}

    from agents.conversation_agent import generate_response
    draft_id = generate_response(
        operator_id=OPERATOR_ID,
        customer_id=customer_id,
        classification="unclear",
        verbose=True,
    )
    if not draft_id:
        raise HTTPException(status_code=500, detail="Failed to generate follow-up draft")
    return {"status": "generated", "draft_id": draft_id}


@app.post("/api/action/book-call/{customer_id}")
def action_book_call(customer_id: int):
    """One-click: generate booking proposal with calendar slots, queue to Meetings Queue."""
    with get_db() as db:
        existing = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                OutreachLog.direction == "outbound",
                OutreachLog.response_classification == "booking_intent",
            )
            .first()
        )
        if existing:
            return {"status": "exists", "draft_id": existing.id}

    try:
        from agents.conversation_agent import generate_response
        draft_id = generate_response(
            operator_id=OPERATOR_ID,
            customer_id=customer_id,
            classification="booking_intent",
            verbose=True,
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"generation error: {exc}")
    if not draft_id:
        raise HTTPException(status_code=500, detail="generate_response returned None — check server logs")
    return {"status": "generated", "draft_id": draft_id}


@app.post("/api/outreach/{log_id}/regenerate")
def regenerate_outreach(log_id: int):
    """Delete the existing draft and regenerate a fresh one for the same customer."""
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID, dry_run=True).first()
        if not log:
            raise HTTPException(status_code=404, detail="Draft not found")
        customer_id = log.customer_id
        db.delete(log)

    # Regenerate
    draft = _generate_reactivation_draft(customer_id)
    with get_db() as db:
        new_log = OutreachLog(
            operator_id=OPERATOR_ID,
            customer_id=customer_id,
            channel="email",
            direction="outbound",
            subject=draft.get("subject", "Checking in"),
            content=draft.get("body", ""),
            dry_run=True,
            sequence_step=0,
            approval_status="pending",
        )
        db.add(new_log)
        db.flush()
        new_id = new_log.id
    return {"status": "regenerated", "draft_id": new_id}


@app.post("/api/meetings/{log_id}/regenerate")
def regenerate_meeting(log_id: int):
    """Delete the existing meeting draft and regenerate a booking proposal."""
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID, dry_run=True).first()
        if not log:
            raise HTTPException(status_code=404, detail="Draft not found")
        customer_id = log.customer_id
        db.delete(log)

    from agents.conversation_agent import generate_response
    draft_id = generate_response(
        operator_id=OPERATOR_ID,
        customer_id=customer_id,
        classification="booking_intent",
        verbose=True,
    )
    if not draft_id:
        raise HTTPException(status_code=500, detail="Failed to regenerate booking proposal")
    return {"status": "regenerated", "draft_id": draft_id}


@app.get("/api/agent/status")
def agent_status():
    with get_db() as db:
        op = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        tone_profile_set = bool(op.tone_profile) if op else False

        latest_reactivation_log = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, sequence_step=0, direction="outbound")
            .order_by(OutreachLog.created_at.desc())
            .first()
        )
        queued_count = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, dry_run=True)
            .count()
        )
        last_reactivation_run = (
            latest_reactivation_log.created_at.isoformat()
            if latest_reactivation_log else None
        )

        customer_profiles = 0
        latest_analyzed = None
        customers = db.query(Customer).filter_by(operator_id=OPERATOR_ID).all()
        for customer in customers:
            profile = _normalize_customer_profile(customer.customer_profile)
            if profile["analyzed_at"]:
                customer_profiles += 1
                if not latest_analyzed or profile["analyzed_at"] > latest_analyzed:
                    latest_analyzed = profile["analyzed_at"]

        tracked_threads = (
            db.query(OutreachLog.gmail_thread_id)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == False,
                OutreachLog.direction == "outbound",
                OutreachLog.gmail_thread_id != None,
            )
            .distinct()
            .count()
        )
        inbound_replies = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, direction="inbound")
            .count()
        )
        follow_up_drafts = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                OutreachLog.sequence_step > 0,
            )
            .count()
        )
        active_sequences = (
            db.query(Customer)
            .filter(
                Customer.operator_id == OPERATOR_ID,
                Customer.reactivation_status.in_(("outreach_sent", "sequence_step_2", "sequence_step_3")),
            )
            .count()
        )

    return {
        "outreach_mode": (op.outreach_mode or "dry_run").strip().lower() if op else "dry_run",
        "tone_profiler": {
            "configured": tone_profile_set,
            "description": "Extracts your writing voice from sent Gmail",
        },
        "reactivation": {
            "configured": True,
            "last_run_at": last_reactivation_run,
            "queued_count": queued_count,
            "description": "Identifies dormant customers and queues personalized outreach drafts",
        },
        "customer_analyzer": {
            "configured": True,
            "profiles_built": customer_profiles,
            "last_run_at": latest_analyzed.isoformat() if latest_analyzed else None,
            "description": "Builds customer relationship profiles from prior correspondence",
        },
        "reply_detector": {
            "configured": True,
            "tracked_threads": tracked_threads,
            "replies_detected": inbound_replies,
            "description": "Detects customer replies using Gmail thread IDs",
        },
        "follow_up": {
            "configured": True,
            "active_sequences": active_sequences,
            "drafts_queued": follow_up_drafts,
            "description": "Queues context-aware follow-up drafts at Day 3/7/14",
        },
    }


@app.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        op = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        operator_data = _operator_data(op)
        tone_profile_set = bool(op.tone_profile) if op else False

        latest_reactivation_log = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, sequence_step=0, direction="outbound")
            .order_by(OutreachLog.created_at.desc())
            .first()
        )
        total_reactivation_drafts = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, sequence_step=0, direction="outbound")
            .count()
        )
        queued_count = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, dry_run=True)
            .count()
        )
        last_reactivation_run = latest_reactivation_log.created_at if latest_reactivation_log else None

        analyzed_profiles = 0
        with_history = 0
        latest_analyzed_at = None
        customers = db.query(Customer).filter_by(operator_id=OPERATOR_ID).all()
        for customer in customers:
            profile = _normalize_customer_profile(customer.customer_profile)
            if not profile["analyzed_at"]:
                continue
            analyzed_profiles += 1
            if profile["email_count"] > 0:
                with_history += 1
            if not latest_analyzed_at or profile["analyzed_at"] > latest_analyzed_at:
                latest_analyzed_at = profile["analyzed_at"]

        tracked_threads = (
            db.query(OutreachLog.gmail_thread_id)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == False,
                OutreachLog.direction == "outbound",
                OutreachLog.gmail_thread_id != None,
            )
            .distinct()
            .count()
        )
        replies_detected = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, direction="inbound")
            .count()
        )
        latest_reply = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, direction="inbound")
            .order_by(OutreachLog.sent_at.desc(), OutreachLog.created_at.desc())
            .first()
        )
        latest_reply_at = (latest_reply.sent_at or latest_reply.created_at) if latest_reply else None

        follow_up_drafts = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.dry_run == True,
                OutreachLog.sequence_step > 0,
            )
            .count()
        )
        latest_follow_up = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.sequence_step > 0,
                OutreachLog.direction == "outbound",
            )
            .order_by(OutreachLog.created_at.desc())
            .first()
        )
        latest_follow_up_at = latest_follow_up.created_at if latest_follow_up else None
        active_sequences = (
            db.query(Customer)
            .filter(
                Customer.operator_id == OPERATOR_ID,
                Customer.reactivation_status.in_(("outreach_sent", "sequence_step_2", "sequence_step_3")),
            )
            .count()
        )
        conversations_attention_count = _get_conversations_attention_count(db)

        scored_count = (
            db.query(Customer)
            .filter(Customer.operator_id == OPERATOR_ID, Customer.score > 0)
            .count()
        )
        high_priority_count = (
            db.query(Customer)
            .filter(Customer.operator_id == OPERATOR_ID, Customer.priority_tier == "high")
            .count()
        )
        classified_replies = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.operator_id == OPERATOR_ID,
                OutreachLog.response_classification != None,
            )
            .count()
        )
        booking_intents = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, response_classification="booking_intent")
            .count()
        )

    return templates.TemplateResponse("agents.html", {
        "request": request,
        "active": "agents",
        "operator": operator_data,
        "queue_count": queued_count,
        "conversations_attention_count": conversations_attention_count,
        "agents": [
            {
                "key": "tone_profiler",
                "name": "Tone Profiler",
                "icon": "🎙",
                "description": "Reads your sent Gmail to extract writing style, tone, and characteristic phrases. Stores a voice profile used by all outreach drafts.",
                "status": "active" if tone_profile_set else "needs_setup",
                "status_label": "Active" if tone_profile_set else "Not configured",
                "last_run_at": _agent_last_run.get("tone_profiler"),
                "stat_label": "Voice profiles" if tone_profile_set else "Setup required",
                "stat_value": str(len(operator_data.get("voice_profiles") or [])) if tone_profile_set else "—",
                "cli": "python -m agents.tone_profiler --operator-id 1",
                "phase": "Phase 2",
            },
            {
                "key": "reactivation",
                "name": "Reactivation Analyzer",
                "icon": "🎯",
                "description": "Identifies customers dormant 365+ days, ranks by priority score (days dormant × spend), generates personalized email drafts, and queues them for your review.",
                "status": "active",
                "status_label": "Active",
                "last_run_at": _agent_last_run.get("reactivation") or last_reactivation_run,
                "stat_label": "Drafts queued",
                "stat_value": str(total_reactivation_drafts),
                "cli": "python -m agents.reactivation --operator-id 1 --limit 10",
                "phase": "Phase 3",
            },
            {
                "key": "scoring",
                "name": "Priority Scorer",
                "icon": "📊",
                "description": "Scores every customer on 5 signals (Recency, Lifetime Value, Frequency, Job Type, Engagement) to produce a 0–100 priority score and tier. Runs at startup and every 24 hours.",
                "status": "active",
                "status_label": "Active (scheduled daily)",
                "last_run_at": _agent_last_run.get("scoring"),
                "stat_label": "Customers scored",
                "stat_value": str(scored_count),
                "stat_meta": f"{high_priority_count} high priority",
                "cli": "python -m core.scoring",
                "phase": "Phase 5",
            },
            {
                "key": "customer_analyzer",
                "name": "Customer Analyzer",
                "icon": "🧠",
                "description": "Builds a structured customer profile from prior Gmail correspondence and stores relationship context for more personalized drafts.",
                "status": "active",
                "status_label": "Active (scheduled daily)",
                "last_run_at": latest_analyzed_at,
                "stat_label": "Profiles built",
                "stat_value": str(analyzed_profiles),
                "stat_meta": f"{with_history} with prior email history",
                "cli": "python -m agents.customer_analyzer --operator-id 1 --all",
                "phase": "Phase 4",
            },
            {
                "key": "reply_detector",
                "name": "Reply Detector",
                "icon": "📬",
                "description": "Checks Gmail inbox by thread ID, logs inbound replies, marks customers as replied, and refreshes customer profiles from new context.",
                "status": "active" if tracked_threads > 0 else "needs_setup",
                "status_label": "Active (15-min poll)" if tracked_threads > 0 else "Waiting for sent Gmail threads",
                "last_run_at": _agent_last_run.get("reply_detector") or latest_reply_at,
                "stat_label": "Replies detected",
                "stat_value": str(replies_detected),
                "stat_meta": f"{tracked_threads} tracked Gmail thread(s)",
                "cli": "python -m agents.reply_detector --operator-id 1",
                "phase": "Phase 4",
            },
            {
                "key": "follow_up",
                "name": "Follow-up Sequencer",
                "icon": "🔁",
                "description": "Queues follow-up drafts at Day 3, Day 7, and Day 14 using customer profile + thread context. Stops when a reply is detected.",
                "status": "active",
                "status_label": "Active (scheduled daily)",
                "last_run_at": _agent_last_run.get("follow_up") or latest_follow_up_at,
                "stat_label": "Follow-ups queued",
                "stat_value": str(follow_up_drafts),
                "stat_meta": f"{active_sequences} customers in active sequence",
                "cli": "python -m agents.follow_up --operator-id 1 --limit 20",
                "phase": "Phase 4",
            },
            {
                "key": "response_classifier",
                "name": "Response Classifier",
                "icon": "🔍",
                "description": "Reads every inbound customer reply and classifies it: booking intent, callback request, price inquiry, not interested, or unclear. Runs automatically after each reply is detected. Drives what happens next.",
                "status": "active",
                "status_label": "Active (auto on reply)",
                "last_run_at": None,
                "stat_label": "Replies classified",
                "stat_value": str(classified_replies),
                "stat_meta": f"{booking_intents} booking intent(s)",
                "cli": "python -m agents.response_classifier",
                "phase": "Phase 6",
            },
            {
                "key": "conversation_agent",
                "name": "Conversation Agent",
                "icon": "✍️",
                "description": "Generates bespoke reply drafts matched to the conversation phase. Booking proposals pull real Google Calendar slots. Price responses use actual job history. All drafts land in the Outreach Queue for your review.",
                "status": "active",
                "status_label": "Active (auto on reply)",
                "last_run_at": None,
                "stat_label": "Drafts generated",
                "stat_value": str(classified_replies),
                "stat_meta": "One draft per classified reply",
                "cli": None,
                "phase": "Phase 6",
            },
            {
                "key": "sms_outreach",
                "name": "SMS Outreach",
                "icon": "💬",
                "description": "Sends and receives text messages via Twilio. Handles two-way replies, opt-outs, and booking confirmations over SMS.",
                "status": "planned",
                "status_label": "Planned — Phase 5",
                "last_run_at": None,
                "stat_label": None,
                "stat_value": None,
                "cli": None,
                "phase": "Phase 5",
            },
        ],
    })


# ── Internal tools ────────────────────────────────────────────────────────────

@app.get("/internal", response_class=HTMLResponse)
def internal_page(request: Request):
    if (guard := _db_starting_response()):
        return guard
    with get_db() as db:
        op = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        operator_data = _operator_data(op)
        customer_count = db.query(Customer).filter_by(operator_id=OPERATOR_ID).count()
        outreach_count = db.query(OutreachLog).filter_by(operator_id=OPERATOR_ID).count()
        booking_count = db.query(Booking).count()
        conversations_attention_count = _get_conversations_attention_count(db)

    return templates.TemplateResponse("internal.html", {
        "request": request,
        "active": "internal",
        "operator": operator_data,
        "conversations_attention_count": conversations_attention_count,
        "db_stats": {
            "customers": customer_count,
            "outreach_logs": outreach_count,
            "bookings": booking_count,
        },
    })


@app.post("/api/internal/run-all-agents")
def api_run_all_agents():
    """Run all agents synchronously in sequence. Updates _agent_last_run for each."""
    global _agent_last_run
    from agents.tone_profiler import run as run_tone_profiler
    from agents.reactivation import run as run_reactivation
    from agents.reply_detector import run as run_reply_detector
    from agents.follow_up import run as run_follow_up

    results = {}

    def _step(key, fn, **kwargs):
        try:
            result = fn(**kwargs)
            _agent_last_run[key] = datetime.utcnow()
            results[key] = {"ok": True, "result": str(result) if result is not None else "done"}
        except Exception as e:
            results[key] = {"ok": False, "error": str(e)[:200]}

    _step("tone_profiler", run_tone_profiler, operator_id=OPERATOR_ID)
    _step("reactivation", run_reactivation, operator_id=OPERATOR_ID, limit=20)
    try:
        _run_scoring_job()
        _agent_last_run["scoring"] = datetime.utcnow()
        results["scoring"] = {"ok": True, "result": "done"}
    except Exception as e:
        results["scoring"] = {"ok": False, "error": str(e)[:200]}
    try:
        _run_customer_analyzer_job()
        results["customer_analyzer"] = {"ok": True, "result": "done"}
    except Exception as e:
        results["customer_analyzer"] = {"ok": False, "error": str(e)[:200]}
    _step("reply_detector", run_reply_detector, operator_id=OPERATOR_ID)
    _step("follow_up", run_follow_up, operator_id=OPERATOR_ID)

    return {"ok": True, "results": results}


@app.post("/api/internal/reseed")
def api_reseed():
    """Wipe and reseed the database with the full 200-customer dataset."""
    import subprocess
    import sys
    try:
        result = subprocess.run(
            [sys.executable, "-m", "data.reseed"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": result.stderr[-2000:] or "reseed failed"},
            )
        return JSONResponse({"ok": True, "output": result.stdout[-2000:]})
    except subprocess.TimeoutExpired:
        return JSONResponse(status_code=500, content={"ok": False, "error": "Reseed timed out after 120s"})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

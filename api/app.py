"""
api/app.py
FastAPI application — serves the Foreman web UI and JSON API.

Web pages:
  GET /               → Dashboard (metrics + customer categories)
  GET /customer/{id}  → Customer detail (history + draft outreach)
  GET /outreach       → Outreach queue (approved drafts pending send)

JSON API:
  GET  /health
  GET  /api/operator/{id}
  GET  /api/operator/{id}/customers
  GET  /api/operator/{id}/stats
  POST /api/draft/{customer_id}          → generate draft via Claude
  POST /api/draft/{customer_id}/approve  → log draft, mark customer contacted
"""

import json
from datetime import datetime
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.config import config
from core.database import get_db, init_db
from core.models import Customer, Job, Operator, OutreachLog

app = FastAPI(title="Foreman", version="0.2.0")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

OPERATOR_ID = 1  # Single-tenant for now


# ── Helpers ───────────────────────────────────────────────────────────────────

def _operator_data(op) -> dict:
    """Serialize operator ORM object to a template-safe dict."""
    return {
        "id": op.id,
        "name": op.name,
        "business_name": op.business_name,
        "niche": op.niche,
        "onboarding_complete": op.onboarding_complete,
        "voice_profiles": op.voice_profiles,
        "tone_profile_set": bool(op.tone_profile),
    }


def _get_queue_count(db) -> int:
    """Count pending drafts (dry_run=True) for the sidebar badge."""
    return db.query(OutreachLog).filter_by(
        operator_id=OPERATOR_ID, dry_run=True
    ).count()

def days_since(dt) -> int:
    if not dt:
        return 0
    return (datetime.utcnow() - dt).days


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


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    init_db()


# ── Web pages ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        raw_customers = db.query(Customer).filter_by(operator_id=OPERATOR_ID).all()
        queue_count = db.query(OutreachLog).filter_by(
            operator_id=OPERATOR_ID, dry_run=True
        ).count()
        operator_data = _operator_data(operator)
        customers = sorted(
            [add_segment(enrich(c)) for c in raw_customers],
            key=lambda x: x["days_dormant"], reverse=True
        )

    cats = {k: [] for k in ("prime", "warming", "in_sequence", "converted", "recent", "unsubscribed")}
    for c in customers:
        cats[c["category"]].append(c)

    prime = cats["prime"]
    prime_revenue = sum(c["total_spend"] for c in prime)
    avg_dormant = int(sum(c["days_dormant"] for c in prime) / len(prime)) if prime else 0

    seg_counts = {k: 0 for k in SEGMENT_INFO}
    for c in customers:
        if c['category'] != 'unsubscribed':
            seg_counts[c['segment_key']] += 1

    top_prospects = sorted(
        [c for c in customers if c['category'] not in ('unsubscribed', 'converted')],
        key=lambda x: x['priority_score'], reverse=True
    )[:6]

    stats = {
        "total_customers": len(customers),
        "prime_count": len(prime),
        "warming_count": len(cats["warming"]),
        "in_sequence_count": len(cats["in_sequence"]),
        "converted_count": len(cats["converted"]),
        "prime_revenue": prime_revenue,
        "avg_days_dormant": avg_dormant,
    }

    today_str = datetime.utcnow().strftime('%A, %B %-d, %Y')

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active": "dashboard",
        "operator": operator_data,
        "stats": stats,
        "seg_counts": seg_counts,
        "categories": cats,
        "top_prospects": top_prospects,
        "queue_count": queue_count,
        "today_str": today_str,
    })


@app.get("/customer/{customer_id}", response_class=HTMLResponse)
def customer_detail(request: Request, customer_id: int):
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        jobs_raw = db.query(Job).filter_by(customer_id=customer_id).order_by(Job.completed_at.desc()).all()
        logs_raw = db.query(OutreachLog).filter_by(customer_id=customer_id).order_by(OutreachLog.sent_at.desc()).all()

        operator_data = _operator_data(operator)
        queue_count = _get_queue_count(db)
        customer_data = enrich(customer)
        customer_data = add_segment(customer_data)
        customer_data["assigned_voice_id"] = customer.assigned_voice_id
        jobs = [{"service_type": j.service_type, "completed_at": j.completed_at,
                 "status": j.status, "amount": j.amount} for j in jobs_raw]
        logs = [{"id": l.id, "subject": l.subject, "content": l.content,
                 "sent_at": l.sent_at, "dry_run": l.dry_run, "sequence_step": l.sequence_step}
                for l in logs_raw]

    return templates.TemplateResponse("customer.html", {
        "request": request,
        "active": "customers",
        "operator": operator_data,
        "queue_count": queue_count,
        "customer": customer_data,
        "jobs": jobs,
        "logs": logs,
    })


@app.get("/outreach", response_class=HTMLResponse)
def outreach_queue(request: Request):
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        rows = (
            db.query(OutreachLog, Customer)
            .join(Customer, OutreachLog.customer_id == Customer.id)
            .filter(OutreachLog.operator_id == OPERATOR_ID)
            .order_by(OutreachLog.created_at.desc())
            .all()
        )
        operator_data = _operator_data(operator)

        def _row(log, customer):
            return {
                "log_id": log.id,
                "customer_id": customer.id,
                "customer_name": customer.name,
                "subject": log.subject,
                "content": log.content,
                "created_at": log.created_at,
                "sent_at": log.sent_at,
                "dry_run": log.dry_run,
                "sequence_step": log.sequence_step,
            }

        pending = [_row(l, c) for l, c in rows if l.dry_run]
        sent = [_row(l, c) for l, c in rows if not l.dry_run]

    return templates.TemplateResponse("outreach.html", {
        "request": request,
        "active": "outreach",
        "operator": operator_data,
        "queue_count": len(pending),
        "pending": pending,
        "sent": sent,
    })


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


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
Return ONLY a JSON object with keys "subject" and "body". No markdown, no code fences."""

DRAFT_USER = """Tone profile:
{tone}

{voice_section}Write a reactivation email for past customer {name}.
Last service: "{service_type}" about {days} days ago ({months:.0f} months).
History: {jobs} jobs, ${spend:.0f} total spent."""


class DraftRequest(BaseModel):
    voice_id: str = None


@app.post("/api/draft/{customer_id}")
def generate_draft(customer_id: int, req: DraftRequest = None):
    req = req or DraftRequest()
    with get_db() as db:
        customer = db.query(Customer).filter_by(id=customer_id, operator_id=OPERATOR_ID).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        operator = db.query(Operator).filter_by(id=OPERATOR_ID).first()

        # Resolve voice profile: use requested voice_id, fall back to customer's assigned, then first profile
        voice_id = req.voice_id or customer.assigned_voice_id
        profiles = operator.voice_profiles
        voice = next((p for p in profiles if p["id"] == voice_id), profiles[0] if profiles else None)

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

    raw = message.content[0].text.strip()
    try:
        draft = json.loads(raw)
    except json.JSONDecodeError:
        draft = {"subject": "Checking in", "body": raw}

    if voice:
        draft["voice_name"] = voice["name"]
    return draft


@app.post("/api/outreach/{log_id}/mark-sent")
def mark_sent(log_id: int):
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=log_id, operator_id=OPERATOR_ID).first()
        if not log:
            raise HTTPException(status_code=404, detail="Log entry not found")
        log.dry_run = False
    return {"status": "sent", "log_id": log_id}


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
            sequence_step=0,
        )
        db.add(log)
        customer.reactivation_status = "outreach_sent"

    return {"status": "approved", "customer_id": customer_id}


# ── Reactivation agent trigger ────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    limit: int = 10
    threshold_days: int = None


@app.post("/api/agent/run")
def run_agent(req: AgentRunRequest = None):
    req = req or AgentRunRequest()
    from agents.reactivation import run as run_reactivation
    import threading

    def _run():
        run_reactivation(
            operator_id=OPERATOR_ID,
            limit=req.limit,
            threshold_days=req.threshold_days,
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "limit": req.limit}


@app.get("/api/agent/status")
def agent_status():
    with get_db() as db:
        op = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        tone_profile_set = bool(op.tone_profile) if op else False

        latest_log = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, sequence_step=0)
            .order_by(OutreachLog.created_at.desc())
            .first()
        )
        queued_count = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, dry_run=True)
            .count()
        )
        last_run_at = latest_log.created_at.isoformat() if latest_log else None

    return {
        "tone_profiler": {
            "configured": tone_profile_set,
            "description": "Extracts your writing voice from sent Gmail",
        },
        "reactivation": {
            "configured": True,
            "last_run_at": last_run_at,
            "queued_count": queued_count,
            "description": "Scans dormant customers and queues email drafts",
        },
    }


@app.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request):
    with get_db() as db:
        op = db.query(Operator).filter_by(id=OPERATOR_ID).first()
        operator_data = _operator_data(op)
        tone_profile_set = bool(op.tone_profile) if op else False

        latest_log = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, sequence_step=0)
            .order_by(OutreachLog.created_at.desc())
            .first()
        )
        total_drafted = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, sequence_step=0)
            .count()
        )
        queued_count = (
            db.query(OutreachLog)
            .filter_by(operator_id=OPERATOR_ID, dry_run=True)
            .count()
        )
        last_run_at = latest_log.created_at if latest_log else None

    return templates.TemplateResponse("agents.html", {
        "request": request,
        "active": "agents",
        "operator": operator_data,
        "queue_count": queued_count,
        "agents": [
            {
                "key": "tone_profiler",
                "name": "Tone Profiler",
                "icon": "🎙",
                "description": "Reads your sent Gmail to extract writing style, tone, and characteristic phrases. Stores a voice profile used by all outreach drafts.",
                "status": "active" if tone_profile_set else "needs_setup",
                "status_label": "Active" if tone_profile_set else "Not configured",
                "last_run_at": None,
                "stat_label": "Voice profiles" if tone_profile_set else "Setup required",
                "stat_value": str(len(operator_data.get("voice_profiles") or [])) if tone_profile_set else "—",
                "cli": "python -m agents.tone_profiler --operator-id 1",
                "phase": "Phase 2",
            },
            {
                "key": "reactivation",
                "name": "Reactivation Agent",
                "icon": "🎯",
                "description": "Scans for customers dormant 365+ days, ranks by priority score (days dormant × spend), generates personalized email drafts, and queues them for your review.",
                "status": "active",
                "status_label": "Active",
                "last_run_at": last_run_at,
                "stat_label": "Drafts queued",
                "stat_value": str(total_drafted),
                "cli": "python -m agents.reactivation --operator-id 1 --limit 10",
                "phase": "Phase 3",
            },
            {
                "key": "follow_up",
                "name": "Follow-up Sequencer",
                "icon": "🔁",
                "description": "Sends follow-up emails at Day 3, Day 7, and Day 14 for customers who haven't replied. Stops automatically when a reply is detected.",
                "status": "planned",
                "status_label": "Planned — Phase 4",
                "last_run_at": None,
                "stat_label": None,
                "stat_value": None,
                "cli": None,
                "phase": "Phase 4",
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

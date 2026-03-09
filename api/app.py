"""
api/app.py
FastAPI application — serves operator data, customer lists, and tone profile.
This is what Railway hosts. CLI agents (tone_profiler, etc.) run locally
and write to the shared database.

Run locally:  uvicorn api.app:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from core.database import get_db, init_db
from core.models import Operator, Customer

app = FastAPI(title="Foreman", version="0.1.0")


@app.on_event("startup")
def startup():
    init_db()


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "Foreman",
        "status": "ok",
        "version": "0.1.0",
        "phase": "2 — Tone Profiler complete",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Operator ──────────────────────────────────────────────────────────────────

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
            "integrations": op.integrations,
        }


@app.get("/api/operator/{operator_id}/customers")
def get_customers(operator_id: int, status: str = None):
    with get_db() as db:
        q = db.query(Customer).filter_by(operator_id=operator_id)
        if status:
            q = q.filter_by(reactivation_status=status)
        customers = q.order_by(Customer.last_service_date.asc()).all()
        return {
            "total": len(customers),
            "customers": [
                {
                    "id": c.id,
                    "name": c.name,
                    "email": c.email,
                    "last_service_date": c.last_service_date.isoformat() if c.last_service_date else None,
                    "last_service_type": c.last_service_type,
                    "total_jobs": c.total_jobs,
                    "total_spend": c.total_spend,
                    "reactivation_status": c.reactivation_status,
                }
                for c in customers
            ],
        }


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

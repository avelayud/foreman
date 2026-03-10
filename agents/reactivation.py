"""
agents/reactivation.py
Reactivation outreach agent.

Scans for dormant customers (never_contacted, days >= threshold), ranks by
priority score, generates a personalized email draft via Claude for each, and
saves it to OutreachLog (dry_run=True) for operator review in the /outreach queue.

Usage:
    python -m agents.reactivation --operator-id 1 [--limit N] [--threshold DAYS]

    # Against Railway Postgres:
    DATABASE_URL="postgresql://..." python -m agents.reactivation --operator-id 1
"""

import argparse
import json
from datetime import datetime

import anthropic

from core.config import config
from core.database import get_db
from core.models import Customer, Operator, OutreachLog


# ── Prompts (mirrors api/app.py — single source of truth TODO: extract to shared) ──

DRAFT_SYSTEM = """You are a ghostwriter for a small field service business owner.
Write a single reactivation email in the owner's exact voice — their tone, greeting style, signoff, and characteristic phrases.
The email should feel personal and genuine, never salesy. Keep it short: 3–5 sentences. End with a soft call to action.
Return ONLY a JSON object with keys "subject" and "body". No markdown, no code fences."""

DRAFT_USER = """Tone profile:
{tone}

{voice_section}Write a reactivation email for past customer {name}.
Last service: "{service_type}" about {days} days ago ({months:.0f} months).
History: {jobs} jobs, ${spend:.0f} total spent."""


# ── Helpers ────────────────────────────────────────────────────────────────────

def days_since(dt) -> int:
    if not dt:
        return 0
    return (datetime.utcnow() - dt).days


def priority_score(days: int, spend: float) -> float:
    return days * (spend / 1000 + 0.5)


def generate_draft(client: anthropic.Anthropic, customer: dict, operator: dict) -> dict:
    """Call Claude and return {"subject": ..., "body": ...}."""
    voice_id = customer.get("assigned_voice_id")
    profiles = operator.get("voice_profiles") or []
    voice = next((p for p in profiles if p["id"] == voice_id), profiles[0] if profiles else None)

    voice_section = (
        f"Write in the voice of {voice['name']} ({voice.get('role', 'team member')}).\n\n"
        if voice else ""
    )

    days = customer["days_dormant"]
    tone = json.dumps(operator.get("tone_profile") or {}, indent=2)

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=512,
        system=DRAFT_SYSTEM,
        messages=[{
            "role": "user",
            "content": DRAFT_USER.format(
                tone=tone,
                voice_section=voice_section,
                name=customer["name"],
                service_type=customer.get("last_service_type") or "service",
                days=days,
                months=days / 30,
                jobs=customer["total_jobs"],
                spend=customer["total_spend"],
            ),
        }],
    )

    raw = message.content[0].text.strip()
    try:
        draft = json.loads(raw)
    except json.JSONDecodeError:
        draft = {"subject": "Checking in", "body": raw}

    if voice:
        draft["voice_name"] = voice["name"]
    return draft


# ── Main agent logic ───────────────────────────────────────────────────────────

def run(operator_id: int, limit: int = 10, threshold_days: int = None, dry_run: bool = True):
    threshold = threshold_days or config.REACTIVATION_THRESHOLD_DAYS

    print(f"\n[reactivation] operator={operator_id} limit={limit} threshold={threshold}d dry_run={dry_run}")

    with get_db() as db:
        operator_obj = db.query(Operator).filter_by(id=operator_id).first()
        if not operator_obj:
            print(f"[reactivation] ERROR: operator {operator_id} not found")
            return

        operator = {
            "id": operator_obj.id,
            "name": operator_obj.name,
            "business_name": operator_obj.business_name,
            "tone_profile": operator_obj.tone_profile,
            "voice_profiles": operator_obj.voice_profiles,
        }

        # Find candidates: never_contacted and dormant past threshold — serialize inside session
        raw_candidates = (
            db.query(Customer)
            .filter_by(operator_id=operator_id, reactivation_status="never_contacted")
            .all()
        )
        raw_serialized = [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "last_service_date": c.last_service_date,
                "last_service_type": c.last_service_type,
                "total_jobs": c.total_jobs,
                "total_spend": c.total_spend,
                "assigned_voice_id": c.assigned_voice_id,
            }
            for c in raw_candidates
        ]

    candidates = []
    for c in raw_serialized:
        d = days_since(c["last_service_date"])
        if d >= threshold:
            c["days_dormant"] = d
            c["priority_score"] = priority_score(d, c["total_spend"])
            candidates.append(c)

    # Sort by priority score descending, take top N
    candidates.sort(key=lambda x: x["priority_score"], reverse=True)
    targets = candidates[:limit]

    print(f"[reactivation] {len(candidates)} eligible candidates → processing top {len(targets)}")

    if not targets:
        print("[reactivation] No eligible customers found. Done.")
        return

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    queued = 0

    for customer in targets:
        print(f"  → {customer['name']} ({customer['days_dormant']}d dormant, ${customer['total_spend']:.0f} LTV)")
        try:
            draft = generate_draft(client, customer, operator)
            print(f"     subject: {draft['subject']}")

            with get_db() as db:
                log = OutreachLog(
                    operator_id=operator_id,
                    customer_id=customer["id"],
                    channel="email",
                    direction="outbound",
                    subject=draft["subject"],
                    content=draft["body"],
                    dry_run=True,
                    sequence_step=0,
                )
                db.add(log)

                # Update status so we don't re-draft on next run
                cust = db.query(Customer).filter_by(id=customer["id"]).first()
                if cust:
                    cust.reactivation_status = "outreach_sent"

            queued += 1
        except Exception as e:
            print(f"     ERROR: {e}")

    print(f"\n[reactivation] Done. {queued}/{len(targets)} drafts queued in /outreach.")


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Foreman reactivation agent")
    parser.add_argument("--operator-id", type=int, default=1)
    parser.add_argument("--limit", type=int, default=10, help="Max customers to draft per run")
    parser.add_argument("--threshold", type=int, default=None, help="Days dormant threshold (default: config)")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Preview targets without writing to DB or calling Claude")
    args = parser.parse_args()

    if args.dry_run:
        # Preview mode — just list targets, no DB writes
        threshold = args.threshold or config.REACTIVATION_THRESHOLD_DAYS
        print(f"\n[reactivation DRY-RUN PREVIEW] operator={args.operator_id} threshold={threshold}d")
        with get_db() as db:
            raw = (
                db.query(Customer)
                .filter_by(operator_id=args.operator_id, reactivation_status="never_contacted")
                .all()
            )
            # Serialize inside session
            serialized = [(c.name, c.last_service_date, c.total_spend) for c in raw]

        hits = []
        for name, lsd, spend in serialized:
            d = days_since(lsd)
            if d >= threshold:
                hits.append((name, d, spend, priority_score(d, spend)))
        hits.sort(key=lambda x: x[3], reverse=True)
        print(f"  {len(hits)} eligible customers (showing top {args.limit}):")
        for name, days, spend, score in hits[:args.limit]:
            print(f"  - {name:30s}  {days:4d}d  ${spend:7.0f}  score={score:.0f}")
    else:
        run(
            operator_id=args.operator_id,
            limit=args.limit,
            threshold_days=args.threshold,
        )

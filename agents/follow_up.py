"""
agents/follow_up.py
Follow-up Sequence Agent.

Runs daily. For customers in an active outreach sequence with no reply detected,
drafts the next follow-up email informed by the customer profile — not a generic
timer-based template.

Sequence cadence (days since LAST outreach):
  Step 1 (Day 3)  → gentle check-in, reference original topic
  Step 2 (Day 7)  → add soft urgency or seasonal angle
  Step 3 (Day 14) → close-loop message, no pressure, leave door open

Claude reads the full CustomerProfile + prior thread content before drafting,
so every follow-up is contextually aware of who this person is.

Drafts land in /outreach queue. Operator edits and approves. Sends via Gmail.
This agent NEVER sends emails directly.

Usage:
    python -m agents.follow_up --operator-id 1 [--limit N]
"""

import argparse
import json
from datetime import datetime

import anthropic

from core.config import config
from core.database import get_db
from core.models import Customer, Operator, OutreachLog
from agents.customer_analyzer import format_profile_for_prompt

try:
    from integrations.gmail import get_thread
    GMAIL_AVAILABLE = True
except Exception:
    GMAIL_AVAILABLE = False


# ── Sequence config ───────────────────────────────────────────────────────────

SEQUENCE_STEPS = {
    1: {"days": 3,  "status_out": "sequence_step_2", "label": "Follow-up 1"},
    2: {"days": 7,  "status_out": "sequence_step_3", "label": "Follow-up 2"},
    3: {"days": 14, "status_out": "sequence_complete", "label": "Close-loop"},
}

STATUS_TO_STEP = {
    "outreach_sent":   1,
    "sequence_step_2": 2,
    "sequence_step_3": 3,
}


# ── Prompts ───────────────────────────────────────────────────────────────────

FOLLOWUP_SYSTEM = """You are a ghostwriter for a small field service business owner.
Write a follow-up email in the owner's exact voice. Be brief, warm, and never pushy.

Guidelines per step:
  Step 1 (Day 3):  Light touch — "just wanted to make sure you saw this"
  Step 2 (Day 7):  Add a soft angle — seasonal relevance, limited availability, or a specific offer
  Step 3 (Day 14): Close the loop gracefully — "no worries if timing isn't right, door is always open"

Use any prior relationship context to personalize. Reference real history naturally if relevant.
Return ONLY a JSON object with keys "subject" and "body". No markdown, no code fences."""

FOLLOWUP_USER = """Tone profile:
{tone}

{voice_section}{profile_section}This is follow-up #{step} for {name}.

Original outreach was sent {days_since_last} days ago.
Original subject: "{original_subject}"
Original message:
{original_body}

Write follow-up #{step} ({label}). Do not repeat the original message verbatim."""


# ── Core logic ────────────────────────────────────────────────────────────────

def days_since(dt) -> int:
    if not dt:
        return 0
    return (datetime.utcnow() - dt).days


def run(operator_id: int, limit: int = 20):
    print(f"\n[follow_up] operator={operator_id} limit={limit}")

    with get_db() as db:
        operator = db.query(Operator).filter_by(id=operator_id).first()
        if not operator:
            print(f"[follow_up] Operator {operator_id} not found")
            return

        op = {
            "id": operator.id,
            "tone_profile": operator.tone_profile,
            "voice_profiles": operator.voice_profiles,
        }

        # Find all customers in an active sequence step
        active_customers = (
            db.query(Customer)
            .filter(
                Customer.operator_id == operator_id,
                Customer.reactivation_status.in_(STATUS_TO_STEP.keys()),
            )
            .all()
        )

        # Serialize to avoid DetachedInstanceError
        candidates = []
        for c in active_customers:
            latest_log = (
                db.query(OutreachLog)
                .filter_by(customer_id=c.id, dry_run=False)
                .order_by(OutreachLog.sent_at.desc())
                .first()
            )
            if not latest_log:
                continue

            step = STATUS_TO_STEP[c.reactivation_status]
            required_days = SEQUENCE_STEPS[step]["days"]
            elapsed = days_since(latest_log.sent_at)

            if elapsed >= required_days:
                candidates.append({
                    "id": c.id,
                    "name": c.name,
                    "email": c.email,
                    "assigned_voice_id": c.assigned_voice_id,
                    "reactivation_status": c.reactivation_status,
                    "customer_profile": c.customer_profile,
                    "step": step,
                    "days_since_last": elapsed,
                    "last_log_id": latest_log.id,
                    "last_subject": latest_log.subject or "",
                    "last_body": latest_log.content or "",
                    "gmail_thread_id": latest_log.gmail_thread_id,
                })

    print(f"[follow_up] {len(candidates)} customers ready for follow-up")

    if not candidates:
        return

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    processed = 0

    for customer in candidates[:limit]:
        step_cfg = SEQUENCE_STEPS[customer["step"]]
        print(f"  → {customer['name']} — Step {customer['step']} ({step_cfg['label']}, "
              f"{customer['days_since_last']}d since last contact)")

        # Optionally fetch thread content for richer context
        thread_context = ""
        if GMAIL_AVAILABLE and customer.get("gmail_thread_id"):
            try:
                thread_msgs = get_thread(customer["gmail_thread_id"])
                if len(thread_msgs) > 1:
                    snippets = [f"[{m.get('from','?')}]: {(m.get('body') or '')[:200]}"
                                for m in thread_msgs[1:]]
                    thread_context = "\nPrior thread context:\n" + "\n---\n".join(snippets) + "\n"
            except Exception:
                pass

        profile = customer.get("customer_profile") or {}
        profile_section = format_profile_for_prompt(profile)
        if thread_context:
            profile_section += thread_context

        voice_id = customer.get("assigned_voice_id")
        profiles = op.get("voice_profiles") or []
        voice = next((p for p in profiles if p["id"] == voice_id), profiles[0] if profiles else None)
        voice_section = (
            f"Write in the voice of {voice['name']} ({voice.get('role', 'team member')}).\n\n"
            if voice else ""
        )
        tone = json.dumps(op.get("tone_profile") or {}, indent=2)

        try:
            from core.operator_config import get_agent_context
            try:
                _fu_ctx = get_agent_context(operator_id)
                _fu_system = _fu_ctx + "\n\n" + FOLLOWUP_SYSTEM
            except Exception:
                _fu_system = FOLLOWUP_SYSTEM

            message = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=600,
                system=_fu_system,
                messages=[{
                    "role": "user",
                    "content": FOLLOWUP_USER.format(
                        tone=tone,
                        voice_section=voice_section,
                        profile_section=profile_section,
                        step=customer["step"],
                        label=step_cfg["label"],
                        name=customer["name"],
                        days_since_last=customer["days_since_last"],
                        original_subject=customer["last_subject"],
                        original_body=customer["last_body"][:400],
                    ),
                }],
            )
            raw = message.content[0].text.strip()
            try:
                draft = json.loads(raw)
            except json.JSONDecodeError:
                draft = {"subject": f"Re: {customer['last_subject']}", "body": raw}

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
                    sequence_step=customer["step"],
                    gmail_thread_id=customer.get("gmail_thread_id"),
                )
                db.add(log)
                c = db.query(Customer).filter_by(id=customer["id"]).first()
                if c:
                    c.reactivation_status = step_cfg["status_out"]

            processed += 1

        except Exception as e:
            print(f"     ERROR: {e}")

    print(f"\n[follow_up] Done — {processed}/{len(candidates[:limit])} follow-ups queued")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Foreman follow-up agent")
    parser.add_argument("--operator-id", type=int, default=1)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    run(args.operator_id, args.limit)

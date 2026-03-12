"""
agents/conversation_agent.py
Context-Aware Conversation Response Generator.

Generates bespoke email drafts based on where a customer is in the
reactivation conversation. Every draft is informed by:
  - Operator tone profile + assigned voice
  - Full conversation thread history
  - Customer relationship profile (from Customer Analyzer)
  - Job history and financial data
  - Response classification (what the customer actually said)
  - Real calendar availability (for booking proposals)

Draft types (matched to response_classifier output):
  booking_intent    -> BookingProposalDraft: proposes 3 real available slots
  callback_request  -> CallbackAckDraft: warm acknowledgement + best call window
  price_inquiry     -> PriceResponseDraft: transparent estimate using job history
  unclear           -> ClarifyingDraft: gentle, open-ended clarification request
  (not_interested is handled by the classifier -- marks unsubscribed, no draft)

All drafts queue as dry_run=True in OutreachLog for operator review.
This agent NEVER sends email directly.

Usage:
    from agents.conversation_agent import generate_response
    log_id = generate_response(operator_id=1, customer_id=7, classification='booking_intent')
"""

import json
from datetime import datetime, timezone

import anthropic

from core.config import config
from core.database import get_db
from core.models import Customer, Job, Operator, OutreachLog
from agents.customer_analyzer import format_profile_for_prompt

try:
    from integrations.calendar import get_available_slots, format_slots_for_email
    CALENDAR_AVAILABLE = True
except Exception:
    CALENDAR_AVAILABLE = False

try:
    from integrations.gmail import get_thread
    GMAIL_AVAILABLE = True
except Exception:
    GMAIL_AVAILABLE = False


# -- Shared system prompt ------------------------------------------------------

AGENT_SYSTEM = """You are a ghostwriter for a small field service business owner.
Write an email reply in the owner's exact voice. Be brief, warm, and specific.

Rules:
- Match the operator's tone profile exactly -- use their characteristic phrases
- Reference the customer's actual history naturally when relevant
- Never be pushy or use sales language
- Keep it short: 3-6 sentences unless the situation demands more
- Return ONLY a JSON object with keys "subject" and "body" -- no markdown, no fences"""


# -- Per-classification prompt templates ---------------------------------------

BOOKING_PROPOSAL_PROMPT = """Operator tone:
{tone}

{voice_section}{profile_section}Customer: {name}
Service history: {service_summary}

The customer has indicated they want to book service. Here are the operator's
next available appointment slots:
{slot_text}

Full conversation so far:
{thread_text}

Most recent customer message:
{reply_text}

Write a warm, direct reply that:
1. Acknowledges their interest naturally (reference what they said)
2. Proposes the 3 available times clearly
3. Makes it easy for them to pick one
4. Mentions the service type if clear from context
5. Signs off in the operator's voice

Subject line should reference the service or be a natural reply continuation."""

PRICE_RESPONSE_PROMPT = """Operator tone:
{tone}

{voice_section}{profile_section}Customer: {name}
Service history: {service_summary}
Estimated job value for this customer: ${estimated_value:,.0f}

Full conversation so far:
{thread_text}

Most recent customer message (asking about price):
{reply_text}

Write a transparent, helpful reply that:
1. Acknowledges the question directly
2. Gives a realistic price range based on the service type (don't just say "it depends")
3. Mentions what's included or what affects the price
4. Ends with an easy next step (book a time or ask a follow-up)

Be honest and specific -- HVAC customers appreciate straight answers over vague hedging."""

CALLBACK_PROMPT = """Operator tone:
{tone}

{voice_section}{profile_section}Customer: {name}

Full conversation so far:
{thread_text}

Most recent customer message (requesting a call):
{reply_text}

Write a brief, warm reply that:
1. Confirms you'll call them
2. Asks what time of day works best (morning / afternoon)
3. If their phone number is visible in the message, confirm it back
4. Keeps it short -- they want to talk, not email

Operator phone: {operator_phone}"""

CLARIFYING_PROMPT = """Operator tone:
{tone}

{voice_section}{profile_section}Customer: {name}

Full conversation so far:
{thread_text}

Most recent customer message (unclear intent):
{reply_text}

Write a brief, friendly reply that:
1. Acknowledges their message warmly
2. Asks one clear question to understand what they need
3. Does NOT assume or project -- stay open-ended
4. Feels natural, not like a form letter"""


# -- Safe prompt formatter -----------------------------------------------------

def _fmt(template: str, **kwargs) -> str:
    """str.format() that pre-escapes curly braces in values so email content
    (which may contain {name}, CSS, etc.) never clashes with template slots."""
    safe = {k: str(v).replace("{", "{{").replace("}", "}}") for k, v in kwargs.items()}
    return template.format(**safe)


# -- Job history formatter -----------------------------------------------------

def _build_service_summary(jobs: list[dict]) -> str:
    if not jobs:
        return "No prior job history on file"
    lines = []
    for j in jobs[-5:]:  # last 5 jobs
        date = j.get("date", "")
        stype = j.get("service_type", "Service")
        amount = j.get("amount", 0)
        if date and hasattr(date, "strftime"):
            date = date.strftime("%b %Y")
        lines.append(f"  {date}: {stype} (${amount:,.0f})")
    total = sum(j.get("amount", 0) for j in jobs)
    return f"{len(jobs)} jobs, ${total:,.0f} total\n" + "\n".join(lines)


def _build_thread_text(thread_entries: list[dict]) -> str:
    if not thread_entries:
        return "No prior thread."
    lines = []
    for e in thread_entries[-8:]:
        direction = e.get("direction", "outbound").upper()
        date = e.get("sent_at", "")
        if date and hasattr(date, "strftime"):
            date = date.strftime("%b %-d")
        content = (e.get("content") or "")[:400]
        lines.append(f"[{direction} {date}]:\n{content}")
    return "\n\n---\n\n".join(lines)


# -- Main entry point ----------------------------------------------------------

def generate_response(
    operator_id: int,
    customer_id: int,
    classification: str,
    inbound_log_id: int = None,
    verbose: bool = True,
) -> int | None:
    """
    Generate a context-rich draft reply and queue it for operator review.

    Returns the OutreachLog.id of the queued draft, or None on failure.
    """
    if classification == "not_interested":
        if verbose:
            print(f"  [conversation_agent] Skipping draft -- customer marked not_interested")
        return None

    # -- Load all context ------------------------------------------------------
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=operator_id).first()
        customer = db.query(Customer).filter_by(id=customer_id).first()

        if not operator or not customer:
            print(f"  [conversation_agent] Operator or customer not found")
            return None

        jobs = (
            db.query(Job)
            .filter_by(customer_id=customer_id)
            .order_by(Job.completed_at)
            .all()
        )

        prior_logs = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == operator_id,
                OutreachLog.dry_run == False,
            )
            .order_by(OutreachLog.sent_at)
            .all()
        )

        # Serialize everything
        op_tone = json.dumps(operator.tone_profile or {}, indent=2)
        op_phone = operator.phone or ""
        voice_profiles = operator.voice_profiles or []
        assigned_voice_id = customer.assigned_voice_id

        cust_name = customer.name
        cust_email = customer.email
        estimated_value = customer.estimated_job_value or 0.0
        customer_profile = customer.customer_profile or {}
        gmail_thread_id = customer.gmail_thread_id if hasattr(customer, "gmail_thread_id") else None

        # Get thread_id from the most recent outbound log
        outbound_logs = [l for l in prior_logs if l.direction == "outbound"]
        if outbound_logs:
            gmail_thread_id = outbound_logs[-1].gmail_thread_id

        job_list = [
            {
                "date": j.completed_at,
                "service_type": j.service_type,
                "amount": j.amount or 0.0,
            }
            for j in jobs
        ]

        thread_entries = [
            {
                "direction": l.direction,
                "sent_at": l.sent_at,
                "content": l.content or "",
                "subject": l.subject or "",
            }
            for l in prior_logs
        ]

        inbound_reply_text = ""
        if inbound_log_id:
            inbound_log = db.query(OutreachLog).filter_by(id=inbound_log_id).first()
            if inbound_log:
                inbound_reply_text = inbound_log.content or ""

        last_outbound_subject = (
            outbound_logs[-1].subject if outbound_logs else f"Re: {cust_name}"
        )

    # -- Optionally enrich thread from Gmail -----------------------------------
    if GMAIL_AVAILABLE and gmail_thread_id and len(thread_entries) < 3:
        try:
            gmail_thread = get_thread(gmail_thread_id)
            for msg in gmail_thread:
                body = (msg.get("body") or "")[:400]
                if body and not any(
                    e.get("content", "")[:100] in body for e in thread_entries
                ):
                    thread_entries.append({
                        "direction": "inbound" if msg.get("is_inbound") else "outbound",
                        "sent_at": msg.get("sent_at"),
                        "content": body,
                        "subject": msg.get("subject", ""),
                    })
        except Exception as e:
            if verbose:
                print(f"  [conversation_agent] Gmail thread fetch: {e}")

    # -- Resolve voice profile -------------------------------------------------
    voice = next(
        (p for p in voice_profiles if p.get("id") == assigned_voice_id),
        voice_profiles[0] if voice_profiles else None,
    )
    voice_section = (
        f"Write in the voice of {voice['name']} ({voice.get('role', 'team member')}).\n\n"
        if voice else ""
    )

    # -- Build shared context strings ------------------------------------------
    profile_section = format_profile_for_prompt(
        customer_profile if isinstance(customer_profile, dict) else {}
    )
    service_summary = _build_service_summary(job_list)
    thread_text = _build_thread_text(thread_entries)

    # -- Get calendar slots for booking proposals ------------------------------
    slots = []
    if classification == "booking_intent" and CALENDAR_AVAILABLE:
        try:
            slots = get_available_slots(days_ahead=10, duration_minutes=90)
            if verbose:
                print(f"  [conversation_agent] Found {len(slots)} available slots")
        except Exception as e:
            if verbose:
                print(f"  [conversation_agent] Calendar unavailable: {e}")

    # -- Select and fill prompt ------------------------------------------------
    if classification == "booking_intent":
        slot_text = format_slots_for_email(slots) if slots else (
            "I don't have my calendar handy -- please ask for their preferred times."
        )
        user_prompt = _fmt(
            BOOKING_PROPOSAL_PROMPT,
            tone=op_tone,
            voice_section=voice_section,
            profile_section=profile_section,
            name=cust_name,
            service_summary=service_summary,
            slot_text=slot_text,
            thread_text=thread_text,
            reply_text=inbound_reply_text or "(see thread above)",
        )
    elif classification == "price_inquiry":
        user_prompt = _fmt(
            PRICE_RESPONSE_PROMPT,
            tone=op_tone,
            voice_section=voice_section,
            profile_section=profile_section,
            name=cust_name,
            service_summary=service_summary,
            estimated_value=estimated_value,
            thread_text=thread_text,
            reply_text=inbound_reply_text or "(see thread above)",
        )
    elif classification == "callback_request":
        user_prompt = _fmt(
            CALLBACK_PROMPT,
            tone=op_tone,
            voice_section=voice_section,
            profile_section=profile_section,
            name=cust_name,
            thread_text=thread_text,
            reply_text=inbound_reply_text or "(see thread above)",
            operator_phone=op_phone,
        )
    else:  # unclear
        user_prompt = _fmt(
            CLARIFYING_PROMPT,
            tone=op_tone,
            voice_section=voice_section,
            profile_section=profile_section,
            name=cust_name,
            thread_text=thread_text,
            reply_text=inbound_reply_text or "(see thread above)",
        )

    # -- Generate draft --------------------------------------------------------
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    if verbose:
        print(f"  [conversation_agent] Drafting {classification} response for {cust_name}")

    try:
        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=700,
            system=AGENT_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text.strip()
        try:
            draft = json.loads(raw)
        except json.JSONDecodeError:
            draft = {"subject": f"Re: {last_outbound_subject}", "body": raw}

    except Exception as e:
        if verbose:
            print(f"  [conversation_agent] Draft error: {e}")
        return None

    # -- Queue the draft -------------------------------------------------------
    with get_db() as db:
        new_log = OutreachLog(
            operator_id=operator_id,
            customer_id=customer_id,
            channel="email",
            direction="outbound",
            subject=draft.get("subject", f"Re: {last_outbound_subject}"),
            content=draft.get("body", ""),
            dry_run=True,
            sequence_step=0,
            gmail_thread_id=gmail_thread_id,
            response_classification=classification,
        )
        db.add(new_log)
        db.flush()
        draft_id = new_log.id

    if verbose:
        print(f"  [conversation_agent] Draft queued (log_id={draft_id}): {draft.get('subject', '')}")

    return draft_id

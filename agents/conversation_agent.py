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
  booking_intent    -> ConversationalReply: proposes 2-3 available day windows in the email body (Outreach Queue)
  booking_confirmed -> BookingConfirmationDraft: confirms the agreed slot (Meetings Queue)
  callback_request  -> CallbackAckDraft: warm acknowledgement + best call window
  price_inquiry     -> PriceResponseDraft: transparent estimate using job history
  not_interested    -> ConversationalDraft: answers their question, respects their position
  unclear           -> ClarifyingDraft: answers any question, gently surfaces what they need
  (unsubscribe_request → no draft generated)

All drafts queue as dry_run=True in OutreachLog for operator review.
This agent NEVER sends email directly.

Usage:
    from agents.conversation_agent import generate_response
    log_id = generate_response(operator_id=1, customer_id=7, classification='booking_intent')
"""

import json
from datetime import datetime, timedelta, timezone

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
Write an email reply in the owner's exact voice. Be brief, warm, and genuinely personal.

Rules:
- Match the operator's tone profile exactly -- use their characteristic phrases
- Read the FULL conversation thread before drafting. Respond to where the customer is NOW,
  not where they were in an earlier message. People change their minds -- follow their lead.
- If they asked a question, answer it directly -- don't dodge it or pivot away
- If they declined something in their CURRENT message, respect it. Do not re-propose the
  same thing in different words in the same reply.
- If a customer previously declined something (e.g. a call) but their CURRENT message
  asks for it, grant the request. Their current ask overrides their earlier position.
- Never be pushy, salesy, or follow a script. Sound like a real person, not a funnel step
- Keep it short: 2-5 sentences unless the situation genuinely demands more
- Sign off with the name on its own line (e.g. "Best,\nArjuna" not "Best, Arjuna")
- Return ONLY a JSON object with keys "subject" and "body" -- no markdown, no fences"""


# -- Per-classification prompt templates ---------------------------------------

BOOKING_PROPOSAL_PROMPT = """Operator tone:
{tone}

{voice_section}{profile_section}Customer: {name}
Service history: {service_summary}

The customer wants to schedule service. Propose 2-3 available day windows naturally in your reply.
Operator's upcoming available days/windows:
{slot_text}

Full conversation so far:
{thread_text}

Most recent customer message:
{reply_text}

Write a warm, conversational reply that:
1. Answers any question the customer asked (be direct — don't dodge)
2. Proposes 2-3 available day windows naturally in the email body
   (e.g. "I have availability Tuesday or Thursday afternoon — would either of those work for you?")
   Use real availability from the list above. Do NOT list specific times or use a formal slot format.
3. Keeps it brief -- 2-4 sentences max

This is a regular reply email, not a formal invite. Subject should be a natural continuation."""

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
2. Gives a realistic price range based on the service type -- do not just say "it depends."
   If a firm number requires diagnosis, say so AND still give a rough ballpark range.
3. If you need more info to give an accurate number, ask one specific question about the
   problem, AND offer a range based on what it typically ends up being
4. Offer a natural easy next step: could be talking live, swinging by for a quick look, or
   booking a time -- don't push hard, just make the option available
5. Keep it brief and honest -- customers appreciate a straight answer over vague hedging

If the customer has already pushed back on a specific option (like a call) in a prior message,
don't re-propose it. Offer an alternative instead."""

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

NOT_INTERESTED_PROMPT = """Operator tone:
{tone}

{voice_section}{profile_section}Customer: {name}
Service history: {service_summary}

Full conversation so far:
{thread_text}

Most recent customer message (they declined or aren't ready, but may have a question):
{reply_text}

The customer is not ready or declined something in a prior message. Read what they said now:
- If they asked a specific question, answer it directly and helpfully -- this is the most
  important thing. Don't dodge it or pivot to a sales pitch.
- If they asked for a quote or pricing, give a realistic range. Don't just say "it depends."
  Offer to discuss more or come take a look if a precise number requires a site visit.
- If they raised a concern, address it honestly.
- If they didn't ask anything, just keep the door open briefly and warmly.
- Only propose a call, visit, or times if they explicitly asked for one in their current message.

Sound like a real person who cares about helping, not a salesperson working a pipeline."""

CLARIFYING_PROMPT = """Operator tone:
{tone}

{voice_section}{profile_section}Customer: {name}
Service history: {service_summary}

Full conversation so far:
{thread_text}

Most recent customer message:
{reply_text}

Their message is a bit ambiguous. Read it carefully:
- If they asked a question, answer it directly first
- If the context makes their need fairly clear, address it
- If you genuinely can't tell what they need, ask one specific question -- not a generic "how can I help"

Write a brief, natural reply. Sound like a real person. Do not propose booking times unless
they specifically asked for them."""

CALENDAR_DECLINED_PROMPT = """Operator tone:
{tone}

{voice_section}{profile_section}Customer: {name}
Service history: {service_summary}

The customer declined the calendar invite for their appointment.

Full conversation so far:
{thread_text}

Write a brief, warm reply that:
1. Acknowledges no problem at all — no pressure, completely relaxed tone
2. Asks if there's a day or time that would work better for them — suggest 2 options as flexible
   ranges (e.g. "sometime next week", "a morning or afternoon") NOT hard specific times
3. Keeps the door open without being pushy — they may have simply had a schedule change
4. 2-3 sentences max — keep it genuinely casual

Do NOT propose specific times or slots. Keep it open and easy."""

BOOKING_CONFIRMATION_PROMPT = """Operator tone:
{tone}

{voice_section}Customer: {name}
Service history: {service_summary}

The customer has confirmed their appointment:
Date/Time: {confirmed_time}
Service: {service_type}

Full conversation so far:
{thread_text}

Customer's confirmation message:
{reply_text}

Write a brief, warm confirmation email that:
1. Confirms the appointment date and time clearly
2. Mentions you'll send them a calendar invite
3. Includes one practical note relevant to the service (e.g. "please make sure the unit is accessible")
4. Signs off warmly

Keep it 3-4 sentences. They've agreed; just confirm and close warmly."""

DATETIME_EXTRACTOR_SYSTEM = """Extract appointment details from a customer's email reply.
Today is {today_weekday}, {today}.

Return ONLY a JSON object — no markdown:
{{
  "slot_start": "YYYY-MM-DDTHH:MM:SS",
  "slot_end": "YYYY-MM-DDTHH:MM:SS",
  "service_type": "string or null",
  "confidence": "high|medium|low"
}}

Rules:
- Convert relative references to absolute dates. Use today's day-of-week to count forward correctly:
  "this Tuesday" or "Tuesday" (when said mid-week) = the coming Tuesday
  "next Tuesday" = the very next Tuesday from today, even if that is only a few days away
  "the 18th" = the 18th of the current or next month, whichever is upcoming
- Do NOT add extra days. If the customer says Tuesday, the slot_start must fall on a Tuesday.
  Double-check: verify that the date you output actually falls on the stated day of the week.
- Assume Eastern time / standard business context
- slot_end = slot_start + 90 minutes if not specified
- "afternoon" = 2:00 PM if no specific time; "morning" = 9:00 AM; "evening" = 5:00 PM
- service_type: pull from conversation context (e.g. "AC tune-up", "HVAC maintenance") or null"""


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


# -- Datetime extractor --------------------------------------------------------

def _extract_confirmed_datetime(reply_text: str, thread_text: str) -> dict:
    """
    Use Claude to extract a confirmed appointment datetime from a customer reply.
    Returns {"slot_start": datetime|None, "slot_end": datetime|None, "service_type": str|None}.
    """
    from datetime import date
    today_dt = date.today()
    today_str = today_dt.isoformat()
    today_weekday = today_dt.strftime("%A")  # e.g. "Friday"

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=200,
            system=DATETIME_EXTRACTOR_SYSTEM.format(today=today_str, today_weekday=today_weekday),
            messages=[{
                "role": "user",
                "content": (
                    f"Thread context (for reference):\n{thread_text}\n\n"
                    f"Customer's confirmation reply:\n{reply_text}"
                ),
            }],
        )
        result = json.loads(msg.content[0].text.strip())
        slot_start = None
        slot_end = None
        if result.get("slot_start"):
            slot_start = datetime.fromisoformat(result["slot_start"])
        if result.get("slot_end"):
            slot_end = datetime.fromisoformat(result["slot_end"])
        elif slot_start:
            slot_end = slot_start + timedelta(minutes=90)
        return {
            "slot_start": slot_start,
            "slot_end": slot_end,
            "service_type": result.get("service_type"),
        }
    except Exception as e:
        print(f"  [conversation_agent] datetime extraction failed: {e}")
        return {"slot_start": None, "slot_end": None, "service_type": None}


# -- Booking confirmation handler ----------------------------------------------

def _generate_booking_confirmation(
    operator_id: int,
    customer_id: int,
    inbound_log_id: int | None,
    verbose: bool,
) -> int | None:
    """
    Handle booking_confirmed classification:
    1. Extract confirmed datetime from the customer's reply using Claude.
    2. Generate a confirmation email draft.
    3. Queue it to the Meetings Queue (dry_run=True, response_classification='booking_confirmed').
    4. Store booking_slot_start/end on the draft so the Meetings Queue can pre-fill the form.
    """
    with get_db() as db:
        operator = db.query(Operator).filter_by(id=operator_id).first()
        customer = db.query(Customer).filter_by(id=customer_id).first()
        if not operator or not customer:
            return None

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
        jobs = (
            db.query(Job)
            .filter_by(customer_id=customer_id)
            .order_by(Job.completed_at)
            .all()
        )

        op_tone = json.dumps(operator.tone_profile or {}, indent=2)
        voice_profiles = operator.voice_profiles or []
        assigned_voice_id = customer.assigned_voice_id
        cust_name = customer.name
        last_service_type = customer.last_service_type or "HVAC service"

        outbound_logs = [l for l in prior_logs if l.direction == "outbound"]
        gmail_thread_id = outbound_logs[-1].gmail_thread_id if outbound_logs else None
        last_outbound_subject = outbound_logs[-1].subject if outbound_logs else f"Re: {cust_name}"

        job_list = [{"date": j.completed_at, "service_type": j.service_type, "amount": j.amount or 0.0} for j in jobs]
        thread_entries = [
            {"direction": l.direction, "sent_at": l.sent_at, "content": l.content or "", "subject": l.subject or ""}
            for l in prior_logs
        ]

        inbound_reply_text = ""
        if inbound_log_id:
            inbound_log = db.query(OutreachLog).filter_by(id=inbound_log_id).first()
            if inbound_log:
                inbound_reply_text = inbound_log.content or ""

    voice = next((p for p in voice_profiles if p.get("id") == assigned_voice_id),
                 voice_profiles[0] if voice_profiles else None)
    voice_section = (
        f"Write in the voice of {voice['name']} ({voice.get('role', 'team member')}).\n\n"
        if voice else ""
    )
    service_summary = _build_service_summary(job_list)
    thread_text = _build_thread_text(thread_entries)

    # Extract the confirmed datetime from the customer's reply
    extracted = _extract_confirmed_datetime(inbound_reply_text, thread_text)
    slot_start = extracted["slot_start"]
    slot_end = extracted["slot_end"]
    service_type = extracted["service_type"] or last_service_type

    confirmed_time = (
        slot_start.strftime("%A, %B %-d at %-I:%M %p")
        if slot_start else "a time to be confirmed"
    )

    if verbose:
        print(f"  [conversation_agent] booking_confirmed — extracted slot: {confirmed_time}")

    # Generate confirmation email draft
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        from core.operator_config import get_agent_context
        _conf_agent_ctx = get_agent_context(operator_id)
        _conf_system = _conf_agent_ctx + "\n\n" + AGENT_SYSTEM
    except Exception:
        _conf_system = AGENT_SYSTEM

    try:
        user_prompt = _fmt(
            BOOKING_CONFIRMATION_PROMPT,
            tone=op_tone,
            voice_section=voice_section,
            name=cust_name,
            service_summary=service_summary,
            confirmed_time=confirmed_time,
            service_type=service_type,
            thread_text=thread_text,
            reply_text=inbound_reply_text or "(see thread above)",
        )
        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=500,
            system=_conf_system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text.strip()
        try:
            draft = json.loads(raw)
        except json.JSONDecodeError:
            draft = {"subject": f"Re: {last_outbound_subject}", "body": raw}
    except Exception as e:
        if verbose:
            print(f"  [conversation_agent] Confirmation draft error: {e}")
        return None

    # Queue the draft with booking slot times stored for Meetings Queue pre-fill
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
            response_classification="booking_confirmed",
            booking_slot_start=slot_start,
            booking_slot_end=slot_end,
        )
        db.add(new_log)
        db.flush()
        draft_id = new_log.id

    if verbose:
        print(f"  [conversation_agent] Booking confirmation draft queued (log_id={draft_id})")

    return draft_id


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
    if classification in ("unsubscribe_request", "calendar_accepted"):
        if verbose:
            print(f"  [conversation_agent] Skipping draft -- {classification}")
        return None

    if classification == "booking_confirmed":
        return _generate_booking_confirmation(operator_id, customer_id, inbound_log_id, verbose)


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
        try:
            estimated_value = float(customer.estimated_job_value or 0) or 0.0
        except (TypeError, ValueError):
            estimated_value = 0.0
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
    elif classification == "not_interested":
        user_prompt = _fmt(
            NOT_INTERESTED_PROMPT,
            tone=op_tone,
            voice_section=voice_section,
            profile_section=profile_section,
            name=cust_name,
            service_summary=service_summary,
            thread_text=thread_text,
            reply_text=inbound_reply_text or "(see thread above)",
        )
    elif classification == "calendar_declined":
        user_prompt = _fmt(
            CALENDAR_DECLINED_PROMPT,
            tone=op_tone,
            voice_section=voice_section,
            profile_section=profile_section,
            name=cust_name,
            service_summary=service_summary,
            thread_text=thread_text,
        )
    else:  # unclear
        user_prompt = _fmt(
            CLARIFYING_PROMPT,
            tone=op_tone,
            voice_section=voice_section,
            profile_section=profile_section,
            name=cust_name,
            service_summary=service_summary,
            thread_text=thread_text,
            reply_text=inbound_reply_text or "(see thread above)",
        )

    # -- Generate draft --------------------------------------------------------
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    if verbose:
        print(f"  [conversation_agent] Drafting {classification} response for {cust_name}")

    try:
        from core.operator_config import get_agent_context
        agent_ctx = get_agent_context(operator_id)
        system_prompt = agent_ctx + "\n\n" + AGENT_SYSTEM
    except Exception:
        system_prompt = AGENT_SYSTEM

    try:
        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=700,
            system=system_prompt,
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

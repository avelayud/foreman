"""
agents/response_classifier.py
Response Classification Agent.

Reads an inbound customer reply in full context (thread history, customer
profile, job history) and classifies it into one of five categories.

Categories:
  booking_intent    — customer wants to schedule service
  callback_request  — customer prefers a phone call
  price_inquiry     — customer is asking about pricing or cost
  not_interested    — customer declines, opts out, or says timing is wrong
  unclear           — ambiguous — surface to operator for review

The classification is stored on OutreachLog.response_classification and
drives what happens next in the pipeline.

Usage:
    from agents.response_classifier import classify_reply
    result = classify_reply(operator_id=1, inbound_log_id=42)
"""

import json
from datetime import datetime, timezone

import anthropic

from core.config import config
from core.database import get_db
from core.models import Customer, Operator, OutreachLog


CLASSIFIER_SYSTEM = """You are an expert at reading customer replies to service business outreach.

Your job: classify a customer's reply into exactly one category.

Categories:
  booking_confirmed — The customer has explicitly agreed to a SPECIFIC proposed time slot.
                      Only use this when a concrete date/time was already proposed and the
                      customer is accepting it. Signals: "Tuesday works for me", "I'll take
                      the 10am slot", "that time works", "perfect, see you then",
                      "confirmed, see you Tuesday"
  booking_intent    — The customer clearly wants to book but hasn't confirmed a specific slot.
                      Signals: "yes", "when can you come?", "book me in", "let's do it",
                      asking for dates/times, saying "I need this done", or a general yes
                      without referring to a specific proposed slot
  callback_request  — Customer wants a phone call before deciding or to discuss details.
                      Signals: "call me", "give me a ring", "easier to talk", phone number given
  price_inquiry     — Customer is asking about cost, pricing, or value before committing.
                      Signals: "how much", "what's the cost", "do you have a quote", "is it expensive"
  not_interested    — Customer declines, is not ready, or asks to be removed.
                      Signals: "not right now", "remove me", "already handled", "not interested",
                      "maybe later" (when combined with no engagement signal)
  unclear           — Reply is ambiguous, too short to classify, or could be multiple categories.

Return ONLY a JSON object — no markdown, no explanation:
{
  "classification": "<one of the six categories>",
  "confidence": "<high|medium|low>",
  "reasoning": "<one sentence explaining why>",
  "key_phrase": "<the exact phrase from their reply that drove the classification>"
}"""

CLASSIFIER_USER = """Classify this customer reply.

CUSTOMER: {name}
SERVICE HISTORY: {service_summary}
PRIOR OUTREACH CONTEXT: {outreach_summary}

PRIOR CONVERSATION:
{thread_text}

CUSTOMER'S REPLY:
{reply_text}

Classify the reply above."""


def classify_reply(operator_id: int, inbound_log_id: int, verbose: bool = True) -> dict:
    """
    Classify an inbound OutreachLog entry. Stores result on the log and returns it.

    Returns dict: {classification, confidence, reasoning, key_phrase}
    """
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=inbound_log_id).first()
        if not log or log.direction != "inbound":
            raise ValueError(f"Log {inbound_log_id} not found or not inbound")

        customer = db.query(Customer).filter_by(id=log.customer_id).first()
        if not customer:
            raise ValueError(f"Customer not found for log {inbound_log_id}")

        # Gather all outbound logs in this conversation for context
        prior_logs = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.customer_id == log.customer_id,
                OutreachLog.operator_id == operator_id,
                OutreachLog.dry_run == False,
                OutreachLog.id != inbound_log_id,
            )
            .order_by(OutreachLog.sent_at)
            .all()
        )

        # Serialize everything before session closes
        reply_text = log.content or ""
        customer_name = customer.name
        total_jobs = customer.total_jobs or 0
        total_spend = customer.total_spend or 0.0
        last_service_type = customer.last_service_type or "HVAC service"

        thread_entries = [
            {
                "direction": l.direction,
                "sent_at": l.sent_at.strftime("%b %-d") if l.sent_at else "",
                "content": (l.content or "")[:300],
            }
            for l in prior_logs
        ]

    # Build context strings
    service_summary = (
        f"{total_jobs} prior job(s), ${total_spend:,.0f} total spend, "
        f"most recent: {last_service_type}"
    )

    outreach_summary = (
        f"{sum(1 for e in thread_entries if e['direction'] == 'outbound')} outbound messages sent"
    )

    thread_text = "\n\n".join(
        f"[{e['direction'].upper()} {e['sent_at']}]: {e['content']}"
        for e in thread_entries[-6:]  # last 6 messages for context
    ) or "No prior thread."

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    try:
        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=256,
            system=CLASSIFIER_SYSTEM,
            messages=[{
                "role": "user",
                "content": CLASSIFIER_USER.format(
                    name=customer_name,
                    service_summary=service_summary,
                    outreach_summary=outreach_summary,
                    thread_text=thread_text,
                    reply_text=reply_text,
                ),
            }],
        )
        result = json.loads(message.content[0].text.strip())
    except json.JSONDecodeError:
        result = {
            "classification": "unclear",
            "confidence": "low",
            "reasoning": "Could not parse classifier output",
            "key_phrase": "",
        }
    except Exception as e:
        if verbose:
            print(f"  [classifier] Error: {e}")
        result = {
            "classification": "unclear",
            "confidence": "low",
            "reasoning": str(e),
            "key_phrase": "",
        }

    # Store on the log
    with get_db() as db:
        log = db.query(OutreachLog).filter_by(id=inbound_log_id).first()
        if log:
            log.response_classification = result["classification"]
            log.classified_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # Note: we intentionally do NOT auto-unsubscribe on "not_interested".
            # A decline is not the same as an unsubscribe request — the customer
            # may still have questions or become interested later.
            # The operator can manually close the conversation from the conversation page.

    if verbose:
        print(
            f"  [classifier] {customer_name}: {result['classification']} "
            f"({result['confidence']}) — \"{result.get('key_phrase', '')[:60]}\""
        )

    return result

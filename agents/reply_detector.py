"""
agents/reply_detector.py
Reply Detection Agent.

Polls Gmail inbox using stored thread IDs to detect customer replies.
When a reply is found:
  1. Logs it as an inbound OutreachLog entry
  2. Runs the CustomerAnalyzer to update the customer profile with reply context
  3. Updates customer.reactivation_status → 'replied'

Uses exact thread_id matching — no fuzzy email address guessing.
Only checks threads for customers currently in an active outreach sequence.

Usage:
    python -m agents.reply_detector --operator-id 1
    # Runs continuously every 30 min:
    python -m agents.reply_detector --operator-id 1 --watch
"""

import argparse
import time
from datetime import datetime

from core.config import config
from core.database import get_db
from core.models import Customer, OutreachLog

try:
    from integrations.gmail import get_inbox_replies
    GMAIL_AVAILABLE = True
except Exception:
    GMAIL_AVAILABLE = False


ACTIVE_STATUSES = {"outreach_sent", "sequence_step_2", "sequence_step_3"}


def run(operator_id: int) -> int:
    """
    Check all active outreach threads for replies.
    Returns the number of new replies detected.
    """
    if not GMAIL_AVAILABLE:
        print("[reply_detector] Gmail not available — skipping")
        return 0

    print(f"\n[reply_detector] operator={operator_id} — checking for replies")

    # Fetch all sent outreach logs with a gmail_thread_id for active customers
    with get_db() as db:
        rows = (
            db.query(OutreachLog, Customer)
            .join(Customer, OutreachLog.customer_id == Customer.id)
            .filter(
                OutreachLog.operator_id == operator_id,
                OutreachLog.dry_run == False,
                OutreachLog.gmail_thread_id != None,
                Customer.reactivation_status.in_(ACTIVE_STATUSES),
            )
            .all()
        )
        thread_map = {
            log.gmail_thread_id: {
                "log_id": log.id,
                "customer_id": customer.id,
                "customer_name": customer.name,
                "customer_email": customer.email,
            }
            for log, customer in rows
            if log.gmail_thread_id
        }

    if not thread_map:
        print("[reply_detector] No active threads to check")
        return 0

    print(f"[reply_detector] Checking {len(thread_map)} active threads")

    # Check Gmail for replies in each thread
    try:
        replies_by_thread = get_inbox_replies(list(thread_map.keys()))
    except Exception as e:
        print(f"[reply_detector] Gmail error: {e}")
        return 0

    new_replies = 0
    for thread_id, reply_messages in replies_by_thread.items():
        ctx = thread_map[thread_id]
        customer_id = ctx["customer_id"]
        customer_name = ctx["customer_name"]

        # Check if we've already logged this reply
        with get_db() as db:
            already_logged = db.query(OutreachLog).filter_by(
                customer_id=customer_id,
                direction="inbound",
            ).first()

        if already_logged:
            continue

        # Use the most recent inbound message
        reply = reply_messages[-1]
        reply_body = reply.get("body", "")
        reply_subject = reply.get("subject", "Re: outreach")
        reply_from = reply.get("from", "")
        sent_at = reply.get("sent_at") or datetime.utcnow()

        print(f"  → Reply detected from {customer_name}: {reply_subject[:60]}")

        # Log the inbound reply
        with get_db() as db:
            log = OutreachLog(
                operator_id=operator_id,
                customer_id=customer_id,
                channel="email",
                direction="inbound",
                subject=reply_subject,
                content=reply_body,
                sent_at=sent_at,
                dry_run=False,
                sequence_step=0,
                gmail_thread_id=thread_id,
                # Store the RFC 2822 Message-ID so future replies can set
                # In-Reply-To to THIS message — ensuring the recipient's email
                # client threads our response under their sent reply.
                rfc_message_id=reply.get("rfc_message_id") or "",
            )
            db.add(log)
            customer = db.query(Customer).filter_by(id=customer_id).first()
            if customer:
                customer.reactivation_status = "replied"

        # Update customer profile with reply context
        try:
            from agents.customer_analyzer import analyze_customer
            analyze_customer(operator_id, customer_id, verbose=False)
        except Exception as e:
            print(f"  [reply_detector] Profile update failed: {e}")

        # Classify the reply
        classification = "unclear"
        try:
            from agents.response_classifier import classify_reply
            with get_db() as _db:
                inbound_log = _db.query(OutreachLog).filter_by(
                    customer_id=customer_id, direction="inbound"
                ).order_by(OutreachLog.created_at.desc()).first()
                inbound_log_id = inbound_log.id if inbound_log else None
            if inbound_log_id:
                result = classify_reply(operator_id, inbound_log_id, verbose=True)
                classification = result.get("classification", "unclear")
        except Exception as e:
            print(f"  [reply_detector] Classification failed: {e}")

        # Generate bespoke response draft (skip if not_interested)
        if classification != "not_interested":
            try:
                from agents.conversation_agent import generate_response
                generate_response(
                    operator_id=operator_id,
                    customer_id=customer_id,
                    classification=classification,
                    inbound_log_id=inbound_log_id,
                    verbose=True,
                )
            except Exception as e:
                print(f"  [reply_detector] Response generation failed: {e}")

        new_replies += 1

    print(f"[reply_detector] Done — {new_replies} new replies detected")
    return new_replies


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Foreman reply detector")
    parser.add_argument("--operator-id", type=int, default=1)
    parser.add_argument("--watch", action="store_true",
                        help="Run continuously, checking every 30 minutes")
    parser.add_argument("--interval", type=int, default=30,
                        help="Poll interval in minutes (default: 30)")
    args = parser.parse_args()

    if args.watch:
        print(f"[reply_detector] Watching — checking every {args.interval} minutes")
        while True:
            run(args.operator_id)
            time.sleep(args.interval * 60)
    else:
        run(args.operator_id)

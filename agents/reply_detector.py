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
    from integrations.gmail import get_inbox_replies, search_inbox_by_sender
    GMAIL_AVAILABLE = True
except Exception:
    GMAIL_AVAILABLE = False


# Statuses that indicate an active outreach sequence — used for thread-based scan.
ACTIVE_STATUSES = {"outreach_sent", "sequence_step_2", "sequence_step_3", "replied"}

# Broader set used for the email-address fallback scan (catches orphaned threads).
SCAN_STATUSES = {"outreach_sent", "sequence_step_2", "sequence_step_3", "replied", "booked"}


def _already_logged_rfc_ids(customer_id: int) -> set[str]:
    """Return the set of rfc_message_ids already logged as inbound for this customer."""
    with get_db() as db:
        rows = (
            db.query(OutreachLog.rfc_message_id, OutreachLog.gmail_thread_id)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.direction == "inbound",
            )
            .all()
        )
        # Include non-empty rfc_message_ids AND gmail_thread_ids for dedup
        ids = set()
        for rfc_id, thread_id in rows:
            if rfc_id:
                ids.add(rfc_id)
            if thread_id:
                ids.add(f"thread:{thread_id}")
        return ids


def _log_and_process_reply(operator_id: int, customer_id: int, customer_name: str,
                            reply: dict, thread_id: str) -> bool:
    """
    Log a single inbound reply, run profile update, classify, and generate draft.
    Returns True if the reply was newly logged, False if it was a duplicate.
    """
    rfc_id = reply.get("rfc_message_id") or ""
    already = _already_logged_rfc_ids(customer_id)
    # Dedup: skip if this RFC Message-ID or thread-reply combo already logged
    if rfc_id and rfc_id in already:
        return False
    if f"thread:{thread_id}" in already and not rfc_id:
        # No RFC ID to distinguish — fall back to thread-level dedup
        return False

    reply_body = reply.get("body", "")
    reply_subject = reply.get("subject", "Re: outreach")
    sent_at = reply.get("sent_at") or datetime.utcnow()

    print(f"  → Reply detected from {customer_name}: {reply_subject[:60]}")

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
            rfc_message_id=rfc_id,
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
    inbound_log_id = None
    try:
        from agents.response_classifier import classify_reply
        with get_db() as _db:
            inbound_log = (
                _db.query(OutreachLog)
                .filter_by(customer_id=customer_id, direction="inbound")
                .order_by(OutreachLog.created_at.desc())
                .first()
            )
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

    return True


def run(operator_id: int) -> int:
    """
    Check all active outreach threads for replies.
    Also scans inbox by email address as a fallback for orphaned threads
    (e.g. replies that landed in a new thread due to client threading differences).
    Returns the number of new replies detected.
    """
    if not GMAIL_AVAILABLE:
        print("[reply_detector] Gmail not available — skipping")
        return 0

    print(f"\n[reply_detector] operator={operator_id} — checking for replies")
    new_replies = 0

    # ── Pass 1: Thread-based scan (primary) ──────────────────────────────────
    # Check each known gmail_thread_id for INBOX messages (fast, exact).
    with get_db() as db:
        rows = (
            db.query(OutreachLog, Customer)
            .join(Customer, OutreachLog.customer_id == Customer.id)
            .filter(
                OutreachLog.operator_id == operator_id,
                OutreachLog.dry_run == False,
                OutreachLog.gmail_thread_id != None,
                OutreachLog.direction == "outbound",
                Customer.reactivation_status.in_(ACTIVE_STATUSES),
            )
            .all()
        )
        thread_map = {
            log.gmail_thread_id: {
                "customer_id": customer.id,
                "customer_name": customer.name,
                "customer_email": customer.email,
            }
            for log, customer in rows
            if log.gmail_thread_id
        }

    if thread_map:
        print(f"[reply_detector] Pass 1: checking {len(thread_map)} tracked threads")
        try:
            replies_by_thread = get_inbox_replies(list(thread_map.keys()))
        except Exception as e:
            print(f"[reply_detector] Gmail error in Pass 1: {e}")
            replies_by_thread = {}

        for thread_id, reply_messages in replies_by_thread.items():
            ctx = thread_map[thread_id]
            reply = reply_messages[-1]  # most recent inbound in thread
            if _log_and_process_reply(operator_id, ctx["customer_id"],
                                       ctx["customer_name"], reply, thread_id):
                new_replies += 1
    else:
        print("[reply_detector] Pass 1: no active threads to check")

    # ── Pass 2: Email-address inbox scan (fallback for orphaned threads) ─────
    # For each customer with active outreach, search inbox for messages FROM
    # their email that aren't already logged. Catches replies that landed on a
    # different thread than the one we sent (client threading differences).
    with get_db() as db:
        active_customers = (
            db.query(Customer)
            .filter(
                Customer.operator_id == operator_id,
                Customer.email != None,
                Customer.reactivation_status.in_(SCAN_STATUSES),
            )
            .all()
        )
        # Build {customer_id → last_outbound_at} so we only look at recent inbox
        last_outbound_map = {}
        for c in active_customers:
            last_ob = (
                db.query(OutreachLog.sent_at)
                .filter(
                    OutreachLog.customer_id == c.id,
                    OutreachLog.operator_id == operator_id,
                    OutreachLog.direction == "outbound",
                    OutreachLog.dry_run == False,
                )
                .order_by(OutreachLog.sent_at.desc())
                .first()
            )
            if last_ob and last_ob[0]:
                last_outbound_map[c.id] = last_ob[0]
        active_list = [
            {"id": c.id, "name": c.name, "email": c.email}
            for c in active_customers
            if c.id in last_outbound_map
        ]

    print(f"[reply_detector] Pass 2: scanning inbox for {len(active_list)} active customer(s)")
    for cust in active_list:
        try:
            messages = search_inbox_by_sender(
                cust["email"],
                since_date=last_outbound_map[cust["id"]],
            )
        except Exception as e:
            print(f"  [reply_detector] inbox scan error for {cust['email']}: {e}")
            continue

        for msg in messages:
            msg_thread_id = msg.get("thread_id") or ""
            if _log_and_process_reply(operator_id, cust["id"], cust["name"],
                                       msg, msg_thread_id):
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

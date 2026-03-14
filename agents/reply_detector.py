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
import re
import time
from datetime import datetime, timedelta

from core.config import config
from core.database import get_db
from core.models import Booking, Customer, OutreachLog


# ── Calendar notification detection ──────────────────────────────────────────
# These automated emails must not trigger draft generation or status changes.

_CAL_ACCEPTED_PATTERNS = [
    re.compile(r"^accepted:", re.IGNORECASE),
    re.compile(r"has accepted your invitation", re.IGNORECASE),
    re.compile(r"accepted this invitation", re.IGNORECASE),
]
_CAL_DECLINED_PATTERNS = [
    re.compile(r"^declined:", re.IGNORECASE),
    re.compile(r"has declined your invitation", re.IGNORECASE),
    re.compile(r"declined this invitation", re.IGNORECASE),
]


def _calendar_notification_type(subject: str, body: str) -> str | None:
    """Return 'calendar_accepted' or 'calendar_declined' if this is a GCal auto-email, else None."""
    text = subject + " " + body
    for pat in _CAL_ACCEPTED_PATTERNS:
        if pat.search(subject) or pat.search(text):
            return "calendar_accepted"
    for pat in _CAL_DECLINED_PATTERNS:
        if pat.search(subject) or pat.search(text):
            return "calendar_declined"
    return None

try:
    from integrations.gmail import get_inbox_replies, search_inbox_by_sender
    GMAIL_AVAILABLE = True
except Exception:
    GMAIL_AVAILABLE = False


# No longer filtering by status — we scan ALL customers who have an outbound thread.
# A customer marked "unsubscribed" or "booked" can still send us a reply that needs
# logging (e.g. they changed their mind, or their earlier reply was miscategorised).


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


def _auto_create_booking(operator_id: int, customer_id: int, inbound_log_id: int | None):
    """
    Called when classifier returns booking_confirmed.
    1. Reads extracted slot times from the queued confirmation draft.
    2. Creates a Booking record (source=ai_outreach, status=confirmed).
    3. Flips Customer.reactivation_status → booked.
    4. Marks the inbound log as converted.
    5. Creates a Google Calendar event and stores the event ID.
    """
    with get_db() as db:
        # The conversation_agent._generate_booking_confirmation already queued a draft
        # with booking_slot_start/end extracted from the customer's reply.
        draft = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.customer_id == customer_id,
                OutreachLog.operator_id == operator_id,
                OutreachLog.response_classification == "booking_confirmed",
                OutreachLog.direction == "outbound",
                OutreachLog.dry_run == True,
                OutreachLog.booking_slot_start != None,
            )
            .order_by(OutreachLog.created_at.desc())
            .first()
        )
        slot_start = draft.booking_slot_start if draft else None
        slot_end = draft.booking_slot_end if draft else None

        customer = db.query(Customer).filter_by(id=customer_id).first()
        cust_email = customer.email if customer else None
        cust_name = customer.name if customer else ""
        service_type = (customer.last_service_type or "HVAC Service") if customer else "HVAC Service"

    if not slot_start:
        print(f"  [reply_detector] booking_confirmed — no slot extracted, skipping auto-booking for customer {customer_id}")
        return

    if not slot_end:
        slot_end = slot_start + timedelta(hours=2)

    # Create Booking record
    now_utc = datetime.utcnow()
    with get_db() as db:
        booking = Booking(
            operator_id=operator_id,
            customer_id=customer_id,
            slot_start=slot_start,
            slot_end=slot_end,
            status="tentative",
            source="ai_outreach",
            service_type=service_type,
            awaiting_estimate=True,  # prompt operator to capture job value
        )
        db.add(booking)
        db.flush()
        booking_id = booking.id

        # Flip customer to booked
        customer = db.query(Customer).filter_by(id=customer_id).first()
        if customer:
            customer.reactivation_status = "booked"

        # Mark inbound log converted
        if inbound_log_id:
            log = db.query(OutreachLog).filter_by(id=inbound_log_id).first()
            if log:
                log.converted_to_job = True
                log.converted_at = now_utc

    print(f"  [reply_detector] Booking created: id={booking_id}, slot={slot_start}")

    # Try to create GCal event (graceful fallback if calendar scope not available)
    try:
        from integrations.calendar import create_calendar_event
        event = create_calendar_event(
            summary=f"{service_type} — {cust_name}",
            start_dt=slot_start,
            end_dt=slot_end,
            customer_email=cust_email,
            description="Booked via Foreman AI outreach",
        )
        gcal_id = event.get("id", "")
        with get_db() as db:
            b = db.query(Booking).filter_by(id=booking_id).first()
            if b:
                b.google_cal_event_id = gcal_id
        print(f"  [reply_detector] GCal event created: {gcal_id}")
    except Exception as e:
        print(f"  [reply_detector] GCal event failed (booking still saved): {e}")


def _log_and_process_reply(operator_id: int, customer_id: int, customer_name: str,
                            reply: dict, thread_id: str) -> bool:
    """
    Log a single inbound reply, update profile, and classify.
    Response generation is handled separately by response_generator.py.
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

    # Pre-classify calendar notifications — skip status change + LLM classification
    cal_type = _calendar_notification_type(reply_subject, reply_body)

    print(f"  → Reply detected from {customer_name}: {reply_subject[:60]}"
          + (f" [auto: {cal_type}]" if cal_type else ""))

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
            # Calendar notifications need no response — mark as already processed
            draft_queued=bool(cal_type),
        )
        db.add(log)
        db.flush()
        inbound_log_id = log.id

        if cal_type:
            # Store classification inline — no LLM needed, no status change
            from datetime import timezone as _tz
            log.response_classification = cal_type
            log.classified_at = datetime.now(_tz.utc).replace(tzinfo=None)
        else:
            # Normal reply — mark customer as replied
            customer = db.query(Customer).filter_by(id=customer_id).first()
            if customer:
                customer.reactivation_status = "replied"

    if cal_type:
        if cal_type == "calendar_accepted":
            # Customer accepted the invite — confirm any tentative booking and mark as booked
            with get_db() as db:
                booking = (
                    db.query(Booking)
                    .filter(
                        Booking.customer_id == customer_id,
                        Booking.operator_id == operator_id,
                        Booking.status.in_(["tentative", "confirmed"]),
                    )
                    .order_by(Booking.created_at.desc())
                    .first()
                )
                if booking:
                    booking.status = "confirmed"
                customer = db.query(Customer).filter_by(id=customer_id).first()
                if customer and customer.reactivation_status in ("invite_sent", "replied", "outreach_sent"):
                    customer.reactivation_status = "booked"
            print(f"  [reply_detector] calendar_accepted: booking confirmed, status → booked")
        else:
            print(f"  [reply_detector] Calendar notification logged ({cal_type}) — no action required")
        return True

    # Update customer profile with reply context (force=True so new reply data is included)
    try:
        from agents.customer_analyzer import analyze_customer
        analyze_customer(operator_id, customer_id, verbose=False, force=True)
    except Exception as e:
        print(f"  [reply_detector] Profile update failed: {e}")

    # Classify the reply — response_generator will pick it up from here
    try:
        from agents.response_classifier import classify_reply
        if inbound_log_id:
            classify_reply(operator_id, inbound_log_id, verbose=True)
    except Exception as e:
        print(f"  [reply_detector] Classification failed: {e}")

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
    # Check every known outbound gmail_thread_id for INBOX messages (fast, exact).
    # No status filter — a customer can reply regardless of their current status.
    with get_db() as db:
        rows = (
            db.query(OutreachLog, Customer)
            .join(Customer, OutreachLog.customer_id == Customer.id)
            .filter(
                OutreachLog.operator_id == operator_id,
                OutreachLog.dry_run == False,
                OutreachLog.gmail_thread_id != None,
                OutreachLog.direction == "outbound",
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
    # For every customer who has received at least one real outbound email, search
    # inbox for messages FROM their address not yet logged.  No status filter.
    with get_db() as db:
        active_customers = (
            db.query(Customer)
            .filter(
                Customer.operator_id == operator_id,
                Customer.email != None,
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

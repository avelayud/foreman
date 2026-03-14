"""
agents/response_generator.py
Response Generation Agent.

Finds classified inbound replies that don't yet have a draft response queued,
generates a bespoke reply draft via conversation_agent, and handles auto-booking
when the customer has confirmed a specific time slot.

Designed to run after reply_detector — typically at the same interval or slightly
delayed. reply_detector handles detection + classification; this agent handles
the LLM call and any downstream booking logic.

Usage:
    python -m agents.response_generator --operator-id 1
    # Runs continuously every 15 min:
    python -m agents.response_generator --operator-id 1 --watch
"""

import argparse
import time
from datetime import datetime, timedelta

from core.config import config
from core.database import get_db
from core.models import Booking, Customer, OutreachLog


def _auto_create_booking(operator_id: int, customer_id: int, inbound_log_id: int | None):
    """
    Called when classifier returns booking_confirmed.
    1. Reads extracted slot times from the queued confirmation draft.
    2. Creates a Booking record (source=ai_outreach, status=tentative).
    3. Flips Customer.reactivation_status → booked only after invite is sent.
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
        print(f"  [response_generator] booking_confirmed — no slot extracted, skipping auto-booking for customer {customer_id}")
        return

    if not slot_end:
        slot_end = slot_start + timedelta(hours=2)

    # Create Booking record as tentative — confirmed only after invite email is sent
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

        # Mark inbound log converted
        if inbound_log_id:
            log = db.query(OutreachLog).filter_by(id=inbound_log_id).first()
            if log:
                log.converted_to_job = True
                log.converted_at = now_utc

    print(f"  [response_generator] Tentative booking created: id={booking_id}, slot={slot_start}")

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
        print(f"  [response_generator] GCal event created: {gcal_id}")
    except Exception as e:
        print(f"  [response_generator] GCal event failed (booking still saved): {e}")


def run(operator_id: int) -> int:
    """
    Find all classified inbound logs where draft_queued=False and generate responses.
    Skips unsubscribe_request classifications (no response needed).
    Returns the number of drafts generated.
    """
    print(f"\n[response_generator] operator={operator_id} — checking for unprocessed replies")

    with get_db() as db:
        pending = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.operator_id == operator_id,
                OutreachLog.direction == "inbound",
                OutreachLog.classified_at != None,
                # draft_queued may be NULL on old rows — treat NULL as not yet processed
                (OutreachLog.draft_queued == False) | (OutreachLog.draft_queued == None),
                OutreachLog.response_classification.notin_(
                    ["unsubscribe_request", "calendar_accepted", "calendar_declined"]
                ),
            )
            .order_by(OutreachLog.created_at.asc())
            .all()
        )
        pending_data = [
            {
                "id": log.id,
                "customer_id": log.customer_id,
                "classification": log.response_classification or "unclear",
            }
            for log in pending
        ]

    if not pending_data:
        print("[response_generator] No unprocessed replies found")
        return 0

    print(f"[response_generator] Found {len(pending_data)} unprocessed classified reply(s)")
    drafts_generated = 0

    for item in pending_data:
        inbound_log_id = item["id"]
        customer_id = item["customer_id"]
        classification = item["classification"]

        try:
            from agents.conversation_agent import generate_response
            generate_response(
                operator_id=operator_id,
                customer_id=customer_id,
                classification=classification,
                inbound_log_id=inbound_log_id,
                verbose=True,
            )
            drafts_generated += 1
            print(f"  [response_generator] Draft generated for customer {customer_id} ({classification})")
        except Exception as e:
            print(f"  [response_generator] Response generation failed for customer {customer_id}: {e}")
            continue

        # Mark the inbound log as processed so we don't re-queue
        with get_db() as db:
            log = db.query(OutreachLog).filter_by(id=inbound_log_id).first()
            if log:
                log.draft_queued = True

        # Auto-create tentative booking when customer confirmed a time
        if classification == "booking_confirmed":
            try:
                _auto_create_booking(operator_id, customer_id, inbound_log_id)
            except Exception as e:
                print(f"  [response_generator] Auto-booking failed for customer {customer_id}: {e}")

    print(f"[response_generator] Done — {drafts_generated} draft(s) generated")
    return drafts_generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Foreman response generator")
    parser.add_argument("--operator-id", type=int, default=1)
    parser.add_argument("--watch", action="store_true",
                        help="Run continuously, checking every 15 minutes")
    parser.add_argument("--interval", type=int, default=15,
                        help="Poll interval in minutes (default: 15)")
    args = parser.parse_args()

    if args.watch:
        print(f"[response_generator] Watching — checking every {args.interval} minutes")
        while True:
            run(args.operator_id)
            time.sleep(args.interval * 60)
    else:
        run(args.operator_id)

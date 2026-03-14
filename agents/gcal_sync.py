"""
agents/gcal_sync.py
Google Calendar Sync Agent.

For every Foreman booking with a google_cal_event_id, checks attendee
response status via the Calendar API. Handles acceptances, declines,
deletions, and time changes that were never detected via Gmail.

Usage:
    python -m agents.gcal_sync --operator-id 1
"""

import argparse
from datetime import datetime, timedelta

from core.database import get_db
from core.models import Booking, Customer, OutreachLog


def run(operator_id: int) -> dict:
    """
    Sync all tracked GCal events with Foreman bookings.
    Returns: {accepted: int, declined: int, deleted: int, time_changed: int, skipped: int}
    """
    counts = {"accepted": 0, "declined": 0, "deleted": 0, "time_changed": 0, "skipped": 0}

    # Check if calendar is available
    try:
        from integrations.calendar import get_event_status
    except ImportError as e:
        print(f"[gcal_sync] Calendar integration not available (ImportError): {e}")
        return counts
    except Exception as e:
        print(f"[gcal_sync] Calendar integration not available: {e}")
        return counts

    print(f"\n[gcal_sync] operator={operator_id} — syncing GCal events")

    with get_db() as db:
        # Fetch all bookings with a linked GCal event that are still active
        bookings = (
            db.query(Booking)
            .filter(
                Booking.operator_id == operator_id,
                Booking.google_cal_event_id != None,
                Booking.status.in_(("tentative", "confirmed")),
            )
            .all()
        )

        print(f"[gcal_sync] Found {len(bookings)} active booking(s) with GCal event IDs")

        for booking in bookings:
            customer = db.query(Customer).filter_by(id=booking.customer_id, operator_id=operator_id).first()
            if not customer:
                counts["skipped"] += 1
                continue

            customer_email = customer.email or ""
            customer_name = customer.name

            try:
                event_info = get_event_status(booking.google_cal_event_id)
            except Exception as e:
                print(f"[gcal_sync] customer={customer.id} error fetching event {booking.google_cal_event_id}: {e}")
                counts["skipped"] += 1
                continue

            # ── Case 3: Event deleted (404 / cancelled) ─────────────────────
            if not event_info.get("exists"):
                if getattr(booking, "orphaned", False):
                    counts["skipped"] += 1
                    continue
                booking.status = "cancelled"
                booking.orphaned = True
                if customer.reactivation_status in ("invite_sent", "booked"):
                    customer.reactivation_status = "replied"
                counts["deleted"] += 1
                print(f"[gcal_sync] customer={customer.id} event deleted — booking orphaned, status → replied")
                continue

            attendees = event_info.get("attendees", [])
            customer_response = None
            for att in attendees:
                if att.get("email", "").lower() == customer_email.lower():
                    customer_response = att.get("responseStatus", "needsAction")
                    break

            # ── Case 1: Customer Accepted ───────────────────────────────────
            if customer_response == "accepted":
                # Dedup: check if calendar_accepted log already exists for this customer
                # created after the booking was created
                existing_accepted = (
                    db.query(OutreachLog)
                    .filter(
                        OutreachLog.customer_id == customer.id,
                        OutreachLog.operator_id == operator_id,
                        OutreachLog.direction == "inbound",
                        OutreachLog.response_classification == "calendar_accepted",
                        OutreachLog.created_at >= booking.created_at,
                    )
                    .first()
                )
                if existing_accepted:
                    counts["skipped"] += 1
                    continue

                # Confirm booking + flip to booked
                booking.status = "confirmed"
                if customer.reactivation_status in ("invite_sent", "replied", "outreach_sent"):
                    customer.reactivation_status = "booked"

                # Log calendar_accepted inbound entry
                log = OutreachLog(
                    operator_id=operator_id,
                    customer_id=customer.id,
                    direction="inbound",
                    channel="email",
                    subject="Accepted: Calendar invite",
                    content="Customer accepted the calendar invite via Google Calendar.",
                    response_classification="calendar_accepted",
                    draft_queued=True,
                    dry_run=False,
                    sent_at=datetime.utcnow(),
                    sequence_step=0,
                )
                db.add(log)
                counts["accepted"] += 1
                print(f"[gcal_sync] customer={customer.id} accepted — booking confirmed, status → booked")

            # ── Case 2: Customer Declined ───────────────────────────────────
            elif customer_response == "declined":
                # Dedup: check if calendar_declined log already exists
                existing_declined = (
                    db.query(OutreachLog)
                    .filter(
                        OutreachLog.customer_id == customer.id,
                        OutreachLog.operator_id == operator_id,
                        OutreachLog.direction == "inbound",
                        OutreachLog.response_classification == "calendar_declined",
                        OutreachLog.created_at >= booking.created_at,
                    )
                    .first()
                )
                if existing_declined:
                    counts["skipped"] += 1
                    continue

                booking.status = "cancelled"
                if customer.reactivation_status in ("invite_sent", "booked"):
                    customer.reactivation_status = "replied"

                # Log calendar_declined inbound entry with draft_queued=False so response_generator picks it up
                log = OutreachLog(
                    operator_id=operator_id,
                    customer_id=customer.id,
                    direction="inbound",
                    channel="email",
                    subject="Declined: Calendar invite",
                    content="Customer declined the calendar invite via Google Calendar.",
                    response_classification="calendar_declined",
                    classified_at=datetime.utcnow(),
                    draft_queued=False,
                    dry_run=False,
                    sent_at=datetime.utcnow(),
                    sequence_step=0,
                )
                db.add(log)
                counts["declined"] += 1
                print(f"[gcal_sync] customer={customer.id} declined — booking cancelled, queuing redraft")

            # ── Case 4: Event time changed (> 30 min threshold) ─────────────
            elif event_info.get("start") is not None:
                new_start = event_info["start"]
                new_end = event_info.get("end")

                if booking.slot_start and new_start:
                    diff_minutes = abs((new_start - booking.slot_start).total_seconds()) / 60
                    if diff_minutes > 30:
                        if getattr(booking, "time_changed", False):
                            counts["skipped"] += 1
                            continue

                        old_start = booking.slot_start
                        booking.slot_start = new_start
                        if new_end:
                            booking.slot_end = new_end
                        booking.time_changed = True
                        counts["time_changed"] += 1
                        print(f"[gcal_sync] customer={customer.id} event time changed from {old_start} to {new_start} — booking updated")
                    else:
                        # Case 5: No attendee response yet or no significant change
                        counts["skipped"] += 1
                else:
                    counts["skipped"] += 1

            else:
                # Case 5: needsAction or tentative — no action
                counts["skipped"] += 1

    print(f"[gcal_sync] Done. {counts}")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Foreman GCal sync agent")
    parser.add_argument("--operator-id", type=int, default=1)
    args = parser.parse_args()
    run(args.operator_id)

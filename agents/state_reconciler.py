"""
agents/state_reconciler.py
Conversation State Reconciler.

Scans all active customers and applies 5 deterministic reconciliation rules
to fix drifted conversation state. Safe to run frequently — each rule is
idempotent. Returns count of customers whose state was corrected.

Usage:
    python -m agents.state_reconciler --operator-id 1
"""

import argparse
from datetime import datetime

from core.database import get_db
from core.models import Booking, Customer, OutreachLog


def run(operator_id: int) -> int:
    """Apply reconciliation rules to all active conversations.
    Returns total number of state corrections made."""

    corrections = 0
    now = datetime.utcnow()

    # Active customers: exclude never_contacted, sequence_complete, unsubscribed
    excluded_statuses = ("never_contacted", "sequence_complete", "unsubscribed")

    with get_db() as db:
        active_customers = (
            db.query(Customer)
            .filter(
                Customer.operator_id == operator_id,
                ~Customer.reactivation_status.in_(excluded_statuses),
            )
            .all()
        )

        for customer in active_customers:
            cid = customer.id

            # ── Rule 1: Orphaned invite_sent ────────────────────────────────
            if customer.reactivation_status == "invite_sent":
                active_booking = (
                    db.query(Booking)
                    .filter(
                        Booking.customer_id == cid,
                        Booking.operator_id == operator_id,
                        Booking.status.in_(("tentative", "confirmed", "complete")),
                    )
                    .first()
                )
                if not active_booking:
                    customer.reactivation_status = "replied"
                    corrections += 1
                    print(f"[state_reconciler] customer={cid} Rule1: orphaned invite_sent → replied")
                    continue

            # ── Rule 2: Orphaned booked ─────────────────────────────────────
            if customer.reactivation_status == "booked":
                active_booking = (
                    db.query(Booking)
                    .filter(
                        Booking.customer_id == cid,
                        Booking.operator_id == operator_id,
                        Booking.status.in_(("tentative", "confirmed", "complete")),
                    )
                    .first()
                )
                if not active_booking:
                    customer.reactivation_status = "replied"
                    corrections += 1
                    print(f"[state_reconciler] customer={cid} Rule2: orphaned booked → replied")
                    continue

            # ── Rule 3: Calendar acceptance confirms booking ─────────────────
            if customer.reactivation_status in ("invite_sent", "replied"):
                cal_accepted_log = (
                    db.query(OutreachLog)
                    .filter(
                        OutreachLog.customer_id == cid,
                        OutreachLog.operator_id == operator_id,
                        OutreachLog.direction == "inbound",
                        OutreachLog.response_classification == "calendar_accepted",
                    )
                    .first()
                )
                if cal_accepted_log:
                    active_booking = (
                        db.query(Booking)
                        .filter(
                            Booking.customer_id == cid,
                            Booking.operator_id == operator_id,
                            Booking.status.in_(("tentative", "confirmed")),
                        )
                        .first()
                    )
                    if active_booking:
                        changed = False
                        if active_booking.status != "confirmed":
                            active_booking.status = "confirmed"
                            changed = True
                        if customer.reactivation_status != "booked":
                            customer.reactivation_status = "booked"
                            changed = True
                        if changed:
                            corrections += 1
                            print(f"[state_reconciler] customer={cid} Rule3: calendar_accepted → booking confirmed, status → booked")

            # ── Rule 4: Stale draft_queued=True with deleted draft ───────────
            inbound_with_stale_draft = (
                db.query(OutreachLog)
                .filter(
                    OutreachLog.customer_id == cid,
                    OutreachLog.operator_id == operator_id,
                    OutreachLog.direction == "inbound",
                    OutreachLog.draft_queued == True,
                    OutreachLog.response_classification != None,
                    ~OutreachLog.response_classification.in_(("calendar_accepted", "unsubscribe_request")),
                )
                .all()
            )
            for inbound_log in inbound_with_stale_draft:
                # Check if there's an outbound dry_run draft created after this inbound log
                draft_exists = (
                    db.query(OutreachLog)
                    .filter(
                        OutreachLog.customer_id == cid,
                        OutreachLog.operator_id == operator_id,
                        OutreachLog.direction == "outbound",
                        OutreachLog.dry_run == True,
                        OutreachLog.created_at > inbound_log.created_at,
                    )
                    .first()
                )
                if not draft_exists:
                    inbound_log.draft_queued = False
                    corrections += 1
                    print(f"[state_reconciler] customer={cid} Rule4: stale draft_queued reset on log={inbound_log.id}")

            # ── Rule 5: Health override expiry ──────────────────────────────
            if customer.health_override and customer.health_override_set_at:
                new_actionable_inbound = (
                    db.query(OutreachLog)
                    .filter(
                        OutreachLog.customer_id == cid,
                        OutreachLog.operator_id == operator_id,
                        OutreachLog.direction == "inbound",
                        OutreachLog.created_at > customer.health_override_set_at,
                        OutreachLog.response_classification != None,
                        ~OutreachLog.response_classification.in_(("calendar_accepted",)),
                    )
                    .first()
                )
                if new_actionable_inbound:
                    customer.health_override = None
                    customer.health_override_set_at = None
                    corrections += 1
                    print(f"[state_reconciler] customer={cid} Rule5: health_override expired — new inbound reply detected")

    print(f"[state_reconciler] Done. {corrections} correction(s) made.")
    return corrections


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Foreman conversation state reconciler")
    parser.add_argument("--operator-id", type=int, default=1)
    args = parser.parse_args()
    run(args.operator_id)

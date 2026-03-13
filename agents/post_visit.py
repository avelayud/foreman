"""
agents/post_visit.py
Post-Visit Agent.

Finds all bookings where slot_start has passed and visit_outcome == 'pending'.
For each: sets Customer.needs_post_visit_update = True so the Updates inbox
surfaces them and the conversation workspace shows the post-visit banner.

Usage:
    python -m agents.post_visit --operator-id 1
"""

import argparse
from datetime import datetime

from core.database import get_db
from core.models import Booking, Customer


def run(operator_id: int) -> int:
    """
    Find all bookings where slot_start < now and visit_outcome == 'pending'.
    For each: set Customer.needs_post_visit_update = True.
    Returns count of customers flagged.
    """
    now = datetime.utcnow()
    flagged = 0

    with get_db() as db:
        past_pending = (
            db.query(Booking)
            .filter(
                Booking.operator_id == operator_id,
                Booking.slot_start < now,
                Booking.visit_outcome == "pending",
            )
            .all()
        )

        for booking in past_pending:
            customer = db.query(Customer).filter_by(id=booking.customer_id).first()
            if customer and not customer.needs_post_visit_update:
                customer.needs_post_visit_update = True
                flagged += 1

    print(f"[post_visit] Flagged {flagged} customer(s) for post-visit update.")
    return flagged


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Foreman post-visit agent")
    parser.add_argument("--operator-id", type=int, default=1)
    args = parser.parse_args()
    run(args.operator_id)

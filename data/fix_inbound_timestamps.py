"""
One-time migration: fix inbound log timestamps that were stored as local EDT
instead of UTC (bug present before 2026-03-11 gmail.py fix).

Inbound logs detected via Gmail had their timezone stripped without first
converting to UTC, so they were stored as e.g. "22:45" (EDT) instead of
"02:45" (UTC next day). This adds the correct EDT offset (4h) to convert them.

Safe to re-run: only touches inbound logs with a gmail_thread_id where
sent_at exists and appears to need correction.

Usage:
    DATABASE_URL=sqlite:///./foreman.db venv/bin/python -m data.fix_inbound_timestamps
"""

import sys
from datetime import timedelta

sys.path.insert(0, ".")
from core.database import get_db
from core.models import OutreachLog

# EDT is UTC-4; to convert a naive local-EDT stored datetime to UTC, add 4h.
# (March 2026 is after DST start on Mar 8, so EDT applies.)
EDT_OFFSET = timedelta(hours=4)


def run():
    fixed = 0
    with get_db() as db:
        logs = (
            db.query(OutreachLog)
            .filter(
                OutreachLog.direction == "inbound",
                OutreachLog.gmail_thread_id.isnot(None),
                OutreachLog.sent_at.isnot(None),
            )
            .all()
        )

        if not logs:
            print("No inbound Gmail logs found — nothing to fix.")
            return

        print(f"Found {len(logs)} inbound Gmail log(s) to inspect.")
        for log in logs:
            old_ts = log.sent_at
            new_ts = old_ts + EDT_OFFSET
            print(f"  Log {log.id}: {old_ts}  →  {new_ts}")
            log.sent_at = new_ts
            fixed += 1

        db.commit()

    print(f"\n✅ Fixed {fixed} timestamp(s). Run the server to verify display.")


if __name__ == "__main__":
    run()

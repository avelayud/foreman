"""
core/database.py
Database connection, session management, and initialization.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from core.config import config
from core.models import Base


def _normalize_database_url(raw_url: str) -> str:
    """
    Normalize known URL variants from PaaS providers.
    SQLAlchemy expects postgresql:// (not legacy postgres://).
    """
    db_url = (raw_url or "").strip()
    if db_url.startswith("postgres://"):
        return "postgresql://" + db_url[len("postgres://"):]
    return db_url


DATABASE_URL = _normalize_database_url(config.DATABASE_URL)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    connect_args = {"connect_timeout": 5}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_timeout=6,
    echo=config.is_development(),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SCHEMA_PATCHES = {
    "product_events": {},
    "operators": {
        "voice_profiles": "TEXT",
        "outreach_mode": "VARCHAR",
        "operator_config": "TEXT",
    },
    "customers": {
        "assigned_voice_id": "VARCHAR",
        "customer_profile": "TEXT",
        "score": "INTEGER",
        "score_breakdown": "TEXT",
        "priority_tier": "VARCHAR",
        "estimated_job_value": "FLOAT",
        "service_interval_days": "INTEGER",
        "predicted_next_service": "TIMESTAMP",
        "needs_post_visit_update": "BOOLEAN",
    },
    "bookings": {
        "estimated_value": "FLOAT",
        "estimate_unknown": "BOOLEAN",
        "awaiting_estimate": "BOOLEAN",
        "visit_outcome": "VARCHAR",
        "quote_given": "FLOAT",
        "quote_given_at": "TIMESTAMP",
        "job_won": "BOOLEAN",
        "final_invoice_value": "FLOAT",
        "closed_at": "TIMESTAMP",
    },
    "outreach_logs": {
        "gmail_thread_id": "VARCHAR",
        "approval_status": "VARCHAR",
        "approved_at": "TIMESTAMP",
        "scheduled_send_at": "TIMESTAMP",
        "send_error": "TEXT",
        "response_classification": "VARCHAR",
        "classified_at": "TIMESTAMP",
        "converted_to_job": "BOOLEAN",
        "converted_job_value": "FLOAT",
        "converted_at": "TIMESTAMP",
        "rfc_message_id": "VARCHAR",
        "booking_slot_start": "TIMESTAMP",
        "booking_slot_end": "TIMESTAMP",
    },
}


def _apply_schema_patches():
    """Backfill columns introduced after initial deploys."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    # Read ALL column info before opening any transaction.
    # Opening a second connection inside engine.begin() while DDL locks are held
    # causes a deadlock on Postgres — inspect() here, then never again inside the tx.
    live_cols: dict[str, set[str]] = {
        t: {col["name"] for col in inspector.get_columns(t)}
        for t in SCHEMA_PATCHES
        if t in table_names
    }

    with engine.begin() as conn:
        # Phase 1: add any missing columns
        for table_name, columns in SCHEMA_PATCHES.items():
            if table_name not in table_names:
                continue
            for column_name, column_type in columns.items():
                if column_name in live_cols.get(table_name, set()):
                    continue
                conn.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )
                print(f"✅ Added missing column {table_name}.{column_name}")
                live_cols.setdefault(table_name, set()).add(column_name)

        # Phase 2: backfill defaults (idempotent CASE WHEN, safe to re-run)
        if "outreach_logs" in table_names and "approval_status" in live_cols.get("outreach_logs", set()):
            conn.execute(
                text(
                    """
                    UPDATE outreach_logs
                    SET approval_status = CASE
                        WHEN approval_status IS NOT NULL THEN approval_status
                        WHEN dry_run THEN 'pending'
                        ELSE 'sent'
                    END
                    """
                )
            )

        if "operators" in table_names and "outreach_mode" in live_cols.get("operators", set()):
            conn.execute(
                text(
                    """
                    UPDATE operators
                    SET outreach_mode = 'dry_run'
                    WHERE outreach_mode IS NULL OR outreach_mode = ''
                    """
                )
            )


def init_db():
    """Create all tables. Safe to call multiple times."""
    Base.metadata.create_all(bind=engine)
    _apply_schema_patches()
    print("✅ Database initialized.")


@contextmanager
def get_db() -> Session:
    """Context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

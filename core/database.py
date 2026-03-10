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
    "operators": {
        "voice_profiles": "TEXT",
        "outreach_mode": "VARCHAR",
    },
    "customers": {
        "assigned_voice_id": "VARCHAR",
        "customer_profile": "TEXT",
    },
    "outreach_logs": {
        "gmail_thread_id": "VARCHAR",
        "approval_status": "VARCHAR",
        "approved_at": "TIMESTAMP",
        "scheduled_send_at": "TIMESTAMP",
        "send_error": "TEXT",
    },
}


def _apply_schema_patches():
    """Backfill columns introduced after initial deploys."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table_name, columns in SCHEMA_PATCHES.items():
            if table_name not in table_names:
                continue

            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name in existing_columns:
                    continue

                conn.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )
                print(f"✅ Added missing column {table_name}.{column_name}")

        inspector = inspect(engine)

        if "outreach_logs" in table_names:
            outreach_columns = {col["name"] for col in inspector.get_columns("outreach_logs")}
            if "approval_status" in outreach_columns:
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

        if "operators" in table_names:
            operator_columns = {col["name"] for col in inspector.get_columns("operators")}
            if "outreach_mode" in operator_columns:
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

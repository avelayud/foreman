"""
core/database.py
Database connection, session management, and initialization.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from core.config import config
from core.models import Base


engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {},
    echo=config.is_development(),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SCHEMA_PATCHES = {
    "operators": {
        "voice_profiles": "TEXT",
    },
    "customers": {
        "assigned_voice_id": "VARCHAR",
        "customer_profile": "TEXT",
    },
    "outreach_logs": {
        "gmail_thread_id": "VARCHAR",
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

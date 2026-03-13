"""
core/product_analytics.py
Lightweight product analytics helpers for Foreman.
All functions are wrapped in try/except — analytics must NEVER crash the app.
"""

import json
import uuid
from datetime import datetime

from core.models import ProductEvent


def get_session_id(request) -> str:
    """Read foreman_session cookie or generate a new UUID."""
    try:
        session_id = request.cookies.get("foreman_session")
        if not session_id:
            session_id = str(uuid.uuid4())
        return session_id
    except Exception:
        return str(uuid.uuid4())


def log_event(
    db,
    session_id: str,
    event_type: str,
    event_name: str,
    page: str,
    properties: dict | None = None,
    operator_id: int | None = None,
) -> None:
    """Insert a ProductEvent row. Always wrapped in try/except — never crashes."""
    try:
        event = ProductEvent(
            operator_id=operator_id,
            session_id=session_id,
            event_type=event_type,
            event_name=event_name,
            page=page,
            properties=json.dumps(properties or {}),
            created_at=datetime.utcnow(),
        )
        db.add(event)
        db.flush()
    except Exception:
        pass


def log_page_view(
    db,
    request,
    page: str,
    operator_id: int | None = None,
    properties: dict | None = None,
) -> None:
    """Convenience wrapper for page_view events."""
    try:
        session_id = get_session_id(request)
        log_event(
            db=db,
            session_id=session_id,
            event_type="page_view",
            event_name=f"page_view:{page}",
            page=page,
            properties=properties or {},
            operator_id=operator_id,
        )
    except Exception:
        pass

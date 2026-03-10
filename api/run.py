"""
api/run.py
Railway-safe process launcher for FastAPI.
Reads PORT from environment without relying on shell expansion.
"""

import os
import uvicorn


def _resolve_port() -> int:
    raw_port = (os.getenv("PORT") or os.getenv("APP_PORT") or "8000").strip()
    try:
        return int(raw_port)
    except ValueError:
        return 8000


if __name__ == "__main__":
    uvicorn.run("api.app:app", host="0.0.0.0", port=_resolve_port())

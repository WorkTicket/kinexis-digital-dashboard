"""UTC helpers — prefer these over deprecated datetime.utcnow()."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC datetime for SQLite/SQLAlchemy compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

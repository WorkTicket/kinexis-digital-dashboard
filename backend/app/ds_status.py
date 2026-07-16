"""Helpers for DataSource sync status + last_error."""

from app.timeutil import utcnow


def mark_active(ds) -> None:
    ds.status = "active"
    ds.last_synced_at = utcnow()
    if hasattr(ds, "last_error"):
        ds.last_error = None


def mark_partial(ds, message: str) -> None:
    """Sync succeeded but data may be truncated / incomplete — never silent full-green."""
    ds.status = "partial"
    ds.last_synced_at = utcnow()
    if hasattr(ds, "last_error"):
        ds.last_error = (message or "Sync incomplete")[:500]


def mark_error(ds, message: str) -> None:
    ds.status = "error"
    if hasattr(ds, "last_error"):
        ds.last_error = (message or "Sync failed")[:500]


def mark_reauth_required(ds, message: str = "Credentials could not be decrypted — reconnect") -> None:
    ds.status = "reauth_required"
    if hasattr(ds, "last_error"):
        ds.last_error = (message or "Reconnect required")[:500]

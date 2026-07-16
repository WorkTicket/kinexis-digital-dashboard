"""Shared helpers for connector sync sessions and metric persistence."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import date
from typing import Any, Callable, Iterator, Optional, Protocol

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import DataSource, MetricDaily

# Per-(client, source) lock so concurrent syncs cannot interleave delete+insert.
# Locks are created lazily; cap total at 2000 entries (100 clients * 20 sources).
# Each lock is ~56 bytes, so worst case is ~112 KB.
_SYNC_LOCKS: dict[tuple[int, str], threading.Lock] = {}
_SYNC_LOCKS_GUARD = threading.Lock()
_SYNC_LOCKS_MAX = 2000


def _sync_lock(client_id: int, source: str) -> threading.Lock:
    key = (int(client_id), str(source))
    with _SYNC_LOCKS_GUARD:
        lock = _SYNC_LOCKS.get(key)
        if lock is None:
            if len(_SYNC_LOCKS) >= _SYNC_LOCKS_MAX:
                _SYNC_LOCKS.clear()
            lock = threading.Lock()
            _SYNC_LOCKS[key] = lock
        return lock


def normalize_dimension(value: Optional[str]) -> str:
    """NULL dims break SQLite UNIQUE (NULLs never collide) â€” always use ''."""
    if value is None:
        return ""
    return str(value)


class Connector(Protocol):
    """Minimal connector contract â€” implement sync(ds) -> bool."""

    def sync(self, ds: DataSource) -> bool: ...


@contextmanager
def connector_session(ds: DataSource) -> Iterator[tuple[Session, DataSource]]:
    """Open a DB session and re-load the datasource; commit/rollback/close safely."""
    db = SessionLocal()
    try:
        fresh = db.query(DataSource).filter(DataSource.id == ds.id).first()
        if not fresh:
            yield db, ds
            return
        yield db, fresh
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def persist_metric_rows(
    db: Session,
    *,
    client_id: int,
    source: str,
    rows: list[dict[str, Any]],
) -> int:
    """Upsert MetricDaily rows (ON CONFLICT replace value)."""
    if not rows:
        return 0
    # Collapse duplicate keys within the same batch (last write wins).
    by_key: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        dim_t = normalize_dimension(row.get("dimension_type"))
        dim_v = normalize_dimension(row.get("dimension_value"))
        key = (
            client_id,
            source,
            row["date"],
            row["metric_name"],
            dim_t,
            dim_v,
        )
        by_key[key] = {
            "client_id": client_id,
            "source": source,
            "date": row["date"],
            "metric_name": row["metric_name"],
            "value": float(row["value"]),
            "dimension_type": dim_t,
            "dimension_value": dim_v,
        }
    payloads = list(by_key.values())
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"

    if dialect == "sqlite":
        # Chunk inserts to stay under SQLite's 999-variable limit
        # (7 columns per row -> ~140 rows per chunk is safe)
        _CHUNK = 100
        count = 0
        for i in range(0, len(payloads), _CHUNK):
            chunk = payloads[i : i + _CHUNK]
            stmt = sqlite_insert(MetricDaily).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    "client_id",
                    "source",
                    "date",
                    "metric_name",
                    "dimension_type",
                    "dimension_value",
                ],
                set_={"value": stmt.excluded.value},
            )
            db.execute(stmt)
            count += len(chunk)
        return count

    count = 0
    for payload in payloads:
        db.add(MetricDaily(**payload))
        count += 1
    return count


def replace_metrics_window(
    db: Session,
    *,
    client_id: int,
    source: str,
    start: date,
    end: date,
    rows: list[dict[str, Any]],
    metric_names: Optional[list[str]] = None,
    dimension_type: Optional[str] = None,
) -> int:
    """Transactional delete+insert under a per-(client, source) sync lock."""
    with _sync_lock(client_id, source):
        q = db.query(MetricDaily).filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == source,
            MetricDaily.date >= start,
            MetricDaily.date <= end,
        )
        if metric_names:
            q = q.filter(MetricDaily.metric_name.in_(metric_names))
        if dimension_type is not None:
            q = q.filter(MetricDaily.dimension_type == dimension_type)
        q.delete(synchronize_session=False)
        return persist_metric_rows(db, client_id=client_id, source=source, rows=rows)
def run_connector_sync(
    ds: DataSource,
    sync_body: Callable[[Session, DataSource], bool],
) -> bool:
    """
    Standard connector wrapper: session + mark_active/mark_error.
    CredentialsDecryptError â†’ mark_reauth_required (never silent empty creds).
    sync_body returns True on success.
    """
    from app.credentials import CredentialsDecryptError
    from app.ds_status import mark_active, mark_error, mark_reauth_required

    db = SessionLocal()
    try:
        fresh = db.query(DataSource).filter(DataSource.id == ds.id).first()
        if not fresh:
            return False
        try:
            ok = sync_body(db, fresh)
            if ok:
                mark_active(fresh)
            else:
                mark_error(fresh, "sync returned false")
            db.commit()
            return bool(ok)
        except CredentialsDecryptError as e:
            db.rollback()
            try:
                fresh = db.query(DataSource).filter(DataSource.id == ds.id).first()
                if fresh:
                    mark_reauth_required(fresh, str(e))
                    db.commit()
            except Exception:
                db.rollback()
            return False
        except Exception as e:
            db.rollback()
            try:
                fresh = db.query(DataSource).filter(DataSource.id == ds.id).first()
                if fresh:
                    mark_error(fresh, str(e)[:500])
                    db.commit()
            except Exception:
                db.rollback()
            raise
    finally:
        db.close()




"""Google ranking tracker — GSC positions + keyword watchlist."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, TrackedKeyword
from app.rankings import build_rankings, keyword_history

router = APIRouter(prefix="/rankings", tags=["rankings"])


class TrackKeywordBody(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=500)
    target_url: Optional[str] = Field(None, max_length=1000)
    notes: Optional[str] = None


def _get_client(db: Session, client_id: int) -> Client:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("/{client_id}")
def get_rankings(
    client_id: int,
    days: int = Query(28, ge=7, le=90),
    bucket: Optional[str] = Query(None, pattern="^(all|top3|top10|page2|deeper)$"),
    q: Optional[str] = Query(None, max_length=200),
    tracked_only: bool = Query(False),
    brand: Optional[str] = Query(
        "all",
        pattern="^(all|brand|non_brand)$",
        description="Filter: all | brand | non_brand",
    ),
    limit: int = Query(200, ge=10, le=500),
    db: Session = Depends(get_db),
):
    _get_client(db, client_id)
    return build_rankings(
        db,
        client_id,
        days=days,
        bucket=None if not bucket or bucket == "all" else bucket,
        search=q,
        tracked_only=tracked_only,
        brand_scope=brand or "all",  # type: ignore[arg-type]
        limit=limit,
    )


@router.get("/{client_id}/history")
def get_keyword_history(
    client_id: int,
    keyword: str = Query(..., min_length=1, max_length=500),
    days: int = Query(90, ge=7, le=180),
    db: Session = Depends(get_db),
):
    _get_client(db, client_id)
    return keyword_history(db, client_id, keyword, days=days)


@router.get("/{client_id}/tracked")
def list_tracked(client_id: int, db: Session = Depends(get_db)):
    _get_client(db, client_id)
    rows = (
        db.query(TrackedKeyword)
        .filter(TrackedKeyword.client_id == client_id)
        .order_by(TrackedKeyword.created_at.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "keyword": t.keyword,
            "target_url": t.target_url,
            "notes": t.notes,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


@router.post("/{client_id}/tracked")
def track_keyword(client_id: int, body: TrackKeywordBody, db: Session = Depends(get_db)):
    _get_client(db, client_id)
    keyword = " ".join(body.keyword.strip().split())
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required")

    existing = (
        db.query(TrackedKeyword)
        .filter(
            TrackedKeyword.client_id == client_id,
            TrackedKeyword.keyword == keyword,
        )
        .first()
    )
    if existing:
        if body.target_url is not None:
            existing.target_url = body.target_url or None
        if body.notes is not None:
            existing.notes = body.notes
        db.commit()
        db.refresh(existing)
        return {
            "id": existing.id,
            "keyword": existing.keyword,
            "target_url": existing.target_url,
            "notes": existing.notes,
            "created_at": existing.created_at.isoformat() if existing.created_at else None,
        }

    row = TrackedKeyword(
        client_id=client_id,
        keyword=keyword,
        target_url=body.target_url or None,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "keyword": row.keyword,
        "target_url": row.target_url,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.delete("/{client_id}/tracked/{tracked_id}")
def untrack_keyword(client_id: int, tracked_id: int, db: Session = Depends(get_db)):
    _get_client(db, client_id)
    row = (
        db.query(TrackedKeyword)
        .filter(TrackedKeyword.id == tracked_id, TrackedKeyword.client_id == client_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tracked keyword not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/{client_id}/serp")
def list_serp_snapshots(
    client_id: int,
    query: Optional[str] = Query(None, max_length=500),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Latest SERP snapshots for Rankings / competitor context."""
    from app.connectors.serp import serp_enabled, serp_snapshot_payload
    from app.models import SerpSnapshot

    _get_client(db, client_id)
    q = (
        db.query(SerpSnapshot)
        .filter(SerpSnapshot.client_id == client_id)
        .order_by(SerpSnapshot.fetched_at.desc())
    )
    if query:
        q = q.filter(SerpSnapshot.query == query.strip())
    rows = q.limit(limit * 3).all()
    # Dedupe to latest per query (fetch extra rows to compensate for duplicates)
    seen: set[str] = set()
    payloads: list = []
    for snap in rows:
        key = (snap.query or "").lower()
        if key in seen:
            continue
        seen.add(key)
        payloads.append(serp_snapshot_payload(snap))
        if len(payloads) >= limit:
            break
    return {
        "enabled": serp_enabled(),
        "snapshots": payloads,
    }


@router.post("/{client_id}/serp/refresh")
def refresh_serp(
    client_id: int,
    keyword: Optional[str] = Query(None, max_length=500),
    db: Session = Depends(get_db),
):
    """Fetch SERP for one keyword or all flagged queries."""
    from app.connectors.serp import (
        ensure_serp_for_flagged_queries,
        fetch_serp_snapshot,
        serp_enabled,
        serp_snapshot_payload,
    )

    _get_client(db, client_id)
    if not serp_enabled():
        raise HTTPException(
            status_code=400,
            detail="SERP disabled — set SERP_PROVIDER and SERP_API_KEY in .env",
        )
    if keyword and keyword.strip():
        snap = fetch_serp_snapshot(db, client_id, keyword.strip())
        if not snap:
            raise HTTPException(status_code=502, detail="SERP fetch failed")
        return {"ok": True, "snapshot": serp_snapshot_payload(snap)}
    snaps = ensure_serp_for_flagged_queries(db, client_id)
    try:
        from app.connectors.sov import write_sov_presence

        write_sov_presence(db, client_id)
    except Exception:
        pass
    return {
        "ok": True,
        "count": len(snaps),
        "snapshots": [serp_snapshot_payload(s) for s in snaps],
    }

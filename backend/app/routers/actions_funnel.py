"""Funnel analysis, success contract, engagement baseline."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client
from app.funnel_analyzer import analyze_funnel
from app.success_report import capture_client_baseline, get_client_baseline

router = APIRouter(tags=["actions"])

# ── Funnel Analysis ───────────────────────────────────────────

@router.get("/funnel/{client_id}")
def get_funnel(
    client_id: int,
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return analyze_funnel(client_id, days=days, db=db)


@router.get("/contract/{client_id}")
def get_success_contract(client_id: int, db: Session = Depends(get_db)):
    """Success Contract progress + brand vs non-brand click split."""
    from app.success_contract import evaluate_success_contract
    from app.brand_queries import brand_split_totals

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    contract = evaluate_success_contract(db, client)
    try:
        brand_split = brand_split_totals(db, client_id, days=28)
    except Exception:
        brand_split = None
    return {"client_id": client_id, **contract, "brand_split": brand_split}



# ── Client engagement baseline ────────────────────────────────

@router.post("/baseline/{client_id}")
def post_baseline(
    client_id: int,
    days: int = Query(30, ge=7, le=90),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    existing = get_client_baseline(db, client_id)
    if existing and not force:
        return {**existing, "status": "exists", "message": "Baseline already set — pass force=true to replace."}
    capture_client_baseline(db, client_id, days=days, force=force)
    return get_client_baseline(db, client_id) or {"status": "error"}


@router.get("/baseline/{client_id}")
def get_baseline(client_id: int, db: Session = Depends(get_db)):
    data = get_client_baseline(db, client_id)
    if not data:
        return {"status": "none", "message": "No engagement baseline captured yet."}
    return data




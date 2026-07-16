from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, DataSource, AnomalyNotification, AiUsageLog
from app.credentials import encrypt_credentials

router = APIRouter(prefix="/clients", tags=["clients"])

ALLOWED_DS_TYPES = frozenset({
    "gsc",
    "ga4",
    "cloudflare",
    "clarity",
    "bing",
    "hubspot",
    "ads_csv",
    "google_ads",
    "meta_ads",
    "pagespeed",
    "gbp",
    "backlinks",
    "crux",
    # serp is a side-job via rankings, not a syncable datasource
})


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    industry: str = Field("", max_length=255)
    brand_color: str = Field("#3B82F6", max_length=7)
    profile_json: Optional[str] = Field("{}", max_length=100_000)
    owner: Optional[str] = Field("", max_length=255)
    priority: Optional[int] = 1


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=255)
    brand_color: Optional[str] = Field(None, max_length=7)
    profile_json: Optional[str] = Field(None, max_length=100_000)
    owner: Optional[str] = Field(None, max_length=255)
    priority: Optional[int] = None
    archived: Optional[bool] = None


class DataSourceCreate(BaseModel):
    type: str = Field(
        ...,
        description="gsc | ga4 | cloudflare | clarity | bing | hubspot | ads_csv | google_ads | meta_ads | gbp | backlinks | pagespeed | crux",
    )
    credentials: Optional[dict] = None


class DataSourceUpdate(BaseModel):
    credentials: Optional[dict] = None
    status: Optional[str] = None


class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    type: str
    last_synced_at: Optional[datetime] = None
    status: str
    last_error: Optional[str] = None
    has_credentials: bool = False


def serialize_datasource(ds: DataSource) -> DataSourceOut:
    return DataSourceOut(
        id=ds.id,
        client_id=ds.client_id,
        type=ds.type,
        last_synced_at=ds.last_synced_at,
        status=ds.status or "pending",
        last_error=ds.last_error,
        has_credentials=bool(ds.credentials_encrypted),
    )


def _validate_ds_type(type_name: str) -> str:
    t = (type_name or "").strip().lower()
    if t not in ALLOWED_DS_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported datasource type. Allowed: {sorted(ALLOWED_DS_TYPES)}",
        )
    return t


@router.get("/")
def list_clients(include_archived: bool = False, db: Session = Depends(get_db)):
    q = db.query(Client)
    if not include_archived:
        q = q.filter((Client.archived == False) | (Client.archived.is_(None)))  # noqa: E712
    return q.order_by(Client.name).all()


@router.post("/")
def create_client(data: ClientCreate, db: Session = Depends(get_db)):
    client = Client(
        name=data.name,
        industry=data.industry,
        brand_color=data.brand_color,
        profile_json=data.profile_json or "{}",
        owner=data.owner or "",
        priority=max(1, min(3, data.priority or 1)),
        archived=False,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/{client_id}")
def get_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.put("/{client_id}")
def update_client(client_id: int, data: ClientUpdate, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        if key == "priority" and val is not None:
            val = max(1, min(3, int(val)))
        setattr(client, key, val)
    db.commit()
    db.refresh(client)
    return client


@router.post("/{client_id}/archive")
def archive_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.archived = True
    db.commit()
    return {"ok": True, "archived": True}


@router.post("/{client_id}/unarchive")
def unarchive_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.archived = False
    db.commit()
    return {"ok": True, "archived": False}


@router.delete("/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.models import (
        ActionPlan,
        ContentBrief,
        DataSource,
        Insight,
        MetricDaily,
        Task,
        TrackedKeyword,
    )
    # Cascade delete all related data
    db.query(AnomalyNotification).filter(AnomalyNotification.client_id == client_id).delete(
        synchronize_session=False
    )
    db.query(AiUsageLog).filter(AiUsageLog.client_id == client_id).delete(synchronize_session=False)
    db.query(MetricDaily).filter(MetricDaily.client_id == client_id).delete(synchronize_session=False)
    db.query(Task).filter(Task.client_id == client_id).delete(synchronize_session=False)
    db.query(Insight).filter(Insight.client_id == client_id).delete(synchronize_session=False)
    db.query(ActionPlan).filter(ActionPlan.client_id == client_id).delete(synchronize_session=False)
    db.query(ContentBrief).filter(ContentBrief.client_id == client_id).delete(synchronize_session=False)
    db.query(TrackedKeyword).filter(TrackedKeyword.client_id == client_id).delete(synchronize_session=False)
    db.query(DataSource).filter(DataSource.client_id == client_id).delete(synchronize_session=False)
    db.delete(client)
    db.commit()
    return {"ok": True}


@router.get("/{client_id}/datasources", response_model=list[DataSourceOut])
def list_datasources(client_id: int, db: Session = Depends(get_db)):
    rows = db.query(DataSource).filter(DataSource.client_id == client_id).all()
    return [serialize_datasource(ds) for ds in rows]


@router.post("/{client_id}/datasources", response_model=DataSourceOut)
def create_datasource(client_id: int, data: DataSourceCreate, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    ds_type = _validate_ds_type(data.type)
    encrypted = None
    if data.credentials:
        # Never persist app client_secret into per-datasource blobs
        creds = {k: v for k, v in data.credentials.items() if k != "client_secret"}
        encrypted = encrypt_credentials(creds)

    existing = (
        db.query(DataSource)
        .filter(DataSource.client_id == client_id, DataSource.type == ds_type)
        .order_by(DataSource.id.desc())
        .all()
    )
    if existing:
        ds = existing[0]
        for dup in existing[1:]:
            db.delete(dup)
        if encrypted is not None:
            ds.credentials_encrypted = encrypted
        ds.status = "pending"
        db.commit()
        db.refresh(ds)
        if ds_type == "hubspot":
            from app.success_contract import ensure_success_contract

            types = {
                row.type
                for row in db.query(DataSource).filter(DataSource.client_id == client_id).all()
            }
            if ensure_success_contract(client, types):
                db.commit()
        return serialize_datasource(ds)

    ds = DataSource(
        client_id=client_id,
        type=ds_type,
        credentials_encrypted=encrypted,
        status="pending",
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)

    # Seed commercial Success Contract when HubSpot (or first CRM) is connected
    if ds_type == "hubspot":
        from app.success_contract import ensure_success_contract

        types = {
            row.type
            for row in db.query(DataSource).filter(DataSource.client_id == client_id).all()
        }
        if ensure_success_contract(client, types):
            db.commit()

    return serialize_datasource(ds)


@router.put("/{client_id}/datasources/{ds_id}", response_model=DataSourceOut)
def update_datasource(client_id: int, ds_id: int, data: DataSourceUpdate, db: Session = Depends(get_db)):
    ds = db.query(DataSource).filter(DataSource.id == ds_id, DataSource.client_id == client_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")
    if data.credentials is not None:
        creds = {k: v for k, v in data.credentials.items() if k != "client_secret"}
        ds.credentials_encrypted = encrypt_credentials(creds)
    if data.status is not None:
        ds.status = data.status
    db.commit()
    db.refresh(ds)
    return serialize_datasource(ds)


@router.delete("/{client_id}/datasources/{ds_id}")
def delete_datasource(client_id: int, ds_id: int, db: Session = Depends(get_db)):
    ds = db.query(DataSource).filter(DataSource.id == ds_id, DataSource.client_id == client_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")
    db.delete(ds)
    db.commit()
    return {"ok": True}

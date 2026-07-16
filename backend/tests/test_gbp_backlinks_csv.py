"""GBP + backlinks CSV ingestion — local SEO / authority path for agents."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Client, MetricDaily, GbpSnapshot, BacklinkSnapshot
from app.connectors.gbp import import_gbp_csv
from app.connectors.backlinks import import_backlinks_csv
from app.routers.clients import ALLOWED_DS_TYPES
from app.scheduler import SYNC_MAP
from app.routers.metrics import _SYNC_FNS


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_gbp_and_backlinks_are_syncable():
    assert "gbp" in ALLOWED_DS_TYPES
    assert "backlinks" in ALLOWED_DS_TYPES
    assert "gbp" in SYNC_MAP and callable(SYNC_MAP["gbp"])
    assert "backlinks" in SYNC_MAP and callable(SYNC_MAP["backlinks"])
    assert _SYNC_FNS["gbp"] is SYNC_MAP["gbp"]
    assert _SYNC_FNS["backlinks"] is SYNC_MAP["backlinks"]


def test_import_gbp_csv_writes_snapshots_and_metrics():
    db = _session()
    client = Client(name="Local Roofer Co")
    db.add(client)
    db.commit()

    csv_text = (
        "Business Name,Search views,Map views,Website clicks,"
        "Direction requests,Phone calls,Direct searches,Discovery searches\n"
        "Local Roofer Co,1200,800,90,60,40,700,500\n"
    )
    stored = import_gbp_csv(db, client.id, csv_text)
    assert stored == 1

    snaps = db.query(GbpSnapshot).filter(GbpSnapshot.client_id == client.id).all()
    assert len(snaps) == 1
    assert snaps[0].search_views == 1200
    assert snaps[0].phone_calls == 40
    assert snaps[0].total_actions == 90 + 60 + 40

    metrics = {
        m.metric_name: m.value
        for m in db.query(MetricDaily)
        .filter(MetricDaily.client_id == client.id, MetricDaily.source == "gbp")
        .all()
    }
    assert metrics.get("search_views") == 1200.0
    assert metrics.get("discovery_searches") == 500.0
    db.close()


def test_import_backlinks_csv_writes_snapshots_and_metrics():
    db = _session()
    client = Client(name="Authority Co")
    db.add(client)
    db.commit()

    csv_text = (
        "Domain,Referring Domains,Total Backlinks,Domain Rating,"
        "New Links (30d),Lost Links (30d),Toxic Score\n"
        "example.com,420,1800,38,12,3,5\n"
        "partner.com,10,20,12,1,0,40\n"
    )
    stored = import_backlinks_csv(db, client.id, csv_text)
    assert stored == 2

    snaps = db.query(BacklinkSnapshot).filter(BacklinkSnapshot.client_id == client.id).all()
    assert len(snaps) == 2

    metrics = {
        m.metric_name: m.value
        for m in db.query(MetricDaily)
        .filter(MetricDaily.client_id == client.id, MetricDaily.source == "backlinks")
        .all()
    }
    assert metrics.get("referring_domains") == 430.0  # 420 + 10
    assert metrics.get("toxic_backlinks") == 20.0  # partner.com only (toxic >= 30)
    assert metrics.get("new_links_30d") == 13.0
    assert metrics.get("lost_links_30d") == 3.0
    db.close()

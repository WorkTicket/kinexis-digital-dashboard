"""site_totals_only must include empty-string dimensions (normalized site totals)."""

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Client, MetricDaily
from app.dimensions import is_site_total_row


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_is_site_total_row_accepts_empty_and_preferred():
    assert is_site_total_row("gsc", "") is True
    assert is_site_total_row("gsc", "device") is True
    assert is_site_total_row("gsc", "query") is False
    assert is_site_total_row("serp", "") is True
    assert is_site_total_row("serp", "query") is False


def test_metrics_list_includes_empty_dim_and_serp():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db

    db = _session()
    client = Client(name="Totals Co")
    db.add(client)
    db.flush()
    today = date.today()
    db.add(
        MetricDaily(
            client_id=client.id,
            source="gsc",
            date=today,
            metric_name="clicks",
            value=42.0,
            dimension_type="",
            dimension_value="",
        )
    )
    db.add(
        MetricDaily(
            client_id=client.id,
            source="serp",
            date=today,
            metric_name="sov_presence",
            value=0.55,
            dimension_type="",
            dimension_value="",
        )
    )
    db.commit()

    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    try:
        tc = TestClient(app)
        res = tc.get(f"/metrics/?client_id={client.id}&site_totals_only=true&days=30")
        assert res.status_code == 200
        rows = res.json()
        names = {(r["source"], r["metric_name"], r.get("dimension_type") or "") for r in rows}
        assert ("gsc", "clicks", "") in names
        assert ("serp", "sov_presence", "") in names
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_db_migrate_raises_on_failure(monkeypatch):
    from app import db_migrate

    def _boom(*_a, **_k):
        raise RuntimeError("fake alembic failure")

    monkeypatch.setattr(db_migrate.command, "upgrade", _boom)
    # Ensure script_location exists so we reach upgrade
    import pytest

    with pytest.raises(RuntimeError, match="migration failed"):
        db_migrate.run_migrations()

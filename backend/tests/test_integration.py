"""Integration tests for critical backend paths.

conftest.py sets DATABASE_URL to a temp file before imports.
Each test fixture creates/tears down tables via SQLAlchemy.
"""

import os
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture
def db_session():
    """Create tables, yield session, drop tables."""
    import app.models as _  # noqa: F401 — ensure all models are loaded into metadata
    from app.database import SessionLocal, engine, Base

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)


class TestClientCRUD:
    def test_create_client(self, db_session):
        from app.models import Client
        client = Client(name="Test Client", industry="tech")
        db_session.add(client)
        db_session.commit()
        db_session.refresh(client)
        assert client.id is not None
        assert client.name == "Test Client"

    def test_archive_client(self, db_session):
        from app.models import Client
        client = Client(name="To Archive")
        db_session.add(client)
        db_session.commit()
        client.archived = True
        db_session.commit()
        assert client.archived is True

    def test_delete_client_cascades(self, db_session):
        from app.models import Client, DataSource, MetricDaily
        client = Client(name="Cascade Delete")
        db_session.add(client)
        db_session.flush()
        cid = client.id
        db_session.add(DataSource(client_id=cid, type="gsc"))
        db_session.add(MetricDaily(
            client_id=cid, source="gsc", date=date(2026, 1, 1),
            metric_name="clicks", value=100.0,
        ))
        db_session.commit()
        db_session.delete(client)
        db_session.commit()
        assert db_session.query(DataSource).filter(DataSource.client_id == cid).count() == 0
        assert db_session.query(MetricDaily).filter(MetricDaily.client_id == cid).count() == 0


class TestInsightPipeline:
    def test_fingerprint_deterministic(self):
        from app.insight_service import insight_fingerprint
        fp1 = insight_fingerprint("ctr_gap", target_url="https://example.com/page")
        fp2 = insight_fingerprint("ctr_gap", target_url="https://example.com/page")
        assert fp1 == fp2 and len(fp1) == 64

    def test_fingerprint_different(self):
        from app.insight_service import insight_fingerprint
        assert insight_fingerprint("ctr_gap", target_url="https://x.com/a") != \
               insight_fingerprint("ctr_gap", target_url="https://x.com/b")

    def test_resolve_stale_insights_no_crash(self, db_session):
        from app.insight_service import resolve_stale_insights
        assert resolve_stale_insights(db_session, 1, set()) >= 0

    def test_prune_noisy_insights_no_crash(self, db_session):
        from app.insight_service import prune_noisy_insights
        assert prune_noisy_insights(db_session, 1) >= 0


class TestAuthMiddleware:
    def test_token_generation(self):
        from app.local_auth import resolve_api_token
        token = resolve_api_token()
        assert isinstance(token, str) and len(token) > 10

    def test_token_comparison(self):
        from app.local_auth import _tokens_equal
        assert _tokens_equal("abc", "abc") is True
        assert _tokens_equal("abc", "def") is False
        assert _tokens_equal("", "abc") is False


class TestAIClient:
    def test_provider_configured(self):
        from app.config import AI_PROVIDER
        assert AI_PROVIDER in ("ollama", "anthropic")

    def test_log_usage_no_crash(self, db_session):
        from app.ai_usage import log_usage
        log_usage(provider="test", model="test-model", purpose="test", client_id=None)

    def test_complete_returns_none_or_str(self, monkeypatch):
        monkeypatch.setattr("app.config.AI_PROVIDER", "ollama")
        from app.ai_client import complete
        result = complete(system="test", user="test", max_tokens=10)
        assert result is None or isinstance(result, str)


class TestFingerprintDedup:
    def test_same_inputs(self):
        from app.action_candidates import compute_task_fingerprint
        fp1 = compute_task_fingerprint(1, "ctr_gap", "query", "https://x.com")
        fp2 = compute_task_fingerprint(1, "ctr_gap", "query", "https://x.com")
        assert fp1 == fp2

    def test_different_playbook(self):
        from app.action_candidates import compute_task_fingerprint
        assert compute_task_fingerprint(1, "ctr_gap", "q", "https://x.com") != \
               compute_task_fingerprint(1, "ctr_opp", "q", "https://x.com")


class TestDimensions:
    def test_known_sources(self):
        from app.dimensions import site_total_dim
        assert site_total_dim("gsc") == "device"
        assert site_total_dim("ga4") == "landing_page"

    def test_unknown_source(self):
        from app.dimensions import site_total_dim
        assert site_total_dim("unknown") is None

    def test_is_site_total_row(self):
        from app.dimensions import is_site_total_row
        assert is_site_total_row("gsc", "device") is True
        assert is_site_total_row("gsc", "query") is False
        assert is_site_total_row("backlinks", "") is True


class TestConfig:
    def test_fernet_key_exists(self):
        from app.config import FERNET_KEY
        assert FERNET_KEY is not None and len(FERNET_KEY) > 10

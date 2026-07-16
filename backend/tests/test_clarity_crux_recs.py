"""Clarity export parsing, CrUX wiring, recommendation lifecycle, pause-campaign rule."""

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Client, Insight, MetricDaily, Recommendation, Task
from app.connectors.clarity import _derive_bounce, _normalize_page, _parse_export_payload
from app.recommendation_service import (
    accept_for_task,
    effectiveness_by_fix_type,
    propose_from_insight,
    verify_from_impact,
)
from app.insights.rule_modules._ga4_ads_rules import _pause_weak_campaigns
from app.routers.clients import ALLOWED_DS_TYPES
from app.scheduler import SYNC_MAP


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_clarity_and_crux_are_syncable():
    assert "clarity" in ALLOWED_DS_TYPES
    assert "crux" in ALLOWED_DS_TYPES
    assert "clarity" in SYNC_MAP
    assert "crux" in SYNC_MAP


def test_clarity_parse_export_page_bounce():
    assert _normalize_page("https://example.com/services/roofing?x=1") == "/services/roofing?x=1"
    assert abs(_derive_bounce(1.0) - 1.0) < 1e-6
    assert abs(_derive_bounce(2.0) - 0.0) < 1e-6

    payload = [
        {
            "metricName": "Traffic",
            "information": [
                {
                    "URL": "https://example.com/landing",
                    "totalSessionCount": "500",
                    "PagesPerSessionPercentage": 1.1,
                }
            ],
        },
        {
            "metricName": "Rage Click Count",
            "information": [{"URL": "/landing", "sessionsCount": "12"}],
        },
    ]
    rows = _parse_export_payload(payload)
    by = {(r["page"], r["metric_name"]): r["value"] for r in rows}
    assert ("/landing", "sessions") in by
    assert by[("/landing", "sessions")] == 500.0
    assert by[("/landing", "bounce_rate")] > 0.8
    assert by[("/landing", "rage_click_count")] == 12.0


def test_recommendation_lifecycle_and_effectiveness():
    db = _session()
    client = Client(name="Learn Co")
    db.add(client)
    db.commit()

    insight = Insight(
        client_id=client.id,
        type="ctr_gap",
        message="CTR gap on brand query",
        recommended_action="Rewrite title/meta",
        severity="high",
        kind="problem",
    )
    db.add(insight)
    db.commit()

    rec = propose_from_insight(db, insight)
    assert rec.status == "proposed"

    task = Task(
        client_id=client.id,
        insight_id=insight.id,
        assigned_to="Alex",
        status="open",
        playbook_pattern="ctr_gap",
    )
    db.add(task)
    db.flush()
    accepted = accept_for_task(db, task)
    assert accepted is not None
    assert accepted.status == "accepted"
    assert accepted.task_id == task.id

    verified = verify_from_impact(db, task.id, "win", lift_pct=18.5)
    assert verified is not None
    assert verified.status == "verified"
    assert verified.outcome == "win"
    assert verified.actual_lift_pct == 18.5
    db.commit()

    eff = effectiveness_by_fix_type(db)
    assert any(r["fix_type"] == "ctr_gap" and r["wins"] == 1 for r in eff)
    db.close()


def test_pause_weak_campaigns_rule():
    db = _session()
    client = Client(name="Ads Co")
    db.add(client)
    db.commit()

    today = date.today()
    for i in range(7):
        d = today - timedelta(days=i)
        db.add(
            MetricDaily(
                client_id=client.id,
                source="google_ads",
                date=d,
                metric_name="cost",
                value=20.0,
                dimension_type="campaign",
                dimension_value="Brand Waste",
            )
        )
        db.add(
            MetricDaily(
                client_id=client.id,
                source="google_ads",
                date=d,
                metric_name="conversions",
                value=0.0,
                dimension_type="campaign",
                dimension_value="Brand Waste",
            )
        )
        db.add(
            MetricDaily(
                client_id=client.id,
                source="google_ads",
                date=d,
                metric_name="clicks",
                value=40.0,
                dimension_type="campaign",
                dimension_value="Brand Waste",
            )
        )
    db.commit()

    findings = _pause_weak_campaigns(client.id, db)
    assert findings
    assert findings[0]["type"] == "pause_weak_campaign"
    assert "Brand Waste" in findings[0]["message"]
    db.close()

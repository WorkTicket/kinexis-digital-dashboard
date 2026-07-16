"""Report library + monthly persist behavior (no AI / full build required for library)."""

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Client, DataSource, MonthlyReport, Task
from app.success_report import get_report_library, persist_monthly_report, _narrative_has_structure
from app.timeutil import utcnow


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_get_report_library_is_cheap_and_lists_saved():
    db = _session()
    client = Client(name="Acme Co", industry="Tech")
    db.add(client)
    db.flush()
    db.add(
        DataSource(
            client_id=client.id,
            type="gsc",
            status="active",
            last_synced_at=utcnow(),
        )
    )
    db.add(
        Task(client_id=client.id, status="done", assigned_to="Self", result_notes="Fixed CTR")
    )
    payload = {
        "client": {"id": client.id, "name": "Acme Co", "industry": "Tech", "brand_color": "#2E5EFF"},
        "narrative": (
            "Headline: Solid month for Acme.\n\n"
            "What changed: Visits up 12%.\n\n"
            "What we did: Completed 2 tasks.\n\n"
            "What we proved: One attributed win.\n\n"
            "What's next: Keep pulling the top lever."
        ),
        "period": {"mode": "monthly", "year": 2026, "month": 6},
        "kpis": [],
        "work": {"tasks_completed": 2, "insights_resolved": 1, "insights_open": 0},
        "impact_wins": [],
        "next_actions": [],
        "generated_at": "2026-07-01",
    }
    db.add(
        MonthlyReport(
            client_id=client.id,
            year=2026,
            month=6,
            payload_json=json.dumps(payload),
            generated_at=utcnow(),
        )
    )
    db.commit()

    lib = get_report_library(db, client.id)
    assert lib.get("error") is None
    assert lib["has_saved"] is True
    assert lib["checklist"]["data_synced"] is True
    assert lib["checklist"]["work_or_proof"] is True
    assert lib["checklist"]["has_saved_report"] is True
    assert lib["checklist"]["narrative_ready"] is True
    assert len(lib["reports"]) == 1
    assert lib["reports"][0]["year"] == 2026
    assert lib["reports"][0]["month"] == 6
    assert lib["reports"][0]["narrative_ready"] is True


def test_narrative_structure_helper():
    good = (
        "Headline: Wins this month.\n"
        "What changed: More visitors.\n"
        "What we did: Shipped fixes.\n"
        "What we proved: Lift on the primary metric.\n"
        "What's next: Continue the plan."
    )
    assert _narrative_has_structure(good) is True
    assert _narrative_has_structure("Just a short blurb without sections.") is False


def test_persist_monthly_report_stores_payload(monkeypatch):
    db = _session()
    client = Client(name="Beta Inc")
    db.add(client)
    db.commit()

    fake = {
        "client": {"id": client.id, "name": "Beta Inc", "industry": "", "brand_color": "#2E5EFF"},
        "period": {"mode": "monthly", "year": 2026, "month": 5, "month_name": "May"},
        "kpis": [],
        "work": {"tasks_completed": 0, "insights_resolved": 0, "insights_open": 0},
        "impact_wins": [],
        "next_actions": [],
        "narrative": "Headline: Quiet month.\n\nWhat changed: Flat.\n\nWhat we did: None.\n\nWhat we proved: None.\n\nWhat's next: Sync data.",
        "generated_at": "2026-06-01",
        "agency": {"name": "Kinexis"},
        "from_cache": False,
    }

    monkeypatch.setattr(
        "app.success_report.build_success_report",
        lambda *args, **kwargs: dict(fake),
    )

    report = persist_monthly_report(db, client.id, 2026, 5)
    assert report.get("monthly_report_id")
    assert report.get("from_cache") is False

    row = (
        db.query(MonthlyReport)
        .filter(MonthlyReport.client_id == client.id, MonthlyReport.year == 2026, MonthlyReport.month == 5)
        .one()
    )
    stored = json.loads(row.payload_json)
    assert "agency" not in stored
    assert "from_cache" not in stored
    assert stored["narrative"].startswith("Headline:")

    # Second persist updates same row
    fake["narrative"] = (
        "Headline: Updated.\n\nWhat changed: A.\n\nWhat we did: B.\n\n"
        "What we proved: C.\n\nWhat's next: D."
    )
    monkeypatch.setattr(
        "app.success_report.build_success_report",
        lambda *args, **kwargs: dict(fake),
    )
    persist_monthly_report(db, client.id, 2026, 5)
    assert db.query(MonthlyReport).filter(MonthlyReport.client_id == client.id).count() == 1

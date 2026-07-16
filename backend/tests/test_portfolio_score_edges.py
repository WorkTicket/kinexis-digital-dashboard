"""Regression tests for health score edge cases (B5 — "0 SCORE" fix).

Covers: score=0 only for truly no-data, score>=1 when any metric or problem exists,
dimension fallback for GSC data, and thin-traffic floors.
"""

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Client, MetricDaily, DataSource, Insight


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_score_zero_only_when_no_data_and_no_problems():
    """Score=0 is reserved for 'never connected' — not 'building baseline.'"""
    db = _session()
    client = Client(name="Zero Test Co")
    db.add(client)
    db.commit()

    from app.portfolio_scoring import compute_client_portfolio_row

    row = compute_client_portfolio_row(
        client,
        db,
        gsc_clicks=0,
        gsc_clicks_prev=0,
        gsc_clicks_prev2=0,
        gsc_impressions=0,
        ga4_sessions=0,
        ga4_sessions_prev=0,
        ga4_conversions=0,
        ga4_conversions_prev=0,
        day_count=7,
        leads=0,
        leads_prev=0,
        revenue=0,
        revenue_prev=0,
        ad_cost=0,
        ad_cost_prev=0,
        open_insights=[],
        open_tasks=[],
        last_sync=None,
        today=date.today(),
    )
    assert row["health_score"] == 0, "No data + no problems → score should be 0"
    assert row["risk"] == "no_data"

    db.close()


def test_score_minimum_one_when_impressions_exist_but_no_clicks():
    """Client with impressions but 0 clicks should get score >= 1, not 0."""
    db = _session()
    client = Client(name="Impression Only Co")
    db.add(client)
    db.commit()

    from app.portfolio_scoring import compute_client_portfolio_row

    row = compute_client_portfolio_row(
        client,
        db,
        gsc_clicks=0,
        gsc_clicks_prev=0,
        gsc_clicks_prev2=0,
        gsc_impressions=4100,
        ga4_sessions=24,
        ga4_sessions_prev=20,
        ga4_conversions=0,
        ga4_conversions_prev=0,
        day_count=7,
        leads=0,
        leads_prev=0,
        revenue=0,
        revenue_prev=0,
        ad_cost=0,
        ad_cost_prev=0,
        open_insights=[],
        open_tasks=[],
        last_sync=None,
        today=date.today(),
    )
    assert row["health_score"] >= 1, (
        f"Client with 4.1K impressions + 24 sessions should get score >= 1, got {row['health_score']}"
    )
    assert row["risk"] != "no_data", "Client with data should not be 'no_data'"

    db.close()


def test_score_minimum_one_when_problems_exist_but_no_metrics():
    """Unresolved problems alone should produce score > 0."""
    db = _session()
    client = Client(name="Problems Only Co")
    db.add(client)
    db.commit()

    insight = Insight(
        client_id=client.id,
        type="decline_alert",
        message="GSC clicks dropped 30%",
        severity="high",
        kind="problem",
        priority_score=80.0,
    )
    db.add(insight)
    db.commit()

    from app.portfolio_scoring import compute_client_portfolio_row

    row = compute_client_portfolio_row(
        client,
        db,
        gsc_clicks=0,
        gsc_clicks_prev=0,
        gsc_clicks_prev2=0,
        gsc_impressions=0,
        ga4_sessions=0,
        ga4_sessions_prev=0,
        ga4_conversions=0,
        ga4_conversions_prev=0,
        day_count=7,
        leads=0,
        leads_prev=0,
        revenue=0,
        revenue_prev=0,
        ad_cost=0,
        ad_cost_prev=0,
        open_insights=[insight],
        open_tasks=[],
        last_sync=None,
        today=date.today(),
    )
    assert row["health_score"] >= 1, (
        f"Client with problems but no metrics should get score >= 1, got {row['health_score']}"
    )
    assert row["risk"] != "no_data"

    db.close()


def test_gsc_fallback_uses_single_alternate_dimension():
    """When device-dimension GSC sums are 0, fallback picks query-dimension only."""
    db = _session()
    client = Client(name="Query Dimension Co")
    db.add(client)
    db.flush()
    ds = DataSource(client_id=client.id, type="gsc", status="active")
    db.add(ds)
    db.commit()

    today = date.today()

    # Write GSC clicks ONLY at query dimension (not device dimension)
    for i in range(7):
        d = today - timedelta(days=7 - i)
        db.add(
            MetricDaily(
                client_id=client.id,
                source="gsc",
                date=d,
                metric_name="clicks",
                value=10.0,
                dimension_type="query",
                dimension_value="roof repair austin",
            )
        )
        db.add(
            MetricDaily(
                client_id=client.id,
                source="gsc",
                date=d,
                metric_name="impressions",
                value=500.0,
                dimension_type="query",
                dimension_value="roof repair austin",
            )
        )
    db.commit()

    from app.portfolio_scoring import build_portfolio_benchmark

    result = build_portfolio_benchmark(db)
    clients = result["clients"]
    assert len(clients) == 1
    client_row = clients[0]

    assert client_row["metrics"]["gsc_clicks"] >= 1, (
        f"Fallback should find clicks at query dimension, got {client_row['metrics']['gsc_clicks']}"
    )
    assert client_row["metrics"]["gsc_impressions"] >= 1, (
        f"Fallback should find impressions at query dimension, got {client_row['metrics']['gsc_impressions']}"
    )
    assert client_row["health_score"] >= 1, (
        f"Score should be >=1 when fallback finds data, got {client_row['health_score']}"
    )

    db.close()


def test_gsc_fallback_does_not_double_count_query_plus_page():
    """Fallback must not SUM across query + page (would 2× inflate health)."""
    db = _session()
    client = Client(name="Multi Dim Co")
    db.add(client)
    db.flush()
    db.add(DataSource(client_id=client.id, type="gsc", status="active"))
    db.commit()

    today = date.today()
    # Portfolio window is today-6..today (7 days) — keep all rows inside it
    for i in range(7):
        d = today - timedelta(days=i)
        for dim, dim_val in (("query", "q1"), ("page", "/services")):
            db.add(
                MetricDaily(
                    client_id=client.id,
                    source="gsc",
                    date=d,
                    metric_name="clicks",
                    value=10.0,
                    dimension_type=dim,
                    dimension_value=dim_val,
                )
            )
            db.add(
                MetricDaily(
                    client_id=client.id,
                    source="gsc",
                    date=d,
                    metric_name="impressions",
                    value=100.0,
                    dimension_type=dim,
                    dimension_value=dim_val,
                )
            )
    db.commit()

    from app.portfolio_scoring import build_portfolio_benchmark

    row = build_portfolio_benchmark(db)["clients"][0]
    # One dimension × 7 days × 10 clicks = 70; double-count would be ~140
    assert row["metrics"]["gsc_clicks"] == 70, (
        f"Expected single-dim fallback 70 clicks, got {row['metrics']['gsc_clicks']}"
    )
    assert row["metrics"]["gsc_impressions"] == 700

    db.close()


def test_score_never_zero_when_ga4_sessions_exist():
    """Minimal GA4 traffic alone should produce score >= 1."""
    db = _session()
    client = Client(name="GA4 Only Co")
    db.add(client)
    db.commit()

    from app.portfolio_scoring import compute_client_portfolio_row

    row = compute_client_portfolio_row(
        client,
        db,
        gsc_clicks=0,
        gsc_clicks_prev=0,
        gsc_clicks_prev2=0,
        gsc_impressions=0,
        ga4_sessions=10,
        ga4_sessions_prev=8,
        ga4_conversions=0,
        ga4_conversions_prev=0,
        day_count=7,
        leads=0,
        leads_prev=0,
        revenue=0,
        revenue_prev=0,
        ad_cost=0,
        ad_cost_prev=0,
        open_insights=[],
        open_tasks=[],
        last_sync=None,
        today=date.today(),
    )
    assert row["health_score"] >= 1, (
        f"Client with 10 GA4 sessions should get score >= 1, got {row['health_score']}"
    )

    db.close()


def test_low_score_without_insights_still_gets_top_action():
    """Volume/efficiency-driven low scores must still surface a raise play."""
    db = _session()
    client = Client(name="Low Volume Co")
    db.add(client)
    db.commit()

    from app.portfolio_scoring import compute_client_portfolio_row

    row = compute_client_portfolio_row(
        client,
        db,
        gsc_clicks=5,
        gsc_clicks_prev=6,
        gsc_clicks_prev2=6,
        gsc_impressions=300,
        ga4_sessions=12,
        ga4_sessions_prev=10,
        ga4_conversions=0,
        ga4_conversions_prev=0,
        day_count=7,
        leads=0,
        leads_prev=0,
        revenue=0,
        revenue_prev=0,
        ad_cost=250,
        ad_cost_prev=200,
        open_insights=[],
        open_tasks=[],
        last_sync=None,
        today=date.today(),
    )
    assert row["health_score"] < 70
    assert row["top_action"] is not None, "Low health with no insights must still get a top action"
    assert row["top_action"]["title"]
    assert row["pillars"]["efficiency"] == 0  # spend with zero leads

    db.close()

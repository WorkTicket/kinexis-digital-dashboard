"""Verify CTR insight rules compute SUM(clicks)/SUM(impressions), not AVG(daily ratios).

This test would have caught Bug #1 from the audit: a single low-volume day with
anomalous CTR skews the average-of-daily-ratios while sum/sum is volume-weighted.
"""

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Client, MetricDaily, DataSource


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def _insert_ctr_test_data(db, client_id: int, query: str) -> dict[str, float]:
    """Insert 30 days of GSC query-dimension data with known daily values.

    Day 1 is an outlier: very low volume (4 impressions) but 50% CTR.
    Days 2-30 are high-volume with a consistent ~3% CTR.

    This creates a deliberate mismatch between AVG(daily_ctr) and SUM(clicks)/SUM(impressions).

    Returns expected values: sum_clicks, sum_impressions, avg_daily_ctr, correct_ctr
    """
    today = date.today()
    start = today - timedelta(days=30)

    total_clicks = 0.0
    total_impressions = 0.0
    daily_ctrs = []

    # Day 1 outlier: 2 clicks / 4 impressions = 50% CTR
    d = today - timedelta(days=30)
    _add_metrics(db, client_id, query, d, clicks=2, impressions=4)
    total_clicks += 2
    total_impressions += 4
    daily_ctrs.append(2 / 4)

    # Days 2-30: high volume, consistent ~3% CTR
    for i in range(1, 30):
        d = today - timedelta(days=30 - i)
        clicks = 30.0 + i
        imps = 1000.0 + i * 20
        _add_metrics(db, client_id, query, d, clicks=clicks, impressions=imps)
        total_clicks += clicks
        total_impressions += imps
        daily_ctrs.append(clicks / imps)

    avg_daily_ctr = sum(daily_ctrs) / len(daily_ctrs)
    correct_ctr = total_clicks / total_impressions if total_impressions > 0 else 0.0

    return {
        "sum_clicks": total_clicks,
        "sum_impressions": total_impressions,
        "avg_daily_ctr": avg_daily_ctr,
        "correct_ctr": correct_ctr,
    }


def _add_metrics(db, client_id: int, query: str, d: date, clicks: float, impressions: float):
    db.add(
        MetricDaily(
            client_id=client_id,
            source="gsc",
            date=d,
            metric_name="clicks",
            value=clicks,
            dimension_type="query",
            dimension_value=query,
        )
    )
    db.add(
        MetricDaily(
            client_id=client_id,
            source="gsc",
            date=d,
            metric_name="impressions",
            value=impressions,
            dimension_type="query",
            dimension_value=query,
        )
    )
    # Store Google's per-day CTR ratio (what the GSC connector actually writes)
    daily_ctr = clicks / impressions if impressions > 0 else 0.0
    db.add(
        MetricDaily(
            client_id=client_id,
            source="gsc",
            date=d,
            metric_name="ctr",
            value=daily_ctr,
            dimension_type="query",
            dimension_value=query,
        )
    )
    # Position ~5.0 — expected CTR benchmark is 5%
    db.add(
        MetricDaily(
            client_id=client_id,
            source="gsc",
            date=d,
            metric_name="position",
            value=5.0,
            dimension_type="query",
            dimension_value=query,
        )
    )


def test_ctr_insight_uses_sum_divided_by_sum():
    """The CTR gap insight must compute actual_ctr = SUM(clicks)/SUM(impressions).

    Insert data where avg(daily_ctr) differs materially from sum/sum CTR.
    Then run the rule and extract the CTR from the insight message.
    """
    db = _session()
    client = Client(name="CTR Test Co")
    db.add(client)
    db.flush()

    ds = DataSource(client_id=client.id, type="gsc", status="active")
    db.add(ds)
    db.commit()

    query = "roof repair austin"
    expected = _insert_ctr_test_data(db, client.id, query)
    db.commit()

    # Verify the data creates a deliberate mismatch
    assert expected["avg_daily_ctr"] != pytest.approx(expected["correct_ctr"], rel=0.01), (
        f"Test data must create a mismatch. "
        f"avg_daily_ctr={expected['avg_daily_ctr']:.4f} vs "
        f"correct_ctr={expected['correct_ctr']:.4f}"
    )

    from app.insights.rules import _gsc_ctr_findings

    insights = _gsc_ctr_findings(client.id, db)

    assert len(insights) > 0, (
        f"Expected at least one CTR insight for query '{query}' "
        f"with {expected['sum_impressions']:.0f} impressions"
    )

    insight = insights[0]
    message = insight.get("message", "")

    # Extract the CTR percentage from the insight message
    # Format: '...has CTR 3.2%...' or '...has CTR 0.032...' or '...CTR 3.2%...'
    import re

    ctr_match = re.search(r"(?:CTR|has CTR)\s+([\d.]+)%", message)
    if not ctr_match:
        ctr_match = re.search(r"CTR\s+([\d.]+)%", message)
    if not ctr_match:
        ctr_match = re.search(r"(?:ctr|CTR)\s+([\d.]+)", message)

    assert ctr_match is not None, f"Could not extract CTR % from message: {message}"

    displayed_ctr_pct = float(ctr_match.group(1))

    correct_ctr_pct = expected["correct_ctr"] * 100

    # The displayed CTR should match sum/sum (within rounding tolerance)
    assert displayed_ctr_pct == pytest.approx(correct_ctr_pct, rel=0.05), (
        f"CTR in insight message ({displayed_ctr_pct:.2f}%) must match "
        f"SUM(clicks)/SUM(impressions) = {correct_ctr_pct:.2f}%, "
        f"NOT avg(daily ratios) = {expected['avg_daily_ctr'] * 100:.2f}%"
    )

    db.close()


import pytest


def test_avg_daily_ctr_differs_from_sum_sum():
    """Sanity check: the test fixture produces a real divergence between methods."""
    expected = {
        "sum_clicks": 2.0 + sum(30.0 + i for i in range(1, 30)),
        "sum_impressions": 4.0 + sum(1000.0 + i * 20 for i in range(1, 30)),
    }
    expected["correct_ctr"] = (
        expected["sum_clicks"] / expected["sum_impressions"]
        if expected["sum_impressions"] > 0
        else 0
    )

    daily_ctrs = [2 / 4]  # Day 1: 50%
    for i in range(1, 30):
        daily_ctrs.append((30 + i) / (1000 + i * 20))
    expected["avg_daily_ctr"] = sum(daily_ctrs) / len(daily_ctrs)

    # The two methods should give meaningfully different results
    assert expected["avg_daily_ctr"] > expected["correct_ctr"], (
        f"Outlier Day 1 (50% CTR on 4 impressions) should inflate avg_daily_ctr "
        f"({expected['avg_daily_ctr']:.4f}) above correct_ctr ({expected['correct_ctr']:.4f})"
    )


def test_ctr_insight_filters_low_impression_query():
    """Queries below the minimum impression threshold should not generate insights."""
    db = _session()
    client = Client(name="Low Impressions Co")
    db.add(client)
    db.flush()

    ds = DataSource(client_id=client.id, type="gsc", status="active")
    db.add(ds)
    db.commit()

    today = date.today()
    query = "rare long tail search phrase"
    for i in range(30):
        d = today - timedelta(days=30 - i)
        _add_metrics(db, client.id, query, d, clicks=0.2, impressions=5)

    db.commit()

    from app.insights.rules import _gsc_ctr_findings

    insights = _gsc_ctr_findings(client.id, db)
    assert len(insights) == 0, (
        "Query with <250 impressions/30d should not trigger CTR insight"
    )

    db.close()

"""Integration tests for remaining insight rules — content opportunity, decline alert,
zero-click, CRO, Cloudflare error spike, PageSpeed, Bing gap, ads/leads/revenue leaks,
and page content issues.

Each test inserts synthetic MetricDaily rows with unique dates to avoid the
UNIQUE constraint on (client_id, source, date, metric_name, dimension_type, dimension_value).
"""

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Client, MetricDaily, DataSource, PageSnapshot
from app.timeutil import utcnow


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def _insert_rows(db, rows: list[dict]):
    """Insert MetricDaily rows with unique (date, metric, dim_value) per batch."""
    for r in rows:
        db.add(
            MetricDaily(
                client_id=r["client_id"],
                source=r["source"],
                date=r["date"],
                metric_name=r["metric_name"],
                value=r["value"],
                dimension_type=r.get("dimension_type", ""),
                dimension_value=r.get("dimension_value", ""),
            )
        )


def _daily_range(start: date, days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(days)]


# ── Content Opportunity ────────────────────────────────────────────────

def test_content_opportunity_fires_at_pos_11_20_with_rising_impressions():
    db = _session()
    client = Client(name="Content Opp Co")
    db.add(client)
    db.flush()
    cid = client.id

    today = date.today()
    rows = []
    query = "roof repair austin"
    # Prevent thin_traffic: add GSC device clicks and GA4 sessions
    for d in _daily_range(today - timedelta(days=7), 7):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 10, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
        rows.append(
            {"client_id": cid, "source": "ga4", "date": d, "metric_name": "sessions",
             "value": 20, "dimension_type": "landing_page", "dimension_value": "/"}
        )
    # Last week: 7 days × 20 = 140 impressions
    for d in _daily_range(today - timedelta(days=14), 7):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "impressions",
             "value": 20, "dimension_type": "query", "dimension_value": query}
        )
    # This week: 7 days × 35 = 245 impressions (+75% WoW)
    for d in _daily_range(today - timedelta(days=7), 7):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "impressions",
             "value": 35, "dimension_type": "query", "dimension_value": query}
        )
    # Days -30 to -15: fill to clear 30d floor (250)
    for d in _daily_range(today - timedelta(days=30), 16):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "impressions",
             "value": 15, "dimension_type": "query", "dimension_value": query}
        )
    # Position ~15 every day for 30 days
    for d in _daily_range(today - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "position",
             "value": 15, "dimension_type": "query", "dimension_value": query}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _gsc_position_opportunity

    results = _gsc_position_opportunity(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "content_opportunity"
    db.close()


def test_content_opportunity_skips_below_threshold():
    db = _session()
    client = Client(name="Low Opp Co")
    db.add(client)
    db.flush()
    cid = client.id

    rows = []
    query = "tiny query"
    for d in _daily_range(date.today() - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "impressions",
             "value": 3, "dimension_type": "query", "dimension_value": query}
        )
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "position",
             "value": 15, "dimension_type": "query", "dimension_value": query}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _gsc_position_opportunity

    results = _gsc_position_opportunity(cid, db)
    assert len(results) == 0
    db.close()


# ── Decline Alert ──────────────────────────────────────────────────────

def test_decline_alert_fires_on_25pct_drop():
    db = _session()
    client = Client(name="Decline Co")
    db.add(client)
    db.flush()
    cid = client.id

    today = date.today()
    rows = []
    # Last week (days -14 to -8): 200 total clicks → ~28/day
    for d in _daily_range(today - timedelta(days=14), 7):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 28, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
    # This week (days -7 to -1): 140 total clicks → ~20/day (-30%)
    for d in _daily_range(today - timedelta(days=7), 7):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 20, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _gsc_decline_alert

    results = _gsc_decline_alert(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "decline_alert"
    assert results[0]["severity"] == "high"
    db.close()


def test_decline_alert_skips_small_sample():
    db = _session()
    client = Client(name="Tiny Decline Co")
    db.add(client)
    db.flush()
    cid = client.id

    today = date.today()
    rows = []
    for d in _daily_range(today - timedelta(days=14), 7):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 1, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
    for d in _daily_range(today - timedelta(days=7), 7):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 0, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _gsc_decline_alert

    results = _gsc_decline_alert(cid, db)
    assert len(results) == 0
    db.close()


# ── Zero-Click Alert ───────────────────────────────────────────────────

def test_zero_click_fires_with_1000_impressions_no_clicks():
    db = _session()
    client = Client(name="Zero Click Co")
    db.add(client)
    db.flush()
    cid = client.id

    rows = []
    query = "roof repair austin"
    for d in _daily_range(date.today() - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "impressions",
             "value": 50, "dimension_type": "query", "dimension_value": query}
        )
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 0, "dimension_type": "query", "dimension_value": query}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _gsc_zero_click_alert

    results = _gsc_zero_click_alert(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "zero_click_alert"
    db.close()


def test_zero_click_skips_below_1000_impressions():
    db = _session()
    client = Client(name="Low Impr Zero Co")
    db.add(client)
    db.flush()
    cid = client.id

    rows = []
    query = "small query"
    for d in _daily_range(date.today() - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "impressions",
             "value": 10, "dimension_type": "query", "dimension_value": query}
        )
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 0, "dimension_type": "query", "dimension_value": query}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _gsc_zero_click_alert

    results = _gsc_zero_click_alert(cid, db)
    assert len(results) == 0
    db.close()


# ── GA4 CRO Opportunity ────────────────────────────────────────────────

def test_cro_fires_for_high_traffic_low_cvr():
    db = _session()
    client = Client(name="CRO Leak Co")
    db.add(client)
    db.flush()
    cid = client.id

    rows = []
    today = date.today()
    # Page A: 500 sessions, 1 conversion (0.2% CVR) — above avg sessions, below avg CVR
    for d in _daily_range(today - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "ga4", "date": d, "metric_name": "sessions",
             "value": 17, "dimension_type": "landing_page", "dimension_value": "/page-a"}
        )
    rows.append(
        {"client_id": cid, "source": "ga4", "date": today - timedelta(days=15), "metric_name": "key_events",
         "value": 1, "dimension_type": "landing_page", "dimension_value": "/page-a"}
    )
    # Page B: 200 sessions, 8 conversions (4% CVR) — avg puller
    for d in _daily_range(today - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "ga4", "date": d, "metric_name": "sessions",
             "value": 7, "dimension_type": "landing_page", "dimension_value": "/page-b"}
        )
    for i in range(8):
        rows.append(
            {"client_id": cid, "source": "ga4", "date": today - timedelta(days=i + 1), "metric_name": "key_events",
             "value": 1, "dimension_type": "landing_page", "dimension_value": "/page-b"}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _ga4_cro_opportunity

    results = _ga4_cro_opportunity(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "cro_opportunity"
    assert "/page-a" in results[0]["message"]
    db.close()


def test_cro_skips_low_traffic():
    db = _session()
    client = Client(name="Low CRO Co")
    db.add(client)
    db.flush()
    cid = client.id

    rows = []
    # Add historical conversion data so tracking-integrity check passes
    rows.append(
        {"client_id": cid, "source": "ga4", "date": date.today() - timedelta(days=60),
         "metric_name": "key_events", "value": 1, "dimension_type": "landing_page",
         "dimension_value": "/page-a"}
    )
    for d in _daily_range(date.today() - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "ga4", "date": d, "metric_name": "sessions",
             "value": 5, "dimension_type": "landing_page", "dimension_value": "/page-a"}
        )
        rows.append(
            {"client_id": cid, "source": "ga4", "date": d, "metric_name": "key_events",
             "value": 0, "dimension_type": "landing_page", "dimension_value": "/page-a"}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _ga4_cro_opportunity

    results = _ga4_cro_opportunity(cid, db)
    assert len(results) == 0
    db.close()


# ── PageSpeed Opportunity ──────────────────────────────────────────────

def test_pagespeed_urgent_below_50():
    db = _session()
    client = Client(name="Slow Co")
    db.add(client)
    db.flush()
    cid = client.id

    db.add(
        MetricDaily(
            client_id=cid, source="pagespeed", date=date.today() - timedelta(days=1),
            metric_name="performance_score_mobile", value=42,
            dimension_type="", dimension_value="https://example.com/slow-page",
        )
    )
    db.commit()

    from app.insights.rules import _pagespeed_opportunity

    results = _pagespeed_opportunity(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "pagespeed_urgent"
    db.close()


def test_pagespeed_improve_50_to_69():
    db = _session()
    client = Client(name="Ok Co")
    db.add(client)
    db.flush()
    cid = client.id

    db.add(
        MetricDaily(
            client_id=cid, source="pagespeed", date=date.today() - timedelta(days=1),
            metric_name="performance_score_mobile", value=58,
            dimension_type="", dimension_value="https://example.com/ok-page",
        )
    )
    db.commit()

    from app.insights.rules import _pagespeed_opportunity

    results = _pagespeed_opportunity(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "pagespeed_improve"
    db.close()


def test_pagespeed_no_insight_above_70():
    db = _session()
    client = Client(name="Fast Co")
    db.add(client)
    db.flush()
    cid = client.id

    db.add(
        MetricDaily(
            client_id=cid, source="pagespeed", date=date.today() - timedelta(days=1),
            metric_name="performance_score_mobile", value=75,
            dimension_type="", dimension_value="https://example.com/fast-page",
        )
    )
    db.commit()

    from app.insights.rules import _pagespeed_opportunity

    results = _pagespeed_opportunity(cid, db)
    assert len(results) == 0
    db.close()


# ── Bing Gap ───────────────────────────────────────────────────────────

def test_bing_opportunity_zero_clicks():
    db = _session()
    client = Client(name="Bing Opp Co")
    db.add(client)
    db.flush()
    cid = client.id

    ds = DataSource(client_id=cid, type="bing", status="active")
    db.add(ds)
    rows = []
    for d in _daily_range(date.today() - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 10, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _bing_gsc_gap

    results = _bing_gsc_gap(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] in ("bing_opportunity", "bing_underperform")
    db.close()


def test_bing_skips_without_datasource():
    db = _session()
    client = Client(name="No Bing Co")
    db.add(client)
    db.flush()
    cid = client.id

    rows = []
    for d in _daily_range(date.today() - timedelta(days=30), 30):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 10, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _bing_gsc_gap

    results = _bing_gsc_gap(cid, db)
    assert len(results) == 0
    db.close()


# ── Ads Spend Low Leads ────────────────────────────────────────────────

def test_ads_fires_high_spend_low_leads():
    db = _session()
    client = Client(name="Ads Waste Co")
    db.add(client)
    db.flush()
    cid = client.id

    rows = []
    today = date.today()
    # Add historical conversion data so tracking-integrity check passes
    rows.append(
        {"client_id": cid, "source": "hubspot", "date": today - timedelta(days=45),
         "metric_name": "leads", "value": 1, "dimension_type": "", "dimension_value": ""}
    )
    for d in _daily_range(today - timedelta(days=7), 7):
        rows.append(
            {"client_id": cid, "source": "google_ads", "date": d, "metric_name": "cost",
             "value": 100, "dimension_type": "campaign", "dimension_value": "camp1"}
        )
        rows.append(
            {"client_id": cid, "source": "hubspot", "date": d, "metric_name": "leads",
             "value": 0, "dimension_type": "", "dimension_value": ""}
        )
        rows.append(
            {"client_id": cid, "source": "ga4", "date": d, "metric_name": "sessions",
             "value": 10, "dimension_type": "landing_page", "dimension_value": "/landing"}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _ads_spend_low_leads

    results = _ads_spend_low_leads(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "ads_spend_low_leads"
    db.close()


def test_ads_skips_low_spend():
    db = _session()
    client = Client(name="Low Spend Co")
    db.add(client)
    db.flush()
    cid = client.id

    rows = []
    for d in _daily_range(date.today() - timedelta(days=7), 7):
        rows.append(
            {"client_id": cid, "source": "google_ads", "date": d, "metric_name": "cost",
             "value": 5, "dimension_type": "campaign", "dimension_value": "camp1"}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _ads_spend_low_leads

    results = _ads_spend_low_leads(cid, db)
    assert len(results) == 0
    db.close()


# ── Leads Revenue Leak ─────────────────────────────────────────────────

def test_leads_revenue_fires_leads_up_revenue_flat():
    db = _session()
    client = Client(name="Leads Leak Co")
    db.add(client)
    db.flush()
    cid = client.id

    today = date.today()
    rows = []
    # Prev 14d: 10 leads
    for d in _daily_range(today - timedelta(days=28), 14):
        rows.append(
            {"client_id": cid, "source": "hubspot", "date": d, "metric_name": "leads",
             "value": 1, "dimension_type": "", "dimension_value": ""}
        )
        rows.append(
            {"client_id": cid, "source": "hubspot", "date": d, "metric_name": "revenue",
             "value": 10, "dimension_type": "", "dimension_value": ""}
        )
    # This 14d: 18 leads (+28% vs 14), same revenue, closed_won <= 1
    for d in _daily_range(today - timedelta(days=14), 14):
        rows.append(
            {"client_id": cid, "source": "hubspot", "date": d, "metric_name": "leads",
             "value": 1.3, "dimension_type": "", "dimension_value": ""}
        )
        rows.append(
            {"client_id": cid, "source": "hubspot", "date": d, "metric_name": "revenue",
             "value": 10, "dimension_type": "", "dimension_value": ""}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _leads_revenue_leak

    results = _leads_revenue_leak(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "leads_revenue_leak"
    db.close()


# ── Organic Leads Leak ─────────────────────────────────────────────────

def test_organic_fires_clicks_up_leads_flat():
    db = _session()
    client = Client(name="Organic Leak Co")
    db.add(client)
    db.flush()
    cid = client.id

    today = date.today()
    rows = []
    # Past 14d: 100 clicks
    for d in _daily_range(today - timedelta(days=28), 14):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 8, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
        rows.append(
            {"client_id": cid, "source": "hubspot", "date": d, "metric_name": "leads",
             "value": 1, "dimension_type": "", "dimension_value": ""}
        )
    # This 14d: 120 clicks (+20%), leads flat
    for d in _daily_range(today - timedelta(days=14), 14):
        rows.append(
            {"client_id": cid, "source": "gsc", "date": d, "metric_name": "clicks",
             "value": 9, "dimension_type": "device", "dimension_value": "DESKTOP"}
        )
        rows.append(
            {"client_id": cid, "source": "hubspot", "date": d, "metric_name": "leads",
             "value": 1, "dimension_type": "", "dimension_value": ""}
        )
    _insert_rows(db, rows)
    db.commit()

    from app.insights.rules import _organic_leads_leak

    results = _organic_leads_leak(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "organic_leads_leak"
    db.close()


# ── Page Content Issues ────────────────────────────────────────────────

def test_crawl_detects_broken_pages():
    db = _session()
    client = Client(name="Broken Co")
    db.add(client)
    db.flush()
    cid = client.id

    snap = PageSnapshot(
        client_id=cid,
        url="https://example.com/dead-page",
        status_code=404,
        fetched_at=utcnow(),
    )
    db.add(snap)
    db.commit()

    from app.insights.rules import _page_content_issues

    results = _page_content_issues(cid, db)
    assert len(results) >= 1
    assert results[0]["type"] == "crawl_broken_pages"
    db.close()


def test_crawl_detects_missing_title():
    db = _session()
    client = Client(name="No Title Co")
    db.add(client)
    db.flush()
    cid = client.id

    snap = PageSnapshot(
        client_id=cid,
        url="https://example.com/about",
        status_code=200,
        title="",
        meta_description="We do stuff",
        h1="About Us",
        word_count=500,
        fetched_at=utcnow(),
    )
    db.add(snap)
    db.commit()

    from app.insights.rules import _page_content_issues

    results = _page_content_issues(cid, db)
    types = [r["type"] for r in results]
    assert "crawl_missing_title" in types
    db.close()


def test_crawl_detects_thin_content():
    db = _session()
    client = Client(name="Thin Co")
    db.add(client)
    db.flush()
    cid = client.id

    snap = PageSnapshot(
        client_id=cid,
        url="https://example.com/thin",
        status_code=200,
        title="Thin Page",
        meta_description="Short page",
        h1="Thin",
        word_count=50,
        fetched_at=utcnow(),
    )
    db.add(snap)
    db.commit()

    from app.insights.rules import _page_content_issues

    results = _page_content_issues(cid, db)
    types = [r["type"] for r in results]
    assert "crawl_thin_content" in types
    db.close()

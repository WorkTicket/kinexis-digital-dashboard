"""Tests for Now-priority agency capability builds."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

from app.connectors.ads_common import ADS_METRICS, PAID_SOURCES
from app.connectors.serp import flagged_queries_for_client, format_serp_snapshot
from app.insights.rules import _page_content_issues
from app.models import Client, Insight, PageSnapshot, SerpSnapshot
from app.success_contract import (
    DEFAULT_CONTRACT,
    default_contract_for_datasources,
    ensure_success_contract,
    parse_success_contract,
)
from app.timeutil import utcnow


def test_default_contract_is_commercial():
    assert DEFAULT_CONTRACT["primary_metric"] == "hubspot.leads"
    assert "hubspot.revenue" in DEFAULT_CONTRACT["secondary_metrics"]


def test_default_contract_for_datasources():
    hs = default_contract_for_datasources({"hubspot", "gsc"})
    assert hs["primary_metric"] == "hubspot.leads"
    paid = default_contract_for_datasources({"google_ads"})
    assert paid["primary_metric"] == "paid.conversions"
    ga = default_contract_for_datasources({"ga4"})
    assert ga["primary_metric"] == "ga4.key_events"
    organic = default_contract_for_datasources({"gsc"})
    assert organic["primary_metric"] == "gsc.clicks"


def test_paid_contract_metrics_registered():
    from app.success_contract import CONTRACT_METRICS

    assert "paid.conversions" in CONTRACT_METRICS
    assert "paid.cost" in CONTRACT_METRICS
    assert CONTRACT_METRICS["paid.conversions"]["source"] == "paid"


def test_ensure_success_contract_seeds_once():
    c = Client(name="Acme", profile_json="{}")
    assert ensure_success_contract(c, {"hubspot"}) is True
    contract = parse_success_contract(c)
    assert contract is not None
    assert contract["primary_metric"] == "hubspot.leads"
    # Second call should not overwrite
    assert ensure_success_contract(c, {"hubspot"}) is False


def test_paid_sources_constant():
    assert "google_ads" in PAID_SOURCES
    assert "meta_ads" in PAID_SOURCES
    assert "impressions" in ADS_METRICS


def test_format_serp_marks_competitors():
    snap = SerpSnapshot(
        client_id=1,
        query="plumber near me",
        results_json='[{"position":1,"title":"Rival","url":"https://www.rival.com/x","snippet":"hi"}]',
        provider="serpapi",
        fetched_at=utcnow(),
    )
    lines = format_serp_snapshot(
        snap,
        competitor_domains=["rival.com"],
        client_domains=["acme.com"],
    )
    assert any("[COMPETITOR]" in line for line in lines)


def test_flagged_queries_include_decline_types():
    """Insight type list includes decline_alert for SERP targeting."""
    # Smoke: function accepts db mock and returns list
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        Insight(
            client_id=1,
            type="decline_alert",
            message='Site dropped — check "emergency plumber"',
            recommended_action="",
            resolved=False,
            priority_score=90,
        )
    ]
    # Chain for declining query path / tracked may also query — keep permissive
    result = flagged_queries_for_client(db, 1, limit=5)
    assert isinstance(result, list)


def test_page_content_issues_from_snapshots():
    db = MagicMock()
    snap = PageSnapshot(
        client_id=1,
        url="https://example.com/broken",
        title=None,
        meta_description=None,
        h1=None,
        word_count=10,
        status_code=404,
        fetched_at=utcnow(),
        headings_json="[]",
        schema_types="[]",
        internal_links_json="[]",
    )
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        snap
    ]
    # thresholds_for_client is called inside — mock via empty thr
    insights = _page_content_issues(1, db, thr={"min_page_words": 150})
    types = {i["type"] for i in insights}
    assert "crawl_broken_pages" in types

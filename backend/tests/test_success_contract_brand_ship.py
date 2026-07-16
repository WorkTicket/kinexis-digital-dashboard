"""Tests for Success Contract, brand queries, and ship-log parsing."""

from app.brand_queries import is_brand_query, filter_query_scope, brand_terms_for_client
from app.ship_log import extract_handoff_blocks, _parse_simple_yaml
from app.success_contract import parse_success_contract, CONTRACT_METRICS
from app.models import Client


def test_is_brand_query_contains():
    terms = ["Acme Plumbing", "acme"]
    assert is_brand_query("acme plumbing near me", terms)
    assert is_brand_query("best acme reviews", terms)
    assert not is_brand_query("emergency plumber chicago", terms)


def test_is_brand_query_short_token_boundary():
    assert is_brand_query("xy tools", ["xy"])
    assert not is_brand_query("xyz tools", ["xy"])  # not a word boundary match


def test_filter_query_scope():
    terms = ["BrandCo"]
    assert filter_query_scope("BrandCo login", terms, "brand")
    assert not filter_query_scope("BrandCo login", terms, "non_brand")
    assert filter_query_scope("other query", terms, "non_brand")
    assert filter_query_scope("anything", terms, "all")


def test_brand_terms_from_client_name_and_profile():
    c = Client(name="Acme Widgets LLC", profile_json='{"brand_terms": "Acme, Widgets Inc"}')
    terms = brand_terms_for_client(c)
    lower = [t.lower() for t in terms]
    assert "acme" in lower
    assert any("widget" in t for t in lower)


def test_parse_success_contract():
    c = Client(
        name="Test",
        profile_json=(
            '{"success_contract": {"primary_metric": "hubspot.leads", '
            '"target_delta_pct": 25, "window_days": 60, '
            '"secondary_metrics": ["gsc.clicks"]}}'
        ),
    )
    contract = parse_success_contract(c)
    assert contract is not None
    assert contract["primary_metric"] == "hubspot.leads"
    assert contract["target_delta_pct"] == 25
    assert contract["window_days"] == 60
    assert "gsc.clicks" in contract["secondary_metrics"]
    assert contract["label"] == CONTRACT_METRICS["hubspot.leads"]["label"]


def test_parse_success_contract_unset():
    c = Client(name="Test", profile_json='{"goals": "grow"}')
    assert parse_success_contract(c) is None


def test_success_contract_sample_gate_insufficient_data():
    """Low sample n → status insufficient_data (not ahead/behind on noise)."""
    from datetime import date, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models import MetricDaily
    from app.success_contract import evaluate_success_contract

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = Session()

    c = Client(
        name="Thin Traffic",
        profile_json=(
            '{"success_contract": {"primary_metric": "gsc.clicks", '
            '"target_delta_pct": 20, "window_days": 30, '
            '"baseline_mode": "prior_period"}}'
        ),
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    today = date.today()
    # Tiny totals (15/window) well below gsc clicks min-n (30)
    for i in range(60):
        d = today - timedelta(days=i)
        db.add(
            MetricDaily(
                client_id=c.id,
                source="gsc",
                date=d,
                metric_name="clicks",
                value=0.5 if i < 30 else 0.4,
                dimension_type="device",
                dimension_value="",
            )
        )
    db.commit()

    result = evaluate_success_contract(db, c)
    assert result["configured"] is True
    assert result["status"] == "insufficient_data"
    assert result["progress"]["change_pct"] is None
    assert result["progress"]["sample_confidence"] in ("sample_too_small", "directional")
    db.close()


def test_parse_simple_yaml_multiline():
    block = """fix_id: 42
title: Fix CTR
changes_made: |
  Updated title on /pricing
  Added FAQ schema
day0_baseline: |
  CTR was 1.1%
"""
    data = _parse_simple_yaml(block)
    assert data["fix_id"] == "42"
    assert "Updated title" in data["changes_made"]
    assert "CTR was" in data["day0_baseline"]


def test_extract_handoff_blocks_fenced():
    md = """
# Brief
```yaml
fix_id: 7
title: Meta rewrite
changes_made: |
  Shipped meta changes
day0_baseline: |
  Baseline notes
```
"""
    blocks = extract_handoff_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["fix_id"] == "7"
    assert "Shipped" in blocks[0]["changes_made"]

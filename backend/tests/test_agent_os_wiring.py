"""Regression tests for senior DM + eng agent-OS wiring."""

from app.competitor_domains import parse_competitor_domains
from app.models import Client


def test_parse_competitor_domains_from_profile():
    client = Client(
        name="Acme Roofing",
        profile_json='{"competitors": "rivalroof.com, https://www.otherco.com/about"}',
    )
    domains = parse_competitor_domains(client)
    assert "rivalroof.com" in domains
    assert "otherco.com" in domains


def test_recommendation_lift_key_matches_summary():
    """Auto-recheck must read avg_primary_metric_change (not primary_lift_pct)."""
    import inspect
    from app import impact_tracker

    src = inspect.getsource(impact_tracker.run_due_impact_rechecks)
    assert 'summary.get("avg_primary_metric_change")' in src
    assert 'summary.get("primary_lift_pct")' not in src


def test_new_insight_types_are_problems():
    from app.insight_scoring import default_kind

    assert default_kind("ads_search_term_waste") == "problem"
    assert default_kind("meta_placement_waste") == "problem"
    assert default_kind("meta_creative_fatigue") == "problem"
    assert default_kind("sov_loss") == "problem"


def test_metrics_service_is_portfolio_facade():
    from app import metrics_service, portfolio_scoring

    assert callable(metrics_service.sum_metric)
    assert callable(portfolio_scoring.metric_sum)


def test_sov_writer_and_experiment_model_importable():
    from app.connectors.sov import write_sov_presence, compute_sov_from_snaps
    from app.models import Experiment

    assert callable(write_sov_presence)
    assert callable(compute_sov_from_snaps)
    assert Experiment.__tablename__ == "experiments"


def test_meta_rules_registered():
    from app.insights import rules

    assert hasattr(rules, "_meta_placement_waste")
    assert hasattr(rules, "_meta_creative_fatigue")
    assert "_meta_placement_waste" in rules.__all__
    assert "_meta_creative_fatigue" in rules.__all__

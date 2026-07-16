"""Pure helpers + scoring tests (no DB required)."""

import json

from app.insight_scoring import score_insight, effort_label, why_it_matters, score_with_impact
from app.impact_math import (
    auto_outcome_from_avg_change,
    change_pct,
    confidence_from_values,
    confidence_from_variance,
)
from app.insight_thresholds import DEFAULT_THRESHOLDS, merge_thresholds
from app.outcome_memory import format_playbook_track_record
from app.connectors.serp import format_serp_snapshot, serp_enabled
from app.models import SerpSnapshot


def test_score_insight_high_beats_low():
    assert score_insight("high", "ctr_opportunity") > score_insight("low", "ctr_opportunity")


def test_score_insight_low_effort_boosts():
    # ctr is low effort (1.0), pagespeed_urgent is high effort (0.45)
    assert score_insight("high", "ctr_opportunity") > score_insight("high", "pagespeed_urgent")


def test_score_with_impact_boosts_large_gaps():
    base = score_insight("medium", "ctr_opportunity")
    boosted = score_with_impact("medium", "ctr_opportunity", impact_weight=80)
    assert boosted >= base


def test_effort_label():
    assert effort_label("ctr_opportunity") == "low"
    assert effort_label("pagespeed_urgent") == "high"


def test_why_it_matters():
    assert "titles" in why_it_matters("ctr_opportunity").lower() or "SERP" in why_it_matters("ctr_opportunity") or "click" in why_it_matters("ctr_opportunity").lower()


def test_change_pct():
    assert change_pct(100, 120) == 20.0
    assert change_pct(0, 10) is None
    assert change_pct(50, 40) == -20.0


def test_confidence_from_values():
    assert confidence_from_values(5, 6) == "low"
    assert confidence_from_values(50, 60) == "medium"
    assert confidence_from_values(500, 600) == "high"


def test_auto_outcome_from_avg_change():
    assert auto_outcome_from_avg_change(5) == "win"
    assert auto_outcome_from_avg_change(-5) == "loss"
    assert auto_outcome_from_avg_change(0.5) == "flat"
    assert auto_outcome_from_avg_change(2.1) == "win"
    assert auto_outcome_from_avg_change(-2.1) == "loss"


def test_confidence_from_variance_within_noise_is_low():
    # High day-to-day noise (~±20); a +5 lift is within 1 stdev
    history = [100.0 + (20 if i % 2 == 0 else -20) for i in range(30)]
    assert confidence_from_variance(100, 105, history) == "low"


def test_confidence_from_variance_large_move_is_high():
    history = [100.0] * 20 + [102.0] * 10
    assert confidence_from_variance(100, 150, history) in ("medium", "high")


def test_confidence_from_variance_short_history_falls_back():
    assert confidence_from_variance(5, 6, [1, 2, 3]) == "low"
    assert confidence_from_variance(500, 600, list(range(10))) == "high"


def test_format_playbook_track_record():
    lines = format_playbook_track_record(
        {"ctr_gap": {"wins": 4, "losses": 1, "flat": 0, "total": 5}}
    )
    assert any("ctr_gap" in line and "4 wins" in line for line in lines)
    assert format_playbook_track_record({}) == []


def test_format_serp_snapshot():
    snap = SerpSnapshot(
        client_id=1,
        query="roof repair austin",
        results_json=json.dumps(
            [
                {
                    "position": 1,
                    "title": "Best Roofers",
                    "url": "https://a.example",
                    "snippet": "Licensed and insured",
                }
            ]
        ),
        provider="serpapi",
    )
    lines = format_serp_snapshot(snap)
    assert any("LIVE SERP" in line for line in lines)
    assert any("Best Roofers" in line for line in lines)
    assert format_serp_snapshot(None) == []


def test_serp_enabled_requires_provider_and_key(monkeypatch):
    import app.config as cfg

    monkeypatch.setattr(cfg, "SERP_PROVIDER", "")
    monkeypatch.setattr(cfg, "SERP_API_KEY", "x")
    assert serp_enabled() is False
    monkeypatch.setattr(cfg, "SERP_PROVIDER", "serpapi")
    monkeypatch.setattr(cfg, "SERP_API_KEY", "")
    assert serp_enabled() is False
    monkeypatch.setattr(cfg, "SERP_PROVIDER", "serpapi")
    monkeypatch.setattr(cfg, "SERP_API_KEY", "secret")
    assert serp_enabled() is True


def test_merge_thresholds_overrides():
    merged = merge_thresholds({"wow_impression_growth": 0.35, "pagespeed_urgent": 40})
    assert merged["wow_impression_growth"] == 0.35
    assert merged["pagespeed_urgent"] == 40
    assert merged["position_min"] == DEFAULT_THRESHOLDS["position_min"]


def test_score_with_impact_none_equals_base():
    assert score_with_impact("high", "ctr_opportunity", None) == score_insight("high", "ctr_opportunity")

"""Success report integrity — phase gating, confidence tiers, baseline alignment, known events."""

from datetime import date

from app.success_report.metrics import (
    _min_n_for_metric,
    _sample_confidence,
    _baseline_deltas,
    compute_report_phase,
    REPORT_PAYLOAD_VERSION,
    is_rate_metric,
)
from app.known_events import events_touching, possible_cause_text, CORE_UPDATES


# ── Phase 2: Report phase gating ──

def test_compute_report_phase_baseline():
    """No work, no wins, no proven levers → baseline."""
    assert compute_report_phase(0, [], 0) == "baseline"


def test_compute_report_phase_active():
    """Tasks completed but no wins → active."""
    assert compute_report_phase(3, [], 0) == "active"


def test_compute_report_phase_proven_from_wins():
    """At least one attributed win → proven."""
    assert compute_report_phase(1, [{"task_id": 1}], 0) == "proven"


def test_compute_report_phase_proven_from_levers():
    """Proven growth levers → proven, even without wins."""
    assert compute_report_phase(0, [], 1) == "proven"


# ── Phase 4: Sample-size confidence gating ──

def test_min_n_for_rate_metric_is_zero():
    """Rate metrics (CTR, position) always show deltas regardless of n."""
    assert _min_n_for_metric("gsc.ctr") == 0
    assert _min_n_for_metric("gsc.position") == 0
    assert _min_n_for_metric("ga4.cvr") == 0


def test_min_n_for_count_metric():
    """Count metrics have a floor of 30 for showing percentages."""
    assert _min_n_for_metric("gsc.clicks") == 30
    assert _min_n_for_metric("ga4.sessions") == 30
    assert _min_n_for_metric("hubspot.leads") == 30


def test_min_n_for_impressions():
    """Impressions need 200+ for reliable deltas."""
    assert _min_n_for_metric("gsc.impressions") == 200


def test_sample_confidence_low_n_gates_pct():
    """< 30 items → no percentage, mark low confidence."""
    ch, tier = _sample_confidence("gsc.clicks", 7, 5)
    assert ch is None
    assert tier == "sample_too_small"


def test_sample_confidence_directional():
    """30–100 items → percentage shown but flagged directional."""
    ch, tier = _sample_confidence("gsc.clicks", 50, 40)
    assert ch == 25.0
    assert tier is None  # both >= 30


def test_sample_confidence_borderline():
    """20 vs 25 (both < 30 but > 10) → directional, no pct shown."""
    ch, tier = _sample_confidence("gsc.clicks", 25, 20)
    assert ch is None  # min(25, 20) = 20, which is < 30
    assert tier == "directional"  # 20 is >= 10 (33% of 30)


def test_sample_confidence_high_n_shows_pct():
    """> 100 items → normal percentage."""
    ch, tier = _sample_confidence("ga4.sessions", 150, 120)
    assert ch == 25.0
    assert tier is None


def test_sample_confidence_zero_prev_is_none():
    """Zero previous → no percentage (avoid +100% invention), no sample flag."""
    ch, tier = _sample_confidence("gsc.clicks", 50, 0)
    assert ch is None
    assert tier is None  # zero-previous is intrinsic, not a sample-size concern


def test_sample_confidence_rate_metric_always_shows():
    """CTR always returns a delta regardless of n."""
    ch, tier = _sample_confidence("gsc.ctr", 0.05, 0.03)
    assert ch == 66.7
    assert tier is None


# ── Phase 1: Baseline/period alignment ──

def test_baseline_deltas_window_mismatch_flag():
    """When baseline 30d vs report 14d, flag the mismatch."""
    baseline = {
        "period_days": 30,
        "period_start": "2026-05-01",
        "period_end": "2026-05-30",
        "kpis": [
            {"key": "ga4.sessions", "value": 150},
            {"key": "gsc.clicks", "value": 100},
        ],
    }
    kpis = [
        {"key": "ga4.sessions", "label": "Website visits", "current": 70, "current_n": 70},
        {"key": "gsc.clicks", "label": "Google clicks", "current": 45, "current_n": 45},
    ]
    deltas = {d["key"]: d for d in _baseline_deltas(baseline, kpis, compare_days=14)}
    # 30d vs 14d → mismatch flagged
    assert deltas["ga4.sessions"]["window_mismatch"] is True
    assert deltas["ga4.sessions"]["normalized"] is True
    # Scaled baseline: 150 * (14/30) = 70.0
    assert deltas["ga4.sessions"]["baseline"] == 70.0
    assert deltas["ga4.sessions"]["scaled"] is True


def test_baseline_deltas_same_length_no_mismatch():
    """30d baseline vs 30d report → no mismatch flag."""
    baseline = {
        "period_days": 30,
        "period_start": "2026-05-01",
        "period_end": "2026-05-30",
        "kpis": [
            {"key": "ga4.sessions", "value": 150},
        ],
    }
    kpis = [
        {"key": "ga4.sessions", "label": "Website visits", "current": 120, "current_n": 120},
    ]
    deltas = _baseline_deltas(baseline, kpis, compare_days=30)
    d = deltas[0]
    assert d.get("window_mismatch") is not True
    assert d.get("scaled") is False
    assert d["change_pct"] == -20.0


def test_baseline_deltas_low_confidence_gates_pct():
    """Low-n metrics in baseline delta get confidence flag."""
    baseline = {
        "period_days": 30,
        "kpis": [
            {"key": "hubspot.leads", "value": 8},
        ],
    }
    kpis = [
        {"key": "hubspot.leads", "label": "Leads", "current": 5, "current_n": 5},
    ]
    deltas = _baseline_deltas(baseline, kpis, compare_days=30)
    d = deltas[0]
    assert d["change_pct"] is None
    assert d["low_confidence"] is True
    assert d["confidence_tier"] == "sample_too_small"
    # Raw values still present
    assert d["current"] == 5
    assert d["baseline"] == 8


# ── Phase 8: Known events ──

def test_events_touching_no_overlap():
    events = events_touching(date(2026, 5, 1), date(2026, 5, 15))
    assert len(events) == 0


def test_events_touching_overlaps():
    events = events_touching(date(2026, 3, 10), date(2026, 3, 20))
    assert len(events) >= 1
    assert any("March 2026" in e["name"] for e in events)
    for e in events:
        assert isinstance(e.get("start"), date)
        assert isinstance(e.get("end"), date)


def test_possible_cause_text_single():
    events = [{"name": "Google March 2026 Core Update", "type": "core_update"}]
    text = possible_cause_text(events)
    assert "Possible cause:" in text
    assert "March 2026" in text


def test_possible_cause_text_multiple():
    events = [
        {"name": "Google March 2026 Core Update", "type": "core_update"},
        {"name": "December holiday traffic slowdown", "type": "seasonal"},
    ]
    text = possible_cause_text(events)
    assert "Possible causes:" in text
    assert "and" in text


def test_possible_cause_text_empty():
    assert possible_cause_text([]) == ""


def test_known_events_list_not_empty():
    assert len(CORE_UPDATES) >= 4
    for ev in CORE_UPDATES:
        assert "name" in ev
        assert "start" in ev
        assert "end" in ev


# ── Phase 7: Unit labeling ──

def test_rate_metrics_have_avg_unit():
    assert is_rate_metric("gsc.ctr") is True
    assert is_rate_metric("gsc.position") is True
    assert is_rate_metric("ga4.cvr") is True
    assert is_rate_metric("gsc.clicks") is False
    assert is_rate_metric("ga4.sessions") is False

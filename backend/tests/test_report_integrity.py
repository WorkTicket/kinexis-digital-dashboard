"""Report math integrity — no fake +100%, no absurd funnel rates, honest baselines."""

from app.success_report.metrics import (
    REPORT_PAYLOAD_VERSION,
    _baseline_deltas,
    _pct_change,
    change_is_favorable,
    inclusive_days,
    scale_baseline_value,
    window_start,
)
from app.portfolio_scoring import pct
from app.impact_math import change_pct
from app.funnel_analyzer import funnel_stage
from datetime import date


def test_pct_change_never_invents_100_from_zero_prior():
    assert _pct_change(46, 0) is None
    assert _pct_change(0, 0) is None
    assert _pct_change(46, 56) == -17.9
    assert _pct_change(20, 10) == 100.0  # real doubling still allowed


def test_portfolio_pct_matches_impact_math():
    assert pct(10, 0) is None
    assert change_pct(0, 10) is None
    assert pct(120, 100) == 20.0


def test_funnel_stage_cross_source_mismatch():
    """Sessions > clicks must not produce 657% / -557%."""
    stage = funnel_stage("Click → Session", 7, 46, cross_source=True)
    assert stage["unreliable"] is True
    assert stage["conversion_rate"] is None
    assert stage["dropoff"] is None
    assert stage["entered"] == 7
    assert stage["exited"] == 46


def test_funnel_stage_normal_ctr():
    stage = funnel_stage("Impression → Click", 2383, 7)
    assert stage["unreliable"] is False
    assert stage["conversion_rate"] == 0.29
    assert stage["dropoff"] == 99.71


def test_window_start_is_inclusive_n_days():
    end = date(2026, 7, 11)
    assert window_start(end, 30) == date(2026, 6, 12)
    assert inclusive_days(window_start(end, 30), end) == 30
    assert inclusive_days(date(2026, 6, 1), date(2026, 6, 30)) == 30


def test_scale_baseline_aligns_unequal_windows():
    # 30d baseline of 30 clicks → 90d equivalent is 90
    assert scale_baseline_value(30, key="gsc.clicks", baseline_days=30, compare_days=90) == 90.0
    # Rates are not scaled
    assert scale_baseline_value(12.5, key="gsc.position", baseline_days=30, compare_days=90) == 12.5
    assert scale_baseline_value(0.02, key="gsc.ctr", baseline_days=30, compare_days=31) == 0.02


def test_baseline_deltas_scale_month_vs_30d():
    baseline = {
        "period_days": 30,
        "period_start": "2026-05-01",
        "period_end": "2026-05-30",
        "kpis": [
            {"key": "ga4.sessions", "value": 200},
            {"key": "gsc.clicks", "value": 150},
            {"key": "gsc.position", "value": 20},
        ],
    }
    # June has 30 days — same length → no scale, real declines
    kpis = [
        {"key": "ga4.sessions", "label": "Website visits", "current": 164, "current_n": 164},
        {"key": "gsc.clicks", "label": "Google clicks", "current": 105, "current_n": 105},
        {"key": "gsc.position", "label": "Avg. position", "current": 15},
    ]
    deltas = {d["key"]: d for d in _baseline_deltas(baseline, kpis, compare_days=30)}
    assert deltas["ga4.sessions"]["change_pct"] == -18.0
    assert deltas["gsc.clicks"]["change_pct"] == -30.0
    assert deltas["gsc.position"]["favorable"] is True  # lower rank is better
    assert deltas["ga4.sessions"]["favorable"] is False
    # No window mismatch for equal lengths
    assert deltas["ga4.sessions"].get("window_mismatch") is not True

    # 90d contract window vs 30d baseline → compare base 90
    kpis90 = [{"key": "ga4.sessions", "label": "Website visits", "current": 540, "current_n": 540}]
    d90 = _baseline_deltas(baseline, kpis90, compare_days=90)[0]
    assert d90["baseline"] == 600.0  # 200 * 3
    assert d90["scaled"] is True
    assert d90["change_pct"] == -10.0  # 540 vs 600


def test_inverse_metric_favorability():
    assert change_is_favorable("gsc.position", -10) is True
    assert change_is_favorable("gsc.position", 10) is False
    assert change_is_favorable("paid.cost", -5) is True
    assert change_is_favorable("gsc.clicks", 10) is True
    assert change_is_favorable("gsc.clicks", -10) is False


def test_payload_version_bumped_for_cache_bust():
    assert REPORT_PAYLOAD_VERSION >= 3

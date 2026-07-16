"""Pure impact math helpers (testable without DB)."""

from __future__ import annotations

import statistics
from typing import Optional


def change_pct(before: float, after: float) -> Optional[float]:
    """Percent change from before → after. None when before is zero or missing."""
    if before is None or before == 0:
        return None
    return round(((after - before) / abs(before)) * 100, 1)


def confidence_from_values(before: float, after: float) -> str:
    """Evidence strength from sample size of the primary metric totals (not causal proof)."""
    sample = max(abs(before or 0), abs(after or 0))
    if sample < 20:
        return "low"
    if sample < 200:
        return "medium"
    return "high"


def auto_outcome_from_avg_change(avg_pct: float) -> str:
    """Shared win/loss/flat rule for Prove UI and outcome memory."""
    if avg_pct > 2:
        return "win"
    if avg_pct < -2:
        return "loss"
    return "flat"


def confidence_from_variance(
    before: float,
    after: float,
    historical_daily_values: list[float] | None,
) -> str:
    """
    Evidence strength vs this metric's own trailing day-to-day noise (stdev).
    Prefer this over flat magnitude buckets when enough history exists (≥14 days).
    Change must clear ~1σ (low) / ~2σ (medium) / ≥2σ+sample (high).
    """
    if historical_daily_values is None or len(historical_daily_values) < 14:
        return confidence_from_values(before, after)
    try:
        stdev = statistics.stdev(historical_daily_values)
    except statistics.StatisticsError:
        return confidence_from_values(before, after)
    change = abs((after or 0) - (before or 0))
    if stdev <= 0:
        return confidence_from_values(before, after)
    if change < stdev:
        return "low"
    if change < 2 * stdev:
        return "medium"
    sample = confidence_from_values(before, after)
    if sample == "low":
        return "low"
    return "high"


# Honest labels for UI — sample-size / magnitude evidence, not causality
EVIDENCE_LABELS = {
    "high": "strong multi-signal evidence",
    "medium": "moderate evidence",
    "low": "limited evidence",
    "insufficient": "insufficient evidence",
    "pending": "awaiting post-ship data",
    "none": "no evidence yet",
}


def evidence_label(confidence: str) -> str:
    return EVIDENCE_LABELS.get((confidence or "").lower(), "limited evidence")


def pre_trend_flag(before_series: list[float] | None, lift_pct: float | None) -> Optional[str]:
    """
    Flag when pre-period already trended in the same direction as the lift.
    Returns a caution string or None. Not a causal test — honesty signal only.
    """
    if not before_series or len(before_series) < 3 or lift_pct is None:
        return None
    first = before_series[0]
    last = before_series[-1]
    if first is None or last is None or first == 0:
        return None
    pre_pct = ((last - first) / abs(first)) * 100
    if (lift_pct > 0 and pre_pct > 5 and pre_pct >= abs(lift_pct) * 0.4) or (
        lift_pct < 0 and pre_pct < -5 and abs(pre_pct) >= abs(lift_pct) * 0.4
    ):
        return (
            f"Pre-period already moved {pre_pct:+.0f}% in the same direction — "
            "lift may partly reflect an existing trend, not only this fix."
        )
    return None


def seasonality_caution(checked_month: int | None = None) -> Optional[str]:
    """Lightweight seasonal honesty note for common marketing months."""
    if checked_month in (11, 12, 1):
        return "Holiday / year-end seasonality can inflate or deflate results independently of this work."
    if checked_month in (6, 7, 8):
        return "Summer seasonality can shift traffic and conversion independently of this work."
    return None

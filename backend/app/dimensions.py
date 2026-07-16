"""
Shared dimension constants — single source of truth for site-level metric aggregation.

Every module that queries MetricDaily for site totals must prefer one dimension per
source so metrics aren't double-counted across query/page/device/country dimensions.
"""

from __future__ import annotations

from typing import Optional

SITE_TOTAL_DIMENSION: dict[str, Optional[str]] = {
    "gsc": "device",
    "bing": "query",
    "ga4": "landing_page",
    "ads_csv": "campaign",
    "google_ads": "campaign",
    "meta_ads": "campaign",
    "clarity": "page",
    "backlinks": None,
    "gbp": None,
    "crux": None,
    "serp": None,
}

PAID_SOURCES = ("ads_csv", "google_ads", "meta_ads")

AVG_METRICS = frozenset({
    "ctr",
    "position",
    "bounce_rate",
    "scroll_depth",
    "sov_presence",
    "sov_loss_rate",
    "frequency",
})


def site_total_dim(source: str) -> str | None:
    """Return the preferred dimension type for site-level aggregation of `source`.
    
    Returns None when the source has no dimension breakdowns (e.g. backlinks, GBP).
    """
    return SITE_TOTAL_DIMENSION.get(source)


def is_site_total_row(source: str, dimension_type: str | None) -> bool:
    """Check whether a MetricDaily row represents a site-level aggregate for `source`."""
    dim = dimension_type or ""
    preferred = SITE_TOTAL_DIMENSION.get(source)
    if preferred is None:
        # Undimensioned sources (serp, gbp, …) — empty dim only
        return dim == ""
    # Prefer the designated breakdown, but accept true site totals ("")
    return dim == "" or dim == preferred

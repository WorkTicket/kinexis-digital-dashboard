"""Per-client Success Contract — primary KPI, target lift, evaluation window."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Client, ClientBaseline, MetricDaily
from app.success_report.metrics import scale_baseline_value, window_start

# Allowed primary metrics (source.metric)
CONTRACT_METRICS: dict[str, dict[str, str]] = {
    "hubspot.leads": {"source": "hubspot", "metric": "leads", "label": "Leads", "agg": "sum"},
    "hubspot.revenue": {"source": "hubspot", "metric": "revenue", "label": "Revenue", "agg": "sum"},
    "hubspot.opportunities": {
        "source": "hubspot",
        "metric": "opportunities",
        "label": "Opportunities",
        "agg": "sum",
    },
    "hubspot.closed_won": {
        "source": "hubspot",
        "metric": "closed_won",
        "label": "Deals won",
        "agg": "sum",
    },
    "paid.conversions": {
        "source": "paid",
        "metric": "conversions",
        "label": "Paid conversions",
        "agg": "sum",
    },
    "paid.cost": {"source": "paid", "metric": "cost", "label": "Paid spend", "agg": "sum"},
    "paid.conversion_value": {
        "source": "paid",
        "metric": "conversion_value",
        "label": "Paid conversion value",
        "agg": "sum",
    },
    "paid.clicks": {"source": "paid", "metric": "clicks", "label": "Paid clicks", "agg": "sum"},
    "gsc.clicks": {"source": "gsc", "metric": "clicks", "label": "Organic clicks", "agg": "sum"},
    "gsc.impressions": {
        "source": "gsc",
        "metric": "impressions",
        "label": "Impressions",
        "agg": "sum",
    },
    "ga4.sessions": {"source": "ga4", "metric": "sessions", "label": "Sessions", "agg": "sum"},
    "ga4.key_events": {
        "source": "ga4",
        "metric": "key_events",
        "label": "Conversions",
        "agg": "sum",
    },
}

from app.dimensions import SITE_TOTAL_DIMENSION as _SITE_DIM

logger = logging.getLogger(__name__)

_PAID_DS_TYPES = {"ads_csv", "google_ads", "meta_ads"}

DEFAULT_CONTRACT = {
    "primary_metric": "hubspot.leads",
    "secondary_metrics": ["hubspot.revenue", "gsc.clicks", "ga4.key_events"],
    "target_delta_pct": 20.0,
    "window_days": 90,
    "baseline_mode": "engagement",
    "notes": "",
}


def default_contract_for_datasources(ds_types: set[str] | list[str]) -> dict:
    """Pick a commercial-first contract based on connected sources."""
    types = {str(t).lower() for t in ds_types}
    contract = dict(DEFAULT_CONTRACT)
    if "hubspot" in types:
        contract["primary_metric"] = "hubspot.leads"
        contract["secondary_metrics"] = ["hubspot.revenue", "gsc.clicks", "ga4.key_events"]
    elif types & _PAID_DS_TYPES:
        contract["primary_metric"] = "paid.conversions"
        contract["secondary_metrics"] = ["paid.cost", "ga4.key_events", "gsc.clicks"]
    elif "ga4" in types:
        contract["primary_metric"] = "ga4.key_events"
        contract["secondary_metrics"] = ["ga4.sessions", "gsc.clicks"]
    else:
        contract["primary_metric"] = "gsc.clicks"
        contract["secondary_metrics"] = ["ga4.key_events", "gsc.impressions"]
    return contract


def ensure_success_contract(client: Client, ds_types: set[str] | list[str] | None = None) -> bool:
    """
    Seed success_contract on the client profile when unset.
    Returns True if profile_json was mutated (caller must commit).

    Never seeds a HubSpot (or any) default when no connected sources are known —
    pick primary from connected sources only.
    """
    if parse_success_contract(client):
        return False
    types = {str(t).lower() for t in (ds_types or [])}
    if not types:
        return False
    contract = default_contract_for_datasources(types)
    profile = parse_profile(client)
    profile["success_contract"] = contract
    client.profile_json = json.dumps(profile)
    return True


def parse_profile(client: Client) -> dict:
    try:
        profile = json.loads(client.profile_json or "{}")
        return profile if isinstance(profile, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def parse_success_contract(client: Client) -> Optional[dict[str, Any]]:
    """Return normalized success_contract or None if unset."""
    profile = parse_profile(client)
    raw = profile.get("success_contract")
    if not isinstance(raw, dict) or not raw:
        return None
    primary = str(raw.get("primary_metric") or "").strip()
    if primary not in CONTRACT_METRICS:
        # Allow legacy "leads" shorthand
        aliases = {
            "leads": "hubspot.leads",
            "revenue": "hubspot.revenue",
            "clicks": "gsc.clicks",
            "sessions": "ga4.sessions",
            "conversions": "ga4.key_events",
            "key_events": "ga4.key_events",
            "paid_conversions": "paid.conversions",
            "ad_conversions": "paid.conversions",
            "ad_spend": "paid.cost",
            "paid_spend": "paid.cost",
        }
        primary = aliases.get(primary.lower(), primary)
    if primary not in CONTRACT_METRICS:
        return None

    secondary: list[str] = []
    sec_raw = raw.get("secondary_metrics") or []
    if isinstance(sec_raw, str):
        sec_raw = [s.strip() for s in sec_raw.split(",") if s.strip()]
    if isinstance(sec_raw, list):
        for s in sec_raw:
            key = str(s).strip()
            if key in CONTRACT_METRICS and key != primary:
                secondary.append(key)

    try:
        target = float(raw.get("target_delta_pct", DEFAULT_CONTRACT["target_delta_pct"]))
    except (TypeError, ValueError):
        target = float(DEFAULT_CONTRACT["target_delta_pct"])
    try:
        window = int(raw.get("window_days", DEFAULT_CONTRACT["window_days"]))
    except (TypeError, ValueError):
        window = int(DEFAULT_CONTRACT["window_days"])
    window = max(14, min(180, window))

    return {
        "primary_metric": primary,
        "secondary_metrics": secondary[:4],
        "target_delta_pct": target,
        "window_days": window,
        "baseline_mode": str(raw.get("baseline_mode") or "engagement"),
        "notes": str(raw.get("notes") or ""),
        "label": CONTRACT_METRICS[primary]["label"],
    }


def _aggregate(
    db: Session,
    client_id: int,
    source: str,
    metric: str,
    start: date,
    end: date,
) -> float:
    if source == "paid":
        from app.connectors.ads_common import sum_paid_metric

        return sum_paid_metric(db, client_id, metric, start, end)
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric,
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    dim = _SITE_DIM.get(source)
    if dim:
        filters.append(MetricDaily.dimension_type == dim)
    val = db.query(func.sum(MetricDaily.value)).filter(and_(*filters)).scalar()
    return float(val or 0)


def _baseline_row(db: Session, client_id: int):
    return db.query(ClientBaseline).filter(ClientBaseline.client_id == client_id).first()


def _baseline_value(db: Session, client_id: int, primary: str) -> Optional[float]:
    row = _baseline_row(db, client_id)
    if not row or not row.kpis_json:
        return None
    try:
        kpis = json.loads(row.kpis_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(kpis, dict):
        return None
    # Baseline stores flat keys like "gsc.clicks" or nested — try common shapes
    if primary in kpis and isinstance(kpis[primary], (int, float)):
        return float(kpis[primary])
    # Legacy baselines may only have ads_csv.* for paid contracts
    if primary.startswith("paid."):
        legacy = primary.replace("paid.", "ads_csv.", 1)
        if legacy in kpis and isinstance(kpis[legacy], (int, float)):
            return float(kpis[legacy])
    if isinstance(kpis, list):
        for item in kpis:
            if isinstance(item, dict) and item.get("key") == primary:
                v = item.get("value") or item.get("current") or item.get("baseline")
                if isinstance(v, (int, float)):
                    return float(v)
    # Nested by source
    meta = CONTRACT_METRICS.get(primary)
    if meta:
        nested = kpis.get(meta["source"])
        if isinstance(nested, dict) and meta["metric"] in nested:
            try:
                return float(nested[meta["metric"]])
            except (TypeError, ValueError):
                pass
    logger.warning(
        "Baseline found for client %s but primary metric %r not in recognized format. "
        "Baseline kpis_json keys: %s",
        client_id,
        primary,
        list(kpis.keys()) if isinstance(kpis, dict) else type(kpis).__name__,
    )
    return None


def _baseline_period_days(db: Session, client_id: int) -> int:
    row = _baseline_row(db, client_id)
    if not row or not row.period_start or not row.period_end:
        return 30
    return max(1, (row.period_end - row.period_start).days + 1)


def evaluate_success_contract(db: Session, client: Client) -> dict[str, Any]:
    """
    Compare primary metric over the contract window vs equal prior window
    (or engagement baseline when available).
    """
    contract = parse_success_contract(client)
    if not contract:
        return {
            "configured": False,
            "status": "unset",
            "contract": None,
            "progress": None,
        }

    primary = contract["primary_metric"]
    meta = CONTRACT_METRICS[primary]
    window = int(contract["window_days"])
    today = date.today()
    cur_start = window_start(today, window)
    prev_end = cur_start - timedelta(days=1)
    prev_start = window_start(prev_end, window)

    current = _aggregate(db, client.id, meta["source"], meta["metric"], cur_start, today)
    previous = _aggregate(
        db, client.id, meta["source"], meta["metric"], prev_start, prev_end
    )

    baseline_val = _baseline_value(db, client.id, primary)
    compare_mode = "prior_period"
    compare_base = previous
    if (
        contract.get("baseline_mode") == "engagement"
        and baseline_val is not None
        and baseline_val > 0
    ):
        baseline_days = _baseline_period_days(db, client.id)
        compare_mode = "engagement_baseline"
        compare_base = scale_baseline_value(
            baseline_val,
            key=primary,
            baseline_days=baseline_days,
            compare_days=window,
        )
    # Zero/missing engagement baseline → fall back to prior period (don't stick in no_data)

    from app.success_report.metrics import _sample_confidence

    # Gate ahead/behind the same way success-report KPIs are gated (min-n).
    sample_tier = None
    if compare_base and compare_base > 0:
        change_pct, sample_tier = _sample_confidence(primary, current, float(compare_base))
    else:
        # Zero/missing compare base → no inventing +100% growth
        change_pct = None

    target = float(contract["target_delta_pct"])
    if change_pct is None and sample_tier in ("sample_too_small", "directional"):
        status = "insufficient_data"
    elif change_pct is None:
        status = "no_data"
    elif change_pct >= target:
        status = "ahead"
    elif change_pct >= target * 0.5:
        status = "on_track"
    else:
        status = "behind"

    progress_ratio = None
    if change_pct is not None and target > 0.01:
        progress_ratio = round(max(0.0, min(2.0, change_pct / target)), 2)

    return {
        "configured": True,
        "status": status,
        "contract": contract,
        "progress": {
            "primary_metric": primary,
            "label": meta["label"],
            "current": round(current, 2),
            "compare_base": round(compare_base, 2) if compare_base is not None else 0,
            "compare_mode": compare_mode,
            "change_pct": change_pct,
            "target_delta_pct": target,
            "progress_ratio": progress_ratio,
            "window_days": window,
            "period_start": cur_start.isoformat(),
            "period_end": today.isoformat(),
            "sample_confidence": sample_tier,
        },
    }


def format_contract_for_prompt(client: Client) -> list[str]:
    contract = parse_success_contract(client)
    if not contract:
        return []
    lines = ["=== SUCCESS CONTRACT (binding) ==="]
    lines.append(
        f"  primary: {contract['primary_metric']} ({contract['label']}) "
        f"target +{contract['target_delta_pct']}% over {contract['window_days']}d"
    )
    if contract.get("secondary_metrics"):
        lines.append(f"  secondary: {', '.join(contract['secondary_metrics'])}")
    if contract.get("notes"):
        lines.append(f"  notes: {contract['notes']}")
    lines.append("")
    return lines

"""GSC insight rules — position, CTR, decline, zero-click."""

from datetime import date, timedelta
from sqlalchemy import func, and_
from app.models import MetricDaily, Client
from app.insight_thresholds import thresholds_for_client, cap_insights
from app.query_intent import classify_query_intent
from app.service_area import parse_service_area

from app.insights.rule_modules._helpers import (
    expected_ctr,
    avg_position_30d,
    brand_terms,
    skip_geo_growth_query,
    fmt_url_list,
    top_gsc_pages_by_clicks,
    top_dropped_gsc_pages,
    top_ga4_landing_pages,
    bing_datasource_connected,
    sum_metric,
    has_ever_had_conversions,
)

# Backward-compatible aliases
_expected_ctr = expected_ctr
_avg_position_30d = avg_position_30d
_brand_terms = brand_terms
_skip_geo_growth_query = skip_geo_growth_query
_fmt_url_list = fmt_url_list
_top_gsc_pages_by_clicks = top_gsc_pages_by_clicks
_top_dropped_gsc_pages = top_dropped_gsc_pages
_top_ga4_landing_pages = top_ga4_landing_pages
_bing_datasource_connected = bing_datasource_connected
_sum_metric = sum_metric
_has_ever_had_conversions = has_ever_had_conversions

def _gsc_position_opportunity(client_id: int, db, thr=None) -> list[dict]:
    """GSC queries in striking distance with rising impressions -> content opportunity."""
    from app.brand_queries import is_brand_query

    thr = thr or thresholds_for_client(db, client_id)
    growth_cut = thr.get("wow_impression_growth", 0.20)
    min_this = thr.get("min_query_impressions_week", 60)
    min_prev = thr.get("min_query_impressions_prev", 40)
    pos_min = thr.get("position_min", 11)
    pos_max = thr.get("position_max", 20)
    min_30d = thr.get("min_impressions_30d_opp", 250)
    insights = []
    brand_terms = _brand_terms(db, client_id)
    today = date.today()
    this_week_start = today - timedelta(days=6)
    last_week_start = today - timedelta(days=13)
    start_30 = today - timedelta(days=30)

    this_week_data = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("total_impressions"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "impressions",
                MetricDaily.dimension_type == "query",
                MetricDaily.date >= this_week_start,
                MetricDaily.date <= today,
            )
        )
        .group_by(MetricDaily.dimension_value)
        .all()
    )

    last_week_data = (
        db.query(MetricDaily.dimension_value, func.sum(MetricDaily.value).label("total_impressions"))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "impressions",
                MetricDaily.dimension_type == "query",
                MetricDaily.date >= last_week_start,
                MetricDaily.date < this_week_start,
            )
        )
        .group_by(MetricDaily.dimension_value)
        .all()
    )

    impr_30 = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("total"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "impressions",
                MetricDaily.dimension_type == "query",
                MetricDaily.date >= start_30,
            )
        )
        .group_by(MetricDaily.dimension_value)
        .all()
    )
    impr_30_map = {r.dimension_value: float(r.total or 0) for r in impr_30}
    last_week_map = {row.dimension_value: row.total_impressions or 0 for row in last_week_data}

    for row in this_week_data:
        query = row.dimension_value
        if not query:
            continue
        # Growth plays optimize non-brand demand; brand queries rarely need "content opportunity"
        if brand_terms and is_brand_query(query, brand_terms):
            continue
        if _skip_geo_growth_query(db, client_id, query):
            continue
        this_impressions = row.total_impressions or 0
        last_impressions = last_week_map.get(query, 0)
        if this_impressions < min_this or last_impressions < min_prev:
            continue
        if impr_30_map.get(query, 0) < min_30d:
            continue
        pos = _avg_position_30d(db, client_id, query, start_30)
        if pos is None or not (pos_min <= pos <= pos_max):
            continue
        if last_impressions > 0:
            change = (this_impressions - last_impressions) / last_impressions
            if change > growth_cut:
                impact_weight = min(100.0, change * 100 + min(40.0, this_impressions / 50))
                insights.append({
                    "type": "content_opportunity",
                    "kind": "opportunity",
                    "message": (
                        f'Query "{query}" at pos {pos:.1f} gaining impressions '
                        f"(+{change:.0%} WoW: {last_impressions:.0f} -> {this_impressions:.0f}). "
                        f"Striking-distance content play."
                    ),
                    "recommended_action": (
                        f'1) Open GSC for "{query}" and note the ranking URL. '
                        f"2) Expand that page (or create a landing page) targeting the query. "
                        f"3) Add 2–3 internal links. 4) Recheck position in 14 days."
                    ),
                    "severity": "medium",
                    "impact_weight": round(impact_weight, 1),
                    "metrics_to_watch": ["gsc.clicks", "gsc.impressions"],
        })
    return cap_insights(insights, thr)


# ── Gap 1: Backlink monitoring ────────────────────────────────────────
def _gsc_ctr_findings(client_id: int, db, thr=None) -> list[dict]:
    """CTR below expected-for-position: severe → problem (ctr_gap), moderate → opportunity."""
    from app.brand_queries import is_brand_query

    thr = thr or thresholds_for_client(db, client_id)
    problem_mult = 1.0 - thr.get("ctr_gap_pct", 0.40)
    opp_mult = 1.0 - thr.get("ctr_gap_pct_opp", 0.30)
    min_impr_problem = thr.get("min_impressions_30d", 1000)
    min_impr_opp = thr.get("min_impressions_30d_opp", 250)
    insights = []
    brand_terms = _brand_terms(db, client_id)
    today = date.today()
    start_date = today - timedelta(days=30)

    rows = (
        db.query(
            MetricDaily.dimension_value,
            func.avg(MetricDaily.value).label("avg_val"),
            func.sum(MetricDaily.value).label("sum_val"),
            MetricDaily.metric_name,
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name.in_(["ctr", "position", "impressions", "clicks"]),
                MetricDaily.dimension_type == "query",
                MetricDaily.date >= start_date,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )

    by_query: dict[str, dict] = {}
    for row in rows:
        q = row.dimension_value or ""
        bucket = by_query.setdefault(q, {})
        if row.metric_name == "position":
            bucket[row.metric_name] = row.avg_val
        elif row.metric_name == "ctr":
            pass  # discard avg of daily ratios — compute from sum(clicks)/sum(impressions)
        else:
            bucket[row.metric_name] = row.sum_val or 0

    for query, metrics in by_query.items():
        if "position" not in metrics:
            continue
        # Prefer non-brand CTR gaps (brand CTR is usually already strong)
        if brand_terms and is_brand_query(query, brand_terms):
            continue
        # Google may serve the site in nearby cities; don't prescribe title/meta for those
        if _skip_geo_growth_query(db, client_id, query):
            continue
        impressions = float(metrics.get("impressions") or 0)
        clicks = float(metrics.get("clicks") or 0)
        if impressions < min_impr_opp:
            continue
        actual_ctr = (clicks / impressions) if impressions > 0 else 0.0
        position = metrics["position"]
        expected = _expected_ctr(position)
        if expected <= 0 or actual_ctr >= expected * opp_mult:
            continue
        gap = (expected - actual_ctr) / expected if expected else 0
        impact_weight = min(100.0, gap * 70 + min(30.0, impressions / 100))
        is_problem = impressions >= min_impr_problem and actual_ctr < expected * problem_mult

        # SERP feature attribution: is this CTR gap caused by Google layout, not bad snippets?
        serp_context = ""
        try:
            from app.serp_attribution import serp_features_for_query
            serp = serp_features_for_query(db, client_id, query)
            if serp and serp.get("features") and serp.get("feature_blocking_pct", 0) >= 0.20:
                feature_names = [k.replace("_", " ") for k in serp["features"].keys()]
                displacement = serp.get("feature_blocking_pct", 0)
                serp_context = (
                    f" SERP analysis shows {', '.join(feature_names)} absorbing "
                    f"~{displacement:.0%} of clicks on this query. The CTR gap may be "
                    f"structural (Google layout), not a snippet issue."
                )
        except Exception:
            pass
        if is_problem:
            insights.append({
                "type": "ctr_gap",
                "kind": "problem",
                "message": (
                    f'"{query}" at pos {position:.1f} has CTR {actual_ctr:.1%} '
                    f'(expected ~{expected:.1%}, {impressions:.0f} impr/30d). '
                    f"Severe SERP underperformance — titles/metas need a fix."
                    f"{serp_context}"
                ),
                "recommended_action": (
                    f"On ranking URL for \"{query}\":\n"
                    f"1) Rewrite title (≤60 chars) with keyword + benefit.\n"
                    f"2) Rewrite meta (≤155 chars) with a CTA.\n"
                    f"3) Request indexing for that URL."
                ),
                "severity": "high" if gap >= 0.5 else "medium",
                "impact_weight": round(impact_weight, 1),
                "metrics_to_watch": ["gsc.ctr", "gsc.clicks"],
            })
        else:
            insights.append({
                "type": "ctr_opportunity",
                "kind": "opportunity",
                "message": (
                    f'"{query}" at pos {position:.1f} has CTR {actual_ctr:.1%} '
                    f'(expected ~{expected:.1%}, {impressions:.0f} impr). Title or meta underperforming.'
                    f"{serp_context}"
                ),
                "recommended_action": (
                    f"On ranking URL for \"{query}\":\n"
                    f"1) Rewrite title (≤60 chars) with keyword + benefit.\n"
                    f"2) Rewrite meta (≤155 chars) with a CTA.\n"
                    f"3) Request indexing for that URL."
                ),
                "severity": "medium",
                "impact_weight": round(impact_weight, 1),
                "metrics_to_watch": ["gsc.ctr", "gsc.clicks"],
            })
    return cap_insights(insights, thr)


def _gsc_decline_alert(client_id: int, db, thr=None) -> list[dict]:
    """GSC clicks or impressions dropping WoW -> technical/indexing alert."""
    thr = thr or thresholds_for_client(db, client_id)
    decline_cut = thr.get("decline_wow", -0.20)
    min_clicks = thr.get("min_site_clicks_decline", 50)
    min_impr = thr.get("min_site_impressions_decline", 500)
    insights = []
    today = date.today()
    this_week_start = today - timedelta(days=6)
    last_week_start = today - timedelta(days=13)

    for metric_name in ("clicks", "impressions"):
        min_prev = min_clicks if metric_name == "clicks" else min_impr
        this_week = (
            db.query(func.sum(MetricDaily.value))
            .filter(
                and_(
                    MetricDaily.client_id == client_id,
                    MetricDaily.source == "gsc",
                    MetricDaily.metric_name == metric_name,
                    MetricDaily.dimension_type == "device",
                    MetricDaily.date >= this_week_start,
                )
            )
            .scalar() or 0
        )
        last_week = (
            db.query(func.sum(MetricDaily.value))
            .filter(
                and_(
                    MetricDaily.client_id == client_id,
                    MetricDaily.source == "gsc",
                    MetricDaily.metric_name == metric_name,
                    MetricDaily.dimension_type == "device",
                    MetricDaily.date >= last_week_start,
                    MetricDaily.date < this_week_start,
                )
            )
            .scalar() or 0
        )
        if last_week < min_prev:
            continue
        if last_week > 0:
            change = (this_week - last_week) / last_week
            if change < decline_cut:
                dropped = _top_dropped_gsc_pages(
                    db,
                    client_id,
                    metric_name,
                    this_week_start,
                    last_week_start,
                    this_week_start - timedelta(days=1),
                    limit=5,
                )
                if dropped:
                    offenders = "; ".join(
                        f"{u} ({p:.0f}→{c:.0f}, {ch:.0%})" for u, p, c, ch in dropped[:3]
                    )
                    top_url = dropped[0][0]
                    message = (
                        f"GSC {metric_name} dropped {abs(change):.0%} WoW "
                        f"({last_week:.0f} -> {this_week:.0f}). "
                        f"Worst pages: {offenders}."
                    )
                    action_lines = [
                        f"On {top_url} (biggest {metric_name} drop):",
                        "1) Open the URL — confirm HTTP 200, no accidental noindex/canonical to homepage.",
                        "2) GSC URL Inspection → request indexing if excluded or soft-404.",
                        "3) Fix 404/redirect chains; restore thinned content if the page was cut.",
                    ]
                    for u, p, c, ch in dropped[1:3]:
                        action_lines.append(
                            f"4+) Next: {u} ({metric_name} {p:.0f}→{c:.0f}, {ch:.0%}) — same triage."
                        )
                    action_lines.append(
                        "Last) Check GSC Manual actions & Security; resubmit sitemap; remeasure in 7 days."
                    )
                    recommended = "\n".join(action_lines)
                else:
                    top_pages = _top_gsc_pages_by_clicks(db, client_id, days=14, limit=3)
                    page_bit = (
                        f" Start with top pages: {_fmt_url_list(top_pages)}."
                        if top_pages
                        else ""
                    )
                    message = (
                        f"GSC {metric_name} dropped {abs(change):.0%} WoW "
                        f"({last_week:.0f} -> {this_week:.0f}). "
                        f"Possible indexing or technical issue — page-level split not available yet."
                    )
                    recommended = (
                        f"1) GSC → Pages: sort by {metric_name} change; open the top losers.{page_bit}\n"
                        "2) For each URL: check HTTP status, noindex, canonical, soft 404.\n"
                        "3) Fix crawl/sitemap issues; request indexing on money pages.\n"
                        f"4) Remeasure site {metric_name} next week."
                    )
                from app.known_events import events_touching, possible_cause_text

                events = events_touching(last_week_start, today)
                possible_cause = possible_cause_text(events) if events else None

                # Seasonality check: is this decline within expected seasonal range?
                try:
                    from app.seasonality_engine import seasonality_caution_for_metric
                    seasonal_note = seasonality_caution_for_metric(
                        db, client_id, "gsc", metric_name,
                        float(this_week),
                    )
                except Exception:
                    seasonal_note = None

                if seasonal_note:
                    message += f" Note: {seasonal_note}"

                insight = {
                    "type": "decline_alert",
                    "kind": "problem",
                    "message": message,
                    "recommended_action": recommended,
                    "severity": "high",
                    "impact_weight": round(min(100.0, abs(change) * 120), 1),
                    "metrics_to_watch": ["gsc.clicks", "gsc.impressions"],
                }
                if possible_cause:
                    insight["possible_cause"] = possible_cause
                insights.append(insight)
    return insights


def _gsc_zero_click_alert(client_id: int, db, thr=None) -> list[dict]:
    """High-volume queries with zero clicks -> routed by intent.
    
    Local commercial queries -> CTR title/meta playbook.
    Informational queries -> content answer + CTA.
    Never defaults to featured-snippet/FAQ schema.
    """
    from app.brand_queries import is_brand_query

    thr = thr or thresholds_for_client(db, client_id)
    min_impr = thr.get("min_impressions_30d", 1000)
    insights = []
    brand_terms = _brand_terms(db, client_id)
    today = date.today()
    start_date = today - timedelta(days=30)
    client_obj = db.query(Client).filter(Client.id == client_id).first()
    sa = parse_service_area(client_obj) if client_obj else None

    rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("total_val"),
            MetricDaily.metric_name,
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name.in_(["impressions", "clicks"]),
                MetricDaily.dimension_type == "query",
                MetricDaily.date >= start_date,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )

    by_query: dict[str, dict] = {}
    for row in rows:
        q = row.dimension_value or ""
        by_query.setdefault(q, {})[row.metric_name] = row.total_val or 0

    for query, metrics in by_query.items():
        if brand_terms and is_brand_query(query, brand_terms):
            continue
        if _skip_geo_growth_query(db, client_id, query):
            continue
        impressions = metrics.get("impressions", 0)
        clicks = metrics.get("clicks", 0)
        if not (impressions >= min_impr and clicks == 0):
            continue

        intent = classify_query_intent(query, sa)

        if intent == "local_commercial":
            insights.append({
                "type": "zero_click_alert",
                "kind": "problem",
                "message": (
                    f'Query "{query}" has {impressions:.0f} impressions/30d but 0 clicks '
                    f"(pos from CTR table — title/meta not earning clicks). "
                    f"Local commercial intent."
                ),
                "recommended_action": (
                    f"On ranking URL for \"{query}\":\n"
                    f"1) Rewrite title (≤60 chars) with keyword + benefit/location.\n"
                    f"2) Rewrite meta (≤155 chars) with a clear CTA.\n"
                    f"3) Request indexing for that URL."
                ),
                "severity": "high",
                "impact_weight": round(min(100.0, impressions / 20), 1),
                "metrics_to_watch": ["gsc.ctr", "gsc.clicks"],
            })
        elif intent == "informational":
            insights.append({
                "type": "zero_click_alert",
                "kind": "problem",
                "message": (
                    f'Query "{query}" has {impressions:.0f} impressions/30d but 0 clicks. '
                    f"Informational intent — add on-page answer with CTA."
                ),
                "recommended_action": (
                    f"On ranking URL for \"{query}\":\n"
                    f"1) Add a clear answer block under a matching H2. "
                    f"2) Follow with a CTA to the relevant service page."
                ),
                "severity": "high",
                "impact_weight": round(min(100.0, impressions / 20), 1),
                "metrics_to_watch": ["gsc.clicks", "gsc.impressions"],
            })
        else:
            insights.append({
                "type": "zero_click_alert",
                "kind": "problem",
                "message": (
                    f'Query "{query}" has {impressions:.0f} impressions/30d but 0 clicks. '
                    f"Likely weak SERP snippet or intent mismatch."
                ),
                "recommended_action": (
                    f"On ranking URL for \"{query}\":\n"
                    f"1) Rewrite title/meta for click appeal.\n"
                    f"2) Request indexing for that URL."
                ),
                "severity": "high",
                "impact_weight": round(min(100.0, impressions / 20), 1),
                "metrics_to_watch": ["gsc.ctr", "gsc.clicks"],
            })
    # Lower cap for zero-click to avoid spam
    zero_click_cap = int(thr.get("max_zero_click_per_rule", 3))
    if len(insights) > zero_click_cap:
        insights.sort(key=lambda i: i.get("impact_weight", 0), reverse=True)
        insights = insights[:zero_click_cap]
    return insights



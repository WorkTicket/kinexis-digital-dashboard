"""Site / Cloudflare / PageSpeed / Bing / content / gap insight rules."""

from datetime import date, timedelta
from sqlalchemy import func, and_
from app.models import MetricDaily, DataSource
from app.insight_thresholds import thresholds_for_client, cap_insights
from app.timeutil import utcnow
from app.insights.new_rules import (
    backlink_drop_alert as _backlink_drop_alert,
    gbp_underperforming as _gbp_underperforming,
    crux_cwv_gap as _crux_cwv_gap,
)

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

def _cloudflare_error_spike(client_id: int, db, thr=None) -> list[dict]:
    """Cloudflare threats spiking + GA4 sessions dropping -> security/traffic quality issue."""
    thr = thr or thresholds_for_client(db, client_id)
    min_sessions = max(30.0, thr.get("thin_traffic_sessions", 50) * 0.6)
    insights = []
    today = date.today()
    this_week_start = today - timedelta(days=6)
    last_week_start = today - timedelta(days=13)

    cf_this = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "cloudflare",
                MetricDaily.metric_name == "threats",
                MetricDaily.date >= this_week_start,
            )
        )
        .scalar() or 0
    )
    cf_last = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "cloudflare",
                MetricDaily.metric_name == "threats",
                MetricDaily.date >= last_week_start,
                MetricDaily.date < this_week_start,
            )
        )
        .scalar() or 1
    )
    cf_change = (cf_this - cf_last) / cf_last if cf_last > 0 else 0

    ga4_this = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "ga4",
                MetricDaily.metric_name == "sessions",
                MetricDaily.dimension_type == "landing_page",
                MetricDaily.date >= this_week_start,
            )
        )
        .scalar() or 0
    )
    ga4_last = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "ga4",
                MetricDaily.metric_name == "sessions",
                MetricDaily.dimension_type == "landing_page",
                MetricDaily.date >= last_week_start,
                MetricDaily.date < this_week_start,
            )
        )
        .scalar() or 0
    )
    if ga4_last < min_sessions or cf_this < 50:
        return insights
    ga4_change = (ga4_this - ga4_last) / ga4_last if ga4_last > 0 else 0

    if cf_change > 0.50 and ga4_change < -0.10:
        insights.append({
            "type": "error_spike_alert",
            "kind": "problem",
            "message": (
                f"Cloudflare threats spiked {cf_change:.0%} WoW while GA4 sessions fell "
                f"{abs(ga4_change):.0%}. Traffic quality or attack pattern may be impacting the funnel."
            ),
            "recommended_action": (
                "1) Cloudflare → Security Events: identify bot/attack patterns. "
                "2) Tighten WAF / bot rules for abusive paths. "
                "3) Confirm real users still pass. 4) Recheck GA4 sessions next week."
            ),
            "severity": "high",
            "impact_weight": round(min(100.0, abs(ga4_change) * 80 + min(20.0, cf_this / 100)), 1),
        })
    return insights


def _pagespeed_opportunity(client_id: int, db, thr=None) -> list[dict]:
    """PageSpeed: <50 problem, 50–69 opportunity. One finding per URL (latest score)."""
    thr = thr or thresholds_for_client(db, client_id)
    urgent = thr.get("pagespeed_urgent", 50)
    improve = thr.get("pagespeed_improve", 70)
    insights = []
    today = date.today()
    start_date = today - timedelta(days=14)

    perf_rows = (
        db.query(MetricDaily)
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "pagespeed",
                MetricDaily.metric_name == "performance_score_mobile",
                MetricDaily.date >= start_date,
            )
        )
        .order_by(MetricDaily.date.desc())
        .all()
    )

    seen_urls: set[str] = set()
    for row in perf_rows:
        url = row.dimension_value or "page"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        score = row.value
        if score < urgent:
            insights.append({
                "type": "pagespeed_urgent",
                "kind": "problem",
                "message": (
                    f'Mobile PageSpeed score for "{url}" is {score:.0f}/100. '
                    f"Core Web Vitals are likely failing — this directly hurts rankings."
                ),
                "recommended_action": (
                    f"On {url}:\n"
                    f"1) Run PageSpeed Insights (mobile) and note the LCP element.\n"
                    f"2) Compress/resize the hero (WebP/AVIF); preload the LCP image; set width/height.\n"
                    f"3) Defer non-critical JS; remove unused CSS/third parties.\n"
                    f"4) Enable CDN caching; retest until mobile score ≥{improve:.0f}; recheck clicks in 14 days."
                ),
                "severity": "high",
                "impact_weight": round(min(100.0, (urgent - score) * 2 + 40), 1),
                "metrics_to_watch": ["gsc.clicks", "ga4.sessions"],
            })
        elif score < improve:
            insights.append({
                "type": "pagespeed_improve",
                "kind": "opportunity",
                "message": (
                    f'Mobile PageSpeed score for "{url}" is {score:.0f}/100. '
                    f"Below the {improve:.0f}-point threshold. Room for meaningful improvement."
                ),
                "recommended_action": (
                    f"On {url}:\n"
                    f"1) Open PSI mobile — focus on LCP and Total Blocking Time.\n"
                    f"2) Lazy-load below-fold media; preload the LCP image.\n"
                    f"3) Retest until mobile score ≥{improve:.0f}."
                ),
                "severity": "low",
                "impact_weight": round(min(80.0, (improve - score) * 1.5 + 20), 1),
                "metrics_to_watch": ["gsc.clicks", "ga4.sessions"],
            })
    return cap_insights(insights, thr)


def _mobile_desktop_gap(client_id: int, db, thr=None) -> list[dict]:
    """Large mobile vs desktop CTR gap with meaningful volume -> mobile UX problem."""
    thr = thr or thresholds_for_client(db, client_id)
    min_impr = thr.get("min_impressions_30d", 1000)
    insights = []
    today = date.today()
    start_date = today - timedelta(days=30)

    device_rows = (
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
                MetricDaily.dimension_type == "device",
                MetricDaily.date >= start_date,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )

    by_device: dict[str, dict] = {}
    for row in device_rows:
        device = row.dimension_value or ""
        bucket = by_device.setdefault(device, {})
        if row.metric_name == "position":
            bucket[row.metric_name] = row.avg_val or 0
        elif row.metric_name == "ctr":
            pass  # discard avg of daily ratios — compute from sum(clicks)/sum(impressions)
        else:
            bucket[row.metric_name] = row.sum_val or 0

    # Compute correct weighted CTR per device from summed clicks / summed impressions
    for device in by_device:
        dev = by_device[device]
        dev_clicks = dev.get("clicks", 0) or 0
        dev_impr = dev.get("impressions", 0) or 0
        dev["ctr"] = (dev_clicks / dev_impr) if dev_impr > 0 else 0

    mobile_ctr = by_device.get("MOBILE", {}).get("ctr", 0)
    desktop_ctr = by_device.get("DESKTOP", {}).get("ctr", 0)
    mobile_impr = by_device.get("MOBILE", {}).get("impressions", 0)

    if desktop_ctr > 0 and mobile_ctr > 0 and mobile_impr >= min_impr:
        ctr_gap = (desktop_ctr - mobile_ctr) / desktop_ctr
        if ctr_gap > 0.30:
            top_pages = _top_gsc_pages_by_clicks(db, client_id, days=30, limit=3)
            page_list = _fmt_url_list(top_pages)
            top_url = top_pages[0] if top_pages else None
            if top_url:
                message = (
                    f"Mobile CTR ({mobile_ctr:.1%}) is significantly lower than desktop "
                    f"({desktop_ctr:.1%}) across {mobile_impr:.0f} mobile impr/30d. "
                    f"Prioritize mobile UX/SERP on: {page_list}."
                )
                recommended = (
                    f"On {top_url} (highest-click page — fix mobile first):\n"
                    "1) Incognito mobile SERP: is the title truncated vs desktop?\n"
                    "2) Open the live page on a phone: fix tap targets, font size, sticky header covering content.\n"
                    "3) Run mobile PageSpeed; fix LCP if score is weak.\n"
                    "4) Recheck GSC mobile CTR for this URL in 14 days."
                    + (
                        f"\n5) Then repeat on {_fmt_url_list(top_pages[1:])}."
                        if len(top_pages) > 1
                        else ""
                    )
                )
            else:
                message = (
                    f"Mobile CTR ({mobile_ctr:.1%}) is significantly lower than desktop "
                    f"({desktop_ctr:.1%}) across {mobile_impr:.0f} mobile impr/30d. "
                    f"Mobile SERP truncation or UX is likely costing clicks."
                )
                recommended = (
                    "1) GSC → Devices → open top pages by impressions; compare mobile vs desktop CTR.\n"
                    "2) On the worst page: shorten title for mobile truncation; fix tap targets/sticky header.\n"
                    "3) Improve mobile speed (LCP). 4) Recheck mobile CTR in 14 days."
                )
            insights.append({
                "type": "mobile_ctr_gap",
                "kind": "problem",
                "message": message,
                "recommended_action": recommended,
                "severity": "medium",
                "impact_weight": round(min(100.0, ctr_gap * 80 + min(20.0, mobile_impr / 500)), 1),
            })

    return insights


def _bing_gsc_gap(client_id: int, db, thr=None) -> list[dict]:
    """Bing vs Google gap — only when Bing datasource is connected."""
    thr = thr or thresholds_for_client(db, client_id)
    if not _bing_datasource_connected(db, client_id):
        return []

    insights = []
    today = date.today()
    start_date = today - timedelta(days=30)

    gsc_clicks = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "clicks",
                MetricDaily.dimension_type == "device",
                MetricDaily.date >= start_date,
            )
        )
        .scalar() or 0
    )

    bing_clicks = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "bing",
                MetricDaily.metric_name == "clicks",
                MetricDaily.dimension_type == "query",
                MetricDaily.date >= start_date,
            )
        )
        .scalar() or 0
    )

    if gsc_clicks > 100 and bing_clicks == 0:
        insights.append({
            "type": "bing_opportunity",
            "kind": "opportunity",
            "message": (
                f"Bing connected but 0 clicks while Google has {gsc_clicks:.0f}. "
                f"Bing may be under-crawled or under-optimized."
            ),
            "recommended_action": (
                "1) Bing Webmaster → Crawl / Index Explorer. "
                "2) Resubmit sitemap. "
                "3) Confirm robots.txt allows Bingbot. 4) Recheck in a week."
            ),
            "severity": "medium",
        })
    elif gsc_clicks > 0 and bing_clicks > 0:
        ratio = bing_clicks / gsc_clicks if gsc_clicks > 0 else 0
        if ratio < 0.05:
            insights.append({
                "type": "bing_underperform",
                "kind": "opportunity",
                "message": (
                    f"Bing generates only {ratio:.1%} of Google's clicks "
                    f"({bing_clicks:.0f} vs {gsc_clicks:.0f}). Industry share is often 8–12%."
                ),
                "recommended_action": (
                    "1) Bing Webmaster → fix crawl errors. "
                    "2) Resubmit sitemap. 3) Confirm robots.txt allows Bingbot."
                ),
                "severity": "low",
            })
    return insights


def _page_content_issues(client_id: int, db, thr=None) -> list[dict]:
    """Technical SEO issues from recent PageSnapshot crawl data."""
    from datetime import datetime, timedelta
    from app.models import PageSnapshot

    thr = thr or thresholds_for_client(db, client_id)
    min_words = int(thr.get("min_page_words", 150) or 150)
    cutoff = utcnow() - timedelta(days=7)

    # Latest snapshot per URL (by fetched_at)
    rows = (
        db.query(PageSnapshot)
        .filter(
            PageSnapshot.client_id == client_id,
            PageSnapshot.fetched_at >= cutoff,
        )
        .order_by(PageSnapshot.fetched_at.desc())
        .limit(200)
        .all()
    )
    latest: dict[str, PageSnapshot] = {}
    for snap in rows:
        key = (snap.url or "").rstrip("/").lower()
        if key and key not in latest:
            latest[key] = snap

    insights: list[dict] = []
    broken = []
    no_title = []
    no_h1 = []
    thin = []
    no_meta = []
    no_schema = []

    for snap in latest.values():
        url = snap.url or ""
        code = snap.status_code or 0
        if code >= 400:
            broken.append((url, code))
            continue
        if not (snap.title or "").strip():
            no_title.append(url)
        if not (snap.h1 or "").strip():
            no_h1.append(url)
        if (snap.word_count or 0) < min_words and code < 400:
            thin.append((url, snap.word_count or 0))
        if not (snap.meta_description or "").strip():
            no_meta.append(url)
        if not (snap.schema_types or "").strip():
            no_schema.append(url)

    def _list_urls(items: list, n: int = 5) -> str:
        urls = [i[0] if isinstance(i, tuple) else i for i in items[:n]]
        return ", ".join(f'"{u}"' for u in urls)

    def _per_url_fix(urls: list[str], verb: str, detail: str, *, max_n: int = 5) -> str:
        lines = []
        for i, u in enumerate(urls[:max_n], 1):
            lines.append(f"{i}) On {u}: {detail}")
        if len(urls) > max_n:
            lines.append(f"{max_n + 1}) Repeat for the remaining {len(urls) - max_n} URL(s).")
        lines.append(f"Last) Deploy, request indexing for fixed URLs, re-{verb} in 7 days.")
        return "\n".join(lines)

    if broken:
        details = "; ".join(f"{u} (HTTP {code})" for u, code in broken[:5])
        insights.append({
            "type": "crawl_broken_pages",
            "kind": "problem",
            "message": (
                f"{len(broken)} crawled page(s) return HTTP errors: {details}."
            ),
            "recommended_action": _per_url_fix(
                [u for u, _ in broken],
                "crawl",
                "fix 4xx/5xx (restore content or 301 to the closest relevant live URL); remove dead links from nav/sitemap.",
            ),
            "severity": "high",
            "metrics_to_watch": ["gsc.clicks", "gsc.impressions"],
        })
    if no_title:
        insights.append({
            "type": "crawl_missing_title",
            "kind": "problem",
            "message": (
                f"{len(no_title)} page(s) missing <title>: {_list_urls(no_title)}."
            ),
            "recommended_action": _per_url_fix(
                no_title,
                "verify",
                'add a unique <title> ≤60 chars with primary keyword + brand (e.g. "Service in City | Brand").',
            ),
            "severity": "medium",
        })
    if no_h1:
        insights.append({
            "type": "crawl_missing_h1",
            "kind": "problem",
            "message": (
                f"{len(no_h1)} page(s) missing H1: {_list_urls(no_h1)}."
            ),
            "recommended_action": _per_url_fix(
                no_h1,
                "check",
                "add one clear H1 matching the page's primary search intent (not a logo alt).",
            ),
            "severity": "medium",
        })
    if thin:
        thin_bits = "; ".join(f"{u} ({wc} words)" for u, wc in thin[:5])
        insights.append({
            "type": "crawl_thin_content",
            "kind": "opportunity",
            "message": (
                f"{len(thin)} page(s) under {min_words} words: {thin_bits}."
            ),
            "recommended_action": _per_url_fix(
                [u for u, _ in thin],
                "measure",
                f"expand to ≥{min_words} useful words — add FAQ/supporting sections that answer the ranking query; do not pad with fluff.",
            ),
            "severity": "low",
        })
    if no_meta and len(no_meta) >= 3:
        insights.append({
            "type": "crawl_missing_meta",
            "kind": "opportunity",
            "message": (
                f"{len(no_meta)} page(s) missing meta description: {_list_urls(no_meta)}."
            ),
            "recommended_action": _per_url_fix(
                no_meta,
                "check CTR",
                "write a unique meta ≤155 chars with primary keyword + clear CTA (call / free estimate).",
            ),
            "severity": "low",
        })
    if no_schema and len(no_schema) >= 3:
        insights.append({
            "type": "crawl_missing_schema",
            "kind": "opportunity",
            "message": (
                f"{len(no_schema)} page(s) missing structured data (schema.org): {_list_urls(no_schema)}."
            ),
            "recommended_action": _per_url_fix(
                no_schema,
                "verify rich results",
                "add relevant schema.org type (LocalBusiness, Article, Product, FAQ) in JSON-LD; test in Google Rich Results.",
            ),
            "severity": "medium",
        })

    return cap_insights(insights, thr)
"""GA4 CRO and ads/leads insight rules."""

from datetime import date, timedelta
from sqlalchemy import func, and_
from app.models import MetricDaily
from app.insight_thresholds import thresholds_for_client, cap_insights
from app.timeutil import utcnow

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

def _ga4_cro_opportunity(client_id: int, db, thr=None) -> list[dict]:
    """GA4 pages with meaningful traffic but below-avg conversion -> CRO problem.

    Before diagnosing conversion leaks, verifies that *any* conversions have ever
    been recorded. If not, the insight is about verifying tracking, not fixing CTAs.
    """
    thr = thr or thresholds_for_client(db, client_id)

    # Tracking-integrity check: if zero conversions ever recorded, the fix is
    # "verify GA4 tracking is installed", not "fix your CTAs"
    has_conv, total_conv = has_ever_had_conversions(db, client_id, lookback_days=90)
    if not has_conv:
        today = date.today()
        start_date = today - timedelta(days=30)
        session_count = float(
            db.query(func.sum(MetricDaily.value))
            .filter(
                and_(
                    MetricDaily.client_id == client_id,
                    MetricDaily.source == "ga4",
                    MetricDaily.metric_name == "sessions",
                    MetricDaily.date >= start_date,
                )
            )
            .scalar() or 0
        )
        if session_count > 0:
            return [{
                "type": "verify_tracking",
                "kind": "problem",
                "message": (
                    f"{session_count:.0f} GA4 sessions in the last 30 days but zero "
                    f"conversions recorded in the last 90 days — likely a tracking gap, "
                    f"not a conversion problem."
                ),
                "recommended_action": (
                    "1) Open GA4 Realtime and submit a test form/call-click yourself; "
                    "confirm the key_event fires.\n"
                    "2) Check GTM (or the site's tracking snippet) is present on the "
                    "live site — view source, search for the GA4 measurement ID.\n"
                    "3) If it's not firing, this is a dev fix, not a CRO fix — reinstall "
                    "tracking before touching CTAs or forms.\n"
                    "4) Once confirmed firing, re-run this rule next cycle — the "
                    "underlying CRO analysis will resume automatically."
                ),
                "severity": "high",
                "impact_weight": 90.0,
            }]
        return []

    min_sessions = thr.get("min_landing_sessions_30d", 250)
    insights = []
    today = date.today()
    start_date = today - timedelta(days=30)

    rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("total_val"),
            MetricDaily.metric_name,
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "ga4",
                MetricDaily.metric_name.in_(["sessions", "key_events"]),
                MetricDaily.dimension_type == "landing_page",
                MetricDaily.date >= start_date,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )

    by_page: dict[str, dict] = {}
    for row in rows:
        page = row.dimension_value or "/"
        by_page.setdefault(page, {})[row.metric_name] = row.total_val or 0

    if not by_page:
        return insights

    total_sessions = sum(v.get("sessions", 0) for v in by_page.values())
    total_conversions = sum(v.get("key_events", 0) for v in by_page.values())
    avg_cvr = total_conversions / total_sessions if total_sessions > 0 else 0
    avg_sessions = total_sessions / len(by_page) if by_page else 0

    for page, metrics in by_page.items():
        sessions = metrics.get("sessions", 0)
        conversions = metrics.get("key_events", 0)
        page_cvr = conversions / sessions if sessions > 0 else 0
        if sessions < min_sessions:
            continue
        if sessions > avg_sessions and page_cvr < avg_cvr * 0.70:
            insights.append({
                "type": "cro_opportunity",
                "kind": "problem",
                "message": (
                    f'"{page}" has {sessions:.0f} sessions/30d (above avg {avg_sessions:.0f}) '
                    f'but converts at {page_cvr:.1%} (avg {avg_cvr:.1%}). '
                    f"High-traffic conversion leak."
                ),
                "recommended_action": (
                    f"On {page}:\n"
                    f"1) Watch Clarity recordings for this exact URL (rage clicks, dead ends).\n"
                    f"2) Put one primary CTA above the fold; remove competing CTAs.\n"
                    f"3) Cut form fields / add trust near CTA.\n"
                    f"4) A/B test headline or CTA for 2 weeks; watch key_events on this URL."
                ),
                "severity": "medium",
                "impact_weight": round(min(100.0, sessions / 20 + (avg_cvr - page_cvr) * 200), 1),
            })
    return cap_insights(insights, thr)


def _high_bounce_low_conversion(client_id: int, db, thr=None) -> list[dict]:
    """High Clarity bounce + low GA4 conversion on high-traffic pages -> problem."""
    thr = thr or thresholds_for_client(db, client_id)
    bounce_cut = thr.get("bounce_rate_high", 0.70)
    min_sessions = thr.get("min_landing_sessions_30d", 250)
    insights = []
    today = date.today()
    start_date = today - timedelta(days=30)

    clarity_rows = (
        db.query(MetricDaily)
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "clarity",
                MetricDaily.metric_name == "bounce_rate",
                MetricDaily.date >= start_date,
            )
        )
        .all()
    )

    high_bounce_pages = set()
    for row in clarity_rows:
        if row.dimension_value and row.value > bounce_cut:
            high_bounce_pages.add(row.dimension_value)
    if not high_bounce_pages:
        return insights

    ga4_rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("total_val"),
            MetricDaily.metric_name,
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "ga4",
                MetricDaily.metric_name.in_(["sessions", "key_events"]),
                MetricDaily.dimension_type == "landing_page",
                MetricDaily.date >= start_date,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )

    by_page: dict[str, dict] = {}
    for row in ga4_rows:
        page = row.dimension_value or "/"
        by_page.setdefault(page, {})[row.metric_name] = row.total_val or 0

    total_conv = sum(v.get("key_events", 0) for v in by_page.values())
    total_sess = sum(v.get("sessions", 0) for v in by_page.values())
    avg_cvr = total_conv / total_sess if total_sess > 0 else 0

    for page in high_bounce_pages:
        metrics = by_page.get(page, {})
        sessions = metrics.get("sessions", 0)
        conversions = metrics.get("key_events", 0)
        page_cvr = conversions / sessions if sessions > 0 else 0

        if sessions >= min_sessions and page_cvr < avg_cvr * 0.50:
            insights.append({
                "type": "bounce_cro_alert",
                "kind": "problem",
                "message": (
                    f'"{page}" has high bounce rate (>{bounce_cut:.0%}) per Clarity + low conversion '
                    f"({page_cvr:.1%} vs avg {avg_cvr:.1%}, {sessions:.0f} sessions/30d). Combined UX/CRO issue."
                ),
                "recommended_action": (
                    f"On {page}:\n"
                    f"1) Watch 5 Clarity recordings for this URL.\n"
                    f"2) Align hero with the search/ad query that sent traffic.\n"
                    f"3) Raise primary CTA; cut clutter above the fold.\n"
                    f"4) Fix load >3s on mobile. 5) Remeasure bounce + CVR on this URL in 14 days."
                ),
                "severity": "medium",
                "impact_weight": round(min(100.0, sessions / 15), 1),
            })
    return cap_insights(insights, thr)


def _ads_spend_low_leads(client_id: int, db, thr=None) -> list[dict]:
    """High ad spend with flat/low CRM leads.

    Before diagnosing offer/tracking leaks, verifies that *any* conversions have ever
    been recorded. If not, the insight is about verifying tracking, not fixing ads.
    """
    today = date.today()

    # Tracking-integrity check: if zero conversions ever recorded, the fix is
    # "verify GA4/CRM tracking", not "pause ad campaigns"
    has_conv, total_conv = has_ever_had_conversions(db, client_id, lookback_days=90)
    cost = (
        _sum_metric(db, client_id, "ads_csv", "cost", today - timedelta(days=30), today, "campaign")
        + _sum_metric(db, client_id, "google_ads", "cost", today - timedelta(days=30), today, "campaign")
        + _sum_metric(db, client_id, "meta_ads", "cost", today - timedelta(days=30), today, "campaign")
    )
    if not has_conv and cost >= 100:
        return [{
            "type": "verify_tracking",
            "kind": "problem",
            "message": (
                f"Ad spend ${cost:,.0f} in 30 days but zero conversions or CRM "
                f"leads have ever been recorded. This is a tracking issue, not an offer issue — "
                f"verify GA4 key_event tags and HubSpot form sync before changing ad strategy."
            ),
            "recommended_action": (
                "1) From each active ad, open the final landing URL and submit a test form.\n"
                "2) Confirm a HubSpot contact is created (with UTMs matching the ad campaign).\n"
                "3) Open GA4 DebugView and trigger the form — does the key_event fire?\n"
                "4) Fix any broken tracking first, then remeasure leads vs spend in 14 days.\n"
                "5) Only pause campaigns after confirming tracking works."
            ),
            "severity": "high",
        }]

    this_start = today - timedelta(days=6)
    prev_start = today - timedelta(days=13)
    prev_end = today - timedelta(days=7)

    cost = (
        _sum_metric(db, client_id, "ads_csv", "cost", this_start, today, "campaign")
        + _sum_metric(db, client_id, "google_ads", "cost", this_start, today, "campaign")
        + _sum_metric(db, client_id, "meta_ads", "cost", this_start, today, "campaign")
    )
    leads = _sum_metric(db, client_id, "hubspot", "leads", this_start, today)
    leads_prev = _sum_metric(db, client_id, "hubspot", "leads", prev_start, prev_end)

    if cost < 100:
        return []
    leads_flat = leads <= max(1, leads_prev * 1.05)
    if leads >= 10 and not leads_flat:
        return []

    cpl = cost / leads if leads > 0 else None
    landers = _top_ga4_landing_pages(db, client_id, days=14, limit=3)
    if not landers:
        landers = _top_gsc_pages_by_clicks(db, client_id, days=14, limit=3)
    lander_list = _fmt_url_list(landers)
    top = landers[0] if landers else None
    if top:
        message = (
            f"Ad spend ${cost:,.0f} this week with only {leads:.0f} CRM leads"
            + (f" (${cpl:,.0f} CPL)" if cpl else " (no leads)")
            + f". Paid → pipeline leak. Check forms/CTAs on: {lander_list}."
        )
        recommended = (
            f"On {top} (top landing page):\n"
            "1) Submit a test lead — confirm a HubSpot contact is created with UTMs.\n"
            "2) Confirm the primary CTA/form matches the ad promise above the fold.\n"
            "3) Pause or cut budget on campaigns still sending traffic here with zero CRM leads.\n"
            "4) Remeasure leads vs spend in 7 days."
            + (f"\n5) Also verify tracking on {_fmt_url_list(landers[1:])}." if len(landers) > 1 else "")
        )
    else:
        message = (
            f"Ad spend ${cost:,.0f} this week with only {leads:.0f} CRM leads"
            + (f" (${cpl:,.0f} CPL)" if cpl else " (no leads)")
            + ". Paid → pipeline leak — identify the live ad landing URLs and test forms."
        )
        recommended = (
            "1) From each active ad, open the final landing URL and submit a test form → HubSpot.\n"
            "2) Pause campaigns with zero leads until a test contact appears.\n"
            "3) Align offer/CTA with ad copy on that exact URL.\n"
            "4) Remeasure leads vs spend in 7 days."
        )
    return [{
        "type": "ads_spend_low_leads",
        "kind": "problem",
        "message": message,
        "recommended_action": recommended,
        "severity": "high" if leads == 0 and cost >= 200 else "medium",
    }]


def _leads_revenue_leak(client_id: int, db, thr=None) -> list[dict]:
    """Leads up but closed_won / revenue flat."""
    today = date.today()
    this_start = today - timedelta(days=14)
    prev_start = today - timedelta(days=28)
    prev_end = today - timedelta(days=15)

    leads = _sum_metric(db, client_id, "hubspot", "leads", this_start, today)
    leads_prev = _sum_metric(db, client_id, "hubspot", "leads", prev_start, prev_end)
    revenue = _sum_metric(db, client_id, "hubspot", "revenue", this_start, today)
    revenue_prev = _sum_metric(db, client_id, "hubspot", "revenue", prev_start, prev_end)
    closed = _sum_metric(db, client_id, "hubspot", "closed_won", this_start, today)

    if leads < 5:
        return []
    leads_up = leads >= leads_prev * 1.15 if leads_prev > 0 else leads >= 8
    revenue_flat = revenue <= revenue_prev * 1.05 if revenue_prev > 0 else revenue == 0
    if not (leads_up and revenue_flat and closed <= 1):
        return []

    landers = _top_ga4_landing_pages(db, client_id, days=28, limit=3)
    lander_bit = f" Top lead sources/landings to sample: {_fmt_url_list(landers)}." if landers else ""
    return [{
        "type": "leads_revenue_leak",
        "kind": "problem",
        "message": (
            f"Leads rose to {leads:.0f} (vs {leads_prev:.0f} prior) but revenue "
            f"${revenue:,.0f} / closed-won {closed:.0f} stayed flat — sales handoff leak."
            f"{lander_bit}"
        ),
        "recommended_action": (
            "1) In HubSpot, open the last 10 leads — note source URL and whether they were in-area/qualified.\n"
            + (
                f"2) For leads from {landers[0]}: check if the page offer matches what sales can close.\n"
                if landers
                else "2) Compare landing offer vs sales qualification criteria.\n"
            )
            + "3) Enforce speed-to-lead SLA (same-day call/email) and log first-touch time.\n"
            "4) Remeasure closed_won and revenue in 14 days."
        ),
        "severity": "high",
    }]


def _organic_leads_leak(client_id: int, db, thr=None) -> list[dict]:
    """Organic clicks up but CRM leads flat.

    Before diagnosing offer/tracking leaks, verifies that *any* conversions have ever
    been recorded. If not, the insight is about verifying tracking, not fixing CTAs.
    """
    today = date.today()

    # Tracking-integrity check: if zero conversions ever recorded, the fix is
    # "verify GA4/CRM tracking", not "fix CTAs on organic pages"
    has_conv, total_conv = has_ever_had_conversions(db, client_id, lookback_days=90)
    if not has_conv:
        organic_clicks = _sum_metric(db, client_id, "gsc", "clicks", today - timedelta(days=30), today, "device")
        if organic_clicks >= 80:
            return [{
                "type": "verify_tracking",
                "kind": "problem",
                "message": (
                    f"Organic clicks {int(organic_clicks):,} in 30 days but zero conversions or CRM "
                    f"leads have ever been recorded. This is a tracking issue, not a UX/offer issue — "
                    f"verify GA4 key_event tags and HubSpot form sync are installed correctly."
                ),
                "recommended_action": (
                    "1) Submit a test form on the top organic landing page.\n"
                    "2) Confirm a HubSpot contact is created (with UTMs).\n"
                    "3) Open GA4 DebugView and trigger the form — does the key_event fire?\n"
                    "4) If using GTM, confirm the key_event tag fires on form submit.\n"
                    "5) Fix any broken tracking, then remeasure leads vs clicks in 14 days."
                ),
                "severity": "high",
            }]
        return []

    this_start = today - timedelta(days=14)
    prev_start = today - timedelta(days=28)
    prev_end = today - timedelta(days=15)

    clicks = _sum_metric(db, client_id, "gsc", "clicks", this_start, today, "device")
    clicks_prev = _sum_metric(db, client_id, "gsc", "clicks", prev_start, prev_end, "device")
    leads = _sum_metric(db, client_id, "hubspot", "leads", this_start, today)
    leads_prev = _sum_metric(db, client_id, "hubspot", "leads", prev_start, prev_end)

    has_crm = leads > 0 or leads_prev > 0 or _sum_metric(
        db, client_id, "hubspot", "opportunities", today - timedelta(days=60), today
    ) > 0
    if not has_crm or clicks < 80:
        return []
    clicks_up = clicks >= clicks_prev * 1.1 if clicks_prev > 0 else clicks >= 100
    leads_flat = leads <= max(leads_prev * 1.05, 1) if leads_prev > 0 else leads == 0
    if not (clicks_up and leads_flat):
        return []

    top_pages = _top_gsc_pages_by_clicks(db, client_id, days=14, limit=3)
    page_list = _fmt_url_list(top_pages)
    top = top_pages[0] if top_pages else None
    if top:
        message = (
            f"Organic clicks {clicks:.0f} (up from {clicks_prev:.0f}) but CRM leads "
            f"{leads:.0f} flat — tracking or offer leak on: {page_list}."
        )
        recommended = (
            f"On {top} (top organic page by clicks):\n"
            "1) Submit the contact form — confirm a HubSpot contact + thank-you/key_event fire.\n"
            "2) Put one clear CTA above the fold (call / free estimate) matching search intent.\n"
            "3) If the page ranks for informational queries, add a mid-page CTA to a service/contact URL.\n"
            "4) Remeasure HubSpot leads vs GSC clicks in 14 days."
            + (f"\n5) Repeat CTA/tracking check on {_fmt_url_list(top_pages[1:])}." if len(top_pages) > 1 else "")
        )
    else:
        message = (
            f"Organic clicks {clicks:.0f} (up from {clicks_prev:.0f}) but CRM leads "
            f"{leads:.0f} flat — tracking or offer leak."
        )
        recommended = (
            "1) GSC → Pages: open the top 3 URLs by clicks; test each form → HubSpot.\n"
            "2) Strengthen CTAs on those exact pages.\n"
            "3) Check intent mismatch on rising queries.\n"
            "4) Remeasure leads vs clicks in 14 days."
        )
    return [{
        "type": "organic_leads_leak",
        "kind": "problem",
        "message": message,
        "recommended_action": recommended,
        "severity": "medium",
    }]


def _pause_weak_campaigns(client_id: int, db, thr=None) -> list[dict]:
    """Flag campaigns with meaningful spend and zero conversions (14d)."""
    thr = thr or thresholds_for_client(db, client_id)
    today = date.today()
    start = today - timedelta(days=14)
    min_spend = float(thr.get("weak_campaign_min_spend", 50))

    rows = (
        db.query(
            MetricDaily.source,
            MetricDaily.dimension_value,
            MetricDaily.metric_name,
            func.sum(MetricDaily.value).label("total"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source.in_(["ads_csv", "google_ads", "meta_ads"]),
                MetricDaily.dimension_type == "campaign",
                MetricDaily.metric_name.in_(["cost", "conversions", "clicks"]),
                MetricDaily.date >= start,
                MetricDaily.date <= today,
            )
        )
        .group_by(MetricDaily.source, MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    by_campaign: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        key = (row.source or "", row.dimension_value or "Unknown")
        by_campaign.setdefault(key, {})[row.metric_name] = float(row.total or 0)

    insights = []
    for (source, campaign), metrics in by_campaign.items():
        cost = metrics.get("cost", 0.0)
        conversions = metrics.get("conversions", 0.0)
        clicks = metrics.get("clicks", 0.0)
        if cost < min_spend or conversions > 0:
            continue
        channel = source.replace("_", " ")
        insights.append({
            "type": "pause_weak_campaign",
            "kind": "problem",
            "message": (
                f'Campaign "{campaign}" ({channel}) spent ${cost:,.0f} in 14 days with '
                f"{conversions:.0f} conversions and {clicks:.0f} clicks — pause or rebuild."
            ),
            "recommended_action": (
                f'In {channel} → Campaigns → "{campaign}":\n'
                "1) Pause the campaign (or cut budget 80%) until a conversion path is proven.\n"
                "2) Open the top ad landing URL and submit a test conversion/form.\n"
                "3) Confirm GA4 key_event + CRM lead fire with the campaign UTM.\n"
                "4) Rebuild creative/offer or keywords only after tracking is verified.\n"
                "5) Remeasure cost vs conversions in 7 days."
            ),
            "severity": "high" if cost >= 200 else "medium",
            "impact_weight": round(min(100.0, cost / 5), 1),
            "target_query": campaign[:500],
        })
    # Cap so one account cannot flood the Fix queue
    insights.sort(key=lambda i: i.get("impact_weight") or 0, reverse=True)
    return cap_insights(insights[:8], thr)


def _ads_search_term_waste(client_id: int, db, thr=None) -> list[dict]:
    """Flag Google Ads search terms with spend and zero conversions (14d)."""
    thr = thr or thresholds_for_client(db, client_id)
    today = date.today()
    start = today - timedelta(days=14)
    min_spend = float(thr.get("search_term_waste_min_spend", 25))

    rows = (
        db.query(
            MetricDaily.dimension_value,
            MetricDaily.metric_name,
            func.sum(MetricDaily.value).label("total"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "google_ads",
                MetricDaily.dimension_type == "search_term",
                MetricDaily.metric_name.in_(["cost", "conversions", "clicks"]),
                MetricDaily.date >= start,
                MetricDaily.date <= today,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    by_term: dict[str, dict[str, float]] = {}
    for row in rows:
        term = row.dimension_value or ""
        if not term:
            continue
        by_term.setdefault(term, {})[row.metric_name] = float(row.total or 0)

    insights = []
    for term, metrics in by_term.items():
        cost = metrics.get("cost", 0.0)
        conversions = metrics.get("conversions", 0.0)
        clicks = metrics.get("clicks", 0.0)
        if cost < min_spend or conversions > 0:
            continue
        insights.append({
            "type": "ads_search_term_waste",
            "kind": "problem",
            "message": (
                f'Search term "{term}" spent ${cost:,.0f} in 14 days with '
                f"{conversions:.0f} conversions ({clicks:.0f} clicks) — add as negative or pause."
            ),
            "recommended_action": (
                f'In Google Ads → Insights & reports → Search terms → "{term}":\n'
                "1) Add as a negative keyword (exact or phrase) on the wasting campaign/ad group.\n"
                "2) Check if a better match type or landing page could convert — otherwise keep negative.\n"
                "3) Remeasure wasted spend in 7 days."
            ),
            "severity": "high" if cost >= 100 else "medium",
            "impact_weight": round(min(100.0, cost / 3), 1),
            "target_query": term[:500],
        })
    insights.sort(key=lambda i: i.get("impact_weight") or 0, reverse=True)
    return cap_insights(insights[:6], thr)


def _meta_placement_waste(client_id: int, db, thr=None) -> list[dict]:
    """Flag Meta placements with spend and zero conversions (14d)."""
    thr = thr or thresholds_for_client(db, client_id)
    today = date.today()
    start = today - timedelta(days=14)
    min_spend = float(thr.get("meta_placement_waste_min_spend", 40))

    rows = (
        db.query(
            MetricDaily.dimension_value,
            MetricDaily.metric_name,
            func.sum(MetricDaily.value).label("total"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "meta_ads",
                MetricDaily.dimension_type == "placement",
                MetricDaily.metric_name.in_(["cost", "conversions", "clicks", "impressions"]),
                MetricDaily.date >= start,
                MetricDaily.date <= today,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    by_place: dict[str, dict[str, float]] = {}
    for row in rows:
        place = (row.dimension_value or "").strip()
        if not place:
            continue
        by_place.setdefault(place, {})[row.metric_name] = float(row.total or 0)

    insights = []
    for place, metrics in by_place.items():
        cost = metrics.get("cost", 0.0)
        conversions = metrics.get("conversions", 0.0)
        clicks = metrics.get("clicks", 0.0)
        if cost < min_spend or conversions > 0:
            continue
        insights.append({
            "type": "meta_placement_waste",
            "kind": "problem",
            "message": (
                f'Meta placement "{place}" spent ${cost:,.0f} in 14 days with '
                f"{conversions:.0f} conversions ({clicks:.0f} clicks) — exclude or reallocate."
            ),
            "recommended_action": (
                f'In Meta Ads Manager → edit placements → exclude "{place}" (or cut budget):\n'
                "1) Keep spend on placements that convert; pause Audience Network / weak surfaces first.\n"
                "2) Confirm pixel events fire on the landing URL for this placement.\n"
                "3) Remeasure wasted spend in 7 days."
            ),
            "severity": "high" if cost >= 120 else "medium",
            "impact_weight": round(min(100.0, cost / 3), 1),
            "target_query": place[:500],
        })
    insights.sort(key=lambda i: i.get("impact_weight") or 0, reverse=True)
    return cap_insights(insights[:6], thr)


def _meta_creative_fatigue(client_id: int, db, thr=None) -> list[dict]:
    """Flag Meta ads with high frequency and collapsing CTR (14d)."""
    thr = thr or thresholds_for_client(db, client_id)
    today = date.today()
    start = today - timedelta(days=14)
    mid = today - timedelta(days=7)
    min_impr = float(thr.get("meta_creative_fatigue_min_impr", 2000))
    min_freq = float(thr.get("meta_creative_fatigue_min_freq", 2.5))
    ctr_drop = float(thr.get("meta_creative_fatigue_ctr_drop", 0.25))

    rows = (
        db.query(
            MetricDaily.dimension_value,
            MetricDaily.date,
            MetricDaily.metric_name,
            func.sum(MetricDaily.value).label("total"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "meta_ads",
                MetricDaily.dimension_type == "ad_creative",
                MetricDaily.metric_name.in_(["impressions", "frequency", "ctr", "cost", "clicks"]),
                MetricDaily.date >= start,
                MetricDaily.date <= today,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.date, MetricDaily.metric_name)
        .all()
    )
    # Aggregate early vs late week per creative
    by_ad: dict[str, dict[str, float]] = {}
    for row in rows:
        ad = (row.dimension_value or "").strip()
        if not ad:
            continue
        bucket = by_ad.setdefault(
            ad,
            {
                "impr": 0.0,
                "cost": 0.0,
                "freq_sum": 0.0,
                "freq_n": 0.0,
                "ctr_early_sum": 0.0,
                "ctr_early_n": 0.0,
                "ctr_late_sum": 0.0,
                "ctr_late_n": 0.0,
            },
        )
        val = float(row.total or 0)
        name = row.metric_name
        d = row.date
        if name == "impressions":
            bucket["impr"] += val
        elif name == "cost":
            bucket["cost"] += val
        elif name == "frequency" and val > 0:
            bucket["freq_sum"] += val
            bucket["freq_n"] += 1
        elif name == "ctr" and val > 0:
            if d < mid:
                bucket["ctr_early_sum"] += val
                bucket["ctr_early_n"] += 1
            else:
                bucket["ctr_late_sum"] += val
                bucket["ctr_late_n"] += 1

    insights = []
    for ad, m in by_ad.items():
        if m["impr"] < min_impr or m["freq_n"] <= 0:
            continue
        avg_freq = m["freq_sum"] / m["freq_n"]
        if avg_freq < min_freq:
            continue
        early = m["ctr_early_sum"] / m["ctr_early_n"] if m["ctr_early_n"] else None
        late = m["ctr_late_sum"] / m["ctr_late_n"] if m["ctr_late_n"] else None
        if early is None or late is None or early <= 0:
            continue
        drop = (early - late) / early
        if drop < ctr_drop:
            continue
        insights.append({
            "type": "meta_creative_fatigue",
            "kind": "problem",
            "message": (
                f'Meta creative "{ad[:80]}" shows fatigue: avg frequency {avg_freq:.1f}x, '
                f"CTR down {drop:.0%} week-over-week (${m['cost']:,.0f} spend)."
            ),
            "recommended_action": (
                f'Refresh creative for "{ad[:80]}":\n'
                "1) Duplicate the ad set with a new primary image/video + hook in the first 3s.\n"
                "2) Pause the fatigued ad once the replacement has spend.\n"
                "3) Cap frequency or broaden audience if the offer is unchanged.\n"
                "4) Remeasure CTR + CPA in 7 days."
            ),
            "severity": "high" if drop >= 0.4 or avg_freq >= 4 else "medium",
            "impact_weight": round(min(100.0, m["cost"] / 4 + drop * 40), 1),
            "target_query": ad[:500],
        })
    insights.sort(key=lambda i: i.get("impact_weight") or 0, reverse=True)
    return cap_insights(insights[:6], thr)


def _serp_sov_loss(client_id: int, db, thr=None) -> list[dict]:
    """Competitor share-of-voice pressure from latest SERP snapshots vs profile competitors."""
    from app.competitor_domains import parse_client_domains, parse_competitor_domains
    from app.models import Client, SerpSnapshot
    import json

    thr = thr or thresholds_for_client(db, client_id)
    client = db.query(Client).filter(Client.id == client_id).first()
    comps = parse_competitor_domains(client)
    owns = parse_client_domains(client)
    if not comps:
        return []

    snaps = (
        db.query(SerpSnapshot)
        .filter(SerpSnapshot.client_id == client_id)
        .order_by(SerpSnapshot.fetched_at.desc())
        .limit(40)
        .all()
    )
    if not snaps:
        return []

    # Dedupe by query keeping latest
    latest: dict[str, SerpSnapshot] = {}
    for s in snaps:
        q = (s.query or "").strip().lower()
        if q and q not in latest:
            latest[q] = s

    losses = 0
    wins = 0
    samples = []
    for q, snap in latest.items():
        try:
            results = json.loads(snap.results_json or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        client_pos = None
        comp_pos = None
        for row in results:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "")
            try:
                from urllib.parse import urlparse

                host = urlparse(url).netloc.lower().removeprefix("www.")
            except Exception:
                host = ""
            pos = int(row.get("position") or 0) or None
            if not host or not pos:
                continue
            if owns and any(host == d or host.endswith("." + d) for d in owns):
                if client_pos is None or pos < client_pos:
                    client_pos = pos
            if any(host == d or host.endswith("." + d) for d in comps):
                if comp_pos is None or pos < comp_pos:
                    comp_pos = pos
        if client_pos is None and comp_pos is None:
            continue
        if comp_pos is not None and (client_pos is None or comp_pos < client_pos):
            losses += 1
            if len(samples) < 3:
                samples.append(q)
        elif client_pos is not None:
            wins += 1

    measured = wins + losses
    if measured < 3 or losses == 0:
        return []
    loss_rate = losses / measured

    # Optional WoW from MetricDaily sov_presence time-series
    today = date.today()
    wow_note = ""
    presence_declined = False
    try:
        from app.metrics_service import sum_metric

        this_sum = sum_metric(
            db, client_id, "serp", "sov_presence", today - timedelta(days=6), today
        )
        prev_sum = sum_metric(
            db,
            client_id,
            "serp",
            "sov_presence",
            today - timedelta(days=13),
            today - timedelta(days=7),
        )
        this_n = (
            db.query(func.count(MetricDaily.id))
            .filter(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "serp",
                MetricDaily.metric_name == "sov_presence",
                MetricDaily.date >= today - timedelta(days=6),
                MetricDaily.date <= today,
            )
            .scalar()
            or 0
        )
        prev_n = (
            db.query(func.count(MetricDaily.id))
            .filter(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "serp",
                MetricDaily.metric_name == "sov_presence",
                MetricDaily.date >= today - timedelta(days=13),
                MetricDaily.date <= today - timedelta(days=7),
            )
            .scalar()
            or 0
        )
        if this_n and prev_n:
            cur_avg = this_sum / this_n
            prev_avg = prev_sum / prev_n
            delta = cur_avg - prev_avg
            if abs(delta) >= 0.05:
                wow_note = f" SoV presence {cur_avg:.0%} vs {prev_avg:.0%} prior week ({delta:+.0%})."
                presence_declined = delta < 0
    except Exception:
        wow_note = ""

    if loss_rate < 0.4 and not presence_declined:
        return []

    sample_str = ", ".join(f'"{s}"' for s in samples) if samples else "tracked queries"
    return [{
        "type": "sov_loss",
        "kind": "problem",
        "message": (
            f"Competitors outrank you on {losses}/{measured} tracked SERP queries "
            f"({loss_rate:.0%} loss rate). Examples: {sample_str}.{wow_note}"
        ),
        "recommended_action": (
            "1) Open Detect → Rankings and filter non-brand queries where competitors win.\n"
            "2) Rewrite title/meta to beat the competitor snippet on the top 3 money queries.\n"
            "3) Strengthen on-page proof (reviews, local NAP, service FAQs) vs rival pages.\n"
            "4) Recheck SERP + Success Contract KPI in 14 days."
        ),
        "severity": "high" if loss_rate >= 0.6 else "medium",
        "impact_weight": round(min(100.0, loss_rate * 100), 1),
    }]



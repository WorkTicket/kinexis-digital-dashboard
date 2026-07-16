"""
Conversion Funnel Analyzer — organic + optional paid + CRM stages.

Traces: (paid) impressions → clicks → sessions → web conversions → leads → revenue
Organic path remains when ads/CRM data is absent.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import MetricDaily
from app.insights.rules import _expected_ctr
from app.dimensions import SITE_TOTAL_DIMENSION

logger = logging.getLogger(__name__)


def funnel_stage(
    name: str,
    entered: float,
    exited: float,
    *,
    cross_source: bool = False,
) -> dict:
    """Build a stage row. Never show >100% rates or negative dropoff.

    Click→Session mixes search/ad clicks with all-channel GA4 sessions, so
    sessions can exceed clicks — that is a source mismatch, not a 657% CVR.
    """
    entered_r = round(entered)
    exited_r = round(exited)
    if entered <= 0:
        return {
            "stage": name,
            "entered": entered_r,
            "exited": exited_r,
            "conversion_rate": 0.0,
            "dropoff": 0.0,
            "unreliable": False,
            "note": None,
        }
    raw_rate = exited / entered * 100
    if cross_source and exited > entered:
        return {
            "stage": name,
            "entered": entered_r,
            "exited": exited_r,
            "conversion_rate": None,
            "dropoff": None,
            "unreliable": True,
            "note": (
                "Sessions include all traffic channels; clicks are search/ads only. "
                "This ratio is not a true funnel conversion rate."
            ),
        }
    rate = round(min(raw_rate, 100.0), 2)
    return {
        "stage": name,
        "entered": entered_r,
        "exited": exited_r,
        "conversion_rate": rate,
        "dropoff": round(max(0.0, 100.0 - rate), 2),
        "unreliable": False,
        "note": None,
    }


def analyze_funnel(
    client_id: int,
    *,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    days: int = 30,
    db: Optional[Session] = None,
) -> dict:
    """Analyze conversion funnel for a rolling window or explicit date range."""
    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        today = date.today()
        if period_start is not None and period_end is not None:
            start_date = period_start
            end_date = period_end
        else:
            end_date = today
            start_date = today - timedelta(days=days)

        def total(source: str, metric: str, dimension_type: str | None = None) -> float:
            filters = [
                MetricDaily.client_id == client_id,
                MetricDaily.source == source,
                MetricDaily.metric_name == metric,
                MetricDaily.date >= start_date,
                MetricDaily.date <= end_date,
            ]
            if dimension_type is not None:
                filters.append(MetricDaily.dimension_type == dimension_type)
            return (
                db.query(func.sum(MetricDaily.value))
                .filter(and_(*filters))
                .scalar()
            ) or 0

        _dim_gsc = SITE_TOTAL_DIMENSION.get("gsc")
        _dim_bing = SITE_TOTAL_DIMENSION.get("bing")
        _dim_ga4 = SITE_TOTAL_DIMENSION.get("ga4")
        _dim_ads = SITE_TOTAL_DIMENSION.get("ads_csv")

        # Organic
        organic_impressions = total("gsc", "impressions", _dim_gsc) + total(
            "bing", "impressions", _dim_bing
        )
        organic_clicks = total("gsc", "clicks", _dim_gsc) + total("bing", "clicks", _dim_bing)
        sessions = total("ga4", "sessions", _dim_ga4)
        organic_sessions = total("ga4", "sessions", "organic_channel")
        conversions = total("ga4", "key_events", _dim_ga4)

        # Average Google ranking position for CTR benchmark
        gsc_position = (
            db.query(func.avg(MetricDaily.value))
            .filter(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "position",
                MetricDaily.dimension_type == _dim_gsc,
                MetricDaily.date >= start_date,
                MetricDaily.date <= end_date,
            )
            .scalar()
        ) or 0.0
        expected_ctr = _expected_ctr(float(gsc_position)) if gsc_position > 0 else 0.02

        # Paid (ads_csv + future live sources)
        paid_impressions = (
            total("ads_csv", "impressions", _dim_ads)
            + total("google_ads", "impressions", _dim_ads)
            + total("meta_ads", "impressions", _dim_ads)
        )
        paid_clicks = (
            total("ads_csv", "clicks", _dim_ads)
            + total("google_ads", "clicks", _dim_ads)
            + total("meta_ads", "clicks", _dim_ads)
        )
        ad_cost = (
            total("ads_csv", "cost", _dim_ads)
            + total("google_ads", "cost", _dim_ads)
            + total("meta_ads", "cost", _dim_ads)
        )
        paid_conversions = (
            total("ads_csv", "conversions", _dim_ads)
            + total("google_ads", "conversions", _dim_ads)
            + total("meta_ads", "conversions", _dim_ads)
        )
        paid_conversion_value = (
            total("ads_csv", "conversion_value", _dim_ads)
            + total("google_ads", "conversion_value", _dim_ads)
            + total("meta_ads", "conversion_value", _dim_ads)
        )

        # CRM
        leads = total("hubspot", "leads")
        opportunities = total("hubspot", "opportunities")
        closed_won = total("hubspot", "closed_won")
        revenue = total("hubspot", "revenue")

        has_paid = paid_impressions > 0 or paid_clicks > 0 or ad_cost > 0
        has_crm = leads > 0 or opportunities > 0 or closed_won > 0 or revenue > 0

        impressions = organic_impressions + paid_impressions
        clicks = organic_clicks + paid_clicks

        imp_to_click = (clicks / impressions * 100) if impressions > 0 else 0
        # Click→Session always blends GSC/Bing clicks (search-only) with GA4 sessions
        # (browser-level). These are fundamentally different measurement systems, so
        # the stage is always flagged cross-source when sessions exceed clicks.
        effective_sessions = organic_sessions if organic_sessions > 0 else sessions
        cross_source_sessions = (
            (organic_sessions <= 0 and sessions > 0)
            or (organic_sessions > 0 and organic_sessions > clicks * 3)
        )
        click_to_session = (effective_sessions / clicks * 100) if clicks > 0 else 0
        # Store original all-channel ratio for internal rates
        all_channel_click_to_session = (sessions / clicks * 100) if clicks > 0 else 0
        session_to_conv = (conversions / sessions * 100) if sessions > 0 else 0
        conv_to_lead = (leads / conversions * 100) if conversions > 0 and has_crm else 0
        lead_to_revenue_rate = (closed_won / leads * 100) if leads > 0 else 0
        overall = (conversions / impressions * 100) if impressions > 0 else 0

        stages = []
        if has_paid and paid_impressions > 0:
            stages.append(
                funnel_stage("Paid Impression → Click", paid_impressions, paid_clicks)
            )

        stages.extend(
            [
                funnel_stage("Impression → Click", impressions, clicks),
                funnel_stage(
                    "Click → Session",
                    clicks,
                    effective_sessions,
                    cross_source=cross_source_sessions,
                ),
                funnel_stage("Session → Conversion", sessions, conversions),
            ]
        )

        if has_crm:
            if conversions > 0:
                stages.append(
                    funnel_stage(
                        "Conversion → Lead",
                        conversions,
                        leads,
                        cross_source=True,
                    )
                )
            stages.append(
                funnel_stage(
                    "Lead → Closed won", leads, closed_won, cross_source=True
                )
            )

        # Rank by how far below expected conversion — skip unreliable cross-source rows
        _expected_cvr = {
            "Paid Impression → Click": 5.0,
            "Impression → Click": round(expected_ctr * 100, 1),
            "Click → Session": 80.0,
            "Session → Conversion": 5.0,
            "Conversion → Lead": 40.0,
            "Lead → Closed won": 15.0,
        }
        rankable = [
            s
            for s in stages
            if not s.get("unreliable") and s.get("conversion_rate") is not None
        ]
        biggest_leak = (
            max(
                rankable,
                key=lambda s: _expected_cvr.get(s["stage"], 50.0)
                - float(s["conversion_rate"]),
            )
            if rankable
            else None
        )

        leaks = []
        # Concrete evidence from opportunity tables (real pages/queries — not jargon)
        try:
            from app.opportunities import build_opportunities
            from app.page_targets import resolve_target_url

            opps = build_opportunities(db, client_id, days=min(28, days), limit=5)
        except Exception as e:
            logger.warning("Funnel opportunity enrichment failed: %s", e)
            opps = {"ctr_underperformers": [], "rising_queries": [], "landing_pages": []}

        ctr_pages = opps.get("ctr_underperformers") or []
        low_cvr = [
            r
            for r in (opps.get("landing_pages") or [])
            if float(r.get("vs_avg") or 0) < -0.5
        ]
        rising = opps.get("rising_queries") or []

        ctr_threshold = expected_ctr * 100 * 0.75  # 25% below expected at that position
        if imp_to_click < ctr_threshold and impressions > 0:
            if ctr_pages:
                top = ctr_pages[0]
                page = str(top.get("page") or "")
                ctr_pct = float(top.get("ctr") or 0) * 100
                exp_pct = float(top.get("expected_ctr") or 0) * 100
                cause = (
                    f"People see your site in Google but rarely click. Worst offender: {page} "
                    f"({ctr_pct:.1f}% CTR vs ~{exp_pct:.1f}% expected at that rank, "
                    f"{top.get('impressions')} impressions). "
                    f"Site CTR is {imp_to_click:.1f}% vs ~{ctr_threshold:.1f}% expected at pos {gsc_position:.1f}."
                )
                fix = (
                    f"On {page}:\n"
                    f"1) Rewrite the Google title (≤60 chars) with the main keyword + a clear benefit.\n"
                    f"2) Rewrite the meta description (≤155 chars) with a CTA (call / free estimate).\n"
                    f"3) Deploy, request indexing for this URL, recheck CTR in 7–14 days.\n"
                    f"4) Repeat for the next CTR-gap pages if this one improves."
                )
                title = f"Rewrite title/meta on {page.split('/')[-1] or page} to lift CTR"
            elif rising:
                q = str(rising[0].get("query") or "")
                url = resolve_target_url(db, client_id, query=q) or "the ranking page"
                cause = (
                    f"Site CTR is only {imp_to_click:.1f}% vs ~{ctr_threshold:.1f}% expected at avg position {gsc_position:.1f}. "
                    f"Rising query \"{q}\" is getting impressions but not enough clicks — "
                    f"the Google title/snippet is probably weak or off-intent."
                )
                fix = (
                    f"On {url} (for query \"{q}\"):\n"
                    f"1) Change the page title so \"{q}\" appears near the front + add a benefit.\n"
                    f"2) Rewrite meta with a CTA. 3) Deploy + request indexing. "
                    f"4) Recheck clicks on \"{q}\" in 14 days."
                )
                title = f'Improve Google snippet for "{q}"'
            else:
                cause = (
                    f"Only {imp_to_click:.1f}% of Google impressions become clicks "
                    f"({int(clicks):,} clicks from {int(impressions):,} impressions) — "
                    f"expected ~{ctr_threshold:.1f}% at avg position {gsc_position:.1f}. "
                    f"Titles and meta descriptions are not winning the click, or traffic is "
                    f"coming from queries outside the service area."
                )
                fix = (
                    "1) Open Prescribe → Fix queue and start with the highest CTR-gap insight.\n"
                    "2) On that exact URL: rewrite title (≤60) and meta (≤155) with keyword + CTA.\n"
                    "3) Confirm service area is set so out-of-area cities are not treated as wins.\n"
                    "4) Recheck site CTR in 14 days."
                )
                title = "Lift Google click-through rate (titles & metas)"
            leaks.append(
                {
                    "stage": "Impression → Click",
                    "leak_pct": round(100 - imp_to_click, 1),
                    "lost_clicks": round(impressions * 0.20 - clicks) if impressions > 0 else 0,
                    "cause": cause,
                    "fix": fix,
                    "title": title,
                    "plain_english": (
                        "Google is showing your pages, but searchers are choosing someone else. "
                        "Fix the title and description they see in search results on the worst page first."
                    ),
                }
            )
        if (
            click_to_session < 80
            and clicks > 0
            and not cross_source_sessions
            and effective_sessions <= clicks
        ):
            entry = (ctr_pages[0].get("page") if ctr_pages else None) or (
                low_cvr[0].get("page") if low_cvr else None
            )
            entry_bit = f" Start with {entry}." if entry else ""
            leaks.append(
                {
                    "stage": "Click → Session",
                    "leak_pct": round(max(0.0, 100 - click_to_session), 1),
                    "lost_sessions": round(clicks * 0.80 - effective_sessions) if clicks > 0 else 0,
                    "cause": (
                        f"People click in Google/ads but only {click_to_session:.0f}% show up as "
                        f"sessions in Analytics ({int(effective_sessions):,} sessions from {int(clicks):,} clicks). "
                        f"Usually a slow page, wrong landing URL, or broken tracking."
                    ),
                    "fix": (
                        f"1) Open the top entry URL in an incognito window — does it load fast?{entry_bit}\n"
                        f"2) Confirm GA4 is firing on that page.\n"
                        f"3) Fix LCP / load time if PageSpeed flags it.\n"
                        f"4) Make sure ads/search point at the matching landing page, not the homepage by mistake."
                    ),
                    "title": "Fix clicks that never become sessions",
                    "plain_english": (
                        "Someone clicked you, then disappeared before Analytics counted a visit. "
                        "Check the landing page loads and tracking works."
                    ),
                }
            )
        if session_to_conv < 5 and sessions > 0:
            if low_cvr:
                page = str(low_cvr[0].get("page") or "")
                cause = (
                    f"Traffic arrives but rarely converts. Worst page: {page} — "
                    f"{low_cvr[0].get('sessions')} sessions at {low_cvr[0].get('cvr')}% CVR "
                    f"({float(low_cvr[0].get('vs_avg') or 0):+.1f}pp vs site average). "
                    f"Overall session→conversion is {session_to_conv:.1f}%."
                )
                fix = (
                    f"On {page}:\n"
                    f"1) Put one primary CTA above the fold (call / form) — remove competing buttons.\n"
                    f"2) Match the headline to why they clicked (service + city).\n"
                    f"3) Add trust near the CTA (reviews, guarantee).\n"
                    f"4) Watch key_events on this URL for 14 days."
                )
                title = f"Raise conversions on {page.split('/')[-1] or page}"
            else:
                cause = (
                    f"Only {session_to_conv:.1f}% of sessions become conversions "
                    f"({int(conversions):,} from {int(sessions):,} sessions). "
                    f"CTAs, forms, or message match need work on money pages."
                )
                fix = (
                    "1) Open the highest-traffic landing page in GA4.\n"
                    "2) One primary CTA above the fold; shorten the form.\n"
                    "3) Align headline with the search/ad that sent traffic.\n"
                    "4) Remeasure key_events in 14 days."
                )
                title = "Turn more visits into leads/conversions"
            leaks.append(
                {
                    "stage": "Session → Conversion",
                    "leak_pct": round(100 - session_to_conv, 1),
                    "lost_conversions": round(sessions * 0.05 - conversions) if sessions > 0 else 0,
                    "cause": cause,
                    "fix": fix,
                    "title": title,
                    "plain_english": (
                        "Visitors land on the site but leave without calling or submitting the form. "
                        "Fix the CTA and offer on the busiest weak page."
                    ),
                }
            )
        if has_paid and ad_cost > 50 and leads == 0 and has_crm:
            lander = None
            if low_cvr:
                lander = str(low_cvr[0].get("page") or "") or None
            if not lander and ctr_pages:
                lander = str(ctr_pages[0].get("page") or "") or None
            if lander:
                cause = (
                    f"You spent ${ad_cost:,.0f} on ads this period but HubSpot shows 0 leads. "
                    f"Start on {lander} — tracking, form sync, or offer/handoff is broken."
                )
                fix = (
                    f"On {lander}:\n"
                    f"1) Submit a test form and confirm a HubSpot contact is created with UTMs.\n"
                    f"2) Confirm the primary CTA matches the ad promise above the fold.\n"
                    f"3) Pause wasteful campaigns until a lead appears from a test on this URL."
                )
                title = f"Reconnect ad spend to leads on {lander.split('/')[-1] or lander}"
            else:
                cause = (
                    f"You spent ${ad_cost:,.0f} on ads this period but HubSpot shows 0 leads. "
                    f"Tracking, form sync, or the offer/handoff is broken."
                )
                fix = (
                    "1) From each active ad, open the final landing URL and submit a test form → HubSpot.\n"
                    "2) Check UTM/campaign parameters on that exact landing URL.\n"
                    "3) Pause wasteful campaigns until a lead appears from a test."
                )
                title = "Reconnect ad spend to HubSpot leads"
            leaks.append(
                {
                    "stage": "Paid → Lead",
                    "leak_pct": 100,
                    "lost_leads": 0,
                    "cause": cause,
                    "fix": fix,
                    "title": title,
                    "plain_english": (
                        "Ads are spending money but no leads show in CRM. "
                        "Fix tracking on the live landing URL before scaling spend."
                    ),
                }
            )
        if has_crm and leads > 5 and closed_won == 0 and revenue == 0:
            leaks.append(
                {
                    "stage": "Lead → Revenue",
                    "leak_pct": 100,
                    "lost_revenue": 0,
                    "cause": (
                        f"{int(leads):,} HubSpot leads this period with 0 closed-won deals. "
                        f"Sales handoff or lead quality is the bottleneck — not more traffic."
                    ),
                    "fix": (
                        "1) Sample 10 recent leads: note each source landing URL and whether they were in-area.\n"
                        "2) Set a speed-to-lead SLA (call/email same day).\n"
                        "3) Align the website offer on those source URLs with what sales can close; "
                        "remeasure closed_won in 14 days."
                    ),
                    "title": "Turn HubSpot leads into closed deals",
                    "plain_english": (
                        "Marketing is generating leads, but none are closing. Fix sales follow-up and lead quality."
                    ),
                }
            )
        if has_crm and organic_clicks > 50 and leads == 0:
            org_page = None
            if ctr_pages:
                org_page = str(ctr_pages[0].get("page") or "") or None
            if not org_page and low_cvr:
                org_page = str(low_cvr[0].get("page") or "") or None
            if org_page:
                cause = (
                    f"{int(organic_clicks):,} organic clicks but 0 HubSpot leads. "
                    f"Forms may not sync, or {org_page} has no clear offer."
                )
                fix = (
                    f"On {org_page}:\n"
                    f"1) Test the contact form → confirm a HubSpot contact is created.\n"
                    f"2) Add a clear CTA above the fold matching search intent.\n"
                    f"3) Remeasure HubSpot leads vs GSC clicks in 14 days."
                )
                title = f"Get organic clicks to create leads on {org_page.split('/')[-1] or org_page}"
            else:
                cause = (
                    f"{int(organic_clicks):,} organic clicks but 0 HubSpot leads. "
                    f"Forms may not sync, or top pages have no clear offer."
                )
                fix = (
                    "1) GSC → Pages: open the top 3 URLs by clicks; test each form → HubSpot.\n"
                    "2) Add a clear CTA on those exact organic landing pages.\n"
                    "3) Remeasure HubSpot leads vs GSC clicks in 14 days."
                )
                title = "Get organic clicks to create HubSpot leads"
            leaks.append(
                {
                    "stage": "Organic → Lead",
                    "leak_pct": 100,
                    "lost_leads": 0,
                    "cause": cause,
                    "fix": fix,
                    "title": title,
                    "plain_english": (
                        "Google traffic is coming in, but CRM shows no leads. "
                        "Fix forms/CTAs on the top organic page first."
                    ),
                }
            )

        # Primary growth lever: prefer actionable leak with a fix, else biggest stage dropoff
        growth_lever = None
        if leaks:
            top = leaks[0]
            growth_lever = {
                "stage": top["stage"],
                "cause": top.get("cause"),
                "fix": top.get("fix"),
                "leak_pct": top.get("leak_pct"),
                "title": top.get("title") or f"Fix {top['stage']}",
                "plain_english": top.get("plain_english"),
            }
        elif biggest_leak:
            growth_lever = {
                "stage": biggest_leak["stage"],
                "cause": (
                    f"{biggest_leak['dropoff']:.0f}% of people drop off at "
                    f"{biggest_leak['stage']} "
                    f"({biggest_leak.get('exited', 0)} continue of {biggest_leak.get('entered', 0)} who enter)."
                ),
                "fix": (
                    "Open Prescribe → Fix queue and take the top insight for this stage. "
                    "Every fix must name the exact page URL and the change to ship."
                ),
                "leak_pct": biggest_leak["dropoff"],
                "title": f"Improve {biggest_leak['stage']}",
                "plain_english": (
                    f"The biggest leak in the funnel is between "
                    f"{biggest_leak['stage'].split('→')[0].strip()} and "
                    f"{biggest_leak['stage'].split('→')[-1].strip()}."
                ),
            }

        return {
            "client_id": client_id,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "totals": {
                "impressions": round(impressions),
                "organic_impressions": round(organic_impressions),
                "paid_impressions": round(paid_impressions),
                "clicks": round(clicks),
                "organic_clicks": round(organic_clicks),
                "paid_clicks": round(paid_clicks),
                "sessions": round(sessions),
                "conversions": round(conversions),
                "leads": round(leads),
                "opportunities": round(opportunities),
                "closed_won": round(closed_won),
                "revenue": round(revenue, 2),
                "ad_cost": round(ad_cost, 2),
                "paid_conversions": round(paid_conversions, 2),
                "paid_conversion_value": round(paid_conversion_value, 2),
            },
            "rates": {
                "impression_to_click_pct": round(min(imp_to_click, 100.0), 2),
                "expected_ctr_at_position_pct": round(expected_ctr * 100, 2),
                "avg_position": round(gsc_position, 1),
                "click_to_session_pct": (
                    None
                    if cross_source_sessions
                    else round(min(click_to_session, 100.0), 2)
                ),
                "session_to_conversion_pct": round(min(session_to_conv, 100.0), 2),
                "conversion_to_lead_pct": (
                    round(min(conv_to_lead, 100.0), 2) if has_crm else None
                ),
                "lead_to_closed_pct": (
                    round(min(lead_to_revenue_rate, 100.0), 2) if has_crm else None
                ),
                "overall_conversion_pct": round(overall, 4),
            },
            "stages": stages,
            "biggest_leak": biggest_leak,
            "leaks": leaks,
            "growth_lever": growth_lever,
            "has_paid": has_paid,
            "has_crm": has_crm,
        }
    finally:
        if owns_session:
            db.close()

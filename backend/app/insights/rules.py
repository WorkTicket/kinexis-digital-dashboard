"""
Insight rules run after each daily sync.
Each rule checks MetricDaily data for patterns that indicate
must-fix problems or growth opportunities the agency can act on.

Returns a list of Insight dicts ready for persistence (includes kind).

Rule implementations live in `rule_modules` (_gsc_rules, _ga4_ads_rules, _site_rules).
"""

import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.insight_thresholds import thresholds_for_client
from app.insights.rule_modules._gsc_rules import (
    _gsc_position_opportunity,
    _gsc_ctr_findings,
    _gsc_decline_alert,
    _gsc_zero_click_alert,
)
from app.insights.rule_modules._ga4_ads_rules import (
    _ga4_cro_opportunity,
    _high_bounce_low_conversion,
    _ads_spend_low_leads,
    _pause_weak_campaigns,
    _ads_search_term_waste,
    _meta_placement_waste,
    _meta_creative_fatigue,
    _serp_sov_loss,
    _leads_revenue_leak,
    _organic_leads_leak,
)
from app.insights.rule_modules._site_rules import (
    _cloudflare_error_spike,
    _pagespeed_opportunity,
    _mobile_desktop_gap,
    _bing_gsc_gap,
    _page_content_issues,
    _backlink_drop_alert,
    _gbp_underperforming,
    _crux_cwv_gap,
)
from app.insights.rule_modules._helpers import expected_ctr as _expected_ctr

logger = logging.getLogger(__name__)

__all__ = [
    "run_all_rules",
    "_expected_ctr",
    "_gsc_position_opportunity",
    "_gsc_ctr_findings",
    "_gsc_decline_alert",
    "_gsc_zero_click_alert",
    "_ga4_cro_opportunity",
    "_high_bounce_low_conversion",
    "_ads_spend_low_leads",
    "_pause_weak_campaigns",
    "_ads_search_term_waste",
    "_meta_placement_waste",
    "_meta_creative_fatigue",
    "_serp_sov_loss",
    "_leads_revenue_leak",
    "_organic_leads_leak",
    "_cloudflare_error_spike",
    "_pagespeed_opportunity",
    "_mobile_desktop_gap",
    "_bing_gsc_gap",
    "_page_content_issues",
    "_backlink_drop_alert",
    "_gbp_underperforming",
    "_crux_cwv_gap",
]


def run_all_rules(client_id: int, db: Session | None = None) -> list[dict]:
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        thr = thresholds_for_client(db, client_id)
        results = []
        rule_fns = [
            _gsc_position_opportunity,
            _gsc_ctr_findings,
            _gsc_decline_alert,
            _gsc_zero_click_alert,
            _ga4_cro_opportunity,
            _cloudflare_error_spike,
            _pagespeed_opportunity,
            _mobile_desktop_gap,
            _bing_gsc_gap,
            _high_bounce_low_conversion,
            _ads_spend_low_leads,
            _pause_weak_campaigns,
            _ads_search_term_waste,
            _meta_placement_waste,
            _meta_creative_fatigue,
            _serp_sov_loss,
            _leads_revenue_leak,
            _organic_leads_leak,
            _page_content_issues,
            _backlink_drop_alert,
            _gbp_underperforming,
            _crux_cwv_gap,
        ]
        for rule_fn in rule_fns:
            try:
                results.extend(rule_fn(client_id, db, thr))
            except Exception as e:
                logger.error("Rule %s failed for client %s: %s", rule_fn.__name__, client_id, e)
        for item in results:
            if "kind" not in item:
                item["kind"] = "opportunity"
    finally:
        if close:
            db.close()
    return results

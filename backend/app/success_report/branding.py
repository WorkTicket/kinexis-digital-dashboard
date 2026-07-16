"""Report branding, plain-language labels, and HTML escaping."""
from __future__ import annotations

import html
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Client, AppSetting

FOCUS_CYAN = "#0891B2"
FOCUS_COBALT = FOCUS_CYAN  # legacy alias
PROOF_GREEN = "#178A55"
SIGNAL_AMBER = "#B86A12"
MOMENTUM_CORAL = "#D95538"
RISK_ROSE = "#D12F4E"
INK_GRAPHITE = "#0C0E12"


def _setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value is not None else default


def resolve_report_accent(agency_accent: str, client_brand: str) -> str:
    """Agency accent → client brand_color → Kinexis Cyan."""
    for candidate in (agency_accent, client_brand):
        c = (candidate or "").strip()
        if c.startswith("#") and len(c) in (4, 7):
            return c
    return FOCUS_CYAN


def agency_branding(db: Session, client: Optional[Client] = None) -> dict:
    """Live white-label block attached to every report payload."""
    name = (_setting(db, "agency_name") or "").strip()
    accent_raw = (_setting(db, "agency_accent") or "").strip()
    logo = (_setting(db, "agency_logo_url") or "").strip()
    client_brand = (client.brand_color if client else "") or ""
    accent = resolve_report_accent(accent_raw, client_brand)
    display_name = name or "Kinexis"
    return {
        "name": display_name,
        "accent": accent,
        "logo_url": logo,
        "is_white_label": bool(name or logo or accent_raw),
    }


def attach_agency_branding(db: Session, report: dict) -> dict:
    if not isinstance(report, dict) or report.get("error"):
        return report
    client_id = (report.get("client") or {}).get("id")
    client = None
    if client_id:
        client = db.query(Client).filter(Client.id == client_id).first()
    report["agency"] = agency_branding(db, client)
    return report


PLAIN_LABELS = {
    "gsc.clicks": "People who found you on Google",
    "gsc.impressions": "Times you showed up in search",
    "gsc.ctr": "How often they chose you",
    "gsc.position": "Average Google ranking",
    "ga4.sessions": "Website visits",
    "ga4.key_events": "Important actions on your site",
    "ga4.cvr": "Conversion rate",
    "bing.clicks": "People who found you on Bing",
    "bing.impressions": "Times you showed up on Bing",
    "hubspot.leads": "New leads in CRM",
    "hubspot.opportunities": "New opportunities",
    "hubspot.closed_won": "Deals won",
    "hubspot.revenue": "Closed revenue",
    "ads_csv.cost": "Ad spend",
    "ads_csv.clicks": "Paid clicks",
    "ads_csv.impressions": "Paid impressions",
    "ads_csv.conversions": "Ad platform conversions",
    "ads_csv.conversion_value": "Ad conversion value",
    "paid.cost": "Paid media spend",
    "paid.clicks": "Paid clicks",
    "paid.impressions": "Paid impressions",
    "paid.conversions": "Paid conversions",
    "paid.conversion_value": "Paid conversion value",
    "google_ads.cost": "Google Ads spend",
    "google_ads.clicks": "Google Ads clicks",
    "google_ads.impressions": "Google Ads impressions",
    "google_ads.conversions": "Google Ads conversions",
    "google_ads.conversion_value": "Google Ads conversion value",
    "meta_ads.cost": "Meta Ads spend",
    "meta_ads.clicks": "Meta Ads clicks",
    "meta_ads.impressions": "Meta Ads impressions",
    "meta_ads.conversions": "Meta Ads conversions",
    "meta_ads.conversion_value": "Meta Ads conversion value",
}

GLOSSARY = [
    ("People who found you on Google", "Clicks from Google Search to your website."),
    ("Times you showed up in search", "How often your pages appeared in Google results."),
    ("How often they chose you", "Share of search appearances that became visits (CTR)."),
    ("Average Google ranking", "Average position in Google results (lower is better)."),
    ("Website visits", "Sessions tracked in Google Analytics."),
    ("Important actions", "Key conversions you care about (forms, calls, purchases)."),
    ("Conversion rate", "Share of visits that completed an important action."),
    ("People who found you on Bing", "Clicks from Bing Search to your website."),
    ("New leads in CRM", "Contacts created in HubSpot during the period."),
    ("New opportunities", "Sales opportunities created in HubSpot."),
    ("Deals won", "Opportunities marked closed-won in HubSpot."),
    ("Closed revenue", "Deal amount marked closed-won in HubSpot."),
    ("Ad spend", "Paid media cost from imported ads data."),
    ("Paid clicks", "Clicks on paid ads."),
    ("Ad platform conversions", "Conversions attributed by the ads platform."),
    ("Ad conversion value", "Revenue or value attributed to paid conversions."),
]


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def plain_label(key: str, fallback: Optional[str] = None) -> str:
    return PLAIN_LABELS.get(key, fallback or key.replace(".", " ").replace("_", " ").title())


def plain_metric_name(source_metric: str) -> str:
    return PLAIN_LABELS.get(source_metric, source_metric.replace(".", " · ").replace("_", " "))


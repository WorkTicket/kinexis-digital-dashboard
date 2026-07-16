"""Client Success Report — KPIs, work completed, measured wins, next actions.

Supports rolling windows and calendar-month reports with plain-language labels.
"""
from __future__ import annotations

from app.success_report.branding import (
    FOCUS_CYAN as FOCUS_COBALT,
    FOCUS_CYAN,
    GLOSSARY,
    INK_GRAPHITE,
    MOMENTUM_CORAL,
    PLAIN_LABELS,
    PROOF_GREEN,
    RISK_ROSE,
    SIGNAL_AMBER,
    agency_branding,
    attach_agency_branding,
    plain_label,
    plain_metric_name,
    resolve_report_accent,
)
from app.success_report.build import build_success_report
from app.success_report.html import render_success_report_html, report_download_filename
from app.success_report.library import (
    get_report_library,
    persist_monthly_report,
    run_monthly_reports_for_all_clients,
)
from app.success_report.metrics import (
    capture_client_baseline,
    get_client_baseline,
)
from app.success_report.narrative import (
    _narrative_has_structure,
    generate_monthly_summary,
)

__all__ = [
    "FOCUS_COBALT",
    "FOCUS_CYAN",
    "PROOF_GREEN",
    "SIGNAL_AMBER",
    "MOMENTUM_CORAL",
    "RISK_ROSE",
    "INK_GRAPHITE",
    "PLAIN_LABELS",
    "GLOSSARY",
    "resolve_report_accent",
    "agency_branding",
    "attach_agency_branding",
    "plain_label",
    "plain_metric_name",
    "capture_client_baseline",
    "get_client_baseline",
    "generate_monthly_summary",
    "_narrative_has_structure",
    "build_success_report",
    "persist_monthly_report",
    "get_report_library",
    "run_monthly_reports_for_all_clients",
    "render_success_report_html",
    "report_download_filename",
]

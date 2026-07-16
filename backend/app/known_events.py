"""
Known events that may explain metric fluctuations (core updates, seasonality, etc.).

Events are manually maintained. When a decline-alert fires inside an event's window,
the event is attached as possible_cause on the insight.
"""

from datetime import date, timedelta
from typing import Optional


# Grace period in days after a site relaunch during which trend comparisons
# are suppressed (trends are unstable while the new site settles).
GRACE_PERIOD_DAYS = 21


CORE_UPDATES: list[dict] = [
    {
        "name": "Google July 2026 Core Update",
        "start": date(2026, 7, 1),
        "end": date(2026, 7, 14),
        "type": "core_update",
        "scope": "global",
    },
    {
        "name": "Google March 2026 Core Update",
        "start": date(2026, 3, 13),
        "end": date(2026, 3, 27),
        "type": "core_update",
        "scope": "global",
    },
    {
        "name": "Google November 2025 Core Update",
        "start": date(2025, 11, 11),
        "end": date(2025, 11, 24),
        "type": "core_update",
        "scope": "global",
    },
    {
        "name": "Google August 2025 Core Update",
        "start": date(2025, 8, 15),
        "end": date(2025, 9, 3),
        "type": "core_update",
        "scope": "global",
    },
    {
        "name": "Google March 2025 Core Update",
        "start": date(2025, 3, 5),
        "end": date(2025, 4, 2),
        "type": "core_update",
        "scope": "global",
    },
    {
        "name": "Google December 2024 Core Update",
        "start": date(2024, 12, 12),
        "end": date(2024, 12, 18),
        "type": "core_update",
        "scope": "global",
    },
    {
        "name": "Google November 2024 Core Update",
        "start": date(2024, 11, 11),
        "end": date(2024, 12, 5),
        "type": "core_update",
        "scope": "global",
    },
]


def _build_seasonal_events() -> list[dict]:
    """Generate year-aware seasonal events for the current and previous year."""
    today = date.today()
    years = sorted({today.year, today.year - 1})
    events: list[dict] = []
    for yr in years:
        events.extend([
            {
                "name": f"December {yr} holiday traffic slowdown",
                "start": date(yr, 12, 15),
                "end": date(yr + 1, 1, 5),
                "type": "seasonal",
                "scope": "global",
                "note": "Many industries see reduced search volume during the holidays.",
            },
            {
                "name": f"July 4th weekend {yr} (US)",
                "start": date(yr, 7, 3),
                "end": date(yr, 7, 7),
                "type": "seasonal",
                "scope": "us",
                "note": "Short holiday week may reduce search activity.",
            },
            {
                "name": f"Black Friday / Cyber Monday {yr}",
                "start": date(yr, 11, 24),
                "end": date(yr, 12, 1),
                "type": "seasonal",
                "scope": "global",
                "note": "E-commerce traffic patterns shift dramatically during this period.",
            },
        ])
    return events


SEASONAL_WEAKNESS: list[dict] = _build_seasonal_events()

ALL_EVENTS = CORE_UPDATES + SEASONAL_WEAKNESS


def events_touching(first: date, last: date) -> list[dict]:
    """Return known events whose window overlaps [first, last]."""
    if first > last:
        first, last = last, first
    result: list[dict] = []
    for event in ALL_EVENTS:
        ev_start = event["start"]
        ev_end = event["end"]
        if ev_start <= last and ev_end >= first:
            result.append({
                "name": event["name"],
                "start": ev_start,
                "end": ev_end,
                "type": event.get("type"),
                "scope": event.get("scope"),
                "note": event.get("note", ""),
            })
    return result


def possible_cause_text(events: list[dict]) -> str:
    """Human-readable sentence to attach to a decline insight."""
    if not events:
        return ""
    names = [e["name"] for e in events[:3]]
    if len(events) == 1:
        return f"Possible cause: {names[0]} overlaps this period."
    joined = ", ".join(names[:-1]) + " and " + names[-1]
    return f"Possible causes: {joined} overlap this period."


# ── Unified discontinuity concept ──────────────────────────────────────────
# Discontinuities are events that invalidate WoW trend comparisons:
# site relaunches, Google core updates, and major seasonal shifts.
# When any discontinuity is active, WoW penalties are suppressed and
# data caveats are added to reports.

from datetime import datetime


def active_discontinuities(
    db,
    client_id: int,
    as_of: date | None = None,
) -> list[dict]:
    """Unify site relaunches (per-client), core updates, and seasonal events
    (global) into one list of currently-active discontinuities for this client.
    'Active' = within GRACE_PERIOD_DAYS of as_of (relaunch) or window overlaps
    as_of (core update / seasonal).
    """
    as_of = as_of or date.today()
    result: list[dict] = []

    # Per-client: relaunches from ClientMilestone
    from app.models import ClientMilestone

    relaunches = (
        db.query(ClientMilestone)
        .filter(
            ClientMilestone.client_id == client_id,
            ClientMilestone.milestone_type == "site_relaunch",
        )
        .all()
    )
    for m in relaunches:
        days_since = (as_of - m.occurred_at).days
        if 0 <= days_since <= GRACE_PERIOD_DAYS:
            result.append({
                "name": f"Site relaunched {days_since}d ago",
                "type": "site_relaunch",
                "scope": "client",
                "occurred_at": m.occurred_at,
                "days_since": days_since,
                "suppresses_trend_comparisons": True,
                "note": m.notes or "",
            })

    # Global: core updates + seasonal, reusing events_touching()
    window_start = as_of - timedelta(days=GRACE_PERIOD_DAYS)
    for ev in events_touching(window_start, as_of):
        evt_type = ev.get("type", "")
        if evt_type == "core_update":
            result.append({
                "name": ev["name"],
                "type": "core_update",
                "scope": ev.get("scope"),
                "occurred_at": None,
                "days_since": None,
                "suppresses_trend_comparisons": True,
                "note": ev.get("note", f"{ev['name']} overlaps this analysis period — "
                                "ranking changes may be update-related, not site issues."),
            })
        elif evt_type == "seasonal":
            result.append({
                "name": ev["name"],
                "type": "seasonal",
                "scope": ev.get("scope"),
                "occurred_at": None,
                "days_since": None,
                "suppresses_trend_comparisons": False,
                "note": ev.get("note", f"{ev['name']} overlaps this period — "
                                "seasonal patterns may affect traffic comparisons."),
            })

    return result


def has_active_discontinuity(discontinuities: list[dict]) -> bool:
    """Check if any active discontinuity suppresses trend comparisons."""
    return any(d.get("suppresses_trend_comparisons") for d in discontinuities)


def discontinuity_caveat(discontinuities: list[dict]) -> str:
    """Human-readable sentence for report/UI display. Keeps relaunch language
    distinct from generic events rather than collapsing everything into one
    phrase."""
    if not discontinuities:
        return ""
    relaunches = [d for d in discontinuities if d["type"] == "site_relaunch"]
    others = [d for d in discontinuities if d["type"] != "site_relaunch"]

    parts = []
    if relaunches:
        d = relaunches[0]
        parts.append(f"the site relaunched {d['days_since']} days ago")
    if others:
        names = [o["name"] for o in others[:2]]
        parts.append(f"{' and '.join(names)} overlaps this period")

    if len(parts) == 1:
        return f"Trends may be skewed: {parts[0]}."
    return f"Trends may be skewed: {' and '.join(parts)}."

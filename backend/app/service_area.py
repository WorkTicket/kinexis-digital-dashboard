"""
Service-area / geo constraints for local clients.

Keeps AI plans and query opportunities inside the client's real markets
(e.g. Cedar Falls IA — not Cedar Lake).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from app.models import Client

# Words that often follow a city stem but are not a different city name.
_PLACE_FOLLOW_STOP = frozenset(
    {
        "ia",
        "iowa",
        "il",
        "illinois",
        "mn",
        "minnesota",
        "wi",
        "wisconsin",
        "ne",
        "nebraska",
        "mo",
        "missouri",
        "county",
        "area",
        "metro",
        "region",
        "near",
        "and",
        "or",
        "the",
        "of",
        "for",
        "in",
        "to",
        "a",
        "an",
        "landscaping",
        "lawn",
        "care",
        "service",
        "services",
        "company",
        "companies",
        "near",
        "best",
        "top",
        "local",
        "cheap",
        "affordable",
    }
)


@dataclass
class ServiceArea:
    primary_location: str = ""
    service_areas: list[str] = field(default_factory=list)
    exclude_areas: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def configured(self) -> bool:
        return bool(
            self.primary_location.strip()
            or self.service_areas
            or self.exclude_areas
        )


def _split_list(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        parts = re.split(r"[,;\n]+", raw)
        return [p.strip() for p in parts if p.strip()]
    return []


def _normalize_place(text: str) -> str:
    t = (text or "").strip().lower()
    t = t.replace(",", " ")
    t = re.sub(r"[^\w\s\-']", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _place_variants(text: str) -> list[str]:
    """
    Expand 'Cedar Falls, Iowa' → ['cedar falls iowa', 'cedar falls', 'iowa']
    Prefer longer phrases first for matching.
    """
    full = _normalize_place(text)
    if not full:
        return []
    variants = [full]
    parts = full.split()
    # City without trailing state (drop last token if it looks like a state)
    if len(parts) >= 3:
        city = " ".join(parts[:-1])
        if city and city not in variants:
            variants.append(city)
    elif len(parts) == 2:
        # Keep full two-word city as primary; also keep as-is
        pass
    # Explicit city-only from original comma split
    raw = (text or "").strip()
    if "," in raw:
        city_only = _normalize_place(raw.split(",", 1)[0])
        if city_only and city_only not in variants:
            variants.append(city_only)
        rest = _normalize_place(raw.split(",", 1)[1])
        rest = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", rest).strip()
        if rest and len(rest) > 2 and rest not in variants:
            variants.append(rest)
    variants.sort(key=len, reverse=True)
    return variants


def parse_service_area(client: Client | dict | None) -> ServiceArea:
    """Read service-area fields from client profile_json or a raw profile dict."""
    profile: dict = {}
    if client is None:
        return ServiceArea()
    if isinstance(client, dict):
        profile = client
    else:
        try:
            profile = json.loads(client.profile_json or "{}")
        except (json.JSONDecodeError, TypeError):
            profile = {}
    if not isinstance(profile, dict):
        return ServiceArea()

    # Nested object preferred; flat keys also accepted
    nested = profile.get("service_area")
    if isinstance(nested, dict):
        primary = str(nested.get("primary_location") or nested.get("primary") or "")
        areas = _split_list(nested.get("service_areas") or nested.get("areas") or [])
        exclude = _split_list(nested.get("exclude_areas") or nested.get("exclude") or [])
        notes = str(nested.get("notes") or "")
    else:
        primary = str(profile.get("primary_location") or profile.get("location") or "")
        areas = _split_list(profile.get("service_areas") or profile.get("markets") or [])
        exclude = _split_list(profile.get("exclude_areas") or profile.get("out_of_area") or [])
        notes = str(profile.get("service_area_notes") or "")

    return ServiceArea(
        primary_location=primary.strip(),
        service_areas=areas,
        exclude_areas=exclude,
        notes=notes.strip(),
    )


def allowed_place_phrases(sa: ServiceArea) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for raw in [sa.primary_location, *sa.service_areas]:
        for v in _place_variants(raw):
            # Skip ultra-short / state-only alone as exclusive "in area" proof
            if len(v) < 4:
                continue
            if v not in seen:
                seen.add(v)
                phrases.append(v)
    phrases.sort(key=len, reverse=True)
    return phrases


def exclude_place_phrases(sa: ServiceArea) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for raw in sa.exclude_areas:
        for v in _place_variants(raw):
            if len(v) < 3:
                continue
            if v not in seen:
                seen.add(v)
                phrases.append(v)
    phrases.sort(key=len, reverse=True)
    return phrases


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    # Word-boundary-ish match so "falls" alone isn't enough; phrases can have spaces
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _conflicting_sibling_place(query: str, allowed: list[str]) -> Optional[str]:
    """
    Detect near-miss place names: allowed 'cedar falls' vs query 'cedar lake'.
    Returns the conflicting snippet if found.
    """
    q = _normalize_place(query)
    tokens = q.split()
    for place in allowed:
        parts = place.split()
        if len(parts) < 2:
            continue
        stem, expected = parts[0], parts[1]
        for i, tok in enumerate(tokens):
            if tok != stem:
                continue
            if i + 1 >= len(tokens):
                continue
            nxt = tokens[i + 1]
            if nxt == expected:
                continue
            if nxt in _PLACE_FOLLOW_STOP:
                continue
            # Same stem, different second word → different place
            return f"{stem} {nxt}"
    return None


def classify_query_geo(query: str, sa: ServiceArea) -> str:
    """
    Return one of: 'in_area' | 'out_of_area' | 'excluded' | 'unknown'

    - excluded: matches an explicit exclude list
    - out_of_area: conflicting sibling place (Cedar Lake vs Cedar Falls) or
      clear place mention that isn't in the allow list when allow list is set
    - in_area: matches an allowed place phrase
    - unknown: no geo signal (still OK to optimize non-local queries)
    """
    if not sa.configured or not (query or "").strip():
        return "unknown"

    q = _normalize_place(query)
    for excl in exclude_place_phrases(sa):
        if _contains_phrase(q, excl):
            return "excluded"

    allowed = allowed_place_phrases(sa)
    conflict = _conflicting_sibling_place(q, allowed) if allowed else None
    if conflict:
        return "out_of_area"

    if allowed and any(_contains_phrase(q, p) for p in allowed):
        return "in_area"

    return "unknown"


def is_growth_eligible_query(query: str, sa: ServiceArea) -> bool:
    """False when we must not prescribe growth work for this query."""
    status = classify_query_geo(query, sa)
    return status not in ("excluded", "out_of_area")


def format_service_area_for_prompt(client: Client | dict | None) -> list[str]:
    """Hard geo constraints for AI system/user context."""
    sa = parse_service_area(client)
    if not sa.configured:
        return []

    lines = ["=== SERVICE AREA (HARD CONSTRAINT — OBEY STRICTLY) ==="]
    if sa.primary_location:
        lines.append(f"  primary_location: {sa.primary_location}")
    if sa.service_areas:
        lines.append(f"  serve_only: {', '.join(sa.service_areas)}")
    if sa.exclude_areas:
        lines.append(f"  never_target: {', '.join(sa.exclude_areas)}")
    if sa.notes:
        lines.append(f"  notes: {sa.notes}")
    lines.append(
        "  RULES: Only prescribe local SEO, content, landing pages, ads, or keyword work "
        "for primary_location / serve_only markets. Never expand into never_target places "
        "or lookalike city names (e.g. Cedar Lake ≠ Cedar Falls). Similar names are "
        "different markets — do not confuse them. Queries marked OUT OF SERVICE AREA "
        "are GSC ranking bleed (Google serving the site in the wrong city), not growth "
        "opportunities. Do not build pages or rewrite titles to win those cities."
    )
    lines.append("")
    return lines


def annotate_query_line(query: str, sa: ServiceArea, base_line: str) -> Optional[str]:
    """
    Return None to drop the line from opportunity lists, or a (possibly annotated) line.
    Top-query lists keep out-of-area rows but mark them so the model does not optimize them.
    """
    status = classify_query_geo(query, sa)
    if status in ("excluded", "out_of_area"):
        return f"  [OUT OF SERVICE AREA — do not prescribe] {base_line.lstrip()}"
    if status == "in_area":
        return f"  [IN SERVICE AREA] {base_line.lstrip()}"
    return base_line

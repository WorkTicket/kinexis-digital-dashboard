"""Parse competitor domains from client profile_json for SERP/SoV tagging."""

from __future__ import annotations

import json
import re
from typing import Optional

from app.models import Client


_DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)",
    re.I,
)


def parse_competitor_domains(client: Optional[Client]) -> list[str]:
    if not client:
        return []
    try:
        profile = json.loads(client.profile_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(profile, dict):
        return []
    raw = profile.get("competitors") or ""
    if isinstance(raw, list):
        blob = " ".join(str(x) for x in raw)
    else:
        blob = str(raw)
    found: list[str] = []
    seen: set[str] = set()
    for m in _DOMAIN_RE.finditer(blob):
        host = m.group(1).lower().removeprefix("www.")
        if host and host not in seen:
            seen.add(host)
            found.append(host)
    return found[:20]


def parse_client_domains(client: Optional[Client]) -> list[str]:
    """Best-effort client site host from name or profile notes (optional)."""
    if not client:
        return []
    domains: list[str] = []
    try:
        profile = json.loads(client.profile_json or "{}")
    except (json.JSONDecodeError, TypeError):
        profile = {}
    if isinstance(profile, dict):
        for key in ("website", "site_url", "domain", "primary_domain"):
            val = str(profile.get(key) or "").strip()
            if val:
                for m in _DOMAIN_RE.finditer(val):
                    host = m.group(1).lower().removeprefix("www.")
                    if host and host not in domains:
                        domains.append(host)
    name = (client.name or "").strip().lower()
    if "." in name and " " not in name:
        host = name.removeprefix("www.")
        if host not in domains:
            domains.append(host)
    return domains[:5]

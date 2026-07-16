"""
Query intent classifier — deterministic, no LLM required.

When a ServiceArea is available (from client profile), it uses service_area's
geo classifier to detect local location references. When no profile is set,
it falls back to a generic US-state + pattern-based detector so the system
works for any client out of the box.

Intents:
    local_commercial  → CTR title/meta fix (highest lead value)
    informational     → on-page answer + CTA (lower lead value)
    navigational      → skip / low priority
    other             → skip / low priority
"""

from __future__ import annotations

import re
from typing import Optional

from app.service_area import ServiceArea, classify_query_geo

_SERVICE_TERMS: set[str] = {
    "landscaping", "landscaper", "landscape", "patio", "patios", "paver", "pavers",
    "retaining", "wall", "walls", "fence", "fencing", "deck", "decks", "siding",
    "roofing", "roof", "concrete", "asphalt", "driveway", "masonry", "brick",
    "stone", "stucco", "drywall", "plumbing", "electrical", "hvac", "heating",
    "cooling", "installation", "repair", "replacement", "contractor", "contractors",
    "company", "companies", "services", "service", "builder", "builders", "construction",
    "plumber", "electrician", "electricians", "roofer", "carpenter",
    "remodeling", "remodel", "renovation", "painting", "painter", "painters", "flooring",
    "carpet", "tile", "window", "windows", "door", "doors", "garage", "gutter",
    "gutters", "lawn", "lawncare", "lawn care", "sod", "mulch", "rock", "gravel",
    "drainage", "excavation", "grading", "seeding", "sprinkler", "irrigation",
    "tree", "trees", "shrub", "shrubs", "plant", "plants", "planting", "plantings",
    "garden", "landscape design", "outdoor", "yard", "care", "design", "install",
    "setup", "maintenance", "cleanup", "clean", "removal", "trimming", "cutting",
    "mowing", "snow", "ice", "paving", "sealcoating", "pest", "control",
}

_ALL_US_STATES: set[str] = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee",
    "texas", "utah", "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming",
}

_INFO_SIGNALS: set[str] = {
    "how to", "how do", "how can", "how much", "what is", "what are", "what does",
    "guide", "tips", "ideas", "cost", "price", "pricing", "estimate",
    "calculator", "vs", "versus", "types of", "best", "top", "review",
    "reviews", "pros and cons", "diy", "tutorial", "example", "examples",
    "benefits", "worth it", "should i", "why", "when to", "can you",
}

_NAV_SIGNALS: set[str] = {
    "login", "sign in", "sign up", "register", "portal", "dashboard",
    "contact", "phone", "address", "hours", "location", "directions",
}

_STOP = frozenset({
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "at",
    "near", "best", "top", "how", "what", "with", "from", "your", "our",
    "is", "are", "it", "its", "my", "his", "her", "their", "this", "that",
})

# Location prepositions — the next word is likely a city/place name
_LOCATION_PREPOSITIONS: set[str] = {"in", "near", "at", "for"}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in _STOP}


def _has_generic_location(q: str) -> bool:
    """
    Generic location detection when no client profile exists.
    Detects: US state names/abbreviations, 'near me', 'in {city}' pattern.
    """
    q_lower = q.lower().strip()
    # "near me" is universal
    if "near me" in q_lower:
        return True

    # Check words directly (catches 2-letter state codes like "fl", "tx")
    words = q_lower.split()
    for w in words:
        stripped = w.strip(".,;:!?")
        if stripped in _ALL_US_STATES:
            return True

    # Multi-word state names: "new york", "north carolina", "rhode island", "west virginia"
    multi_word_states = {
        "new hampshire", "new jersey", "new mexico", "new york",
        "north carolina", "north dakota", "rhode island",
        "south carolina", "south dakota", "west virginia",
    }
    for phrase in multi_word_states:
        if phrase in q_lower:
            return True

    tokens = _tokens(q_lower)

    # State full names (3+ chars) in tokens
    if tokens & _ALL_US_STATES:
        return True

    # "in {word}" pattern — the word after 'in' is likely a city
    words = q_lower.split()
    for i, w in enumerate(words):
        if w == "in" and i + 1 < len(words):
            next_word = words[i + 1]
            # Skip stop words
            if next_word not in _STOP and len(next_word) > 2:
                return True

    return False


def classify_query_intent(query: str, sa: Optional[ServiceArea] = None) -> str:
    """
    Classify a search query into: local_commercial, informational, navigational, other.

    When `sa` (ServiceArea from client profile) is provided, location detection uses
    `classify_query_geo` for accurate in-area/out-of-area routing. Otherwise falls back
    to a generic US-location detector that works for any client.
    """
    q = query.lower().strip()
    if not q or len(q) < 3:
        return "other"

    has_service = any(t in q for t in _SERVICE_TERMS)
    has_info = any(t in q for t in _INFO_SIGNALS)
    has_nav = any(t in q for t in _NAV_SIGNALS)

    if sa and sa.configured:
        geo = classify_query_geo(q, sa)
        # Hard gate: only explicit in_area counts as local — unknown ≠ in-area.
        has_location = geo == "in_area"
    else:
        has_location = _has_generic_location(q)

    # Navigational (contact, login, etc.) — lowest value
    if has_nav and not has_service:
        return "navigational"

    # Local commercial: service + location → CTR title/meta
    if has_service and has_location:
        return "local_commercial"

    # Service + informational without location → informational
    if has_service and has_info:
        return "informational"

    # Pure informational without service term
    if has_info and not has_service:
        return "informational"

    # Service-only, no location, no info → local commercial (broad intent)
    # When a service area is configured, only explicit in_area qualifies —
    # unknown must not become local_commercial.
    if has_service:
        if sa and sa.configured:
            return "other"
        return "local_commercial"

    return "other"


def lead_intent_weight(intent: str) -> float:
    weights = {
        "local_commercial": 1.0,
        "informational": 0.4,
        "navigational": 0.1,
        "other": 0.2,
    }
    return weights.get(intent, 0.2)

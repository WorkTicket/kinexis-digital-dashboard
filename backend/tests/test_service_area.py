"""Service-area geo matching — keep local SEO inside real markets."""

from app.models import Client
from app.service_area import (
    classify_query_geo,
    format_service_area_for_prompt,
    is_growth_eligible_query,
    parse_service_area,
)


def _client(**profile) -> Client:
    import json

    return Client(name="Landscaper", profile_json=json.dumps(profile))


def test_cedar_falls_vs_cedar_lake():
    c = _client(
        primary_location="Cedar Falls, Iowa",
        service_areas="Cedar Falls, Waterloo",
        exclude_areas="Cedar Lake",
    )
    sa = parse_service_area(c)
    assert classify_query_geo("landscaping cedar falls ia", sa) == "in_area"
    assert classify_query_geo("lawn care cedar lake iowa", sa) == "excluded"
    assert classify_query_geo("cedar lake landscaping near me", sa) == "excluded"
    # Sibling place without explicit exclude still flagged via stem conflict
    c2 = _client(primary_location="Cedar Falls, Iowa", service_areas="Cedar Falls")
    sa2 = parse_service_area(c2)
    assert classify_query_geo("landscaping cedar lake", sa2) == "out_of_area"
    assert not is_growth_eligible_query("landscaping cedar lake", sa2)
    assert is_growth_eligible_query("landscaping cedar falls", sa2)


def test_non_geo_queries_still_eligible():
    c = _client(primary_location="Cedar Falls, Iowa", service_areas="Cedar Falls, Waterloo")
    sa = parse_service_area(c)
    assert classify_query_geo("how to aerate lawn", sa) == "unknown"
    assert is_growth_eligible_query("how to aerate lawn", sa)


def test_unknown_is_not_in_area_or_local_commercial():
    """Hard gate: unknown location ≠ in_area / local_commercial eligible."""
    from app.query_intent import classify_query_intent

    c = _client(primary_location="Cedar Falls, Iowa", service_areas="Cedar Falls, Waterloo")
    sa = parse_service_area(c)
    assert classify_query_geo("landscaping near me", sa) != "in_area"
    assert classify_query_geo("landscaping near me", sa) == "unknown"
    # Service term + unknown geo must NOT become local_commercial
    assert classify_query_intent("landscaping services", sa) != "local_commercial"
    # Explicit in-area still qualifies
    assert classify_query_intent("landscaping cedar falls", sa) == "local_commercial"


def test_prompt_includes_hard_constraint():
    c = _client(
        primary_location="Cedar Falls, Iowa",
        service_areas="Cedar Falls, Waterloo, Evansdale",
        exclude_areas="Cedar Lake",
    )
    lines = "\n".join(format_service_area_for_prompt(c))
    assert "SERVICE AREA" in lines
    assert "Cedar Falls" in lines
    assert "Cedar Lake" in lines
    assert "HARD CONSTRAINT" in lines


def test_nested_service_area_object():
    c = _client(
        service_area={
            "primary_location": "Cedar Falls, IA",
            "service_areas": ["Cedar Falls", "Waterloo"],
            "exclude_areas": ["Cedar Lake"],
        }
    )
    sa = parse_service_area(c)
    assert sa.primary_location.startswith("Cedar Falls")
    assert "Waterloo" in sa.service_areas
    assert classify_query_geo("mowing cedar lake", sa) == "excluded"

"""Page target resolution for concrete fixes."""

from app.page_targets import (
    build_concrete_recommended_action,
    propose_serp_copy,
    _score_page_for_query,
)


def test_score_prefers_matching_service_page():
    q = "landscaping cedar falls"
    score_good = _score_page_for_query(
        q,
        "https://example.com/landscaping-cedar-falls",
        "Landscaping in Cedar Falls | Acme",
        "Cedar Falls Landscaping",
        "Local landscaping",
    )
    score_bad = _score_page_for_query(
        q,
        "https://example.com/about",
        "About Us",
        "Our Story",
        "Company history",
    )
    assert score_good > score_bad
    assert score_good >= 0.35


def test_concrete_ctr_action_has_from_to():
    action = build_concrete_recommended_action(
        kind="ctr_gap",
        query="lawn care cedar falls",
        url="https://acme.com/lawn-care",
        state={"title": "Services", "meta": "We do stuff", "h1": "Services"},
        proposed={
            "title": "Lawn Care Cedar Falls | Acme",
            "meta": "Lawn care cedar falls with clear pricing. Request a free estimate from Acme today.",
        },
    )
    assert "https://acme.com/lawn-care" in action
    assert 'FROM "Services"' in action
    assert "Lawn Care Cedar Falls | Acme" in action


def test_propose_serp_copy_lengths():
    p = propose_serp_copy("landscaping cedar falls iowa", "GreenCo", {})
    assert len(p["title"]) <= 60
    assert len(p["meta"]) <= 155
    assert "GreenCo" in p["title"]

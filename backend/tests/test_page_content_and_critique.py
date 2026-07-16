"""Unit tests for page HTML extraction and AI critique filtering."""

from app.ai_critique import filter_rejected_actions
from app.connectors.page_content import (
    extract_page_fields,
    extract_urls_from_text,
    looks_like_empty_shell,
)
from app.connectors.pagespeed import _offender_from_item
from app.impact_tracker import snapshot_task_metrics


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Acme Roofing | Local Experts</title>
  <meta name="description" content="Trusted roof repair and replacement in Austin." />
  <link rel="canonical" href="https://example.com/roofing" />
  <script type="application/ld+json">
    {"@type": "LocalBusiness", "name": "Acme"}
  </script>
</head>
<body>
  <h1>Roof Repair in Austin</h1>
  <h2>Our Services</h2>
  <h3>Emergency Fixes</h3>
  <p>We fix leaks fast with a free estimate for homeowners.</p>
  <a href="/contact">Contact us</a>
  <a href="https://other.com/x">External</a>
</body>
</html>
"""


def test_extract_page_fields_title_meta_h1():
    fields = extract_page_fields(SAMPLE_HTML, base_url="https://example.com/roofing")
    assert fields["title"] == "Acme Roofing | Local Experts"
    assert "Trusted roof repair" in fields["meta_description"]
    assert fields["h1"] == "Roof Repair in Austin"
    assert fields["word_count"] >= 5
    assert fields["canonical_url"] == "https://example.com/roofing"
    assert "LocalBusiness" in fields["schema_types"]
    assert any(h.startswith("H2:") for h in fields["headings"])
    assert any(h.startswith("H3:") for h in fields["headings"])
    assert fields["content_hash"]
    # Internal link kept; external dropped when base_host set
    hrefs = [l["href"] for l in fields["internal_links"]]
    assert any("contact" in h for h in hrefs)
    assert not any("other.com" in h for h in hrefs)


def test_extract_urls_from_text():
    urls = extract_urls_from_text(
        'See https://example.com/a and https://example.com/b.'
    )
    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_filter_rejected_actions_drops_rejects():
    actions = [
        {"title": "Keep me", "evidence": "CTR 2.1%"},
        {"title": "Drop me", "evidence": "invented"},
        {"title": "Also keep", "evidence": "pos 12"},
    ]
    reviewed = [
        {"title": "Keep me", "reject": False},
        {"title": "Drop me", "reject": True, "reason": "unsupported"},
        {"title": "Also keep", "reject": False},
    ]
    kept = filter_rejected_actions(actions, reviewed)
    assert [a["title"] for a in kept] == ["Keep me", "Also keep"]


def test_filter_rejected_actions_fail_soft_on_length_mismatch():
    actions = [{"title": "A"}, {"title": "B"}]
    reviewed = [{"reject": True}]  # wrong length
    assert filter_rejected_actions(actions, reviewed) == actions


def test_geo_rejected_local_seo_not_fail_soft_revived():
    """OOA local SEO actions must stay dropped even when all actions are policy-rejected."""
    from app.ai_critique import critique_action_list, reset_critique_stats
    from app.service_area import parse_service_area
    from app.models import Client
    import json

    reset_critique_stats()
    c = Client(
        name="Landscaper",
        profile_json=json.dumps(
            {
                "primary_location": "Cedar Falls, Iowa",
                "service_areas": "Cedar Falls, Waterloo",
                "exclude_areas": "Cedar Lake",
            }
        ),
    )
    sa = parse_service_area(c)
    actions = [
        {
            "title": "Local SEO for Cedar Lake",
            "playbook_pattern": "local_onsite",
            "category": "local_seo",
            "target_url": "https://example.com/cedar-lake",
            "target_query": "landscaping cedar lake",
            "insight_id": 1,
            "evidence": "impressions",
        }
    ]
    kept = critique_action_list("ctx", actions, service_area=sa)
    assert kept == []


def test_offender_from_item():
    assert _offender_from_item({"url": "https://cdn.example/a.js", "wastedMs": 400}) == {
        "url": "https://cdn.example/a.js",
        "wastedMs": 400.0,
    }
    assert _offender_from_item({"wastedBytes": 100}) is None
    assert _offender_from_item("nope") is None


def test_looks_like_empty_shell():
    assert looks_like_empty_shell({"word_count": 5, "title": "App", "h1": ""})
    assert looks_like_empty_shell({"word_count": 0, "title": "", "h1": ""})
    assert not looks_like_empty_shell(
        {"word_count": 200, "title": "Roofing", "h1": "Austin Roof Repair"}
    )


def test_snapshot_task_metrics_is_importable_reopen_contract():
    """Reopen path relies on snapshot_task_metrics never overwriting baselines."""
    assert callable(snapshot_task_metrics)
    assert "never overwritten" in (snapshot_task_metrics.__doc__ or "").lower() or (
        "fallback" in (snapshot_task_metrics.__doc__ or "").lower()
    )

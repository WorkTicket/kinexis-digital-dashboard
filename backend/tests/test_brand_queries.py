"""Brand query classification tests — no DB required."""

from app.brand_queries import is_brand_query, brand_terms_for_client, filter_query_scope


class TestIsBrandQuery:
    def test_multi_word_brand_substring_match(self):
        """Multi-word terms: raw substring match is safe (no false positives)."""
        terms = ["chase bank", "my company"]
        assert is_brand_query("chase bank login", terms) is True
        assert is_brand_query("my company phone", terms) is True
        assert is_brand_query("chase bank near me", terms) is True

    def test_single_token_short_word_boundary(self):
        """Short single-token terms (<5 chars): word boundary prevents substring FP."""
        terms = ["abc", "xyz"]
        # Should match: term is a standalone word
        assert is_brand_query("abc roofing services", terms) is True
        assert is_brand_query("contact xyz today", terms) is True
        # Should NOT match: term is embedded inside another word
        assert is_brand_query("dabco services", terms) is False  # "abc" inside "dabco"
        assert is_brand_query("wxyz llc", terms) is False  # "xyz" inside "wxyz"
        assert is_brand_query("abcd solutions", terms) is False  # "abc" inside "abcd"

    def test_single_token_long_word_boundary(self):
        """Long single-token terms (>=5 chars): word boundary prevents substring FP.

        This is the fix for Bug #2 from the audit — previously terms >=5 chars
        got raw substring matching, causing false positives like 'Chase' matching
        'steeplechase'.
        """
        terms = ["chase", "presto", "salon123"]
        # Should match: term is a standalone word
        assert is_brand_query("chase bank login", terms) is True
        assert is_brand_query("presto services llc", terms) is True
        assert is_brand_query("salon123 reviews", terms) is True
        # Should NOT match: term is embedded inside another word
        assert is_brand_query("steeplechase results", terms) is False
        assert is_brand_query("paper chaser guide", terms) is False
        assert is_brand_query("prestolite battery", terms) is False
        assert is_brand_query("preston highway exit", terms) is False
        assert is_brand_query("super salontoday", terms) is False

    def test_brand_term_at_start_or_end(self):
        """Word boundary should work at sentence edges and with punctuation."""
        terms = ["chase"]
        assert is_brand_query("chase", terms) is True
        assert is_brand_query("chase!", terms) is True
        assert is_brand_query("chase.", terms) is True
        assert is_brand_query("welcome to chase", terms) is True
        assert is_brand_query("chase, bank", terms) is True

    def test_case_insensitive(self):
        terms = ["Chase", "PRESTO"]
        assert is_brand_query("CHASE bank", terms) is True
        assert is_brand_query("chase login", terms) is True
        assert is_brand_query("presto services", terms) is True
        assert is_brand_query("PRESTO LLC", terms) is True

    def test_empty_inputs(self):
        assert is_brand_query("", ["chase"]) is False
        assert is_brand_query("chase bank", []) is False
        assert is_brand_query("", []) is False

    def test_no_false_positive_on_common_words(self):
        """Agencies often work with clients whose names contain common words.
        Verify that a brand term 'concrete' doesn't match 'concrete' in
        'concrete driveway cost' ONLY as part of a phrase."""
        terms = ["concrete", "stone", "deck"]
        assert is_brand_query("concrete driveway cost", terms) is True
        assert is_brand_query("stone work near me", terms) is True
        assert is_brand_query("deck repair service", terms) is True
        # Should NOT match: embedded inside longer words
        assert is_brand_query("concreteresults lab", terms) is False
        assert is_brand_query("milestone results", terms) is False
        assert is_brand_query("deckers outdoor", terms) is False


class TestFilterQueryScope:
    def test_all_scope_passes_everything(self):
        assert filter_query_scope("steeplechase results", ["chase"], "all") is True
        assert filter_query_scope("chase bank", ["chase"], "all") is True
        assert filter_query_scope("random query", ["chase"], "all") is True
        assert filter_query_scope("random query", [], "all") is True

    def test_brand_scope_only_passes_branded(self):
        terms = ["chase"]
        assert filter_query_scope("chase bank login", terms, "brand") is True
        assert filter_query_scope("steeplechase results", terms, "brand") is False
        assert filter_query_scope("lawn care service", terms, "brand") is False

    def test_non_brand_scope_only_passes_non_branded(self):
        terms = ["chase"]
        assert filter_query_scope("chase bank login", terms, "non_brand") is False
        assert filter_query_scope("steeplechase results", terms, "non_brand") is True
        assert filter_query_scope("lawn care service", terms, "non_brand") is True

    def test_scope_no_terms_passes_all(self):
        """When no brand terms exist, filter should pass everything (unknown brand)."""
        assert filter_query_scope("any query", [], "brand") is True
        assert filter_query_scope("any query", [], "non_brand") is True
        assert filter_query_scope("any query", [], "all") is True

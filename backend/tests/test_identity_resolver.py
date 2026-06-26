"""
Tests for identity_resolver — deterministic same-name disambiguation.

These cover the pure ``classify_profiles`` function and its helpers, which label
each collected social profile as primary / candidate / divergent relative to an
anchor identity, so the AI never merges different namesakes into one description.
"""

from app.services.identity_resolver import (
    _handle_from_url,
    _tokens,
    anchor_corroborated_by_web,
    classify_profiles,
    filter_intelligence_sources,
    web_relevance_ratio,
)


def _matches(classification: dict) -> dict[str, list[str]]:
    """Helper: collapse classification into {platform: [match labels]}."""
    return {platform: [item["match"] for item in items] for platform, items in classification["profiles"].items()}


class TestHelpers:
    def test_handle_from_url_strips_path_and_at(self):
        assert _handle_from_url("https://instagram.com/@yigtwx/") == "yigtwx"

    def test_handle_from_url_ignores_linkedin_in_keyword(self):
        # 'in' is a routing segment, not a handle.
        assert _handle_from_url("https://www.linkedin.com/in") == ""

    def test_handle_from_url_normalizes_diacritics(self):
        assert _handle_from_url("https://twitter.com/Yiğit") == "yigit"

    def test_tokens_drops_single_chars(self):
        assert _tokens("Yigit E Erdogan") == {"yigit", "erdogan"}


class TestNoConfidentAnchor:
    """Without a stable handle, nothing is split — legacy behaviour preserved."""

    def test_no_github_and_unique_handles_all_primary(self):
        social = {
            "linkedin": [{"url": "https://linkedin.com/in/john-smith-5", "bio": "doctor"}],
            "instagram": [{"url": "https://instagram.com/random_guy", "bio": "traveler"}],
        }
        result = classify_profiles(social, github_data=None, real_name="John Smith")
        assert result["has_others"] is False, "no anchor should mean no split"
        labels = _matches(result)
        assert labels["linkedin"] == ["primary"]
        assert labels["instagram"] == ["primary"]


class TestGithubAnchor:
    """GitHub login is the strongest anchor handle."""

    def test_matching_handle_is_primary(self):
        github = {"login": "yigtwx", "name": "Yigit Erdogan", "location": "Istanbul"}
        social = {
            "instagram": [{"url": "https://instagram.com/yigtwx", "bio": "developer"}],
        }
        result = classify_profiles(social, github_data=github, real_name="Yigit Erdogan")
        assert _matches(result)["instagram"] == ["primary"]

    def test_different_handle_no_support_is_divergent(self):
        github = {"login": "yigtwx", "name": "Yigit Erdogan", "location": "Istanbul"}
        social = {
            # Completely unrelated handle/bio → likely a different person.
            "twitter": [{"url": "https://twitter.com/cooldoctor99", "bio": "surgeon in Berlin"}],
        }
        result = classify_profiles(social, github_data=github, real_name="Yigit Erdogan")
        assert _matches(result)["twitter"] == ["divergent"]
        assert result["has_others"] is True

    def test_different_handle_with_name_support_is_candidate(self):
        github = {"login": "yigtwx", "name": "Yigit Erdogan", "location": "Istanbul"}
        social = {
            # Different handle, but the name appears → keep cautious, not divergent.
            "linkedin": [{"url": "https://linkedin.com/in/yigit-erdogan-9", "bio": "analyst"}],
        }
        result = classify_profiles(social, github_data=github, real_name="Yigit Erdogan")
        assert _matches(result)["linkedin"] == ["candidate"]

    def test_mixed_people_separated(self):
        """The core bug scenario: real account + namesake must not both be primary."""
        github = {"login": "yigtwx", "name": "Yigit Erdogan", "location": "Istanbul"}
        social = {
            "instagram": [{"url": "https://instagram.com/yigtwx", "bio": "software dev, Istanbul"}],
            "twitter": [{"url": "https://twitter.com/yigtwx", "bio": "coding"}],
            "linkedin": [{"url": "https://linkedin.com/in/another-yigit-md", "bio": "physician, Ankara"}],
        }
        result = classify_profiles(social, github_data=github, real_name="Yigit Erdogan")
        labels = _matches(result)
        assert labels["instagram"] == ["primary"], "anchor handle account is the target"
        assert labels["twitter"] == ["primary"]
        assert "primary" not in labels["linkedin"], "the physician namesake must not be primary"
        assert result["has_others"] is True


class TestDominantHandleAnchor:
    """Without GitHub, a handle recurring across platforms becomes the anchor."""

    def test_cross_platform_handle_anchors_identity(self):
        social = {
            "instagram": [{"url": "https://instagram.com/yigtwx", "bio": "dev"}],
            "twitter": [{"url": "https://twitter.com/yigtwx", "bio": "dev"}],
            "linkedin": [{"url": "https://linkedin.com/in/someone-else-1", "bio": "lawyer"}],
        }
        result = classify_profiles(social, github_data=None, real_name="Yigit Erdogan")
        labels = _matches(result)
        assert labels["instagram"] == ["primary"]
        assert labels["twitter"] == ["primary"]
        assert result["has_others"] is True, "the unrelated lawyer should be flagged"


class TestFilterIntelligenceSources:
    """Deterministic removal of different-name web/deep sources before the briefing."""

    def test_drops_namesake_source_and_its_deep_node(self):
        raw = [
            {"title": "Yigit Erdogan GitHub", "snippet": "developer yigit erdogan", "url": "https://u/keep"},
            {"title": "Yigit Bulut economy advisor", "snippet": "yigit bulut economist", "url": "https://u/drop"},
        ]
        deep = "--- NODE: https://u/keep ---\nreal content\n\n--- NODE: https://u/drop ---\nbulut bio\n\n"
        web, deep_out, dropped = filter_intelligence_sources("Yigit Erdogan", "orig web", deep, raw)
        assert dropped == 1, f"the namesake source should be dropped, got {dropped}"
        assert "u/keep" in web and "u/drop" not in web, "web text should keep only the matching source"
        assert "real content" in deep_out, "matching deep node must remain"
        assert "bulut bio" not in deep_out, "off-target deep node must be removed"

    def test_all_match_returns_unchanged(self):
        raw = [{"title": "Yigit Erdogan dev", "snippet": "yigit erdogan", "url": "https://u/1"}]
        deep = "--- NODE: https://u/1 ---\ncontent\n\n"
        web, deep_out, dropped = filter_intelligence_sources("Yigit Erdogan", "orig", deep, raw)
        assert dropped == 0
        assert web == "orig" and deep_out == deep, "nothing dropped → inputs returned unchanged"

    def test_no_sources_is_noop(self):
        assert filter_intelligence_sources("Yigit Erdogan", "w", "d", None) == ("w", "d", 0)

    def test_web_never_blanked_when_all_dropped(self):
        raw = [{"title": "Someone Else", "snippet": "unrelated", "url": "https://u/x"}]
        web, _deep, dropped = filter_intelligence_sources("Yigit Erdogan", "orig web", "", raw)
        assert dropped == 1
        assert web == "orig web", "must fall back to original web text rather than blank it out"


class TestAnchorCorroboration:
    """The adversarial case: a same-name namesake shares the name tokens, so only a
    distinctive GitHub login/profile can prove the web is about the real subject."""

    def test_none_without_github(self):
        assert anchor_corroborated_by_web(None, [{"title": "x"}], "") is None

    def test_false_when_login_absent(self):
        github = {"login": "yigtwxx", "name": "Yigit Erdogan", "profile_url": "https://github.com/Yigtwxx"}
        # Namesake content contains 'yigit' AND 'erdogan' but NOT the distinctive login.
        raw = [{"title": "Yigit Bulut advisor to President Erdogan", "snippet": "economist", "url": "u"}]
        assert anchor_corroborated_by_web(github, raw, "Yigit Bulut economic advisor to Erdogan") is False

    def test_true_when_login_present(self):
        github = {"login": "yigtwxx", "name": "Yigit Erdogan", "profile_url": "https://github.com/Yigtwxx"}
        raw = [{"title": "Yigit Erdogan portfolio", "snippet": "see github.com/yigtwxx", "url": "u"}]
        assert anchor_corroborated_by_web(github, raw, "") is True

    def test_true_when_profile_url_present(self):
        github = {"login": "yigtwxx", "name": "Yigit Erdogan", "profile_url": "https://github.com/yigtwxx"}
        raw = [{"title": "dev", "snippet": "blog", "url": "https://github.com/yigtwxx"}]
        assert anchor_corroborated_by_web(github, raw, "") is True


class TestWebRelevanceRatio:
    def test_high_when_sources_match(self):
        raw = [
            {"title": "Yigit Erdogan dev", "snippet": "yigit erdogan", "url": "u1"},
            {"title": "Yigit Erdogan talk", "snippet": "yigit erdogan", "url": "u2"},
        ]
        assert web_relevance_ratio("Yigit Erdogan", raw) == 1.0

    def test_low_when_namesake_dominates(self):
        raw = [
            {"title": "Yigit Bulut economist", "snippet": "yigit bulut", "url": "u1"},
            {"title": "Random news", "snippet": "unrelated", "url": "u2"},
        ]
        ratio = web_relevance_ratio("Yigit Erdogan", raw)
        assert ratio is not None and ratio < 0.34, f"expected low ratio, got {ratio}"

    def test_none_without_sources(self):
        assert web_relevance_ratio("Yigit Erdogan", []) is None


class TestMentionPlatforms:
    def test_mention_platforms_always_primary(self):
        github = {"login": "yigtwx", "name": "Yigit Erdogan", "location": "Istanbul"}
        social = {
            "discord": [{"url": "", "bio": "yigit#1234 mentioned"}],
        }
        result = classify_profiles(social, github_data=github, real_name="Yigit Erdogan")
        assert _matches(result)["discord"] == ["primary"]

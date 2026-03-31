"""
Tests for the SecurityAgent cross-validation logic.

This tests the pure-algorithmic cross_validate() static method
which detects inconsistencies between data sources.
"""

from app.agents.security_agent import SecurityAgent, _normalize_text


class TestNormalizeText:
    """Test Unicode normalization helper."""

    def test_basic_lowercase(self):
        assert _normalize_text("Hello World") == "hello world"

    def test_diacritics_removed(self):
        # Turkish characters
        assert _normalize_text("İstanbul") == "istanbul"
        assert _normalize_text("Çağdaş") == "cagdas"

    def test_empty_string(self):
        assert _normalize_text("") == ""


class TestCrossValidation:
    """Test SecurityAgent.cross_validate() — the algorithm that finds data inconsistencies."""

    def test_no_issues_when_data_consistent(self):
        """Consistent data should produce no issues."""
        issues = SecurityAgent.cross_validate(
            github_data={"login": "johndoe", "name": "John Doe", "location": "Istanbul", "bio": "developer"},
            social_profiles={"twitter": [{"url": "https://x.com/johndoe"}]},
            web_results="John Doe is a developer based in Istanbul",
            real_name="John Doe",
            username="johndoe",
        )
        assert len(issues) == 0

    def test_github_login_mismatch(self):
        """GitHub login different from searched username should flag issues."""
        issues = SecurityAgent.cross_validate(
            github_data={"login": "totallyDifferent", "name": "John Doe"},
            social_profiles={},
            web_results="",
            real_name="John Doe",
            username="johndoe",
        )
        assert any("doesn't match" in issue for issue in issues)

    def test_github_location_not_in_web(self):
        """GitHub location keywords missing from web results should flag."""
        issues = SecurityAgent.cross_validate(
            github_data={"login": "johndoe", "name": "John Doe", "location": "Berlin, Germany"},
            social_profiles={},
            web_results="John Doe is a developer based in Tokyo, Japan.",
            real_name="John Doe",
            username="johndoe",
        )
        assert any("location" in issue.lower() for issue in issues)

    def test_github_name_mismatch(self):
        """GitHub name with no overlapping words should flag identity mismatch."""
        issues = SecurityAgent.cross_validate(
            github_data={"login": "coder42", "name": "Alice Smith"},
            social_profiles={},
            web_results="",
            real_name="Bob Johnson",
            username="coder42",
        )
        assert any("identity mismatch" in issue.lower() or "doesn't share" in issue.lower() for issue in issues)

    def test_no_social_but_web_presence(self):
        """No social profiles but significant web results should be flagged."""
        issues = SecurityAgent.cross_validate(
            github_data=None,
            social_profiles={"twitter": [], "instagram": []},
            web_results="A" * 600,  # Significant web presence
            real_name="Test Person",
        )
        assert any("No social media profiles" in issue for issue in issues)

    def test_profession_conflict(self):
        """GitHub bio as developer but web says 'doctor' should flag."""
        issues = SecurityAgent.cross_validate(
            github_data={"login": "medic", "name": "Dr. Smith", "bio": "Full-stack developer and coding enthusiast"},
            social_profiles={"twitter": [{"url": "https://x.com/drsmith"}]},
            web_results="Dr. Smith is a renowned physician at the hospital",
            real_name="Dr. Smith",
            username="medic",
        )
        assert any("developer" in issue.lower() or "physician" in issue.lower() for issue in issues)

    def test_github_only_no_corroboration(self):
        """Only GitHub data with no other sources should flag limited reliability."""
        issues = SecurityAgent.cross_validate(
            github_data={"login": "loner", "name": "Alone User"},
            social_profiles={"twitter": [], "instagram": []},
            web_results="",
            real_name="Alone User",
            username="loner",
        )
        assert any("reliability is limited" in issue.lower() for issue in issues)

    def test_empty_data(self):
        """Completely empty data should not crash."""
        issues = SecurityAgent.cross_validate(
            github_data=None,
            social_profiles={},
            web_results="",
            real_name="",
        )
        assert isinstance(issues, list)

    def test_github_login_substring_ok(self):
        """GitHub login that is a substring of username shouldn't flag (e.g., 'john' in 'johndoe')."""
        issues = SecurityAgent.cross_validate(
            github_data={"login": "john", "name": "John Doe"},
            social_profiles={"twitter": [{"url": "https://x.com/john"}]},
            web_results="John is a developer",
            real_name="John Doe",
            username="johndoe",
        )
        mismatch_issues = [i for i in issues if "doesn't match" in i.lower() and "login" in i.lower()]
        assert len(mismatch_issues) == 0

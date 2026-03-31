"""
Tests for the SearchOrchestrationService.

Covers the pure-utility helpers and the parse_query method
that were extracted from the monolithic search_person route.
"""

from datetime import UTC, datetime, timedelta

from app.services.search_orchestration_service import (
    SearchOrchestrationService,
    _format_last_activity,
    _join_bios,
    _join_urls,
    _parse_snippet_date,
)


class TestParseQuery:
    """Test query parsing (splitting 'Real Name / username')."""

    def test_simple_name(self):
        name, username = SearchOrchestrationService.parse_query("John Doe")
        assert name == "John Doe"
        assert username == "John Doe"

    def test_name_with_username(self):
        name, username = SearchOrchestrationService.parse_query("John Doe / johndoe")
        assert name == "John Doe"
        assert username == "johndoe"

    def test_whitespace_handling(self):
        name, username = SearchOrchestrationService.parse_query("  Ali Veli  /  aliveli  ")
        assert name == "Ali Veli"
        assert username == "aliveli"

    def test_only_slash(self):
        name, username = SearchOrchestrationService.parse_query("/")
        assert name == ""
        assert username == ""

    def test_multiple_slashes(self):
        name, username = SearchOrchestrationService.parse_query("Name / user / extra")
        assert name == "Name"
        assert username == "user"


class TestParseSnippetDate:
    """Test date extraction from search result snippets."""

    def test_hours_ago(self):
        dt = _parse_snippet_date("Posted 3 hours ago")
        assert dt is not None
        assert (datetime.now(UTC) - dt).total_seconds() < 4 * 3600

    def test_days_ago(self):
        dt = _parse_snippet_date("Updated 5 days ago")
        assert dt is not None
        assert (datetime.now(UTC) - dt).days <= 6

    def test_yesterday(self):
        dt = _parse_snippet_date("Last seen yesterday")
        assert dt is not None
        assert (datetime.now(UTC) - dt).days <= 2

    def test_explicit_date(self):
        dt = _parse_snippet_date("Published on Jan 15, 2025")
        assert dt is not None
        assert dt.month == 1
        assert dt.year == 2025

    def test_iso_date(self):
        dt = _parse_snippet_date("Date: 2025-06-15")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 6
        assert dt.day == 15

    def test_no_date(self):
        assert _parse_snippet_date("No date here") is None

    def test_empty_string(self):
        assert _parse_snippet_date("") is None

    def test_none_input(self):
        assert _parse_snippet_date(None) is None


class TestFormatLastActivity:
    """Test the last activity summary formatter."""

    def test_active_today(self):
        result = _format_last_activity(
            github_data={"last_active": datetime.now(UTC).isoformat()},
        )
        assert result == "Active today"

    def test_active_days_ago(self):
        three_days_ago = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        result = _format_last_activity(
            github_data={"last_active": three_days_ago},
        )
        assert "3d ago" in result

    def test_no_data(self):
        result = _format_last_activity(github_data=None)
        assert result is None

    def test_invalid_last_active(self):
        result = _format_last_activity(github_data={"last_active": "not-a-date"})
        assert result is None


class TestJoinUrls:
    """Test URL joining helper."""

    def test_single_profile(self):
        profiles = {"twitter": [{"url": "https://x.com/test", "bio": "bio"}]}
        assert _join_urls(profiles, "twitter") == "https://x.com/test"

    def test_multiple_profiles(self):
        profiles = {"twitter": [
            {"url": "https://x.com/test1", "bio": ""},
            {"url": "https://x.com/test2", "bio": ""},
        ]}
        result = _join_urls(profiles, "twitter")
        assert "test1" in result
        assert "test2" in result

    def test_empty_profiles(self):
        assert _join_urls({"twitter": []}, "twitter") is None

    def test_missing_platform(self):
        assert _join_urls({}, "twitter") is None


class TestJoinBios:
    """Test bio joining helper."""

    def test_single_bio(self):
        profiles = {"twitter": [{"url": "https://x.com/test", "bio": "Hello world"}]}
        assert _join_bios(profiles, "twitter") == "Hello world"

    def test_empty_bio(self):
        profiles = {"twitter": [{"url": "https://x.com/test", "bio": ""}]}
        # Empty bios produce an empty join which returns None
        assert _join_bios(profiles, "twitter") is None

    def test_missing_platform(self):
        assert _join_bios({}, "tinder") is None

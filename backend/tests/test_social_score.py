"""
Unit tests for SocialScoreService (Digital Impact Score Algorithm).
"""
import sys
import os

# Add the backend app directory to the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.social_score_service import SocialScoreService


service = SocialScoreService()


def test_no_data():
    """Score should be 0 when no data is available at all."""
    result = service.calculate_score(
        github_data=None,
        social_profiles={"instagram": [], "twitter": [], "linkedin": [], "spotify": [], "tiktok": [], "snapchat": [], "tumblr": [], "tinder": [], "bumble": []},
        raw_sources=[],
        web_results="",
    )
    assert result["total_score"] == 0
    assert all(v == 0.0 for v in result["breakdown"].values())
    print(f"  [PASS] No data → score = {result['total_score']}")


def test_github_only():
    """A user with only a GitHub profile should get a modest score."""
    result = service.calculate_score(
        github_data={
            "followers": 50,
            "public_repos": 10,
            "last_active": "2026-03-01T12:00:00Z",
            "bio": "Full-stack developer",
            "blog": "https://example.com",
        },
        social_profiles={"instagram": [], "twitter": [], "linkedin": [], "spotify": [], "tiktok": [], "snapchat": [], "tumblr": [], "tinder": [], "bumble": []},
        raw_sources=[],
        web_results="",
    )
    assert 10 <= result["total_score"] <= 50, f"Expected 10-50, got {result['total_score']}"
    assert result["breakdown"]["platform_presence"] > 0
    assert result["breakdown"]["follower_impact"] > 0
    assert result["breakdown"]["activity_intensity"] > 0
    assert result["breakdown"]["digital_diversity"] > 0
    print(f"  [PASS] GitHub only → score = {result['total_score']}, breakdown: {result['breakdown']}")


def test_full_profile():
    """A user with GitHub + all social media + search results should score very high."""
    result = service.calculate_score(
        github_data={
            "followers": 5000,
            "public_repos": 80,
            "last_active": "2026-03-05T10:00:00Z",
            "bio": "Senior engineer @bigcorp",
            "blog": "https://myblog.dev",
        },
        social_profiles={
            "instagram": [{"url": "https://instagram.com/user", "bio": "Tech enthusiast | 10K followers"}],
            "twitter": [{"url": "https://x.com/user", "bio": "Software engineer"}],
            "linkedin": [{"url": "https://linkedin.com/in/user", "bio": "CTO at Startup"}],
            "spotify": [{"url": "https://open.spotify.com/user/user", "bio": ""}],
            "tiktok": [{"url": "https://tiktok.com/@user", "bio": "Coding tutorials"}],
            "snapchat": [{"url": "https://snapchat.com/add/user", "bio": ""}],
            "tumblr": [{"url": "https://user.tumblr.com", "bio": "My blog"}],
            "tinder": [{"url": "https://example.com", "bio": "[Mention] tinder profile found"}],
            "bumble": [{"url": "https://example.com", "bio": "[Mention] bumble profile found"}],
        },
        raw_sources=[{"title": f"Result {i}", "url": f"https://example.com/{i}", "snippet": "..."} for i in range(20)],
        web_results="A" * 5000,
    )
    assert result["total_score"] >= 75, f"Expected >= 75, got {result['total_score']}"
    assert result["breakdown"]["platform_presence"] == 1.0
    print(f"  [PASS] Full profile → score = {result['total_score']}, breakdown: {result['breakdown']}")


def test_web_only():
    """A person with only web search results but no profiles."""
    result = service.calculate_score(
        github_data=None,
        social_profiles={"instagram": [], "twitter": [], "linkedin": [], "spotify": [], "tiktok": [], "snapchat": [], "tumblr": [], "tinder": [], "bumble": []},
        raw_sources=[{"title": f"News {i}", "url": f"https://news.com/{i}", "snippet": "..."} for i in range(10)],
        web_results="B" * 3000,
    )
    assert 5 <= result["total_score"] <= 30, f"Expected 5-30, got {result['total_score']}"
    assert result["breakdown"]["web_visibility"] > 0
    print(f"  [PASS] Web only → score = {result['total_score']}, breakdown: {result['breakdown']}")


def test_score_always_0_to_100():
    """Score should always be within 0-100 range."""
    # Extreme high values
    result = service.calculate_score(
        github_data={"followers": 1_000_000, "public_repos": 500, "last_active": "2026-03-05T10:00:00Z", "bio": "x", "blog": "x"},
        social_profiles={
            "instagram": [{"url": "u", "bio": "Very long bio content here abc"}],
            "twitter": [{"url": "u", "bio": "bio"}],
            "linkedin": [{"url": "u", "bio": "bio"}],
            "spotify": [{"url": "u", "bio": "bio"}],
            "tiktok": [{"url": "u", "bio": "bio"}],
            "snapchat": [{"url": "u", "bio": "bio"}],
            "tumblr": [{"url": "u", "bio": "bio"}],
            "tinder": [{"url": "u", "bio": "mention"}],
            "bumble": [{"url": "u", "bio": "mention"}],
        },
        raw_sources=[{"title": "t", "url": "u", "snippet": "s"} for _ in range(50)],
        web_results="X" * 20000,
    )
    assert 0 <= result["total_score"] <= 100, f"Score out of range: {result['total_score']}"
    print(f"  [PASS] Extreme values → score = {result['total_score']} (still in 0-100)")


def test_explanation_generated():
    """Explanation string should be non-empty and meaningful."""
    result = service.calculate_score(
        github_data={"followers": 100, "public_repos": 5, "last_active": "2026-02-01T00:00:00Z"},
        social_profiles={"instagram": [{"url": "u", "bio": ""}], "twitter": [], "linkedin": [], "spotify": [], "tiktok": []},
        raw_sources=[],
        web_results="",
    )
    assert isinstance(result["explanation"], str)
    assert len(result["explanation"]) > 20
    print(f"  [PASS] Explanation: '{result['explanation'][:80]}...'")


if __name__ == "__main__":
    print("\n🧪 Running Digital Impact Score tests...\n")
    test_no_data()
    test_github_only()
    test_full_profile()
    test_web_only()
    test_score_always_0_to_100()
    test_explanation_generated()
    print("\n✅ All tests passed!\n")

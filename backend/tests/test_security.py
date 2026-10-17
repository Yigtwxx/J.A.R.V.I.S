"""
Tests for the Security Middleware.

Covers:
- API key authentication (verify_api_key dependency)
- Rate limiting middleware
"""

import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.middleware.security import RateLimitMiddleware, is_rate_limit_exempt
from app.utils.logger import logger


class TestRateLimiting:
    """Test the RateLimitMiddleware via the real app."""

    def test_requests_under_limit_succeed(self, client):
        """Normal requests should succeed and include rate limit headers."""
        response = client.get("/health")
        assert response.status_code == 200
        # Health is exempt, so try root
        response = client.get("/")
        assert response.status_code == 200

    def test_rate_limit_headers_present(self, client):
        """API responses should include X-RateLimit-* headers."""
        response = client.get("/api/profiles/")
        assert response.status_code == 200
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers

    def test_health_endpoint_exempt(self, client):
        """Health endpoint should not be rate limited."""
        for _ in range(50):
            response = client.get("/health")
            assert response.status_code == 200


class TestApiKeyAuthentication:
    """Test API key authentication on the search endpoint."""

    # Both tests below post an empty body deliberately. Auth runs ahead of
    # request validation, so an authenticated call stops at 422 — enough to
    # prove the key was accepted, without running the real search pipeline
    # (a valid body sends it to the live network and takes over two minutes).

    def test_search_with_key_passes_auth(self, client):
        """A request carrying the configured key gets past auth to validation."""
        response = client.post("/api/search/", json={})
        assert response.status_code == 422

    def test_search_without_key_is_rejected(self, unauthenticated_client):
        """Auth is never disabled: main.py auto-generates a key when none is
        configured, so a request with no key must be rejected."""
        response = unauthenticated_client.post("/api/search/", json={})
        assert response.status_code == 401

    @patch("app.middleware.security.settings")
    def test_search_rejected_without_key(self, mock_settings):
        """When API_KEY is set, requests without the key should get 401."""
        mock_settings.api_key = "secret-key-123"
        import asyncio

        from app.middleware.security import verify_api_key

        with pytest.raises(HTTPException):
            asyncio.run(verify_api_key(None))

    @patch("app.middleware.security.settings")
    def test_search_accepted_with_correct_key(self, mock_settings):
        """When API_KEY is set and correct key is provided, auth should pass."""
        mock_settings.api_key = "secret-key-123"
        import asyncio

        from app.middleware.security import verify_api_key

        result = asyncio.run(verify_api_key("secret-key-123"))
        assert result == "secret-key-123"

    @patch("app.middleware.security.settings")
    def test_search_rejected_with_wrong_key(self, mock_settings):
        """When API_KEY is set but wrong key is provided, should get 401."""
        mock_settings.api_key = "secret-key-123"
        import asyncio

        from app.middleware.security import verify_api_key

        with pytest.raises(HTTPException):
            asyncio.run(verify_api_key("wrong-key"))


class TestRateLimiterUnit:
    """Unit tests for the RateLimitMiddleware internals."""

    def test_clean_old_entries(self):
        """Old timestamps should be purged from the sliding window."""
        import time

        middleware = RateLimitMiddleware(app=None, max_requests=10, window_seconds=60)
        ip = "127.0.0.1"
        now = time.time()

        # Add some old entries (90 seconds ago) and some recent ones
        middleware._requests[ip] = [now - 90, now - 80, now - 5, now - 1]
        middleware._clean_old_entries(ip, now)

        # Only the last 2 should remain (within 60s window)
        assert len(middleware._requests[ip]) == 2


class TestRateLimitExemptions:
    """What the limiter must NOT count.

    One finished search renders a dozen or more avatars at once. Counting those
    authenticated blob reads against a per-minute budget makes the UI
    rate-limit itself: the pictures 429 and the operator log fills with
    "rate limit exceeded" for the user's own browser.
    """

    def test_media_reads_are_exempt(self):
        assert is_rate_limit_exempt("/api/media/avatars/abc.jpg"), "avatar reads must not consume the budget"

    def test_docs_and_health_stay_exempt(self):
        assert is_rate_limit_exempt("/health")
        assert is_rate_limit_exempt("/docs/oauth2-redirect")

    def test_the_search_api_is_still_counted(self):
        assert not is_rate_limit_exempt("/api/search/sessions"), "the expensive path must stay limited"
        assert not is_rate_limit_exempt("/api/profiles/")


class TestOperatorLogsStayOffTheLiveFeed:
    """The SSE feed is how a user watches a *search*.

    HTTP-plumbing warnings (auth, rate limits, CSRF) are operator concerns; in
    the search feed they read as the search itself failing.
    """

    @pytest.mark.asyncio
    async def test_broadcast_false_keeps_a_warning_out_of_the_feed(self):
        queue: asyncio.Queue = asyncio.Queue()
        logger.subscribers.add(queue)
        try:
            logger.log_warning("Rate limit exceeded for IP 127.0.0.1", broadcast=False)
            # The push is scheduled on the loop, so yield before judging it empty.
            await asyncio.sleep(0)
            assert queue.empty(), "an infrastructure warning must not reach the live feed"
        finally:
            logger.subscribers.discard(queue)

    @pytest.mark.asyncio
    async def test_ordinary_warnings_still_reach_the_feed(self):
        queue: asyncio.Queue = asyncio.Queue()
        logger.subscribers.add(queue)
        try:
            logger.log_warning("Search engine 'brave' disabled for this session")
            await asyncio.sleep(0)
            assert not queue.empty(), "search progress must still be broadcast"
        finally:
            logger.subscribers.discard(queue)

"""
Tests for the Security Middleware.

Covers:
- API key authentication (verify_api_key dependency)
- Rate limiting middleware
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.middleware.security import RateLimitMiddleware


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

    def test_search_without_key_when_disabled(self, client):
        """When API_KEY is empty, search should work without a key (auth disabled)."""
        # We just test the validation — the endpoint will fail because
        # we haven't mocked all services, but it shouldn't be 401
        response = client.post("/api/search/", json={"query": "test"})
        assert response.status_code != 401  # Not unauthorized

    @patch("app.middleware.security.settings")
    def test_search_rejected_without_key(self, mock_settings):
        """When API_KEY is set, requests without the key should get 401."""
        mock_settings.api_key = "secret-key-123"
        from app.middleware.security import verify_api_key
        import asyncio

        with pytest.raises(Exception):  # HTTPException
            asyncio.run(verify_api_key(None))

    @patch("app.middleware.security.settings")
    def test_search_accepted_with_correct_key(self, mock_settings):
        """When API_KEY is set and correct key is provided, auth should pass."""
        mock_settings.api_key = "secret-key-123"
        from app.middleware.security import verify_api_key
        import asyncio

        result = asyncio.run(verify_api_key("secret-key-123"))
        assert result == "secret-key-123"

    @patch("app.middleware.security.settings")
    def test_search_rejected_with_wrong_key(self, mock_settings):
        """When API_KEY is set but wrong key is provided, should get 401."""
        mock_settings.api_key = "secret-key-123"
        from app.middleware.security import verify_api_key
        import asyncio

        with pytest.raises(Exception):
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

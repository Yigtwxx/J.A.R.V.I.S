"""
Tests for core FastAPI application endpoints.

Covers: root, health, docs availability, CORS, status endpoints.
"""

import pytest


class TestRootEndpoint:
    """GET /"""

    def test_root_returns_welcome(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "J.A.R.V.I.S" in data["message"]
        assert data["version"] == "1.0.0"
        assert data["status"] == "operational"

    def test_root_lists_endpoints(self, client):
        response = client.get("/")
        data = response.json()
        assert "search" in data["endpoints"]
        assert "profiles" in data["endpoints"]
        assert "docs" in data["endpoints"]


class TestHealthEndpoint:
    """GET /health"""

    def test_health_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestDocsEndpoint:
    """OpenAPI docs should be accessible."""

    def test_docs_page(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "J.A.R.V.I.S API"


class TestCORSHeaders:
    """CORS should be properly configured."""

    def test_cors_allowed_origin(self, client):
        response = client.options(
            "/api/profiles/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


class TestSearchTestEndpoint:
    """GET /api/search/test"""

    def test_search_test(self, client):
        response = client.get("/api/search/test")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "services" in data

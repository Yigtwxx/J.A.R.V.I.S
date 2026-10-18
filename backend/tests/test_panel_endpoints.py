"""
Tests for the endpoints behind the console's feature tabs.

Each case here pins a shape or a status the panels crashed on, so a regression
shows up as a failing test rather than a blank console with a TypeError in it.
"""

import os

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.plugins import plugin_manager

# conftest pins this before app.config caches Settings; read it back rather than
# repeating the literal, so the two can never drift apart.
TEST_API_KEY = os.environ["API_KEY"]


class TestMemorySearch:
    """POST /api/memory/search"""

    def test_search_returns_a_list_not_a_string(self, client):
        """The panel groups results with ``.reduce`` — a string there took the whole UI down.

        The route used to serve ``semantic_recall``'s prompt string straight to
        the client, so any non-empty result crashed the Memory tab.
        """
        client.post(
            "/api/memory/",
            json={"category": "preference", "key": "editor", "value": "vim", "importance": 7},
        )

        response = client.post("/api/memory/search", json={"query": "vim", "n_results": 5})

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["results"], list), f"results must be a list, got {type(body['results']).__name__}"
        assert body["count"] == len(body["results"])

    def test_search_hit_carries_whole_records(self, client):
        """Each hit must look like a memory row, not a rendered line of text."""
        client.post(
            "/api/memory/",
            json={"category": "preference", "key": "editor", "value": "vim", "importance": 7},
        )

        results = client.post("/api/memory/search", json={"query": "vim"}).json()["results"]

        assert len(results) == 1
        hit = results[0]
        assert set(hit) >= {"id", "category", "key", "value", "importance", "created_at", "updated_at"}
        assert hit["key"] == "editor"
        assert hit["value"] == "vim"

    def test_search_without_matches_is_an_empty_list(self, client):
        """An empty result is still a list — the panel must not special-case it."""
        response = client.post("/api/memory/search", json={"query": "nothing-matches-this"})

        assert response.status_code == 200
        assert response.json()["results"] == []
        assert response.json()["count"] == 0


class TestWatchStatus:
    """GET /api/watch/{query}"""

    def test_unknown_watch_is_404(self, client):
        """A 200 here handed the client a body with none of the keys its schema needs."""
        response = client.get("/api/watch/nobody-is-watching-this")

        assert response.status_code == 404
        assert "nobody-is-watching-this" in response.json()["detail"]


class TestPluginInfo:
    """GET /api/plugins/"""

    def test_every_plugin_reports_an_author(self, client):
        """The frontend renders ``by {author}``; without the field it printed "by undefined"."""
        response = client.get("/api/plugins/")

        assert response.status_code == 200
        plugins = response.json()["plugins"]
        assert plugins, "expected at least one bundled plugin"
        for plugin in plugins:
            assert plugin.get("author"), f"plugin {plugin['name']} reports no author"

    def test_plugin_manager_info_includes_author(self):
        """Guard the contract at its source, not only through the route."""
        for info in plugin_manager.list_plugins():
            assert "author" in info


class TestErrorsKeepCorsHeaders:
    """A failure the browser can read is worth more than one it reports as 'network error'."""

    def test_unhandled_error_returns_500_with_cors_headers(self):
        """CORS used to be the innermost middleware, so 500s left without its headers.

        Chrome then blocked the response and axios reported ERR_NETWORK, which
        the UI phrased as "backend unreachable" — hiding a real server fault.
        """

        def _explode():
            raise RuntimeError("simulated backend fault")

        app.dependency_overrides[get_db] = _explode
        try:
            # raise_server_exceptions=False so the response is inspected the way
            # a browser would see it instead of being re-raised into the test.
            with TestClient(app, raise_server_exceptions=False) as raw:
                response = raw.get(
                    "/api/memory/",
                    headers={"X-API-Key": TEST_API_KEY, "Origin": "http://localhost:3000"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 500
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000", (
            "a 500 without CORS headers reaches the browser as a network error, "
            "which hides the real failure from the user"
        )
        assert response.json()["type"] == "server_error"

    def test_successful_response_still_carries_cors_headers(self, client):
        """Reordering the stack must not cost the headers the happy path already had."""
        response = client.get("/api/watch/", headers={"Origin": "http://localhost:3000"})

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

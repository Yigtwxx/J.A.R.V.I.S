"""The two HTTP surfaces the search brief adds, and the contract they hold.

``POST /api/search/brief/parse`` is what lets the UI show the user what the
search is about to do *before* it starts — so it has to be cheap, deterministic
and free of side effects. ``POST /api/search/brief/avatar`` is the only place a
user's own file enters the system, so it validates the bytes rather than the
content type the browser claimed.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.discovery.dependencies import get_avatar_store
from app.discovery.media.store import AvatarStore
from app.main import app

PARSE_URL = "/api/search/brief/parse"
UPLOAD_URL = "/api/search/brief/avatar"


def png_bytes(size: tuple[int, int] = (48, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def upload_client(client: TestClient, tmp_path: Path):
    """The real client, with the avatar store pointed at a temporary directory."""
    store = AvatarStore(tmp_path / "avatars")
    app.dependency_overrides[get_avatar_store] = lambda: store
    yield client, store
    app.dependency_overrides.pop(get_avatar_store, None)


class TestParse:
    def test_it_returns_the_structure_the_chip_renders(self, client: TestClient) -> None:
        response = client.post(PARSE_URL, json={"text": "Eylul Akduman, kız, instagram.com/eylulakduman"})

        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        assert body["name"] == "Eylul Akduman"
        assert body["gender"] == "female"
        assert body["known_profiles"] == [
            {
                "platform": "instagram",
                "username": "eylulakduman",
                "canonical_url": "https://www.instagram.com/eylulakduman/",
                "raw_url": "instagram.com/eylulakduman",
            }
        ]
        assert body["is_empty"] is False

    def test_a_plain_name_reports_an_empty_brief(self, client: TestClient) -> None:
        body = client.post(PARSE_URL, json={"text": "Jane Doe"}).json()

        assert body["is_empty"] is True, "nothing was stated, so the UI must be able to hide the chip"
        assert body["gender"] == "unknown"

    def test_what_it_could_not_place_comes_back_rather_than_being_guessed(self, client: TestClient) -> None:
        body = client.post(PARSE_URL, json={"text": "Jane Doe, roblox.com/users/1, likes hiking"}).json()

        assert body["known_profiles"] == [], "roblox.com/users/1 is not a profile URL on any platform"
        assert set(body["unparsed"]) == {"roblox.com/users/1", "likes hiking"}

    def test_empty_text_is_a_422(self, client: TestClient) -> None:
        assert client.post(PARSE_URL, json={"text": ""}).status_code == 422

    def test_it_needs_the_api_key(self, unauthenticated_client: TestClient) -> None:
        assert unauthenticated_client.post(PARSE_URL, json={"text": "Jane Doe"}).status_code in (401, 403)


class TestUpload:
    def test_an_image_comes_back_as_a_digest_the_search_can_refer_to(self, upload_client) -> None:
        client, store = upload_client

        response = client.post(UPLOAD_URL, files={"file": ("me.png", png_bytes(), "image/png")})

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["sha256"]) == 64
        assert len(body["dhash"]) == 16
        assert body["preview_url"] == f"/api/media/avatars/{body['sha256']}.png"
        assert store.resolve(f"{body['sha256']}.png") is not None, "the file must actually be on disk"

    def test_the_declared_content_type_is_not_believed(self, upload_client) -> None:
        """A page served as `image/jpeg` is how junk would otherwise get a URL."""
        client, _ = upload_client

        response = client.post(UPLOAD_URL, files={"file": ("evil.jpg", b"<html>nope</html>", "image/jpeg")})

        assert response.status_code == 415, response.text

    def test_an_empty_file_is_refused(self, upload_client) -> None:
        client, _ = upload_client

        assert client.post(UPLOAD_URL, files={"file": ("empty.png", b"", "image/png")}).status_code == 400

    def test_it_needs_the_api_key(self, unauthenticated_client: TestClient) -> None:
        response = unauthenticated_client.post(UPLOAD_URL, files={"file": ("me.png", png_bytes(), "image/png")})

        assert response.status_code in (401, 403)


class TestSessionStart:
    def test_an_unrecognised_known_profile_url_is_rejected_loudly(self, client: TestClient) -> None:
        """Silently dropping it would let the search ignore the user's surest fact."""
        response = client.post(
            "/api/search/sessions",
            json={"query": "Jane Doe", "brief": {"known_profiles": ["roblox.com/users/1"]}},
        )

        assert response.status_code == 422, response.text
        assert "roblox.com/users/1" in response.text

    def test_a_valid_brief_is_accepted(self, client: TestClient) -> None:
        response = client.post(
            "/api/search/sessions",
            json={
                "query": "Eylul Akduman",
                "depth": 1,
                "brief": {"gender": "female", "known_profiles": ["instagram.com/eylulakduman"]},
            },
        )

        # 202 when discovery is on, 503 when it is switched off in this env; both
        # prove the body was accepted, which is what this test is about.
        assert response.status_code in (202, 503), response.text

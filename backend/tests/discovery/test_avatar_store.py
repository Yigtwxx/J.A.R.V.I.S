"""The avatar store must be content-addressed, picky about payloads, and unescapable.

Three properties are load-bearing:

1. **Content addressing.** The same picture found on five platforms is one file.
2. **Magic-byte verification.** CDNs serve HTML error pages with
   ``Content-Type: image/jpeg``; trusting the header is how junk gets stored.
3. **A hermetic ``resolve``.** It is the only input the media route hands to the
   filesystem, so traversal, absolute paths and odd extensions must all die there.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.discovery.fetch.result import FetchResult
from app.discovery.media.store import AvatarStore
from app.discovery.types import FetchStatus, FetchTier

HTML_ERROR_PAGE = b"<!doctype html><html><body>404 - avatar not found</body></html>"
OVERSIZE_JPEG = b"\xff\xd8\xff" + b"\x00" * (9 * 1024 * 1024)


def png_bytes(color: tuple[int, int, int] = (12, 34, 56), size: tuple[int, int] = (64, 48)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeFetchSession:
    """Local stand-in for ``FetchSession`` — same signatures, zero network."""

    def __init__(self, blobs: dict[str, bytes] | None = None) -> None:
        self._blobs = blobs or {}
        self.stealth_available = False
        self.stealth_unavailable_reason = "stealth disabled in tests"
        self.calls: list[str] = []

    async def get(
        self,
        url: str,
        *,
        tier: FetchTier = FetchTier.HTTP,
        escalate: bool = True,
        timeout_s: float | None = None,
        min_html_bytes: int = 2_000,
        expect_selector: str | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
    ) -> FetchResult:
        return FetchResult.failure(url, FetchStatus.NOT_FOUND, tier=tier, http_status=404)

    async def get_json(self, url: str) -> tuple[FetchResult, Any | None]:
        return await self.get(url), None

    async def get_bytes(self, url: str, timeout_s: float | None = None) -> tuple[FetchResult, bytes | None]:
        self.calls.append(url)
        raw = self._blobs.get(url)
        if raw is None:
            return FetchResult.failure(url, FetchStatus.NOT_FOUND, tier=FetchTier.HTTP, http_status=404), None
        result = FetchResult(
            url=url,
            final_url=url,
            status=FetchStatus.OK,
            http_status=200,
            html=None,
            page=raw,
            tier=FetchTier.HTTP,
        )
        return result, raw

    async def stealth(
        self,
        url: str,
        *,
        network_idle: bool = True,
        solve_cloudflare: bool = True,
        wait_selector: str | None = None,
    ) -> FetchResult:
        return FetchResult.failure(url, FetchStatus.BLOCKED, tier=FetchTier.STEALTH, error="no stealth in tests")


@pytest.mark.asyncio
async def test_saving_the_same_image_twice_stores_one_file_and_returns_one_digest(tmp_path: Path) -> None:
    data = png_bytes()
    fetch = FakeFetchSession({"https://cdn.example.com/a.png": data, "https://cdn.example.com/b.png": data})
    store = AvatarStore(tmp_path)

    first = await store.save(fetch, "https://cdn.example.com/a.png", platform="github", username="jdoe")
    second = await store.save(fetch, "https://cdn.example.com/b.png", platform="x", username="jdoe")

    assert first is not None and second is not None, "a valid PNG must be stored"
    assert first.sha256 == second.sha256, "identical bytes must map onto one digest"
    assert first.path == second.path, "content addressing means one path per digest"
    assert len(list(tmp_path.glob("*.png"))) == 1, "the same image must not be written twice"
    assert first.local_url == f"/api/media/avatars/{first.sha256}.png", "local_url must be the public media path"
    assert (first.width, first.height) == (64, 48), "dimensions must be read from the stored bytes"
    assert first.dhash and len(first.dhash) == 16, "a stored avatar must carry a usable dhash"


@pytest.mark.asyncio
async def test_non_image_payload_is_rejected_even_when_the_url_looks_like_an_image(tmp_path: Path) -> None:
    fetch = FakeFetchSession({"https://cdn.example.com/avatar.jpg": HTML_ERROR_PAGE})
    store = AvatarStore(tmp_path)

    stored = await store.save(fetch, "https://cdn.example.com/avatar.jpg", platform="instagram", username="jdoe")

    assert stored is None, "an HTML error page must never be stored as an avatar"
    assert not list(tmp_path.glob("*")), "a rejected payload must leave nothing on disk"


@pytest.mark.asyncio
async def test_oversize_payload_is_rejected_before_it_is_written(tmp_path: Path) -> None:
    fetch = FakeFetchSession({"https://cdn.example.com/huge.jpg": OVERSIZE_JPEG})
    store = AvatarStore(tmp_path)

    stored = await store.save(fetch, "https://cdn.example.com/huge.jpg", platform="x", username="jdoe")

    assert stored is None, "a payload above the 8 MB cap must be refused"
    assert not list(tmp_path.glob("*")), "an oversize payload must leave nothing on disk"


@pytest.mark.asyncio
async def test_a_failed_download_returns_none_instead_of_raising(tmp_path: Path) -> None:
    fetch = FakeFetchSession({})
    store = AvatarStore(tmp_path)

    stored = await store.save(fetch, "https://cdn.example.com/missing.png", platform="x", username="jdoe")

    assert stored is None, "a 404 avatar must degrade to None, never raise"


@pytest.mark.asyncio
async def test_resolve_refuses_traversal_and_accepts_only_a_stored_digest(tmp_path: Path) -> None:
    fetch = FakeFetchSession({"https://cdn.example.com/a.png": png_bytes()})
    store = AvatarStore(tmp_path)
    stored = await store.save(fetch, "https://cdn.example.com/a.png", platform="github", username="jdoe")
    assert stored is not None, "fixture setup: the avatar must have been stored"

    assert store.resolve("../../etc/passwd") is None, "path traversal must be refused"
    assert store.resolve("../" + stored.path.name) is None, "a digest reached via .. must still be refused"
    assert store.resolve("/etc/passwd") is None, "an absolute path must be refused"
    assert store.resolve(f"{stored.sha256}.exe") is None, "a valid digest with a bogus extension must be refused"
    assert store.resolve(f"{stored.sha256}.png.exe") is None, "a double extension must be refused"
    assert store.resolve("not-a-digest.png") is None, "a non-digest basename must be refused"
    assert store.resolve("") is None, "an empty name must be refused"
    assert store.resolve(f"{'a' * 64}.png") is None, "a well-formed digest with no file on disk must be refused"
    assert store.resolve(f"{stored.sha256}.png") == stored.path.resolve(), "a stored digest must resolve to its file"

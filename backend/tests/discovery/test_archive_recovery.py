"""Archive recovery reads history — it must never be able to assert existence.

The behavioural tests cover the two useful paths (a capture with OpenGraph
metadata, and nothing archived at all). The last test is a *contract* check: the
API surface must offer no way to express "this profile exists", because a deleted
profile is still deleted no matter how rich its 2021 snapshot was.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

import pytest
from scrapling.parser import Selector

from app.discovery.fetch.result import FetchResult
from app.discovery.sources.archive import (
    ARCHIVE_CONFIDENCE_MULTIPLIER,
    ArchivedSnapshot,
    ArchiveRecovery,
)
from app.discovery.types import FetchStatus, FetchTier

PROFILE_URL = "https://x.com/janedoe"
SNAPSHOT_URL = "https://web.archive.org/web/20210411103000/https://x.com/janedoe"

AVAILABLE_PAYLOAD: dict[str, Any] = {
    "url": "x.com/janedoe",
    "archived_snapshots": {
        "closest": {
            "status": "200",
            "available": True,
            "url": "http://web.archive.org/web/20210411103000/https://x.com/janedoe",
            "timestamp": "20210411103000",
        }
    },
}
EMPTY_PAYLOAD: dict[str, Any] = {"url": "x.com/ghost", "archived_snapshots": {}}
EMPTY_CDX: list[list[str]] = [["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]]
CDX_ROWS: list[list[str]] = [
    ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
    ["com,x)/janedoe", "20190101090000", "https://x.com/janedoe", "text/html", "200", "AAA", "1000"],
    ["com,x)/janedoe", "20210411103000", "https://x.com/janedoe", "text/html", "200", "BBB", "1200"],
]

SNAPSHOT_HTML = """
<html><head>
  <meta property="og:title" content="Jane Doe | X">
  <meta property="og:description" content="Security engineer.   Istanbul.">
  <meta property="og:image" content="https://web.archive.org/web/2021im_/https://pbs.example/avatar.jpg">
</head><body>archived copy</body></html>
"""


class FakeFetchSession:
    """Local stand-in for ``FetchSession`` — same signatures, zero network."""

    def __init__(
        self,
        *,
        availability: Any = None,
        cdx: Any = None,
        pages: dict[str, str] | None = None,
    ) -> None:
        self._availability = availability
        self._cdx = cdx
        self._pages = pages or {}
        self.stealth_available = False
        self.stealth_unavailable_reason = "stealth disabled in tests"
        self.requested: list[str] = []

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
        self.requested.append(url)
        body = self._pages.get(url)
        if body is None:
            return FetchResult.failure(url, FetchStatus.NOT_FOUND, tier=tier, http_status=404)
        return FetchResult(
            url=url,
            final_url=url,
            status=FetchStatus.OK,
            http_status=200,
            html=body,
            page=Selector(body),
            tier=tier,
        )

    async def get_json(self, url: str) -> tuple[FetchResult, Any | None]:
        self.requested.append(url)
        if "wayback/available" in url:
            payload = self._availability
        elif "cdx/search/cdx" in url:
            payload = self._cdx
        else:
            payload = None
        status = FetchStatus.OK if payload is not None else FetchStatus.NOT_FOUND
        result = FetchResult(url=url, final_url=url, status=status, http_status=200 if payload else 404)
        return result, payload

    async def get_bytes(self, url: str, timeout_s: float | None = None) -> tuple[FetchResult, bytes | None]:
        return FetchResult.failure(url, FetchStatus.NOT_FOUND, tier=FetchTier.HTTP, http_status=404), None

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
async def test_recovered_snapshot_yields_display_name_bio_and_avatar_from_og_tags() -> None:
    fetch = FakeFetchSession(availability=AVAILABLE_PAYLOAD, pages={SNAPSHOT_URL: SNAPSHOT_HTML})

    snapshot = await ArchiveRecovery().recover_profile(fetch, PROFILE_URL, platform="x")

    assert snapshot is not None, "an available capture must be recovered"
    assert snapshot.snapshot_url == SNAPSHOT_URL, "the http:// snapshot URL must be upgraded to https"
    assert snapshot.timestamp == datetime(2021, 4, 11, 10, 30, tzinfo=UTC), "the capture date must be parsed as UTC"
    assert snapshot.status == 200, "the archived HTTP status must be carried through"
    assert snapshot.display_name == "Jane Doe", "og:title must be read and the platform suffix stripped"
    assert snapshot.bio == "Security engineer. Istanbul.", "og:description must be read and whitespace collapsed"
    assert snapshot.avatar_url is not None and "avatar.jpg" in snapshot.avatar_url, "og:image must be read"


@pytest.mark.asyncio
async def test_a_url_with_no_capture_returns_none() -> None:
    fetch = FakeFetchSession(availability=EMPTY_PAYLOAD, cdx=EMPTY_CDX)

    assert await ArchiveRecovery().latest_snapshot(fetch, "https://x.com/ghost") is None, (
        "an unarchived URL must yield no snapshot"
    )
    assert await ArchiveRecovery().recover_profile(fetch, "https://x.com/ghost", platform="x") is None, (
        "recovery of an unarchived URL must yield None, not an empty snapshot"
    )


@pytest.mark.asyncio
async def test_cdx_fallback_picks_the_newest_capture_when_availability_is_empty() -> None:
    fetch = FakeFetchSession(availability=EMPTY_PAYLOAD, cdx=CDX_ROWS)

    snapshot = await ArchiveRecovery().latest_snapshot(fetch, PROFILE_URL)

    assert snapshot is not None, "the CDX fallback must find a capture the availability API missed"
    assert snapshot.timestamp.year == 2021, f"the newest row must win, got {snapshot.timestamp!r}"
    assert snapshot.snapshot_url == SNAPSHOT_URL, "the snapshot URL must be built from the newest timestamp"


@pytest.mark.asyncio
async def test_a_disabled_recovery_never_calls_the_archive() -> None:
    fetch = FakeFetchSession(availability=AVAILABLE_PAYLOAD)

    assert await ArchiveRecovery(enabled=False).latest_snapshot(fetch, PROFILE_URL) is None, (
        "a disabled recovery must return None"
    )
    assert fetch.requested == [], "a disabled recovery must issue no requests at all"


@pytest.mark.asyncio
async def test_archive_recovery_cannot_report_that_a_profile_exists() -> None:
    """Contract check: nothing in this API can turn history into a live verdict.

    Archive data is evidence about the past. A deleted profile stays NOT_FOUND, so
    the surface deliberately offers no ``exists``/``verdict`` field for a caller to
    misread — and callers discount what it does offer by 0.75.
    """
    forbidden = ("exists", "verdict", "existence", "found", "is_live", "alive")

    field_names = {field.name for field in dataclasses.fields(ArchivedSnapshot)}
    assert field_names == {
        "url",
        "snapshot_url",
        "timestamp",
        "status",
        "display_name",
        "bio",
        "avatar_url",
    }, f"ArchivedSnapshot grew an unexpected field: {sorted(field_names)}"
    for name in forbidden:
        assert name not in field_names, f"ArchivedSnapshot must not carry a {name!r} field"

    public_api = {name for name in dir(ArchiveRecovery) if not name.startswith("_")}
    for name in public_api:
        lowered = name.lower()
        assert not any(word in lowered for word in forbidden), (
            f"ArchiveRecovery.{name} looks like an existence verdict; archives must not produce one"
        )

    fetch = FakeFetchSession(availability=AVAILABLE_PAYLOAD, pages={SNAPSHOT_URL: SNAPSHOT_HTML})
    snapshot = await ArchiveRecovery().recover_profile(fetch, PROFILE_URL, platform="x")
    assert snapshot is not None, "fixture setup: the snapshot must have been recovered"
    for name in forbidden:
        assert not hasattr(snapshot, name), f"a recovered snapshot must expose no {name!r} attribute"

    assert ARCHIVE_CONFIDENCE_MULTIPLIER == 0.75, "archive-derived confidence must stay discounted at 0.75"

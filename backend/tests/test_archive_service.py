"""Tests for ArchiveService — Wayback Machine snapshots (httpx mocked)."""

import asyncio

import httpx

from app.services import archive_service as mod
from app.services.archive_service import ArchiveService

_CDX_ROWS = [
    ["timestamp", "original", "statuscode"],
    ["20200101000000", "http://example.com/", "200"],
    ["20210601120000", "http://example.com/about", "200"],
]


def _cdx_handler(request: httpx.Request) -> httpx.Response:
    if "web.archive.org" in request.url.host:
        return httpx.Response(200, json=_CDX_ROWS)
    return httpx.Response(404)


def _patch_client(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*a, **k):
        return real(transport=httpx.MockTransport(handler), follow_redirects=True)

    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)


def test_derive_urls_dedup_and_cap():
    svc = ArchiveService()
    urls = svc.derive_urls(
        ["https://x.com/a", "https://x.com/a"], "example.com", ["acme.io"]
    )
    assert "https://x.com/a" in urls
    assert "https://example.com" in urls
    assert "https://acme.io" in urls
    assert len(urls) == len(set(urls))


def test_history_parses_snapshots():
    svc = ArchiveService()

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(_cdx_handler)) as c:
            return await svc._history(c, "http://example.com")

    snaps = asyncio.run(go())
    assert len(snaps) == 2
    assert snaps[0]["snapshot_url"].startswith("https://web.archive.org/web/")
    assert all(s["source_url"] for s in snaps)
    assert all(s["retrieved_at"] for s in snaps)


def test_aggregate_empty_returns_empty():
    assert asyncio.run(ArchiveService().aggregate([])) == []


def test_aggregate_happy(monkeypatch):
    _patch_client(monkeypatch, _cdx_handler)
    snaps = asyncio.run(ArchiveService().aggregate(["http://example.com"]))
    assert len(snaps) == 2
    # newest first
    assert snaps[0]["timestamp"] >= snaps[1]["timestamp"]


def test_aggregate_error_degrades(monkeypatch):
    _patch_client(monkeypatch, lambda r: httpx.Response(500))
    assert asyncio.run(ArchiveService().aggregate(["http://example.com"])) == []

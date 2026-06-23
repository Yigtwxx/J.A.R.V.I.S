"""Tests for SanctionsService — OFAC SDN screening (httpx mocked)."""

import asyncio

import httpx

from app.services import sanctions_service as mod
from app.services.sanctions_service import SanctionsService

# ent_num, name, type, program, ...
_SDN_CSV = (
    '1,"JOHN SMITH TEST",individual,"UKRAINE-EO13662",-0-,-0-,-0-,-0-,-0-,-0-,-0-,-0-\n'
    '2,"ACME WEAPONS LLC",entity,"IRAN",-0-,-0-,-0-,-0-,-0-,-0-,-0-,-0-\n'
)


def _handler(request: httpx.Request) -> httpx.Response:
    if "treasury.gov" in request.url.host:
        return httpx.Response(200, content=_SDN_CSV.encode("utf-8"))
    return httpx.Response(404)


def _patch_client(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*a, **k):
        return real(transport=httpx.MockTransport(handler), follow_redirects=True)

    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)


def _clear_cache():
    with mod._sdn_lock:
        mod._sdn_cache.clear()


def test_check_short_name_returns_empty():
    assert asyncio.run(SanctionsService().check("ab")) == []


def test_check_exact_match(monkeypatch):
    _clear_cache()
    _patch_client(monkeypatch, _handler)
    hits = asyncio.run(SanctionsService().check("John Smith Test"))
    assert len(hits) >= 1
    top = hits[0]
    assert top["list_name"] == "OFAC SDN"
    assert top["match_score"] >= 0.86
    assert top["source_url"]
    assert "verification required" in top["note"].lower()


def test_check_no_match(monkeypatch):
    _clear_cache()
    _patch_client(monkeypatch, _handler)
    hits = asyncio.run(SanctionsService().check("Zzqq Nomatch Personae"))
    assert hits == []


def test_check_download_failure_degrades(monkeypatch):
    _clear_cache()
    _patch_client(monkeypatch, lambda r: httpx.Response(500))
    assert asyncio.run(SanctionsService().check("John Smith Test")) == []

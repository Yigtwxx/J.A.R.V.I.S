"""Tests for ScholarlyService — Semantic Scholar / arXiv / Crossref (httpx mocked)."""

import asyncio

import httpx

from app.services import scholarly_service as mod
from app.services.scholarly_service import ScholarlyService

_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678</id>
    <title>Deep Learning for OSINT</title>
    <published>2019-05-01T00:00:00Z</published>
    <author><name>Jane Researcher</name></author>
  </entry>
</feed>"""


def _handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    path = request.url.path
    if host == "api.semanticscholar.org":
        if path.endswith("/author/search"):
            return httpx.Response(200, json={"data": [{"authorId": "A1", "name": "Jane"}]})
        if "/papers" in path:
            return httpx.Response(200, json={"data": [
                {"title": "Graph Methods", "year": 2021, "venue": "NeurIPS", "url": "https://s2/p1"},
            ]})
        return httpx.Response(404)
    if host == "export.arxiv.org":
        return httpx.Response(200, text=_ARXIV_XML)
    if host == "api.crossref.org":
        return httpx.Response(200, json={"message": {"items": [
            {"title": ["Crossref Paper"], "published-print": {"date-parts": [[2018]]},
             "container-title": ["Journal X"], "URL": "https://doi/1", "author": [
                 {"given": "Jane", "family": "Researcher"}]},
        ]}})
    return httpx.Response(404)


def _patch_client(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*a, **k):
        return real(transport=httpx.MockTransport(handler), follow_redirects=True)

    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)


def test_aggregate_empty_name():
    assert asyncio.run(ScholarlyService().aggregate("")) == []


def test_aggregate_merges_all_sources(monkeypatch):
    _patch_client(monkeypatch, _handler)
    records = asyncio.run(ScholarlyService().aggregate("Jane Researcher"))
    titles = {r["title"] for r in records}
    assert "Graph Methods" in titles          # Semantic Scholar
    assert "Deep Learning for OSINT" in titles  # arXiv
    assert "Crossref Paper" in titles          # Crossref
    assert all(r["source_url"] for r in records)
    assert all(r["retrieved_at"] for r in records)
    # sorted newest first
    years = [r.get("year") or 0 for r in records]
    assert years == sorted(years, reverse=True)


def test_aggregate_error_degrades(monkeypatch):
    _patch_client(monkeypatch, lambda r: httpx.Response(500))
    assert asyncio.run(ScholarlyService().aggregate("Jane Researcher")) == []

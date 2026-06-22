"""Tests for DomainIntelService — public RDAP / DNS / Certificate Transparency.

HTTP is mocked with httpx.MockTransport (no extra deps). Async methods are
driven via asyncio.run so the suite needs no pytest-asyncio configuration.
"""

import asyncio

import httpx
import pytest

from app.services import domain_intel_service as dim
from app.services.domain_intel_service import DomainIntelService

# ---------------------------------------------------------------------------
# Canned public responses
# ---------------------------------------------------------------------------

_RDAP = {
    "entities": [
        {
            "roles": ["registrar"],
            "vcardArray": [
                "vcard",
                [["version", {}, "text", "4.0"], ["fn", {}, "text", "Example Registrar Inc."]],
            ],
        }
    ],
    "events": [
        {"eventAction": "registration", "eventDate": "2010-05-01T00:00:00Z"},
        {"eventAction": "expiration", "eventDate": "2030-05-01T00:00:00Z"},
    ],
    "nameservers": [{"ldhName": "ns1.example.com"}, {"ldhName": "ns2.example.com"}],
    "status": ["client transfer prohibited"],
}

_DNS = {
    "A": {"Status": 0, "Answer": [{"name": "example.com.", "type": 1, "data": "93.184.216.34"}]},
    "MX": {"Answer": [{"data": "10 mail.example.com."}]},
    "TXT": {"Answer": [{"data": '"v=spf1 -all"'}]},
    "NS": {"Answer": [{"data": "ns1.example.com."}]},
}

_CRTSH = [
    {"name_value": "example.com\nwww.example.com"},
    {"name_value": "*.example.com\napi.example.com"},
    {"name_value": "www.example.com"},  # duplicate
]


def _ok_handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "rdap.org":
        return httpx.Response(200, json=_RDAP)
    if host == "dns.google":
        rtype = request.url.params.get("type", "A")
        return httpx.Response(200, json=_DNS.get(rtype, {"Answer": []}))
    if host == "crt.sh":
        return httpx.Response(200, json=_CRTSH)
    return httpx.Response(404)


def _patch_client(monkeypatch, handler) -> None:
    """Force the service's AsyncClient to use a MockTransport handler."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler), follow_redirects=True)

    monkeypatch.setattr(dim.httpx, "AsyncClient", factory)


# ---------------------------------------------------------------------------
# derive_domains (pure, no network)
# ---------------------------------------------------------------------------

def test_derive_domains_filters_free_mail_and_parses_blog():
    svc = DomainIntelService()
    domains = svc.derive_domains(
        ["john@acme.io", "spam@gmail.com", "x@outlook.com"],
        "https://www.example.com/blog",
    )
    assert "acme.io" in domains
    assert "example.com" in domains  # www. stripped, host parsed
    assert "gmail.com" not in domains
    assert "outlook.com" not in domains


def test_derive_domains_empty_and_cap():
    svc = DomainIntelService()
    assert svc.derive_domains([], None) == []
    many = [f"u@d{i}.com" for i in range(10)]
    assert len(svc.derive_domains(many, None)) <= 5


# ---------------------------------------------------------------------------
# Per-source parsing (client injected directly)
# ---------------------------------------------------------------------------

def _run_one(handler, domain="example.com"):
    svc = DomainIntelService()

    async def _go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await svc._fetch_one(client, domain)

    return asyncio.run(_go())


def test_fetch_one_parses_all_sources():
    rec = _run_one(_ok_handler)
    assert rec["domain"] == "example.com"
    assert rec["registrar"] == "Example Registrar Inc."
    assert rec["created"] == "2010-05-01T00:00:00Z"
    assert rec["expires"] == "2030-05-01T00:00:00Z"
    assert rec["nameservers"] == ["ns1.example.com", "ns2.example.com"]
    assert rec["dns"]["a"] == ["93.184.216.34"]
    assert rec["dns"]["mx"] == ["10 mail.example.com."]
    # crt.sh: own domain excluded, wildcard stripped, deduped
    assert rec["subdomains"] == ["api.example.com", "www.example.com"]
    # provenance is mandatory on every record
    assert rec["source_url"].startswith("https://rdap.org/domain/")
    assert rec["retrieved_at"]
    assert 0.0 <= rec["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Graceful degradation — never raises, never breaks the pipeline
# ---------------------------------------------------------------------------

def test_aggregate_empty_returns_empty():
    svc = DomainIntelService()
    assert asyncio.run(svc.aggregate([])) == []


def test_aggregate_http_error_degrades(monkeypatch):
    _patch_client(monkeypatch, lambda req: httpx.Response(500))
    svc = DomainIntelService()
    records = asyncio.run(svc.aggregate(["example.com"]))
    # still returns a record (with empty fields) rather than raising
    assert len(records) == 1
    assert records[0]["domain"] == "example.com"
    assert records[0]["registrar"] is None
    assert records[0]["subdomains"] == []


def test_aggregate_network_error_degrades(monkeypatch):
    def _boom(req):
        raise httpx.ConnectError("network down")

    _patch_client(monkeypatch, _boom)
    svc = DomainIntelService()
    records = asyncio.run(svc.aggregate(["example.com"]))
    assert len(records) == 1
    assert records[0]["registrar"] is None


def test_aggregate_happy_path(monkeypatch):
    _patch_client(monkeypatch, _ok_handler)
    svc = DomainIntelService()
    records = asyncio.run(svc.aggregate(["example.com"]))
    assert len(records) == 1
    assert records[0]["registrar"] == "Example Registrar Inc."
    assert records[0]["subdomains"] == ["api.example.com", "www.example.com"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

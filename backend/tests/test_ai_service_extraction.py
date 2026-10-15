"""Tests for AIService.extract_profile_data error containment.

Extraction is an enrichment step called outside the post-analysis gather, so any
exception it raises propagates all the way to the search route. Its except tuple
used to omit TimeoutError and ollama.ResponseError, which turned a slow or
unavailable model into a failed search minutes in.

Only the external dependency (the Ollama client) is mocked; the parsing and
fallback logic under test runs for real.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import ollama
import pytest

from app.services.ai_service import AIService

FALLBACK_KEYS = {
    "name",
    "description",
    "similar_profiles",
    "cross_validation_issues",
    "network_connections",
    "email_addresses",
}


@pytest.fixture
def service() -> AIService:
    svc = AIService()
    svc.client = AsyncMock()
    return svc


def assert_is_fallback(result: dict, query: str) -> None:
    assert set(result) == FALLBACK_KEYS, f"Unexpected fallback shape: {sorted(result)}"
    assert result["name"] == query, f"Fallback must keep the queried name, got {result['name']!r}"
    assert result["network_connections"] == []
    assert result["email_addresses"] == []


@pytest.mark.parametrize(
    "raised",
    [
        pytest.param(TimeoutError(), id="timeout"),
        pytest.param(ollama.ResponseError("model not found", 404), id="ollama_response_error"),
        pytest.param(ConnectionError("connection refused"), id="connection_error"),
        pytest.param(OSError("socket closed"), id="os_error"),
    ],
)
@pytest.mark.asyncio
async def test_extract_profile_data_contains_client_failures(service, raised):
    service.client.generate.side_effect = raised

    result = await service.extract_profile_data("Some prior analysis text", "Target Name")

    assert_is_fallback(result, "Target Name")


@pytest.mark.asyncio
async def test_extract_profile_data_timeout_is_not_swallowed_by_oserror_clause(service):
    """TimeoutError subclasses OSError on 3.11 — clause order must keep them apart.

    If the OSError tuple matched first the search would still survive, but the
    log would blame a generic extraction failure and hide the real cause.
    """
    service.client.generate.side_effect = TimeoutError()

    result = await service.extract_profile_data("text", "Target")

    assert_is_fallback(result, "Target")


@pytest.mark.asyncio
async def test_extract_profile_data_malformed_json_returns_fallback(service):
    service.client.generate.return_value = {"response": "there is no json here at all"}

    result = await service.extract_profile_data("prior text", "Target")

    assert_is_fallback(result, "Target")


@pytest.mark.asyncio
async def test_extract_profile_data_parses_json_after_thinking_block(service):
    payload = {"name": "Target", "description": "A person", "email_addresses": ["a@b.com"]}
    service.client.generate.return_value = {"response": f"<think>weighing options</think>{json.dumps(payload)}"}

    result = await service.extract_profile_data("prior text", "Target")

    assert result == payload, "thinking blocks must be stripped before JSON extraction"


@pytest.mark.asyncio
async def test_extract_profile_data_uses_configured_timeout(service, monkeypatch):
    """The budget is configurable — a hardcoded 60s was too tight for local models."""
    from app.services import ai_service as ai_service_module

    monkeypatch.setattr(ai_service_module.settings, "llm_extraction_timeout_seconds", 0.01)

    async def never_finishes(*_args, **_kwargs):
        await asyncio.sleep(5)

    service.client.generate = never_finishes

    result = await asyncio.wait_for(service.extract_profile_data("text", "Target"), timeout=2)

    assert_is_fallback(result, "Target")

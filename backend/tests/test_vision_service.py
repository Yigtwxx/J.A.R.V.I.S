"""VisionService — a failure must never come back looking like an observation.

The bug these tests pin was live on 2026-08-29: ``vision_model`` pointed at
``llama3.2-vision``, Ollama 0.32.13 had dropped the ``mllama`` architecture, and
every method caught the load failure and returned ``f"Vision analysis error:
{exc}"`` as its answer. Four endpoints replied 200 with prose describing an
outage, and nothing anywhere reported a problem.
"""

import asyncio

import httpx
import pytest

from app.services import vision_service as module
from app.services.vision_service import (
    VisionImageError,
    VisionService,
    VisionUnavailableError,
)


def run(coro):
    """The repo's dominant idiom: drive one coroutine from a sync test."""
    return asyncio.run(coro)


class _FakeClient:
    """Stands in for ``ollama.AsyncClient``, recording what it was asked."""

    def __init__(self, *, reply: object = None, raises: Exception | None = None) -> None:
        self.reply = reply
        self.raises = raises
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.reply


def _service(client: _FakeClient) -> VisionService:
    service = VisionService.__new__(VisionService)
    service.model = "test-vlm"
    service.client = client
    return service


def _patch_download(monkeypatch, handler) -> None:
    """Point the module's httpx client at an in-process transport.

    ``real`` is captured before the patch: ``module.httpx`` *is* the global httpx
    module, so a factory that called ``httpx.AsyncClient`` after patching would
    call itself.
    """
    real = httpx.AsyncClient

    def factory(*_args, **_kwargs):
        return real(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


def test_a_model_that_cannot_load_raises_instead_of_returning_prose():
    client = _FakeClient(raises=RuntimeError("unknown model architecture: 'mllama'"))
    service = _service(client)

    with pytest.raises(VisionUnavailableError) as caught:
        run(service.analyze_image_bytes(b"\xff\xd8\xffimage"))

    message = str(caught.value)
    assert "mllama" in message, f"the cause must survive into the error, got {message!r}"
    assert "test-vlm" in message, f"the error must name the model that failed, got {message!r}"


def test_an_empty_reply_is_an_outage_not_an_answer():
    service = _service(_FakeClient(reply={"message": {"content": "   "}}))

    with pytest.raises(VisionUnavailableError):
        run(service.analyze_image_bytes(b"\xff\xd8\xffimage"))


def test_analyze_image_bytes_reaches_the_model_without_a_url_round_trip(monkeypatch):
    def explode(_request):  # pragma: no cover - must never run
        raise AssertionError("bytes already in hand must not be downloaded")

    _patch_download(monkeypatch, explode)
    client = _FakeClient(reply={"message": {"content": "a login form"}})

    result = run(_service(client).analyze_image_bytes(b"\xff\xd8\xffimage", "read this"))

    assert result == "a login form", f"expected the model's text, got {result!r}"
    assert client.calls, "the model was never asked"
    images = client.calls[0]["messages"][0]["images"]
    assert len(images) == 1, f"exactly one image should be sent, got {len(images)}"


def test_empty_bytes_are_refused_before_the_model_is_troubled():
    client = _FakeClient(reply={"message": {"content": "unreachable"}})

    with pytest.raises(VisionImageError):
        run(_service(client).analyze_image_bytes(b""))

    assert client.calls == [], "an empty image must not cost a model call"


def test_an_unreachable_image_is_reported_apart_from_a_model_outage(monkeypatch):
    _patch_download(monkeypatch, lambda request: httpx.Response(404))
    client = _FakeClient(reply={"message": {"content": "unreachable"}})

    with pytest.raises(VisionImageError):
        run(_service(client).analyze_image("https://example.com/missing.jpg"))

    assert client.calls == [], "a missing image must not be blamed on the model"


def test_the_social_photo_parse_keeps_the_raw_reply_alongside_the_fields(monkeypatch):
    _patch_download(monkeypatch, lambda request: httpx.Response(200, content=b"\xff\xd8\xffjpeg"))
    raw = "DESCRIPTION: A man on a boat\nLOCATION CLUES: Turkish signage\nOSINT NOTES: none"
    client = _FakeClient(reply={"message": {"content": raw}})

    parsed = run(_service(client).analyze_social_photo("https://example.com/a.jpg"))

    assert parsed["description"] == "A man on a boat", f"got {parsed['description']!r}"
    assert parsed["location_clues"] == "Turkish signage", f"got {parsed['location_clues']!r}"
    assert parsed["raw_analysis"] == raw, "the raw reply must survive a prefix-based parse"


def test_a_social_photo_outage_raises_rather_than_returning_an_error_dict(monkeypatch):
    _patch_download(monkeypatch, lambda request: httpx.Response(200, content=b"\xff\xd8\xffjpeg"))
    service = _service(_FakeClient(raises=RuntimeError("model gone")))

    with pytest.raises(VisionUnavailableError):
        run(service.analyze_social_photo("https://example.com/a.jpg"))

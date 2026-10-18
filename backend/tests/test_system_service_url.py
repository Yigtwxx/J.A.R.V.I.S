"""Tests for the URL guard on the System Control panel's "open URL" action.

Two failures used to hide behind this feature. A scheme-less host such as
``youtube.com`` — what people actually type — was passed straight to
``webbrowser.open``, which resolves it as a relative *path* and opens nothing
while still reporting success. And any scheme at all was accepted, so an
approved "open a link" action could reach ``file://`` or an OS handler.

``normalize_url`` is pure, so nothing is mocked here.
"""

import pytest

from app.services.system_service import normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("youtube.com", "https://youtube.com"),
        ("www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("  https://youtu.be/dQw4w9WgXcQ  ", "https://youtu.be/dQw4w9WgXcQ"),
        ("HTTPS://YouTube.com/x", "https://YouTube.com/x"),
        # An explicit scheme means the user meant it, so dot-less dev targets stay usable.
        ("http://localhost:3000", "http://localhost:3000"),
    ],
)
def test_normalize_url_accepts_web_urls(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "file:///C:/Windows/win.ini",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://example.com/secret",
    ],
)
def test_normalize_url_rejects_non_web_schemes(raw: str) -> None:
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        normalize_url(raw)


@pytest.mark.parametrize("raw", ["", "   ", "notaurl", "https://"])
def test_normalize_url_rejects_empty_and_malformed_input(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_url(raw)

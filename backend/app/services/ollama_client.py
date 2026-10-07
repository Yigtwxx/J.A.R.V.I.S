"""Shared Ollama client factory.

Two problems this fixes, both silent:

1. ``ollama.AsyncClient()`` defaults to ``timeout=None``, which it hands straight
   to httpx. A daemon that accepts the connection and then never answers blocks
   the request forever — there is no connect or read bound at all.
2. Every call site constructed the client without a ``host``, so the configured
   ``OLLAMA_URL`` was quietly ignored and the library default was used instead.

The read timeout is per-read, not per-request: for a streaming generation it
means "no new bytes for N seconds". A healthy long-running generation keeps
resetting it, so this never truncates real work — it only cuts a connection that
has gone silent.
"""

import httpx
import ollama

from app.config import get_settings


def build_ollama_client(read_timeout: float | None = None) -> ollama.AsyncClient:
    """Return an AsyncClient pointed at OLLAMA_URL with explicit httpx timeouts.

    Args:
        read_timeout: Seconds to wait for new bytes. Defaults to
            ``settings.ollama_request_timeout_seconds``.
    """
    settings = get_settings()
    return ollama.AsyncClient(
        host=settings.ollama_url,
        timeout=httpx.Timeout(
            connect=settings.ollama_connect_timeout_seconds,
            read=read_timeout if read_timeout is not None else settings.ollama_request_timeout_seconds,
            write=30.0,
            pool=settings.ollama_connect_timeout_seconds,
        ),
    )

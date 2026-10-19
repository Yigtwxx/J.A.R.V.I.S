"""A host that will not complete a TCP handshake must fail fast.

Measured live on 2026-08-29, against an address this network drops silently
(``html.duckduckgo.com`` / 20.204.244.192, unreachable on both 80 and 443 while
every other host tested connected normally):

    timeout=30      -> 21.1 s   curl (28) "Failed to connect ... after 21098 ms"
    timeout=(5, 30) ->  5.0 s   curl (28) "Connection timed out after 5015 ms"

That 21 s is the OS connect timeout, not our budget, and ``FetchStatus.TIMEOUT``
is retryable — so one logical fetch against an unroutable host cost **three**
attempts at 21 s. With a search-engine circuit breaker that needs three such
failures before retiring an engine, and that revives it every 180 s, a single
blocked engine was spending minutes of a 30-minute search budget on a socket
that was never going to open.

Splitting connect from read is the whole fix: a healthy but slow page still gets
the full read budget, because slowness there is in the body, not the handshake.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.discovery.fetch import session as session_module
from app.discovery.fetch.httppool import CONNECT_TIMEOUT_S
from app.discovery.fetch.ratelimit import DomainRateLimiter
from app.discovery.fetch.session import FetchSession


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class CapturingPool:
    """Stands in for ``HttpSessionPool`` — records the kwargs it was handed."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get(self, url: str, **kwargs: Any) -> Any:
        del url
        self.calls.append(kwargs)
        raise TimeoutError("connect timed out")

    async def aclose(self) -> None:
        return None


def _no_backoff(monkeypatch) -> None:
    """Skip the retry backoff. The delays are real behaviour, but waiting them
    out here would add fifteen seconds to the suite to prove nothing."""

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(session_module.asyncio, "sleep", instant)


def _session(**kwargs: Any) -> tuple[FetchSession, CapturingPool]:
    session = FetchSession(rate_limiter=DomainRateLimiter(jitter=0.0), stealth_enabled=False, **kwargs)
    pool = CapturingPool()
    session._http = pool  # the transport seam; nothing below it is under test
    return session, pool


def test_the_http_tier_asks_for_a_connect_timeout_separate_from_the_read_budget(monkeypatch):
    _no_backoff(monkeypatch)
    session, pool = _session(http_timeout_s=30.0)

    run(session.get("https://example.invalid/", escalate=False))

    assert pool.calls, "the transport was never called"
    timeout = pool.calls[0]["timeout"]
    assert isinstance(timeout, tuple), f"expected a (connect, read) pair, got {timeout!r}"
    connect, read = timeout
    assert connect == CONNECT_TIMEOUT_S, f"connect budget was {connect}, expected {CONNECT_TIMEOUT_S}"
    assert read == 30.0, f"the read budget must survive untouched, got {read}"


def test_a_caller_asking_for_less_than_the_connect_budget_still_gets_less(monkeypatch):
    """A 2 s fetch must not be silently promoted to a 5 s handshake."""
    _no_backoff(monkeypatch)
    session, pool = _session(http_timeout_s=30.0)

    run(session.get("https://example.invalid/", timeout_s=2.0, escalate=False))

    connect, read = pool.calls[0]["timeout"]
    assert connect <= 2.0, f"connect budget {connect} exceeded the caller's total of 2.0"
    assert read == 2.0, f"got {read}"


def test_an_unreachable_host_still_reports_a_timeout_not_an_absence(monkeypatch):
    """Invariant 1: a socket that never opened says nothing about the account."""
    _no_backoff(monkeypatch)
    session, _pool = _session()

    result = run(session.get("https://example.invalid/", escalate=False))

    assert result.status.value == "timeout", f"got {result.status}"
    assert not result.ok

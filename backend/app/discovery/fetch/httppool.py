"""One long-lived HTTP session per host, so cookies survive between requests.

Before this, the HTTP tier called ``AsyncFetcher.get`` — a classmethod that builds
a throwaway ``AsyncCurlSession`` for every single request
(``scrapling/engines/static.py:450-457``). Fast, but stateless: a consent cookie,
a ``csrftoken``, a Cloudflare clearance were all discarded the moment the request
finished, so we arrived at every host as a client that had never been there
before. That is both a weaker fingerprint and wasted work.

**Why one session per registrable domain rather than one for everything.**
Scrapling's own comment at that same line explains it: *"Using a single session
for many requests at the same time in async doesn't sit well with curl_cffi."*
The pipeline fans out — ``ExistenceChecker.check_many`` runs six handles at once
— so a single shared session would be exactly the pattern upstream warns about.
Partitioning by host gives each realm its own session and its own lock, and
serialising within a realm costs nothing that was not already being paid: the
``DomainRateLimiter`` spaces same-domain requests seconds apart regardless.

Sessions are capped and evicted LRU so a long search cannot accumulate hundreds
of open sessions.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from app.discovery.fetch.identity import DEFAULT_IMPERSONATE
from app.discovery.fetch.ratelimit import registrable_domain
from app.utils.logger import logger

# Scrapling's retry loop is `for attempt in range(retries)`, so 1 means "try once,
# never retry" — 0 would skip the request entirely. Our own loop in
# fetch/session.py owns retries, because only it can tell a refusal (never retry)
# from a transport error (retry). Leaving Scrapling's default of 3 in place would
# multiply out to nine requests for one logical fetch.
NO_INNER_RETRY = 1


@dataclass(slots=True)
class _Realm:
    """One host's session, plus the lock that keeps curl_cffi happy."""

    session: Any
    entered: Any
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class HttpSessionPool:
    """Per-domain ``FetcherSession`` pool with a shared cookie jar per host.

    Never raises on teardown, and degrades to a one-off request if a session
    cannot be created — the HTTP tier must keep working even when the
    optimisation does not.
    """

    def __init__(
        self,
        *,
        timeout_s: float,
        impersonate: str = DEFAULT_IMPERSONATE,
        max_realms: int = 24,
        enabled: bool = True,
    ) -> None:
        self._timeout_s = timeout_s
        self._impersonate = impersonate
        self._max_realms = max(1, max_realms)
        self._enabled = enabled
        self._realms: OrderedDict[str, _Realm] = OrderedDict()
        self._lock = asyncio.Lock()
        self._closed = False

    @staticmethod
    def realm_for(url: str) -> str:
        """The host whose session and cookie jar this URL belongs to."""
        return registrable_domain(url)

    async def get(self, url: str, **kwargs: Any) -> Any:
        """GET ``url`` through this host's session, falling back to a one-off request."""
        realm = await self._realm(url)
        if realm is None:
            from scrapling.fetchers import AsyncFetcher

            return await AsyncFetcher.get(url, **kwargs)

        async with realm.lock:
            return await realm.entered.get(url, **kwargs)

    async def aclose(self) -> None:
        """Close every session. Safe to call twice; one bad session cannot block the rest."""
        if self._closed:
            return
        self._closed = True
        async with self._lock:
            realms, self._realms = list(self._realms.items()), OrderedDict()
        for domain, realm in realms:
            await _close_realm(domain, realm)

    async def _realm(self, url: str) -> _Realm | None:
        """The session for this host, or None to fall back to a stateless request."""
        if not self._enabled or self._closed:
            return None
        domain = self.realm_for(url)
        if not domain:
            return None

        async with self._lock:
            existing = self._realms.get(domain)
            if existing is not None:
                self._realms.move_to_end(domain)
                return existing

            try:
                from scrapling.fetchers import FetcherSession

                session = FetcherSession(
                    impersonate=self._impersonate,
                    stealthy_headers=True,
                    timeout=self._timeout_s,
                    retries=NO_INNER_RETRY,
                    follow_redirects=True,
                )
                entered = await session.__aenter__()
            except Exception as exc:
                # A session is an optimisation. Losing it means falling back to the
                # old stateless behaviour, never losing the fetch.
                logger.log_warning(
                    f"HTTP session for {domain} unavailable ({exc}); using one-off requests",
                    broadcast=False,
                )
                return None

            realm = _Realm(session=session, entered=entered)
            self._realms[domain] = realm
            evicted = self._evict_if_needed()

        for name, stale in evicted:
            await _close_realm(name, stale)
        return realm

    def _evict_if_needed(self) -> list[tuple[str, _Realm]]:
        """Drop least-recently-used realms. Caller closes them outside the lock."""
        evicted: list[tuple[str, _Realm]] = []
        while len(self._realms) > self._max_realms:
            evicted.append(self._realms.popitem(last=False))
        return evicted


async def _close_realm(domain: str, realm: _Realm) -> None:
    try:
        await realm.session.__aexit__(None, None, None)
    except Exception as exc:  # a session that will not close must not fail the search
        logger.log_warning(f"HTTP session for {domain} failed to close: {exc}", broadcast=False)

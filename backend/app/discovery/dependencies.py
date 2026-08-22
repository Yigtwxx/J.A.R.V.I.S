"""Dependency providers for the discovery pipeline.

Which objects may be cached is a correctness question, not a style one:

* ``DomainRateLimiter`` **must** be a process-wide singleton — a rate limit
  belongs to the remote host, so two concurrent searches sharing Instagram have to
  queue behind the same bucket or the limit means nothing.
* ``QuestionBroker`` and ``SessionManager`` must be singletons because the answer
  endpoint and the discovery task have to find the same pending future.
* ``CookieVault`` and ``BrowserProfilePool`` are singletons for the same reason as
  the rate limiter: what they hold describes the *remote* host, not our session.
  Both deliberately store data only — cookie values and directory paths — never a
  live browser, which is what keeps them on the right side of the rule below.
* ``FetchSession`` must **never** be cached. It holds a live browser and a
  per-search response cache; the ``@lru_cache(maxsize=1)`` pattern used elsewhere
  in ``app/dependencies.py`` would leak a browser for the process lifetime and
  serve one search's cached pages to another.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.discovery.evidence.store import EvidenceStore
from app.discovery.fetch.cookies import CookieVault
from app.discovery.fetch.profiles import BrowserProfilePool
from app.discovery.fetch.ratelimit import DomainRateLimiter
from app.discovery.hitl.broker import QuestionBroker
from app.discovery.loop.runner import DiscoveryRunner
from app.discovery.media.store import AvatarStore
from app.discovery.session.manager import SessionManager


@lru_cache(maxsize=1)
def get_domain_rate_limiter() -> DomainRateLimiter:
    settings = get_settings()
    return DomainRateLimiter(
        jitter=settings.discovery_rate_jitter,
        adaptive=settings.discovery_adaptive_backoff,
    )


@lru_cache(maxsize=1)
def get_cookie_vault() -> CookieVault:
    """Process-wide, for the same reason as the rate limiter.

    What a host handed us belongs to that host, not to one search: a Cloudflare
    clearance cookie solved by search A is exactly what search B needs in order
    not to solve the same challenge again.
    """
    return CookieVault(enabled=get_settings().discovery_cookie_persistence)


@lru_cache(maxsize=1)
def get_browser_profile_pool() -> BrowserProfilePool:
    """Leases user-data directories, never live browsers.

    This is why it may be cached while ``FetchSession`` may not: it holds paths
    and a lock, so it costs nothing to keep and leaks nothing between searches.
    """
    settings = get_settings()
    return BrowserProfilePool(
        root=settings.discovery_browser_profile_dir,
        size=max(1, settings.discovery_max_concurrent_stealth_sessions),
        persist=settings.discovery_browser_profile_persist,
    )


@lru_cache(maxsize=1)
def get_question_broker() -> QuestionBroker:
    return QuestionBroker()


@lru_cache(maxsize=1)
def get_session_manager() -> SessionManager:
    return SessionManager()


@lru_cache(maxsize=1)
def get_evidence_store() -> EvidenceStore:
    return EvidenceStore()


@lru_cache(maxsize=1)
def get_avatar_store() -> AvatarStore:
    return AvatarStore()


@lru_cache(maxsize=1)
def get_discovery_runner() -> DiscoveryRunner:
    """The runner is stateless per call; all mutable state lives in DiscoveryState."""
    return DiscoveryRunner(
        store=get_evidence_store(),
        broker=get_question_broker(),
        manager=get_session_manager(),
        rate_limiter=get_domain_rate_limiter(),
        cookies=get_cookie_vault(),
        profiles=get_browser_profile_pool(),
    )

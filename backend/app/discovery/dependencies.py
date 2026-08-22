"""Dependency providers for the discovery pipeline.

Which objects may be cached is a correctness question, not a style one:

* ``DomainRateLimiter`` **must** be a process-wide singleton — a rate limit
  belongs to the remote host, so two concurrent searches sharing Instagram have to
  queue behind the same bucket or the limit means nothing.
* ``QuestionBroker`` and ``SessionManager`` must be singletons because the answer
  endpoint and the discovery task have to find the same pending future.
* ``FetchSession`` must **never** be cached. It holds a Camoufox browser and a
  per-search response cache; the ``@lru_cache(maxsize=1)`` pattern used elsewhere
  in ``app/dependencies.py`` would leak a browser for the process lifetime and
  serve one search's cached pages to another.
"""

from __future__ import annotations

from functools import lru_cache

from app.discovery.evidence.store import EvidenceStore
from app.discovery.fetch.ratelimit import DomainRateLimiter
from app.discovery.hitl.broker import QuestionBroker
from app.discovery.loop.runner import DiscoveryRunner
from app.discovery.media.store import AvatarStore
from app.discovery.session.manager import SessionManager


@lru_cache(maxsize=1)
def get_domain_rate_limiter() -> DomainRateLimiter:
    return DomainRateLimiter()


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
    )

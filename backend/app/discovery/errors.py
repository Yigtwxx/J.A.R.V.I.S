"""Discovery-specific exceptions.

Deliberately few: most failure modes are *reported* as a status on a result object
rather than raised, because a raised exception is exactly how the old pipeline
turned a blocked platform into a silently empty field.
"""

from __future__ import annotations


class DiscoveryError(Exception):
    """Base class for every discovery failure."""


class FetchLayerUnavailable(DiscoveryError):
    """A transport tier cannot be used at all (e.g. Camoufox is not installed).

    Callers degrade to a lower tier and report ``blocked`` — they must not crash.
    """


class BudgetExhausted(DiscoveryError):
    """A RoundBudget limit was hit. Carries the limit name for the termination reason."""

    def __init__(self, limit: str) -> None:
        super().__init__(f"discovery budget exhausted: {limit}")
        self.limit = limit


class SessionNotFound(DiscoveryError):
    """No live or persisted search session with the given id."""


class SessionNotAwaitingAnswer(DiscoveryError):
    """An answer arrived for a session that is not currently asking anything."""

    def __init__(self, session_id: str, status: str) -> None:
        super().__init__(f"session {session_id} is {status}, not awaiting an answer")
        self.session_id = session_id
        self.status = status

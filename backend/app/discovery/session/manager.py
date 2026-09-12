"""The registry of searches that are running right now.

A discovery run is launched with ``asyncio.create_task`` and outlives the HTTP
request that started it, so something has to hold the handle: the SSE endpoint
needs the bus, the answer endpoint needs to know the session is real, and
shutdown needs to stop everything. That something is this manager.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any

from app.discovery.session.bus import SessionEventBus
from app.utils.logger import logger


@dataclass(slots=True)
class LiveSession:
    """In-memory handle on one running search."""

    session_id: str
    target_key: str
    bus: SessionEventBus
    task: asyncio.Task[Any] | None = None
    status: str = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_live(self) -> bool:
        """Whether the session still holds in-memory state worth keeping.

        `running` is the only such state. Parking on a question does not change
        it — the loop is suspended *inside* the run and the pending future lives
        in `QuestionBroker._pending`, which is also what tells the answer endpoint
        "no such question" from "you answered the wrong one". A separate
        `awaiting_answer` status was listed here and assigned by nothing.
        """
        return self.status == "running"


class SessionManager:
    """Process-wide map of ``session_id`` to its live state."""

    def __init__(self) -> None:
        self._sessions: dict[str, LiveSession] = {}

    def create(self, session_id: str, target_key: str) -> LiveSession:
        existing = self._sessions.get(session_id)
        if existing is not None:
            logger.log_warning(f"SessionManager: session '{session_id}' recreated, replacing the previous handle")
        session = LiveSession(session_id=session_id, target_key=target_key, bus=SessionEventBus(session_id))
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> LiveSession | None:
        return self._sessions.get(session_id)

    def register_task(self, session_id: str, task: asyncio.Task[Any]) -> None:
        """Attach the discovery task and make its failure impossible to miss.

        An ``asyncio.Task`` that raises and is never awaited swallows the
        exception until it is garbage collected, which prints an "exception was
        never retrieved" warning to stderr — long after the endpoint returned an
        empty result. That is precisely the "the search silently produced
        nothing" failure this rewrite exists to eliminate, so the done-callback
        below observes the exception and logs it the moment it happens.
        """
        session = self._sessions.get(session_id)
        if session is None:
            logger.log_warning(f"SessionManager: register_task for unknown session '{session_id}'")
            return
        session.task = task
        task.add_done_callback(partial(self._on_task_done, session_id))

    def _on_task_done(self, session_id: str, task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            logger.log_warning(f"Discovery task for session '{session_id}' was cancelled")
            return
        exc = task.exception()
        if exc is not None:
            logger.log_error(f"Discovery task for session '{session_id}' crashed: {type(exc).__name__}: {exc}")
            session = self._sessions.get(session_id)
            if session is not None:
                session.status = "error"

    async def cancel(self, session_id: str) -> bool:
        """Request cancellation and close the stream. False if unknown."""
        session = self._sessions.get(session_id)
        if session is None:
            return False
        if session.task is not None and not session.task.done():
            session.task.cancel()
        session.status = "cancelled"
        await session.bus.close()
        logger.log_action("Discovery session cancelled", session_id)
        return True

    async def finish(self, session_id: str, status: str) -> None:
        """Mark the session terminal, close its bus and forget it."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        session.status = status
        await session.bus.close()

    def active(self) -> list[str]:
        return sorted(sid for sid, session in self._sessions.items() if session.is_live)

    async def close_all(self) -> None:
        """Shutdown hook: stop every search and release every stream."""
        for session_id in list(self._sessions):
            session = self._sessions.pop(session_id, None)
            if session is None:
                continue
            if session.task is not None and not session.task.done():
                session.task.cancel()
            session.status = "cancelled"
            await session.bus.close()

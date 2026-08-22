"""The run log: search sessions, platform verdicts, and questions asked.

Split out of ``store.py`` so neither file grows unreadable: this half records
*what the pipeline did*, ``store.py`` records *what it learned*. Both share the
plumbing in ``StoreBase``, which ``EvidenceStore`` inherits via ``JournalMixin``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.discovery import PlatformOutcome, SearchSession, UserAnswer
from app.utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.discovery.platforms.existence import ExistenceResult

_T = TypeVar("_T")

# These states hold in-memory state (question futures) that dies with the process.
_LIVE_STATUSES = ("running", "awaiting_answer")


class StoreBase:
    """Session handling shared by every discovery-table accessor.

    Two constraints shape it. **The loop outlives the request**: a deep search
    runs for many minutes after the HTTP handler returned, so a request-scoped
    ``db`` would be closed underneath us and each operation opens its own
    short-lived ``SessionLocal()`` instead. **SQLite writes block**: every call is
    pushed onto a worker thread with ``asyncio.to_thread``, because a synchronous
    commit on the event loop would stall every concurrent fetch in the pipeline.
    """

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def _run(self, fn: Callable[[Session], _T], default: _T, op: str) -> _T:
        """Execute ``fn`` in a fresh session, committing on success.

        Never raises. Losing one row is a bad outcome; killing a 20-minute search
        over it is a worse one, so failures are logged and degrade to ``default``.

        Opening the session is inside the try on purpose: if the database file is
        gone or locked, ``self._session_factory()`` is itself what raises, and that
        must degrade like any other failure rather than tear down the search.
        """
        session: Session | None = None
        try:
            session = self._session_factory()
            result = fn(session)
            session.commit()
            return result
        except Exception as exc:
            if session is not None:
                session.rollback()
            logger.log_error(f"EvidenceStore.{op} failed: {type(exc).__name__}: {exc}")
            return default
        finally:
            if session is not None:
                session.close()

    async def _call(self, fn: Callable[[Session], _T], default: _T, op: str) -> _T:
        return await asyncio.to_thread(self._run, fn, default, op)


class JournalMixin(StoreBase):
    """Session lifecycle, platform outcomes, and the question/answer trail."""

    # -- sessions -------------------------------------------------------------

    async def create_session(
        self,
        *,
        session_id: str,
        target_key: str,
        raw_query: str,
        entity_type: str,
        depth: int,
        interactive: bool,
    ) -> None:
        def _op(session: Session) -> None:
            session.add(
                SearchSession(
                    id=session_id,
                    target_key=target_key,
                    raw_query=raw_query,
                    entity_type=entity_type,
                    depth=depth,
                    interactive=interactive,
                    status="running",
                )
            )

        await self._call(_op, None, "create_session")

    async def update_session(self, session_id: str, **fields: Any) -> None:
        """Patch a session row. Unknown keys are ignored rather than fatal."""

        def _op(session: Session) -> None:
            row = session.get(SearchSession, session_id)
            if row is None:
                return
            for key, value in fields.items():
                if hasattr(row, key):
                    setattr(row, key, value)

        await self._call(_op, None, "update_session")

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        def _op(session: Session) -> dict[str, Any] | None:
            row = session.get(SearchSession, session_id)
            return _session_dict(row) if row is not None else None

        return await self._call(_op, None, "get_session")

    async def abandon_stale_sessions(self) -> int:
        """Mark every running/awaiting_answer session as abandoned.

        Called at app startup. The loop parks pending questions on in-memory
        futures, which die with the process, so any session still claiming to be
        live after a restart is a zombie that nothing will ever advance. Marking
        them keeps the history honest instead of leaving rows stuck at "running".
        """

        def _op(session: Session) -> int:
            result = session.execute(
                update(SearchSession)
                .where(SearchSession.status.in_(_LIVE_STATUSES))
                .values(
                    status="abandoned",
                    termination_reason="process_restart",
                    finished_at=datetime.now(UTC),
                )
            )
            return int(result.rowcount or 0)

        return await self._call(_op, 0, "abandon_stale_sessions")

    # -- platform outcomes ----------------------------------------------------

    async def record_platform_outcome(self, session_id: str, result: ExistenceResult) -> None:
        """Upsert one platform verdict, including ``blocked`` and ``not_found``.

        Every verdict is stored, never just the hits: ``blocked`` means "we were
        refused", which is neither presence nor absence, and dropping it would let
        the report imply an account does not exist when we never got to look.

        SQLite has no clean ORM-level upsert here, so this is SELECT-then-update
        against the ``uq_platform_outcome`` triple. A re-check of the same handle
        must overwrite rather than accumulate: the latest verdict is the true one.
        """

        def _op(session: Session) -> None:
            existing = session.execute(
                select(PlatformOutcome).where(
                    PlatformOutcome.session_id == session_id,
                    PlatformOutcome.platform == result.platform,
                    PlatformOutcome.username == result.username,
                )
            ).scalar_one_or_none()

            values: dict[str, Any] = {
                "status": str(result.verdict),
                "detail": result.detail,
                "signals": list(result.signals),
                "tier_used": str(result.tier_used),
                "checked_at": result.checked_at,
            }
            if existing is None:
                session.add(
                    PlatformOutcome(
                        session_id=session_id,
                        platform=result.platform,
                        username=result.username,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(existing, key, value)

        await self._call(_op, None, "record_platform_outcome")

    # -- questions and answers ------------------------------------------------

    async def record_question(
        self,
        session_id: str,
        target_key: str,
        *,
        question_id: str,
        kind: str,
        text: str,
        options: list[dict[str, Any]] | None,
    ) -> None:
        def _op(session: Session) -> None:
            session.add(
                UserAnswer(
                    session_id=session_id,
                    target_key=target_key,
                    question_id=question_id,
                    question_kind=kind,
                    question_text=text,
                    options_json=options,
                )
            )

        await self._call(_op, None, "record_question")

    async def record_answer(
        self,
        session_id: str,
        question_id: str,
        *,
        option_ids: list[str] | None,
        text: str | None,
        skipped: bool,
        timed_out: bool,
        unknown: bool,
    ) -> None:
        """Attach the reply to its question.

        ``skipped``, ``timed_out`` and ``unknown`` stay three separate flags: "I
        don't know" is information about the target, a timeout is only information
        about the user's attention, and collapsing them would lose that.
        """

        def _op(session: Session) -> None:
            row = session.execute(
                select(UserAnswer).where(
                    UserAnswer.session_id == session_id,
                    UserAnswer.question_id == question_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.answer_option_ids = option_ids
            row.answer_text = text
            row.skipped = skipped
            row.timed_out = timed_out
            row.unknown = unknown
            row.answered_at = datetime.now(UTC)

        await self._call(_op, None, "record_answer")

    async def load_answers(self, target_key: str) -> list[dict[str, Any]]:
        def _op(session: Session) -> list[dict[str, Any]]:
            stmt = select(UserAnswer).where(UserAnswer.target_key == target_key).order_by(UserAnswer.id)
            return [_answer_dict(r) for r in session.execute(stmt).scalars().all()]

        return await self._call(_op, [], "load_answers")


_SESSION_FIELDS = (
    "id",
    "target_key",
    "raw_query",
    "entity_type",
    "depth",
    "interactive",
    "status",
    "anchor_handle",
    "elected_cluster_id",
    "rounds_completed",
    "termination_reason",
    "started_at",
    "finished_at",
    "error",
    "result_json",
)


def _session_dict(row: SearchSession) -> dict[str, Any]:
    return {name: getattr(row, name) for name in _SESSION_FIELDS}


def _answer_dict(row: UserAnswer) -> dict[str, Any]:
    return {
        "session_id": row.session_id,
        "question_id": row.question_id,
        "question_kind": row.question_kind,
        "question_text": row.question_text,
        "options": row.options_json,
        "answer_option_ids": row.answer_option_ids,
        "answer_text": row.answer_text,
        "skipped": bool(row.skipped),
        "timed_out": bool(row.timed_out),
        "unknown": bool(row.unknown),
        "asked_at": row.asked_at,
        "answered_at": row.answered_at,
    }

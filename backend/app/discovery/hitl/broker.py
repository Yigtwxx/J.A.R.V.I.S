"""Parks a round on a question until a human answers it.

HOW THE PIPELINE "PAUSES"
-------------------------
:meth:`QuestionBroker.ask` creates an ``asyncio.Future`` and awaits it. Awaiting
suspends the round coroutine and hands control straight back to the event loop —
nothing spins, no thread is held, and no timer is polled. FastAPI keeps serving
every other request in the meantime, including the very endpoint that will
deliver the answer, which is what makes the whole design work: the request that
resumes the search is served by the same loop the search is parked on.

The wait is unbounded. Only two things end it: an answer, or
:meth:`cancel_session` tearing the search down. There used to be a third, a
120 s deadline that resolved the question as "I don't know" on the user's
behalf — cheap for us and expensive for them, since reading the question took
longer than that and the answer was the point of asking.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.discovery.hitl.questions import Answer, Question
from app.discovery.session.events import EventType, question_payload


class QuestionBroker:
    """Owns the pending question futures for every live session."""

    def __init__(self) -> None:
        # Keyed by (session_id, question_id). Question ids are derived from the
        # question's semantic hash, so two concurrent searches asking the same
        # thing produce the SAME id — the session_id in the key is the only
        # reason they cannot resolve each other's futures.
        self._pending: dict[tuple[str, str], asyncio.Future[Answer]] = {}

    async def ask(
        self,
        session_id: str,
        q: Question,
        *,
        bus: Any,
        store: Any,
        target_key: str,
    ) -> Answer:
        """Publish ``q``, suspend until it is answered, and persist the outcome."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Answer] = loop.create_future()
        key = (session_id, q.id)
        self._pending[key] = future

        try:
            await store.record_question(
                session_id,
                target_key,
                question_id=q.id,
                kind=str(q.kind),
                text=q.text,
                options=q.wire_options(),
            )
            await bus.publish(EventType.question, question_payload(q))

            # No deadline: the card stays on screen and this round stays parked
            # until a human decides. See the module docstring.
            answer = await future
            await bus.publish(
                EventType.answer_received,
                {
                    "question_id": q.id,
                    "kind": str(q.kind),
                    "option_ids": list(answer.option_ids),
                    "text": answer.text,
                    "unknown": answer.unknown,
                    "skipped": answer.skipped,
                },
            )

            # Recorded on every path, "I don't know" included: the persisted
            # history is only useful if it shows the questions nobody resolved.
            await store.record_answer(
                session_id,
                q.id,
                option_ids=list(answer.option_ids),
                text=answer.text,
                skipped=answer.skipped,
                timed_out=answer.timed_out,
                unknown=answer.unknown,
            )
            return answer
        finally:
            self._pending.pop(key, None)

    def resolve(self, session_id: str, answer: Answer) -> bool:
        """Deliver an answer. False for an unknown or already-resolved question.

        Called from a FastAPI handler that runs on the SAME event loop as the
        ``asyncio.create_task``-launched discovery task, so a bare ``set_result``
        is safe. If discovery ever moves to a worker thread or its own loop, this
        MUST become ``loop.call_soon_threadsafe(fut.set_result, answer)`` —
        setting a future's result from another thread is a data race that
        silently fails to wake the waiter.
        """
        future = self._pending.get((session_id, answer.question_id))
        if future is None or future.done():
            return False
        future.set_result(answer)
        return True

    def pending_for(self, session_id: str) -> list[str]:
        """Question ids this session is currently waiting on."""
        return sorted(qid for sid, qid in self._pending if sid == session_id)

    def cancel_session(self, session_id: str) -> None:
        """Cancel every pending question for a session that is going away.

        The awaiting ``ask`` sees a ``CancelledError``, which is correct: the
        search is being torn down, so there is no answer and no default to fall
        back on.
        """
        for key in [k for k in self._pending if k[0] == session_id]:
            future = self._pending.pop(key, None)
            if future is not None and not future.done():
                future.cancel()

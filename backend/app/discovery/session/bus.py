"""Fan-out of a session's events to every attached client.

One bus per search. The discovery loop publishes; zero or more SSE responses
subscribe. A subscriber that reads slowly must never be able to stall the search
or, worse, silently lose a frame the loop is waiting on an answer to.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.discovery.session.events import EventType, SearchEvent, utc_now_iso
from app.utils.logger import logger

# BACKPRESSURE RULE
# -----------------
# When a subscriber is over its high-water mark, only these two kinds may be
# dropped. They are pure telemetry: a missing progress tick makes a bar jump, a
# missing log line makes the console shorter, and the search is unaffected.
#
# Everything else is force-appended past the limit and is NEVER dropped. The
# load-bearing case is `question`: the round coroutine is suspended awaiting an
# answer, and the only thing that can produce that answer is a human who saw the
# question. Dropping it does not degrade the stream, it hangs the search until
# the question times out minutes later — and a timeout is "we still don't know",
# so the search then finishes on strictly less information than it had. The same
# reasoning applies to `anchor_changed` and `result_invalidated` (the client
# would keep rendering findings we have already retracted) and to `done` /
# `error` (the client would spin forever on a session that already ended).
# `browse_step` joins them for the same reason: a dropped frame makes the live
# view skip, while `browse_started` and `browse_finished` are what open and close
# the panel at all, and every count that matters is repeated in the latter.
_DROPPABLE: frozenset[EventType] = frozenset({EventType.progress, EventType.log, EventType.browse_step})


# eq=False keeps identity hashing, so subscribers can live in a set: two clients
# with the same (empty) queue are still two different clients.
@dataclass(slots=True, eq=False)
class _Subscriber:
    """One attached client.

    The queue is unbounded and ``capacity`` is enforced by hand. An
    ``asyncio.Queue(maxsize=...)`` would leave only two ways to handle a full
    queue for an undroppable event — block the publisher (one slow browser tab
    stalls the whole search) or reach into ``queue._queue`` — so the limit is
    kept as a soft high-water mark instead. ``put_nowait`` then never raises and
    never blocks, and forcing a critical event past the mark is a normal put.
    """

    queue: asyncio.Queue[SearchEvent | None] = field(default_factory=asyncio.Queue)
    capacity: int = 256
    dropped: int = 0

    def offer(self, event: SearchEvent) -> bool:
        """Enqueue ``event``. Returns False only when it was deliberately dropped."""
        if self.queue.qsize() >= self.capacity and event.type in _DROPPABLE:
            self.dropped += 1
            return False
        self.queue.put_nowait(event)
        return True

    def stop(self) -> None:
        self.queue.put_nowait(None)


class SessionEventBus:
    """Sequenced, replayable, multi-subscriber event fan-out for one session."""

    def __init__(self, session_id: str, *, ring_size: int = 500, queue_capacity: int = 256) -> None:
        self._session_id = session_id
        self._ring: deque[SearchEvent] = deque(maxlen=max(1, ring_size))
        self._subscribers: set[_Subscriber] = set()
        self._queue_capacity = max(1, queue_capacity)
        self._seq = 0
        self._closed = False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def last_seq(self) -> int:
        return self._seq

    async def publish(self, type: EventType, data: dict[str, Any]) -> SearchEvent:
        """Stamp, buffer and fan out one event.

        Publishing to a closed bus is a no-op that logs. A late event from a
        cleanup path must not raise into the loop's ``finally`` block and mask
        the real reason the session ended.
        """
        if self._closed:
            logger.log_warning(f"SessionEventBus[{self._session_id}]: dropped '{type}' — bus already closed")
            return SearchEvent(seq=self._seq, session_id=self._session_id, ts=utc_now_iso(), type=type, data=dict(data))

        self._seq += 1
        event = SearchEvent(
            seq=self._seq,
            session_id=self._session_id,
            ts=utc_now_iso(),
            type=type,
            data=dict(data),
        )
        self._ring.append(event)
        for subscriber in list(self._subscribers):
            subscriber.offer(event)
        return event

    def subscribe(self, *, last_event_id: int | None = None) -> AsyncIterator[SearchEvent]:
        """Attach a client, optionally replaying everything after ``last_event_id``.

        Registration happens here rather than on first iteration so that events
        published between ``subscribe()`` and the first ``__anext__`` are queued
        instead of lost.
        """
        subscriber = _Subscriber(capacity=self._queue_capacity)
        backlog = self.replay(last_event_id) if last_event_id is not None else []
        self._subscribers.add(subscriber)
        if self._closed:
            subscriber.stop()
        return self._iterate(subscriber, backlog)

    def replay(self, after_seq: int) -> list[SearchEvent]:
        """Buffered events strictly newer than ``after_seq``, oldest first.

        Anything older than the ring has been evicted; a client that fell that
        far behind gets the tail rather than an error, because a partial stream
        is more useful than none.
        """
        return [event for event in self._ring if event.seq > after_seq]

    async def close(self) -> None:
        """End the stream for every live subscriber."""
        if self._closed:
            return
        self._closed = True
        for subscriber in list(self._subscribers):
            subscriber.stop()

    async def _iterate(self, subscriber: _Subscriber, backlog: list[SearchEvent]) -> AsyncIterator[SearchEvent]:
        try:
            for event in backlog:
                yield event
            while True:
                item = await subscriber.queue.get()
                if item is None:  # close() sentinel — finish the iterator cleanly
                    return
                yield item
        finally:
            self._subscribers.discard(subscriber)

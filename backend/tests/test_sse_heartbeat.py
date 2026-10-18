"""A silent SSE stream is a stream something in the middle will cut.

Measured on 2026-08-29: Node's undici killed both live streams after exactly
300 s of silence (`UND_ERR_BODY_TIMEOUT`, `GET .../stream 500 in 304208ms`), and
the browser reported `TypeError: network error` for a search that was working.

The second test here is the one that matters most. The natural implementation of
a heartbeat — `asyncio.wait_for(anext(source), interval)` — cancels the source on
every idle tick, and a cancelled waiter on a queue is how an event that arrived
at that exact moment gets dropped. On this stream that event can be the
`question` the search is suspended on.
"""

import asyncio
import inspect

import pytest

from app.utils.sse import HEARTBEAT_FRAME, with_heartbeat


def run(coro):
    return asyncio.run(coro)


async def _collect(source, *, interval_s: float, limit: int) -> list[str]:
    out: list[str] = []
    async for frame in with_heartbeat(source, interval_s=interval_s):
        out.append(frame)
        if len(out) >= limit:
            break
    return out


def test_a_stream_that_says_nothing_still_sends_something():
    async def silent():
        await asyncio.sleep(3600)
        yield "never"  # pragma: no cover - the point is that it never arrives

    frames = run(_collect(silent(), interval_s=0.01, limit=3))

    assert frames == [HEARTBEAT_FRAME] * 3, f"got {frames!r}"


def test_an_event_arriving_during_a_heartbeat_wait_is_not_lost():
    """The data-loss hazard the implementation exists to avoid."""
    queue: asyncio.Queue[str] = asyncio.Queue()

    async def from_queue():
        while True:
            yield await queue.get()

    async def scenario() -> list[str]:
        out: list[str] = []
        stream = with_heartbeat(from_queue(), interval_s=0.01)
        # Let several heartbeats elapse first, so the source has been waiting
        # across more than one idle tick when the event finally lands.
        for _ in range(3):
            out.append(await anext(stream))

        await queue.put("event: question\ndata: {}\n\n")
        # Drain until the real event appears; heartbeats may interleave.
        for _ in range(20):
            frame = await anext(stream)
            out.append(frame)
            if frame != HEARTBEAT_FRAME:
                break
        await stream.aclose()
        return out

    frames = run(scenario())

    assert any("question" in frame for frame in frames), f"the event was swallowed by a heartbeat tick; got {frames!r}"


def test_source_frames_pass_through_unchanged_and_in_order():
    async def chatty():
        for index in range(4):
            yield f"data: {index}\n\n"

    frames = run(_collect(chatty(), interval_s=30.0, limit=4))

    assert frames == [f"data: {i}\n\n" for i in range(4)], f"got {frames!r}"


def test_the_stream_ends_when_the_source_does():
    async def brief():
        yield "data: only\n\n"

    async def scenario() -> list[str]:
        return [frame async for frame in with_heartbeat(brief(), interval_s=30.0)]

    assert run(scenario()) == ["data: only\n\n"]


def test_a_failing_source_still_surfaces_its_error():
    """A heartbeat must not turn a broken stream into a quiet one."""

    async def broken():
        yield "data: first\n\n"
        raise RuntimeError("upstream died")

    async def scenario() -> None:
        async for _ in with_heartbeat(broken(), interval_s=30.0):
            pass

    with pytest.raises(RuntimeError, match="upstream died"):
        run(scenario())


def test_closing_early_does_not_leave_the_source_waiting():
    started = asyncio.Event()

    async def slow():
        started.set()
        await asyncio.sleep(3600)
        yield "never"  # pragma: no cover

    async def scenario() -> None:
        stream = with_heartbeat(slow(), interval_s=0.01)
        assert await anext(stream) == HEARTBEAT_FRAME
        await stream.aclose()
        # A pending __anext__ left running would keep the subscriber registered
        # and the queue alive for the life of the process.
        await asyncio.sleep(0)

    run(scenario())
    assert started.is_set()


def test_both_live_endpoints_wrap_their_stream_in_the_heartbeat():
    """The wiring, not the helper.

    Asserted by inspecting the response rather than by reading the socket: these
    streams never end on their own, so a test that consumed one would have to
    decide when to stop and would hang if it decided wrong. What can regress here
    is someone returning the bare generator again — and that is visible from the
    response object itself.
    """
    from app.main import stream_status
    from app.routes.discovery import stream_search_session

    for endpoint in (stream_status, stream_search_session):
        source = inspect.getsource(endpoint)
        assert "with_heartbeat(" in source, f"{endpoint.__name__} streams a bare generator; a quiet phase will be cut"

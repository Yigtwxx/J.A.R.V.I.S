"""Keep-alive framing for Server-Sent Events.

A search can spend minutes in one phase without publishing anything — a stealth
fetch, an archive lookup, a browse task — and an SSE response that sends no bytes
for that long is indistinguishable from a dead one. Something in the middle
eventually agrees and cuts it.

Observed live on 2026-08-29, in ``logs/frontend.log``::

    [Error: failed to pipe response] {
      [cause]: [TypeError: terminated] {
        [cause]: [Error [BodyTimeoutError]: Body Timeout Error] {
          code: 'UND_ERR_BODY_TIMEOUT' } } }
    GET /api/proxy/api/search/sessions/<id>/stream 500 in 304208ms

304 s is Node's ``undici`` default ``bodyTimeout`` of 300 s: its fetch kills a
response body that goes five minutes without a chunk. The Next.js proxy relays
both streams with that fetch, so the browser saw ``TypeError: network error`` and
the console reported a failure in a search that was working perfectly.

The fix is the one SSE has always had for this: send a comment frame on idle.
A line beginning with ``:`` is ignored by every conformant reader — including
this project's own ``parseSseFrames``, which already skipped them long before the
server sent any.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

HEARTBEAT_FRAME = ": keep-alive\n\n"
"""An SSE comment. Carries no event, so no client state changes."""

HEARTBEAT_INTERVAL_S = 15.0
"""Comfortably under every timeout in the path, at two bytes a tick.

undici cuts a silent body at 300 s and nginx's ``proxy_read_timeout`` defaults to
60 s, so the interval has to clear the *smallest* of them with room for a slow
hop. Fifteen seconds is also short enough that a client notices a genuinely dead
connection in seconds rather than minutes.
"""


async def with_heartbeat(
    source: AsyncIterator[str],
    *,
    interval_s: float | None = None,
) -> AsyncIterator[str]:
    """Relay ``source``, emitting a keep-alive whenever it goes quiet.

    The pending ``__anext__`` is held across heartbeats and **never cancelled**.
    The obvious implementation — ``asyncio.wait_for(anext(...), interval)`` —
    cancels the source on every idle tick, and cancelling a waiter on a queue is
    exactly how an event that arrived at that instant gets dropped. On this
    stream a dropped event can be the ``question`` the search is suspended on,
    so the cost of that shortcut is a search that hangs until the question times
    out minutes later.
    """
    # Resolved here rather than as a default argument, which would bind the
    # module constant at import time and leave the interval unpatchable — and
    # therefore the wiring untestable without waiting fifteen real seconds.
    interval = HEARTBEAT_INTERVAL_S if interval_s is None else interval_s

    iterator = source.__aiter__()
    pending: asyncio.Task[str] | None = None

    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(iterator.__anext__())

            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                # The same task carries on waiting; nothing is cancelled and
                # nothing can be lost.
                yield HEARTBEAT_FRAME
                continue

            task, pending = pending, None
            try:
                frame = task.result()
            except StopAsyncIteration:
                return
            yield frame
    finally:
        # Client went away, or the generator was closed. The in-flight
        # `__anext__` has nobody left to deliver to.
        if pending is not None:
            pending.cancel()
            with contextlib.suppress(BaseException):
                await pending


__all__ = ["HEARTBEAT_FRAME", "HEARTBEAT_INTERVAL_S", "with_heartbeat"]

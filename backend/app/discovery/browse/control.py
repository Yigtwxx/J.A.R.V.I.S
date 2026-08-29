"""The Stop button, server side.

One flag per session, checked between browse steps. Shaped like
``QuestionBroker._pending`` (`hitl/broker.py`) and a process-wide singleton for
the same reason: the HTTP handler that raises the flag and the discovery task
that reads it must be looking at the same object, or Stop sets something nothing
reads.

Two deliberate simplifications:

* **A flag, not a cancellation.** Stopping the browse lets the search carry on
  through its remaining phases with everything already collected. Cancelling the
  task would throw that away, which is not what "stop showing me this" asks for.
* **No "is it browsing right now?" state.** Raising the flag before the phase
  starts simply means the phase stops on its first step. Tracking activity would
  add a race — between the round entering the phase and the request arriving —
  whose only product would be a spurious 409.
"""

from __future__ import annotations


class BrowseControl:
    """Which sessions have been asked to stop browsing."""

    def __init__(self) -> None:
        self._stopped: set[str] = set()

    def stop(self, session_id: str) -> None:
        """Ask a session to stop its current or next browse."""
        if session_id:
            self._stopped.add(session_id)

    def is_stopped(self, session_id: str) -> bool:
        return session_id in self._stopped

    def clear(self, session_id: str) -> None:
        """Forget a session. Called from the search's teardown."""
        self._stopped.discard(session_id)


__all__ = ["BrowseControl"]

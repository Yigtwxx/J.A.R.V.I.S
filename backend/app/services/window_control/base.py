"""What "move a window" means, independently of whose windows they are.

The spatial console needs four things from an operating system: what windows are
open, where they are, how to move one, and how to bring one to the front. Each
platform answers those with a completely different API, so the contract lives
here and the adapters in ``windows.py`` and ``darwin.py`` implement it.

Two rules run through the whole package:

**Nothing is ever silently empty.** Every operation reports an outcome. A window
that could not be moved because it belongs to an elevated process is ``blocked``,
which is a different fact from ``gone`` (it closed while we were talking about
it) and from ``ok``. The console shows which; it never leaves a card sitting
where the user did not put it with no explanation.

**An unsupported platform says so.** ``get_window_controller`` always returns a
controller. On a platform with no adapter it returns one that answers every call
with ``WindowControlUnsupported`` and a reason worth reading, rather than an
empty list that reads as "you have no windows open".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class WindowControlUnsupported(RuntimeError):
    """This platform has no adapter, or the OS refused us the permission it needs."""


class Outcome(StrEnum):
    """What happened to one window."""

    OK = "ok"
    #: The OS refused. Almost always an elevated window seen from a normal
    #: process, which no amount of retrying will fix.
    BLOCKED = "blocked"
    #: The window closed between being listed and being addressed.
    GONE = "gone"


@dataclass(frozen=True)
class WindowInfo:
    """One top-level window, in virtual-desktop pixels."""

    #: The OS handle, as a string. Valid only while this process is running.
    id: str
    #: Stable across restarts, unlike ``id``: this is what the browser stores so
    #: a window parked off the left edge yesterday is still there today.
    key: str
    title: str
    #: Executable basename, e.g. ``chrome.exe`` — what the card is labelled with.
    app: str
    x: int
    y: int
    width: int
    height: int
    minimized: bool


@dataclass(frozen=True)
class DesktopBounds:
    """The whole virtual desktop, which may span several monitors."""

    x: int
    y: int
    width: int
    height: int


@runtime_checkable
class WindowController(Protocol):
    """The four operations the spatial console needs from an OS."""

    @property
    def platform(self) -> str: ...

    def is_supported(self) -> bool:
        """False when this platform cannot be driven, or has not granted permission."""
        ...

    def unsupported_reason(self) -> str | None:
        """Why not, in words a user can act on. ``None`` when supported."""
        ...

    def desktop_bounds(self) -> DesktopBounds: ...

    def list_windows(self) -> list[WindowInfo]: ...

    def move(self, window_id: str, x: int, y: int, width: int, height: int) -> Outcome: ...

    def focus(self, window_id: str) -> Outcome: ...


_UNSAFE = re.compile(r"[^a-z0-9._-]+")


def stable_key(app: str, ordinal: int = 1) -> str:
    """An identity for a window that survives a restart.

    The OS handle cannot do this: it is a pointer, and a new one every launch.

    Neither can the title, which was the first thing tried here and is worse than
    it looks. A browser's title is its current page; an editor's is its current
    file. Keying on it means the Chrome card loses its place in the room every
    time the user changes tab — the exact opposite of what the key is for. And it
    would put page titles and file names, which can be anything, into the
    browser's local storage.

    So the key is the application, plus an ordinal when it has more than one
    window open. That is stable across restarts for the common case of one window
    per application, and for the uncommon case it is stable in the order the OS
    enumerates them — which can shuffle between sessions. The cost of a shuffle
    is two windows of the same application swapping places in the room, which the
    user can fix with one drag. The cost of the alternative was losing the layout
    several times a minute.
    """
    slug = _UNSAFE.sub("-", app.lower()).strip("-") or "unknown"
    return slug if ordinal <= 1 else f"{slug}#{ordinal}"


class UnsupportedController:
    """The honest answer on a platform with no adapter.

    Every method raises rather than returning nothing, because an empty window
    list is indistinguishable from a working system with nothing open — and the
    console would show a room with no windows in it and no reason why.
    """

    def __init__(self, platform_name: str, reason: str) -> None:
        self._platform = platform_name
        self._reason = reason

    @property
    def platform(self) -> str:
        return self._platform

    def is_supported(self) -> bool:
        return False

    def unsupported_reason(self) -> str | None:
        return self._reason

    def desktop_bounds(self) -> DesktopBounds:
        raise WindowControlUnsupported(self._reason)

    def list_windows(self) -> list[WindowInfo]:
        raise WindowControlUnsupported(self._reason)

    def move(self, window_id: str, x: int, y: int, width: int, height: int) -> Outcome:
        raise WindowControlUnsupported(self._reason)

    def focus(self, window_id: str) -> Outcome:
        raise WindowControlUnsupported(self._reason)

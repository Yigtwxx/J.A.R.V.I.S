"""Window control on macOS, through Quartz and the Accessibility API.

macOS splits the job in two, and the split is the reason this adapter looks the
way it does.

**Listing** goes through Quartz (``CGWindowListCopyWindowInfo``). It needs no
permission, sees every on-screen window, and reports each one's owner, title and
bounds.

**Moving** goes through the Accessibility API, which is the only public way to
place another application's window — and it is gated behind a permission the user
grants once, in System Settings, per application. Until they do,
``AXIsProcessTrusted`` is false and every write silently does nothing. That
silence is exactly the failure this package exists to avoid, so the permission is
checked up front and reported as an unsupported reason with the fix in it.

The two APIs do not share an identifier. A Quartz window number cannot be turned
into an accessibility element by any public call, so windows are matched by owner
process and then by title, falling back to geometry when an application has two
windows with the same name. That is what every public tool does; the private
``_AXUIElementGetWindow`` would be exact, and is not worth depending on.

Cannot be exercised on the Windows machine this was written on: it is covered by
unit tests against a fake Quartz layer, and is marked as not live-verified.
"""

from __future__ import annotations

import sys
from typing import Any

from app.services.window_control.base import (
    DesktopBounds,
    Outcome,
    WindowControlUnsupported,
    WindowInfo,
    stable_key,
)

_IS_DARWIN = sys.platform == "darwin"

#: Layer 0 is the ordinary application layer. Everything above it is the menu
#: bar, the Dock, notifications and screen-saver surfaces — none of which is a
#: window the user thinks of as open.
_NORMAL_LAYER = 0

#: Below this a "window" is a shadow helper or a status item, not something to
#: put in the room.
_MIN_EDGE = 60


#: Where the Accessibility symbols live depends on the pyobjc build: some ship
#: them in ApplicationServices, some re-export them from HIServices, and Quartz
#: carries a subset. Trying in order beats guessing, and beats a crash that names
#: the wrong missing package.
_AX_MODULES = ("ApplicationServices", "HIServices", "Quartz")


def _load_quartz() -> Any:
    """Import Quartz lazily, so this module imports fine on Windows."""
    import Quartz  # noqa: PLC0415 - deliberately deferred; absent on other platforms

    return Quartz


def _load_ax() -> Any:
    """The Accessibility API, from whichever module this pyobjc build put it in."""
    for name in _AX_MODULES:
        try:
            module = __import__(name)
        except ImportError:
            continue
        if hasattr(module, "AXIsProcessTrusted"):
            return module
    raise ImportError(
        "None of " + ", ".join(_AX_MODULES) + " exposes the Accessibility API. "
        "Install pyobjc-framework-ApplicationServices (see requirements.txt)."
    )


def _load_appkit() -> Any:
    import AppKit  # noqa: PLC0415 - deliberately deferred

    return AppKit


class DarwinController:
    """Drives real macOS windows."""

    platform = "darwin"

    def is_supported(self) -> bool:
        if not _IS_DARWIN:
            return False
        try:
            ax = _load_ax()
        except ImportError:
            return False
        return bool(ax.AXIsProcessTrusted())

    def unsupported_reason(self) -> str | None:
        if not _IS_DARWIN:
            return f"Window control needs macOS; this backend is running on {sys.platform}."
        try:
            ax = _load_ax()
        except ImportError as exc:
            return f"The macOS bindings are missing or incomplete: {exc}"
        if not ax.AXIsProcessTrusted():
            return (
                "macOS has not granted this application Accessibility permission, so it cannot move "
                "windows. Grant it in System Settings > Privacy & Security > Accessibility, then "
                "restart the backend."
            )
        return None

    # --- geometry ------------------------------------------------------------

    def desktop_bounds(self) -> DesktopBounds:
        """The union of every screen, so a multi-display setup is one room."""
        self._require()
        appkit = _load_appkit()

        screens = list(appkit.NSScreen.screens())
        if not screens:
            raise WindowControlUnsupported("macOS reported no screens.")

        main_height = screens[0].frame().size.height
        left = top = right = bottom = None
        for screen in screens:
            frame = screen.frame()
            # AppKit's origin is bottom-left; every other coordinate in this
            # package is top-left, so the y axis is flipped once, here.
            x0 = frame.origin.x
            y0 = main_height - (frame.origin.y + frame.size.height)
            x1 = x0 + frame.size.width
            y1 = y0 + frame.size.height

            left = x0 if left is None else min(left, x0)
            top = y0 if top is None else min(top, y0)
            right = x1 if right is None else max(right, x1)
            bottom = y1 if bottom is None else max(bottom, y1)

        return DesktopBounds(
            x=int(left or 0),
            y=int(top or 0),
            width=int((right or 0) - (left or 0)),
            height=int((bottom or 0) - (top or 0)),
        )

    # --- enumeration ---------------------------------------------------------

    def list_windows(self) -> list[WindowInfo]:
        self._require()
        quartz = _load_quartz()

        listed = quartz.CGWindowListCopyWindowInfo(
            quartz.kCGWindowListOptionOnScreenOnly | quartz.kCGWindowListExcludeDesktopElements,
            quartz.kCGNullWindowID,
        )

        windows: list[WindowInfo] = []
        # One counter per application, so a second window of the same app gets a
        # key of its own instead of overwriting the first one's place.
        seen: dict[str, int] = {}
        for entry in listed or []:
            info = self._describe(entry, seen)
            if info is not None:
                windows.append(info)
        return windows

    def _describe(self, entry: dict[str, Any], seen: dict[str, int]) -> WindowInfo | None:
        if entry.get("kCGWindowLayer", -1) != _NORMAL_LAYER:
            return None

        bounds = entry.get("kCGWindowBounds") or {}
        width = int(bounds.get("Width", 0))
        height = int(bounds.get("Height", 0))
        if width < _MIN_EDGE or height < _MIN_EDGE:
            return None

        owner = str(entry.get("kCGWindowOwnerName") or "").strip()
        pid = int(entry.get("kCGWindowOwnerPID", 0))
        number = int(entry.get("kCGWindowNumber", 0))
        if not owner or not pid or not number:
            return None

        # An untitled window is usually a palette or a sheet; the owner's name is
        # a better label than an empty string, and keeps the key stable.
        title = str(entry.get("kCGWindowName") or "").strip() or owner

        seen[owner] = seen.get(owner, 0) + 1

        return WindowInfo(
            id=f"{pid}:{number}",
            key=stable_key(owner, seen[owner]),
            title=title,
            app=owner,
            x=int(bounds.get("X", 0)),
            y=int(bounds.get("Y", 0)),
            width=width,
            height=height,
            # Quartz lists on-screen windows only, so anything here is not
            # minimized. AX would answer exactly, at the cost of a permission
            # prompt just to draw a list.
            minimized=False,
        )

    # --- manipulation --------------------------------------------------------

    def move(self, window_id: str, x: int, y: int, width: int, height: int) -> Outcome:
        self._require()
        quartz = _load_quartz()
        ax = _load_ax()

        element = self._element_for(window_id)
        if element is None:
            return Outcome.GONE

        point = ax.AXValueCreate(ax.kAXValueCGPointType, quartz.CGPoint(float(x), float(y)))
        size = ax.AXValueCreate(ax.kAXValueCGSizeType, quartz.CGSize(float(width), float(height)))

        # Size before position: a window clamped to a minimum size would
        # otherwise be re-centred by the window server after the move.
        size_result = ax.AXUIElementSetAttributeValue(element, ax.kAXSizeAttribute, size)
        move_result = ax.AXUIElementSetAttributeValue(element, ax.kAXPositionAttribute, point)

        if move_result == ax.kAXErrorSuccess and size_result == ax.kAXErrorSuccess:
            return Outcome.OK
        if ax.kAXErrorInvalidUIElement in (move_result, size_result):
            return Outcome.GONE
        # Everything else — a window the application has marked unresizable, or
        # one belonging to a process the sandbox will not let us touch.
        return Outcome.BLOCKED

    def focus(self, window_id: str) -> Outcome:
        """Raise the window and hand its application the keyboard.

        Both halves are needed: raising alone leaves the previous application
        owning the menu bar and the keyboard, so the window comes forward and
        typing still goes somewhere else.
        """
        self._require()
        ax = _load_ax()
        appkit = _load_appkit()

        element = self._element_for(window_id)
        if element is None:
            return Outcome.GONE

        raised = ax.AXUIElementPerformAction(element, ax.kAXRaiseAction)

        pid = self._pid_of(window_id)
        running = appkit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) if pid else None
        if running is not None:
            running.activateWithOptions_(appkit.NSApplicationActivateIgnoringOtherApps)

        if raised == ax.kAXErrorSuccess:
            return Outcome.OK
        if raised == ax.kAXErrorInvalidUIElement:
            return Outcome.GONE
        return Outcome.BLOCKED

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _pid_of(window_id: str) -> int | None:
        pid, _, _number = window_id.partition(":")
        try:
            return int(pid)
        except ValueError:
            return None

    def _element_for(self, window_id: str) -> Any | None:
        """Find the accessibility element for a Quartz window.

        There is no public call from a window number to an element, so the search
        is by owning process and then by title. When an application has two
        windows with the same title — two empty editor windows, say — geometry
        breaks the tie, which is the best a public API allows.
        """
        ax = _load_ax()

        pid = self._pid_of(window_id)
        if pid is None:
            return None

        target = self._quartz_entry(window_id)
        if target is None:
            return None

        app = ax.AXUIElementCreateApplication(pid)
        error, windows = ax.AXUIElementCopyAttributeValue(app, ax.kAXWindowsAttribute, None)
        if error != ax.kAXErrorSuccess or not windows:
            return None

        wanted_title = str(target.get("kCGWindowName") or "").strip()
        bounds = target.get("kCGWindowBounds") or {}

        fallback = None
        for element in windows:
            _err, title = ax.AXUIElementCopyAttributeValue(element, ax.kAXTitleAttribute, None)
            if wanted_title and str(title or "").strip() == wanted_title:
                return element
            if fallback is None and self._matches_bounds(ax, element, bounds):
                fallback = element

        return fallback or (windows[0] if len(windows) == 1 else None)

    def _quartz_entry(self, window_id: str) -> dict[str, Any] | None:
        quartz = _load_quartz()
        _pid, _, number = window_id.partition(":")
        try:
            wanted = int(number)
        except ValueError:
            return None

        listed = quartz.CGWindowListCopyWindowInfo(
            quartz.kCGWindowListOptionOnScreenOnly | quartz.kCGWindowListExcludeDesktopElements,
            quartz.kCGNullWindowID,
        )
        for entry in listed or []:
            if int(entry.get("kCGWindowNumber", 0)) == wanted:
                return entry
        return None

    @staticmethod
    def _matches_bounds(ax: Any, element: Any, bounds: dict[str, Any]) -> bool:
        """Within a few pixels: window servers round, and shadows shift edges."""
        error, value = ax.AXUIElementCopyAttributeValue(element, ax.kAXPositionAttribute, None)
        if error != ax.kAXErrorSuccess or value is None:
            return False

        ok, point = ax.AXValueGetValue(value, ax.kAXValueCGPointType, None)
        if not ok:
            return False
        return abs(point.x - float(bounds.get("X", 0))) <= 4 and abs(point.y - float(bounds.get("Y", 0))) <= 4

    def _require(self) -> None:
        reason = self.unsupported_reason()
        if reason is not None:
            raise WindowControlUnsupported(reason)

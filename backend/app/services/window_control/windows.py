"""Window control on Windows, through ``user32`` and ``dwmapi``.

Pure ``ctypes``, no new dependency. That is a deliberate match for
``app/services/app_launcher/windows.py``, which already reaches into
``ctypes`` and ``winreg`` for the same reason: everything needed here is a
handful of stable Win32 calls, and pulling in ``pywin32`` to make them would add
a compiled dependency to a backend that otherwise has none.

Three details are load-bearing and each of them is a bug if it is missed:

**The visible frame is not the window rect.** Since Vista, ``GetWindowRect``
includes an invisible resize border several pixels wide. Positioning by it puts
every window slightly up and to the left of where the user dropped it, and the
error grows with the DPI. ``DwmGetWindowAttribute`` reports the frame the user
can actually see, and moves are corrected by the difference.

**Cloaked windows are not open windows.** A UWP application that is suspended,
and every window on another virtual desktop, still passes ``IsWindowVisible``.
Listing them fills the room with cards for things the user cannot see.

**Foreground is not ours to take.** Windows refuses ``SetForegroundWindow`` from
a process that does not own the foreground, to stop applications stealing focus.
The documented way through is to attach to the foreground thread's input queue
first, which is what the shell itself does.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

from app.services.window_control.base import (
    DesktopBounds,
    Outcome,
    WindowControlUnsupported,
    WindowInfo,
    stable_key,
)

_IS_WINDOWS = sys.platform == "win32"

# Loaded lazily so this module can be imported (and unit-tested) anywhere.
if _IS_WINDOWS:  # pragma: no cover - exercised only on Windows
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi")
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:  # pragma: no cover - the import path taken by the test suite on CI
    _user32 = _dwmapi = _kernel32 = None  # type: ignore[assignment]

#: Per-monitor DPI aware, v2.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def _declare_dpi_aware() -> None:  # pragma: no cover - Windows only
    """Ask Windows to stop lying about coordinates.

    A process that has not declared DPI awareness is fed *scaled* numbers by
    ``GetSystemMetrics`` while DWM keeps reporting window frames in real pixels.
    On a 1920x1200 display at 125% that is 1536x960 against 1920x1200 — so the
    desktop the console thinks it is placing windows on is a quarter smaller than
    the one they land on, and everything drifts down and to the right, further
    the further right it goes.

    Three generations of API, newest first, because each one is available on a
    narrower range of Windows versions than the last. Failure is fine: it means
    something set awareness already, which is the state we wanted.
    """
    for attempt in (
        lambda: _user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2),
        lambda: ctypes.WinDLL("shcore").SetProcessDpiAwareness(2),
        lambda: _user32.SetProcessDPIAware(),
    ):
        try:
            if attempt():
                return
        except (AttributeError, OSError):
            continue


if _IS_WINDOWS:  # pragma: no cover - Windows only
    _declare_dpi_aware()

# --- Win32 constants ---------------------------------------------------------

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOREDIRECTIONBITMAP = 0x00200000

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

SW_RESTORE = 9

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_WINDOW_HANDLE = 1400

#: Shell surfaces that are technically top-level windows and never what the user
#: means by "my open applications".
_SHELL_TITLES = frozenset({"Program Manager", "Windows Input Experience", "Settings"})


def _enum_proc_type():  # pragma: no cover - Windows only
    return ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class WindowsController:
    """Drives real Windows windows."""

    platform = "win32"

    def is_supported(self) -> bool:
        return _IS_WINDOWS

    def unsupported_reason(self) -> str | None:
        if _IS_WINDOWS:
            return None
        return f"Window control needs Windows; this backend is running on {sys.platform}."

    # --- geometry ------------------------------------------------------------

    def desktop_bounds(self) -> DesktopBounds:
        """The whole virtual desktop, so a multi-monitor setup is one room.

        Measured rather than assumed: a second monitor to the left of the primary
        one puts the desktop origin at a negative x, and a console that assumed
        (0, 0) would park every window onto the wrong screen.
        """
        self._require()
        return DesktopBounds(
            x=_user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
            y=_user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
            width=_user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
            height=_user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
        )

    # --- enumeration ---------------------------------------------------------

    def list_windows(self) -> list[WindowInfo]:
        self._require()
        found: list[WindowInfo] = []
        # One counter per application, so a second Chrome window gets a key of
        # its own instead of overwriting the first one's place in the room.
        seen: dict[str, int] = {}

        @_enum_proc_type()
        def collect(hwnd: int, _param: int) -> bool:
            info = self._describe(hwnd, seen)
            if info is not None:
                found.append(info)
            return True

        _user32.EnumWindows(collect, 0)
        return found

    def _describe(self, hwnd: int, seen: dict[str, int]) -> WindowInfo | None:
        """One window, or ``None`` when it is not one the user would recognise."""
        if not _user32.IsWindowVisible(hwnd):
            return None

        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if not title or title in _SHELL_TITLES:
            return None

        ex_style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW:
            return None
        if self._is_cloaked(hwnd):
            return None

        rect = self._frame_rect(hwnd)
        if rect is None:
            return None

        left, top, right, bottom = rect
        app = self._app_of(hwnd)
        seen[app] = seen.get(app, 0) + 1

        return WindowInfo(
            id=str(hwnd),
            key=stable_key(app, seen[app]),
            title=title,
            app=app,
            x=left,
            y=top,
            width=max(0, right - left),
            height=max(0, bottom - top),
            minimized=bool(_user32.IsIconic(hwnd)),
        )

    def _is_cloaked(self, hwnd: int) -> bool:
        """Suspended UWP apps and other virtual desktops still look visible."""
        cloaked = wintypes.DWORD()
        result = _dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_CLOAKED),
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        return result == 0 and cloaked.value != 0

    def _frame_rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        """The frame the user can see, not the one with the invisible border."""
        rect = wintypes.RECT()
        result = _dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        # DWM off, or a window too young to have a frame yet: fall back to the
        # outer rect, which is at least the right order of magnitude.
        if result != 0 and not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return rect.left, rect.top, rect.right, rect.bottom

    def _app_of(self, hwnd: int) -> str:
        """The executable's basename, or ``unknown`` if the OS will not say."""
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return "unknown"

        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            # An elevated process refuses this to a normal one; the window is
            # still listed, and moving it will report `blocked` in its own right.
            return "unknown"
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return "unknown"
            return os.path.basename(buffer.value) or "unknown"
        finally:
            _kernel32.CloseHandle(handle)

    # --- manipulation --------------------------------------------------------

    def move(self, window_id: str, x: int, y: int, width: int, height: int) -> Outcome:
        """Put a window's *visible* frame at (x, y), sized (width, height).

        Corrected for the invisible border, so the frame lands where the user
        dropped the card rather than a few pixels up and to the left of it.
        """
        self._require()
        hwnd = self._handle(window_id)
        if hwnd is None:
            return Outcome.GONE

        self._restore_if_snapped(hwnd)

        outer = wintypes.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(outer)):
            return Outcome.GONE

        frame = self._frame_rect(hwnd)
        if frame is None:
            return Outcome.GONE

        pad_left = frame[0] - outer.left
        pad_top = frame[1] - outer.top
        pad_width = (outer.right - outer.left) - (frame[2] - frame[0])
        pad_height = (outer.bottom - outer.top) - (frame[3] - frame[1])

        ctypes.set_last_error(0)
        moved = _user32.SetWindowPos(
            wintypes.HWND(hwnd),
            None,
            int(x - pad_left),
            int(y - pad_top),
            int(width + pad_width),
            int(height + pad_height),
            # Never activates: dragging a card must not steal the keyboard from
            # whatever the user is typing into.
            SWP_NOZORDER | SWP_NOACTIVATE,
        )
        if moved:
            return Outcome.OK
        return self._classify(hwnd)

    def focus(self, window_id: str) -> Outcome:
        """Bring a window to the front and give it the keyboard.

        Windows refuses a bare ``SetForegroundWindow`` from a process that does
        not already own the foreground. Attaching to the foreground thread's
        input queue for the duration is the documented way round it, and the
        attachment is always undone — leaving it in place ties our message queue
        to another application's for as long as the process lives.
        """
        self._require()
        hwnd = self._handle(window_id)
        if hwnd is None:
            return Outcome.GONE

        self._restore_if_snapped(hwnd)

        foreground = _user32.GetForegroundWindow()
        target_thread = _user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = _kernel32.GetCurrentThreadId()
        foreground_thread = _user32.GetWindowThreadProcessId(foreground, None) if foreground else 0

        attached = False
        if foreground_thread and foreground_thread != current_thread:
            attached = bool(_user32.AttachThreadInput(current_thread, foreground_thread, True))
        try:
            ctypes.set_last_error(0)
            if _user32.SetForegroundWindow(hwnd):
                return Outcome.OK
            # Best effort: BringWindowToTop still raises it visually even when
            # the shell will not hand over the keyboard.
            if _user32.BringWindowToTop(hwnd):
                return Outcome.OK
            return self._classify(hwnd)
        finally:
            if attached:
                _user32.AttachThreadInput(current_thread, foreground_thread, False)
            # Nothing to unwind for the target thread: it was never attached.
            _ = target_thread

    # --- helpers -------------------------------------------------------------

    def _restore_if_snapped(self, hwnd: int) -> bool:
        """Un-maximize or un-minimize a window so it can actually be placed.

        Found by moving a real window and asking the OS where it ended up.
        ``SetWindowPos`` on a maximized window returns TRUE and then does
        nothing — the window manager snaps it straight back to filling the
        screen — so the move reported ``ok`` while the window had not moved,
        which is the single thing this package promises never to do. A minimized
        window has no meaningful position at all.

        Restoring first is also what dragging a maximized window by its title
        bar does, so it is what the gesture should mean anyway.
        """
        if not (_user32.IsZoomed(hwnd) or _user32.IsIconic(hwnd)):
            return False
        _user32.ShowWindow(hwnd, SW_RESTORE)
        return True

    def _handle(self, window_id: str) -> int | None:
        try:
            hwnd = int(window_id)
        except ValueError:
            return None
        return hwnd if _user32.IsWindow(hwnd) else None

    def _classify(self, hwnd: int) -> Outcome:
        """Turn the last Win32 error into an outcome worth showing."""
        error = ctypes.get_last_error()
        if error == ERROR_INVALID_WINDOW_HANDLE or not _user32.IsWindow(hwnd):
            return Outcome.GONE
        if error == ERROR_ACCESS_DENIED:
            return Outcome.BLOCKED
        # An elevated window usually fails with no error set at all, which is
        # indistinguishable from refusal — and refusal is the useful thing to
        # tell the user, because it names the one fix that works.
        return Outcome.BLOCKED

    def _require(self) -> None:
        if not _IS_WINDOWS:
            raise WindowControlUnsupported(self.unsupported_reason() or "Window control is unavailable.")

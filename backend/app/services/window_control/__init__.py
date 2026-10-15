"""Pick the window controller for whatever this backend is running on.

Same shape as ``app/services/app_launcher``: a protocol, one adapter per
platform, and a cached dispatch that always returns *something*. A platform with
no adapter gets `UnsupportedController`, which raises with a reason rather than
answering an empty list — an empty list is indistinguishable from a working
machine with nothing open, and the console would show a room with no windows in
it and nothing to say about why.
"""

from __future__ import annotations

import sys
from functools import lru_cache

from app.services.window_control.base import (
    DesktopBounds,
    Outcome,
    UnsupportedController,
    WindowController,
    WindowControlUnsupported,
    WindowInfo,
    stable_key,
)

__all__ = [
    "DesktopBounds",
    "Outcome",
    "WindowController",
    "WindowControlUnsupported",
    "WindowInfo",
    "get_window_controller",
    "stable_key",
]


@lru_cache(maxsize=1)
def get_window_controller() -> WindowController:
    """The controller for this platform. Cached: adapters are stateless."""
    if sys.platform == "win32":
        from app.services.window_control.windows import WindowsController  # noqa: PLC0415 - platform-gated

        return WindowsController()

    if sys.platform == "darwin":
        from app.services.window_control.darwin import DarwinController  # noqa: PLC0415 - platform-gated

        return DarwinController()

    return UnsupportedController(
        sys.platform,
        f"The spatial console can move real windows on Windows and macOS. This backend is running on "
        f"{sys.platform}, where it has no way to reach them — the room, the hands and the panels all "
        f"still work.",
    )

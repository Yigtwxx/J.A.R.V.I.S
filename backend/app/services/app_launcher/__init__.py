"""Find the applications installed on this machine, and start one by name.

This replaces a hand-written alias table that mapped a slug to an argv list. The
table could not work and had never worked: ``"spotify": ["spotify"]`` needed
``spotify`` on PATH, which it is not on any machine, and ``"browser": ["start",
"msedge"]`` named a shell builtin that ``shell=False`` can never find. Discord
was absent. Worse, the table encoded one author's machine, so a fresh clone found
nothing of the new user's own software.

Discovery answers that: each platform enumerates what the desktop itself knows
about, the user's text is matched against *that*, and only a target this module
produced is ever handed to the OS. The typed string never becomes part of a
command line, which is the same posture ``normalize_url`` holds for links.

Discovery is blocking I/O, so callers use :func:`discover_apps` from a thread.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from collections.abc import Sequence
from types import ModuleType

from app.services.app_launcher.matching import merge_executable_aliases, resolve, suggest
from app.services.app_launcher.models import AppEntry, AppLaunchError, MatchResult, normalize_app_name
from app.utils.logger import logger

__all__ = [
    "AppEntry",
    "AppLaunchError",
    "MatchResult",
    "discover_apps",
    "launch_app",
    "normalize_app_name",
    "resolve_app",
    "suggest_apps",
    "unavailable_reason",
]

CACHE_TTL_SECONDS = 300.0
"""How long a discovery result is reused.

The directory walk is cheap (about 5 ms warm), but the *first* touch of those
files after boot is not - a filesystem filter driver made it 3.3 seconds on one
measured machine. Without a cache the first "open Spotify" of the day would look
broken, so the cost is paid once per five minutes instead of once per request.
"""

_cache: tuple[float, tuple[AppEntry, ...]] | None = None
_lock = threading.Lock()
"""Held across the scan: FastAPI runs sync work in a threadpool, and ten
concurrent requests must not each pay the cold scan."""


def _backend() -> ModuleType | None:
    """The platform implementation, imported lazily.

    Lazily because each back-end imports things that only exist on its own
    platform - ``winreg`` most obviously - so a module-level import would break
    the whole service everywhere else.
    """
    if sys.platform == "win32":
        from app.services.app_launcher import windows

        return windows
    if sys.platform == "darwin":
        from app.services.app_launcher import darwin

        return darwin
    if sys.platform.startswith("linux"):
        from app.services.app_launcher import linux

        return linux
    return None


def discover_apps(*, refresh: bool = False) -> tuple[AppEntry, ...]:
    """Applications installed on this machine. Blocking; call it in a thread."""
    global _cache
    with _lock:
        now = time.monotonic()
        if not refresh and _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
            return _cache[1]

        backend = _backend()
        if backend is None:
            logger.log_warning(f"App discovery is not implemented for {sys.platform}", broadcast=False)
            _cache = (now, ())
            return ()
        try:
            entries = tuple(merge_executable_aliases(backend.enumerate_apps()))
        except Exception as exc:
            # Discovery reads a lot of foreign data - registries, plists, ini
            # files. One unreadable corner must not take the panel down.
            logger.log_warning(f"App discovery failed: {type(exc).__name__}: {exc}", broadcast=False)
            entries = ()
        _cache = (now, entries)
        return entries


async def discover_apps_async(*, refresh: bool = False) -> tuple[AppEntry, ...]:
    """:func:`discover_apps` off the event loop."""
    return await asyncio.to_thread(discover_apps, refresh=refresh)


def resolve_app(query: str, *, entries: Sequence[AppEntry] | None = None) -> MatchResult:
    """Match ``query`` against what is installed. Never guesses between equals."""
    return resolve(query, entries if entries is not None else discover_apps())


def suggest_apps(query: str, *, limit: int = 12, refresh: bool = False) -> list[AppEntry]:
    """Applications to offer while the user is typing."""
    return suggest(query, discover_apps(refresh=refresh), limit=limit)


def launch_app(entry: AppEntry) -> None:
    """Start a *discovered* application. Raises :class:`AppLaunchError` on failure."""
    backend = _backend()
    if backend is None:
        raise AppLaunchError(f"Launching applications is not supported on {sys.platform}.")
    backend.launch(entry)


def unavailable_reason() -> str:
    """Why nothing was discovered, phrased for the person reading the panel."""
    backend = _backend()
    if backend is None:
        return f"Launching applications is not supported on {sys.platform}."
    return backend.describe_unavailable()

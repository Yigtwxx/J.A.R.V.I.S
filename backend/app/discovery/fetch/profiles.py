"""Reusable browser profile directories.

Scrapling's stealth session defaults to a throwaway user-data directory, so every
search met every host as a browser that had never existed before: no Cloudflare
clearance, no consent cookie, no local storage. That is the fingerprint of a
freshly-provisioned bot, and it also means paying the challenge-solving cost once
per search forever.

Persisting the directory fixes both. The constraint is that Chromium takes an
exclusive lock on a user-data directory, so directories cannot simply be shared:
this pool leases one at a time, sized to the same limit that caps concurrent
browsers, so a lease is always available exactly when a browser slot is.

Profiles hold anonymous browsing state only — no account is ever signed in — and
live under ``backend/data/``, which is already gitignored.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from app.utils.logger import logger

# Where relative profile roots resolve from: backend/. __file__ is
# backend/app/discovery/fetch/profiles.py, so four parents up is backend/.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class BrowserProfilePool:
    """Hands out user-data directories, one holder at a time.

    Holds paths and a lock — never a browser — which is what makes it safe to keep
    as a process-wide singleton (see ``app/discovery/dependencies.py``).
    """

    def __init__(self, *, root: str, size: int, persist: bool = True) -> None:
        self._root = Path(root) if Path(root).is_absolute() else _BACKEND_ROOT / root
        self._size = max(1, size)
        self._persist = persist
        self._free: list[Path] | None = None
        self._lock = asyncio.Lock()

    @property
    def persistent(self) -> bool:
        return self._persist

    async def lease(self) -> Path | None:
        """Reserve a profile directory, or None to let Scrapling use a temp one.

        Returning None rather than raising is deliberate: a profile is an
        optimisation, and a filesystem problem must degrade to the old behaviour
        instead of costing the search its browser tier.
        """
        if not self._persist:
            return None
        async with self._lock:
            try:
                if self._free is None:
                    self._free = self._provision()
                return self._free.pop() if self._free else None
            except OSError as exc:
                logger.log_warning(
                    f"Browser profile pool unavailable ({exc}); using throwaway profiles",
                    broadcast=False,
                )
                self._persist = False
                return None

    async def release(self, path: Path | None) -> None:
        """Return a leased directory to the pool. Safe with None and with duplicates."""
        if path is None:
            return
        async with self._lock:
            if self._free is None:
                self._free = []
            if path not in self._free:
                self._free.append(path)

    async def evict(self, path: Path | None) -> None:
        """Delete a directory that a browser refused to start against, then re-add it.

        A corrupt or stale-locked profile would otherwise poison every later
        search that leased it.
        """
        if path is None:
            return
        async with self._lock:
            try:
                shutil.rmtree(path, ignore_errors=True)
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.log_warning(f"Could not reset browser profile {path.name}: {exc}", broadcast=False)
                return
            if self._free is None:
                self._free = []
            if path not in self._free:
                self._free.append(path)

    def _provision(self) -> list[Path]:
        """Create the directories on first use. Raises OSError, handled by ``lease``."""
        self._root.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for index in range(self._size):
            path = self._root / f"profile-{index}"
            path.mkdir(parents=True, exist_ok=True)
            paths.append(path)
        return paths

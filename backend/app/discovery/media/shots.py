"""Where browse frames live so the console can show them.

Modelled on :mod:`app.discovery.media.store`, and deliberately **not** sharing
its directory. ``AvatarStore`` keeps every image for ever, which is right: an
avatar is a finding. A frame is telemetry — a dozen or more per task at ~80 KB
— so storing them the same way would be a slow disk leak rather than a wart.
Hence a per-session directory, a TTL, a file cap, and an explicit purge the
runner calls when a search ends.

Frames go to disk rather than into the event payload because base64 in the
stream would pin tens of megabytes per session in the bus replay ring *and* in
every subscriber queue, on an event type that then could not be dropped.
"""

from __future__ import annotations

import io
import os
import re
import time
from pathlib import Path

from app.utils.logger import logger

_DEFAULT_ROOT = Path("data/browse_frames")
PUBLIC_PREFIX = "/api/media/frames"

_SAFE_SESSION = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")
_SAFE_NAME = re.compile(r"^\d{1,4}\.jpg$")
"""Both halves of the path are allow-listed before anything touches the disk.
A session id reaches this module from a URL, so it is untrusted input in exactly
the way a filename is."""


class FrameStore:
    """Saves and serves the screenshots one browse task produced."""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        *,
        max_edge: int = 1024,
        quality: int = 60,
        ttl_seconds: int = 3600,
        max_files: int = 500,
    ) -> None:
        self._root = Path(root) if root is not None else _DEFAULT_ROOT
        self._max_edge = max(320, max_edge)
        self._quality = max(30, min(95, quality))
        self._ttl_seconds = max(60, ttl_seconds)
        """Floored, because a TTL shorter than a minute would delete frames while
        the panel is still fetching them — a configuration that cannot work,
        rather than one that merely trims hard."""

        self._max_files = max(1, max_files)
        """Not floored the same way: a small cap is unusual but coherent, and
        silently substituting a larger number for the one in the settings would
        make the configuration a lie."""

    @property
    def root(self) -> Path:
        return self._root

    # -- writing -------------------------------------------------------------

    def save(self, session_id: str, step: int, data: bytes) -> str:
        """Write one frame and return its public path, or ``""`` on any failure.

        Never raises: a frame that will not save is a picture the user does not
        see, and that must not be allowed to end a search.
        """
        if not data or not _SAFE_SESSION.match(session_id or ""):
            return ""
        try:
            folder = self._root / session_id
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{max(0, min(9999, int(step)))}.jpg"
            payload = self.shrink(data)

            # Same atomic write as AvatarStore: a half-written frame must never
            # be served, and the UI polls these as soon as the event arrives.
            target = folder / name
            temp = folder / f"{name}.{os.getpid()}.tmp"
            temp.write_bytes(payload)
            os.replace(temp, target)
            return f"{PUBLIC_PREFIX}/{session_id}/{name}"
        except Exception as exc:
            logger.log_warning(f"Browse frame not saved: {exc}", broadcast=False)
            return ""

    def shrink(self, data: bytes) -> bytes:
        """Shrink to the long edge the model and the panel both use.

        Public because the *model* needs it too, and that was the bug: the agent
        handed the policy the raw screenshot and only the disk copy was shrunk.
        A headless Chromium here renders at device-scale 2, so a 1280x800
        viewport produces a 2560x1600 frame — 133 KB of JPEG, 178 KB once
        base64-encoded — and ollama answered **HTTP 400** to every such request.
        Three refusals in a row retired the model, so the panel opened, showed a
        blank frame and never took a step. Measured 2026-08-29: the same call
        with a 1024-wide frame (38 KB) succeeds.

        One size serves both on purpose: the panel renders at roughly 360 px and
        the model does not benefit from more, so a second encode would buy
        nothing and cost a Pillow pass per step.
        """
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                image = image.convert("RGB")
                if max(image.size) > self._max_edge:
                    ratio = self._max_edge / max(image.size)
                    image = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))))
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=self._quality, optimize=True)
                return buffer.getvalue()
        except Exception as exc:
            # The browser already produced a JPEG; storing it unshrunk is a worse
            # frame, not a missing one.
            logger.log_warning(f"Browse frame not downscaled: {exc}", broadcast=False)
            return data

    # -- reading -------------------------------------------------------------

    def resolve(self, session_id: str, name: str) -> Path | None:
        """The file behind a public path, or ``None``.

        Two independent barriers, the same pair ``AvatarStore.resolve`` uses:
        an allow-list on each path segment, then a real ``relative_to`` check
        after resolution, which also catches a symlink pointing out of the tree.
        """
        if not _SAFE_SESSION.match(session_id or "") or not _SAFE_NAME.match(name or ""):
            return None
        try:
            root = self._root.resolve()
            candidate = (root / session_id / name).resolve()
            candidate.relative_to(root)
        except (OSError, ValueError):
            return None
        return candidate if candidate.is_file() else None

    # -- housekeeping --------------------------------------------------------

    def purge(self, session_id: str) -> int:
        """Delete one session's frames. Returns how many files went."""
        if not _SAFE_SESSION.match(session_id or ""):
            return 0
        folder = self._root / session_id
        removed = 0
        try:
            if not folder.is_dir():
                return 0
            for path in folder.iterdir():
                if path.is_file():
                    path.unlink(missing_ok=True)
                    removed += 1
            folder.rmdir()
        except OSError as exc:
            logger.log_warning(f"Browse frames not fully purged: {exc}", broadcast=False)
        return removed

    def sweep(self) -> int:
        """Drop frames past the TTL, then oldest-first down to the file cap.

        A backstop for the sessions that never reached their ``finally`` — a
        killed process, a crashed task. Without it the directory only ever grows.
        """
        removed = 0
        try:
            if not self._root.is_dir():
                return 0
            files = [p for p in self._root.rglob("*.jpg") if p.is_file()]
        except OSError:
            return 0

        cutoff = time.time() - self._ttl_seconds
        survivors: list[tuple[float, Path]] = []
        for path in files:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
            else:
                survivors.append((mtime, path))

        if len(survivors) > self._max_files:
            survivors.sort()
            for _, path in survivors[: len(survivors) - self._max_files]:
                path.unlink(missing_ok=True)
                removed += 1

        self._prune_empty_dirs()
        return removed

    def _prune_empty_dirs(self) -> None:
        try:
            for folder in self._root.iterdir():
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
        except OSError:  # pragma: no cover - housekeeping is best effort
            pass


__all__ = ["PUBLIC_PREFIX", "FrameStore"]

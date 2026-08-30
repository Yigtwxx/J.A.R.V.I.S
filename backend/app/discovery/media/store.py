"""Content-addressed on-disk store for downloaded avatars.

**Why the bytes are downloaded instead of the URL being linked.** Instagram and
TikTok serve avatars from signed CDN URLs (``…&_nc_sid=…&oe=<expiry>``) that stop
resolving within hours, so a stored link renders as a broken image the moment the
user reopens the report. Two more reasons make downloading the obviously right
call:

* The sha256 and dhash scoring signals become free — we already hold the bytes,
  so "the same picture appears on both accounts" costs nothing extra.
* It avoids adding an image-proxy endpoint. A ``/api/media/proxy?url=…`` route is
  a textbook SSRF hole; serving a fixed, content-addressed filename from our own
  directory has no attacker-controlled destination at all.

Storage is content-addressed by sha256, so the same picture found on five
platforms is one file on disk. Nothing here trusts the server: the payload is
verified by magic bytes (``Content-Type`` is advisory and routinely wrong), size
is capped, and ``resolve`` only ever accepts a ``<sha256>.<ext>`` basename that
stays inside the store root.
"""

from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.discovery.media.hashing import dhash64, image_dimensions, sha256_bytes
from app.discovery.types import EvidenceKind
from app.utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover - import kept out of the runtime path
    from app.discovery.fetch.session import FetchSession

EVIDENCE_KIND = EvidenceKind.AVATAR
"""What a stored avatar asserts when it is turned into evidence."""

_DEFAULT_ROOT = Path("data/avatars")
_MAX_BYTES = 8 * 1024 * 1024
_PUBLIC_PREFIX = "/api/media/avatars"

# Basenames the media route may serve. Anything else — traversal, absolute paths,
# a valid digest with a bogus extension — is refused before touching the disk.
_SAFE_NAME = re.compile(r"^[0-9a-f]{64}\.(?:jpg|png|gif|webp)$")


@dataclass(frozen=True, slots=True)
class StoredAvatar:
    """One avatar that is now on our disk, with everything needed to score it."""

    sha256: str
    dhash: str
    path: Path
    local_url: str
    source_url: str
    platform: str
    username: str
    width: int | None
    height: int | None
    bytes_len: int
    content_type: str


class AvatarStore:
    """Downloads, verifies and de-duplicates avatar images."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else _DEFAULT_ROOT

    @property
    def root(self) -> Path:
        return self._root

    async def save(
        self,
        fetch: FetchSession,
        url: str,
        *,
        platform: str,
        username: str,
    ) -> StoredAvatar | None:
        """Download ``url`` and store it. Returns None on any failure; never raises.

        A repeat of an image already on disk is not re-written — the digest is the
        filename, so the second call simply describes the existing file.
        """
        target = (url or "").strip()
        if not target:
            return None

        try:
            result, raw = await fetch.get_bytes(target)
        except Exception as exc:
            logger.log_warning(f"Avatar download raised for {platform}:{username}: {type(exc).__name__}: {exc}")
            return None

        if not raw:
            logger.log_warning(f"Avatar unavailable for {platform}:{username} — {result.describe()}")
            return None
        if len(raw) > _MAX_BYTES:
            logger.log_warning(f"Avatar rejected for {platform}:{username} — {len(raw)} bytes exceeds the 8 MB cap")
            return None

        sniffed = sniff_image(raw)
        if sniffed is None:
            # Almost always an HTML error page or a JSON body served with an
            # image Content-Type. Trusting the header here is how junk gets stored.
            logger.log_warning(f"Avatar rejected for {platform}:{username} — payload is not a recognised image")
            return None
        extension, content_type = sniffed

        digest = sha256_bytes(raw)
        path = self.path_for(digest, extension)
        if not path.exists() and not self._write(path, raw):
            return None

        dimensions = image_dimensions(raw)
        return StoredAvatar(
            sha256=digest,
            dhash=dhash64(raw),
            path=path,
            local_url=f"{_PUBLIC_PREFIX}/{digest}.{extension}",
            source_url=result.final_url or target,
            platform=platform,
            username=username,
            width=dimensions[0] if dimensions else None,
            height=dimensions[1] if dimensions else None,
            bytes_len=len(raw),
            content_type=content_type,
        )

    def save_bytes(
        self,
        raw: bytes,
        *,
        platform: str = "user",
        username: str = "reference",
        source_url: str = "",
    ) -> StoredAvatar | None:
        """Store bytes we already hold. Returns None on any failure; never raises.

        The upload path for a reference photo. It is the second half of
        :meth:`save` with the download removed, and it repeats every check that
        one makes for the same reason: the cap, and above all the magic-byte
        sniff. A browser will happily send an HTML error page or a PDF with an
        ``image/jpeg`` content type, and trusting the header is how junk gets a
        digest and a public URL.

        Synchronous on purpose - there is no I/O to await beyond one small write,
        and callers on the event loop should hand it to a thread if the file is
        large.
        """
        if not raw:
            return None
        if len(raw) > _MAX_BYTES:
            logger.log_warning(f"Image rejected for {platform}:{username} - {len(raw)} bytes exceeds the 8 MB cap")
            return None

        sniffed = sniff_image(raw)
        if sniffed is None:
            logger.log_warning(f"Image rejected for {platform}:{username} - payload is not a recognised image")
            return None
        extension, content_type = sniffed

        digest = sha256_bytes(raw)
        path = self.path_for(digest, extension)
        if not path.exists() and not self._write(path, raw):
            return None

        dimensions = image_dimensions(raw)
        return StoredAvatar(
            sha256=digest,
            dhash=dhash64(raw),
            path=path,
            local_url=f"{_PUBLIC_PREFIX}/{digest}.{extension}",
            source_url=source_url,
            platform=platform,
            username=username,
            width=dimensions[0] if dimensions else None,
            height=dimensions[1] if dimensions else None,
            bytes_len=len(raw),
            content_type=content_type,
        )

    def path_for(self, sha256: str, ext: str = "jpg") -> Path:
        """Where an image with this digest lives. Does not touch the disk."""
        return self._root / f"{sha256}.{ext}"

    def resolve(self, sha_with_ext: str) -> Path | None:
        """Map a public basename onto a real file, or None.

        This is the media route's only entry point, so it is written to be
        boring: an allow-list regex on the basename, then a ``resolve()``
        containment check as a second, independent barrier against traversal
        (``..``), absolute paths and symlinks that point outside the store.
        """
        name = (sha_with_ext or "").strip()
        if not name or not _SAFE_NAME.match(name):
            return None

        root = self._root.resolve()
        candidate = (root / name).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def _write(self, path: Path, raw: bytes) -> bool:
        """Write atomically so a partial download is never served. False on failure."""
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(raw)
            os.replace(temporary, path)
        except OSError as exc:
            logger.log_warning(f"Avatar write failed for {path.name}: {exc}")
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            return False
        return True


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """``(extension, content_type)`` from magic bytes, or None when not an image.

    ``Content-Type`` is deliberately ignored: CDNs mislabel avatars constantly, and
    an attacker-controlled header is not a fact about the payload.
    """
    if not data or len(data) < 12:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "png", "image/png"
    if data.startswith(b"GIF8"):
        return "gif", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None

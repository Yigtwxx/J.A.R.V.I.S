"""Wayback Machine recovery for profiles that are gone or walled off.

**Archive data never turns a NOT_FOUND verdict into EXISTS.** A deleted profile is
still deleted; a 404 today is authoritative about today. What an archived snapshot
provides is supplementary evidence about what the account *used to be* — the
display name, bio and avatar it carried on a given date — which is exactly what is
needed to link a dead handle to a living identity.

Because that evidence is historical, callers must:

* multiply its confidence by ``ARCHIVE_CONFIDENCE_MULTIPLIER`` (0.75), and
* stamp the snapshot date on every claim derived from it, so "worked at X" is
  read as "worked at X *as of 2021-04-11*".

Nothing in this module's API can express existence, on purpose: ``ArchivedSnapshot``
carries no ``exists``/``verdict`` field, so there is no way to accidentally launder
an archive read into a live verdict.

Endpoints are the same public, keyless ones ``app/services/archive_service.py``
already uses: the availability API for "is there a snapshot at all", and the CDX
API as the fallback that can filter on ``statuscode:200``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from app.discovery.fetch.selectors import dig, meta_content
from app.discovery.types import SourceKind
from app.utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover - import kept out of the runtime path
    from app.discovery.fetch.session import FetchSession

SOURCE_KIND = SourceKind.ARCHIVE
ARCHIVE_CONFIDENCE_MULTIPLIER = 0.75
"""Callers multiply the confidence of any archive-derived claim by this."""

_AVAILABILITY_URL = "https://archive.org/wayback/available?url={u}"
_CDX_URL = "https://web.archive.org/cdx/search/cdx?url={u}&output=json&limit=-5&filter=statuscode:200"
_SNAPSHOT_URL = "https://web.archive.org/web/{ts}/{url}"

# Suffix separators sites append to og:title ("Jane Doe | LinkedIn").
_TITLE_SEPARATORS = (" | ", " • ", " · ", " - ", " — ", " – ")


@dataclass(frozen=True, slots=True)
class ArchivedSnapshot:
    """One Wayback capture of a URL. Deliberately carries no existence verdict."""

    url: str
    snapshot_url: str
    timestamp: datetime
    status: int | None
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None


class ArchiveRecovery:
    """Finds the newest usable Wayback capture of a URL and reads its metadata."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    async def latest_snapshot(self, fetch: FetchSession, url: str) -> ArchivedSnapshot | None:
        """Newest capture of ``url``, or None when the archive has nothing usable."""
        target = (url or "").strip()
        if not self._enabled or not target:
            return None
        try:
            snapshot = await self._from_availability(fetch, target)
            if snapshot is None:
                snapshot = await self._from_cdx(fetch, target)
        except Exception as exc:
            logger.log_warning(f"Archive lookup raised for {target}: {type(exc).__name__}: {exc}")
            return None
        return snapshot

    async def recover_profile(self, fetch: FetchSession, url: str, *, platform: str) -> ArchivedSnapshot | None:
        """Fetch the newest usable snapshot and read og:title / og:description / og:image.

        The returned snapshot describes the account *at the snapshot date*. It is
        never an assertion that the account exists now.
        """
        snapshot = await self.latest_snapshot(fetch, url)
        if snapshot is None:
            return None

        try:
            result = await fetch.get(snapshot.snapshot_url, escalate=False, min_html_bytes=0)
        except Exception as exc:
            logger.log_warning(f"Archive snapshot fetch raised for {snapshot.snapshot_url}: {exc}")
            return snapshot
        if not result.ok:
            # The capture exists but we could not read it. Report the capture
            # anyway — its date alone is evidence the account once existed.
            logger.log_warning(f"Archive snapshot unreadable ({result.describe()}): {snapshot.snapshot_url}")
            return snapshot

        page = result.page
        title = meta_content(page, "og:title", "twitter:title")
        description = meta_content(page, "og:description", "twitter:description", "description")
        image = meta_content(page, "og:image", "og:image:secure_url", "twitter:image")
        return replace(
            snapshot,
            display_name=_strip_platform_suffix(title, platform) if title else None,
            bio=" ".join(description.split()) if description else None,
            avatar_url=image or None,
        )

    async def _from_availability(self, fetch: FetchSession, url: str) -> ArchivedSnapshot | None:
        """Wayback availability API — one request, newest closest capture."""
        _, payload = await fetch.get_json(_AVAILABILITY_URL.format(u=quote(url, safe="")))
        closest = dig(payload, "archived_snapshots.closest")
        if not isinstance(closest, dict) or closest.get("available") is False:
            return None
        moment = _parse_timestamp(str(closest.get("timestamp") or ""))
        snapshot_url = str(closest.get("url") or "").strip()
        if moment is None or not snapshot_url:
            return None
        return ArchivedSnapshot(
            url=url,
            snapshot_url=_https(snapshot_url),
            timestamp=moment,
            status=_as_int(closest.get("status")),
        )

    async def _from_cdx(self, fetch: FetchSession, url: str) -> ArchivedSnapshot | None:
        """CDX fallback — the only endpoint that can filter to ``statuscode:200``."""
        _, payload = await fetch.get_json(_CDX_URL.format(u=quote(url, safe="")))
        if not isinstance(payload, list) or len(payload) < 2:
            return None

        header = [str(cell).strip().lower() for cell in payload[0]] if isinstance(payload[0], list) else []
        index_ts = header.index("timestamp") if "timestamp" in header else 1
        index_original = header.index("original") if "original" in header else 2
        index_status = header.index("statuscode") if "statuscode" in header else 4

        best: ArchivedSnapshot | None = None
        for row in payload[1:]:
            if not isinstance(row, list) or len(row) <= max(index_ts, index_original):
                continue
            moment = _parse_timestamp(str(row[index_ts]))
            original = str(row[index_original] or "").strip()
            if moment is None or not original:
                continue
            candidate = ArchivedSnapshot(
                url=url,
                snapshot_url=_SNAPSHOT_URL.format(ts=str(row[index_ts]).strip(), url=original),
                timestamp=moment,
                status=_as_int(row[index_status]) if len(row) > index_status else None,
            )
            if best is None or candidate.timestamp > best.timestamp:
                best = candidate
        return best


def _parse_timestamp(raw: str) -> datetime | None:
    """Wayback stamps are ``YYYYMMDDhhmmss`` in UTC. None when unparseable."""
    text = (raw or "").strip()
    if len(text) < 14 or not text[:14].isdigit():
        return None
    try:
        return datetime.strptime(text[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _https(url: str) -> str:
    """Wayback still hands out http:// snapshot URLs; upgrade them."""
    return "https://" + url[len("http://") :] if url.startswith("http://") else url


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _strip_platform_suffix(title: str, platform: str) -> str:
    """``"Jane Doe | LinkedIn"`` -> ``"Jane Doe"``. Leaves unrelated titles alone."""
    cleaned = " ".join(str(title or "").split())
    marker = (platform or "").strip().lower()
    if not marker:
        return cleaned
    for separator in _TITLE_SEPARATORS:
        head, found, tail = cleaned.rpartition(separator)
        if found and head.strip() and marker in tail.lower():
            cleaned = head.strip()
    return cleaned

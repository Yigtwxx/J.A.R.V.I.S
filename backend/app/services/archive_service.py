"""
Archive / Historical Intelligence Service
=========================================
Surfaces historical snapshots of a subject's public URLs from the Internet
Archive (Wayback Machine). 100% public and keyless.

Sources:
  - Availability:  GET https://archive.org/wayback/available?url={url}
  - History (CDX): GET http://web.archive.org/cdx/search/cdx?url={url}
                       &output=json&collapse=timestamp:6&limit=20

Every returned snapshot carries a public `source_url` + `retrieved_at`.
Never raises — degrades to an empty result so the pipeline is never broken.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from app.utils.logger import logger

_AVAIL_BASE = "https://archive.org/wayback/available"
_CDX_BASE = "http://web.archive.org/cdx/search/cdx"
_TIMEOUT = 10.0
_USER_AGENT = "J.A.R.V.I.S-OSINT/2.0"

_MAX_URLS = 8
_MAX_SNAPSHOTS_PER_URL = 12


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wayback_ts_to_iso(ts: str) -> str:
    """Convert a Wayback timestamp (YYYYMMDDhhmmss) to an ISO date string."""
    try:
        return datetime.strptime(ts[:14], "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        ).isoformat()
    except Exception:  # noqa: BLE001
        return ts


class ArchiveService:
    """Aggregates public Wayback Machine snapshots for a set of URLs."""

    @staticmethod
    def derive_urls(
        social_urls: list[str] | None,
        blog: str | None,
        domains: list[str] | None,
    ) -> list[str]:
        """Build a de-duplicated list of public URLs worth checking for history."""
        found: list[str] = []
        for u in social_urls or []:
            if isinstance(u, str) and u.strip():
                found.append(u.strip())
        if blog and isinstance(blog, str) and blog.strip():
            raw = blog.strip()
            found.append(raw if "//" in raw else f"https://{raw}")
        for d in domains or []:
            if isinstance(d, str) and d.strip():
                found.append(f"https://{d.strip()}")

        clean: list[str] = []
        for u in found:
            if u not in clean:
                clean.append(u)
            if len(clean) >= _MAX_URLS:
                break
        return clean

    async def _history(self, client: httpx.AsyncClient, url: str) -> list[dict]:
        """Return up to N historical snapshots for a single URL via the CDX API."""
        snapshots: list[dict] = []
        try:
            resp = await client.get(
                _CDX_BASE,
                params={
                    "url": url,
                    "output": "json",
                    "collapse": "timestamp:6",
                    "limit": _MAX_SNAPSHOTS_PER_URL,
                    "fl": "timestamp,original,statuscode",
                },
                headers={"user-agent": _USER_AGENT},
                timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                return []
            rows = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"Archive CDX failed for {url!r}: {exc}")
            return []

        # First row is the header (["timestamp","original","statuscode"])
        now = _utcnow_iso()
        for row in (rows or [])[1:]:
            if not isinstance(row, list) or len(row) < 2:
                continue
            ts, original = row[0], row[1]
            snapshots.append({
                "url": original,
                "snapshot_url": f"https://web.archive.org/web/{ts}/{original}",
                "timestamp": _wayback_ts_to_iso(ts),
                "source_url": (
                    f"{_CDX_BASE}?url={url}&output=json&collapse=timestamp:6"
                ),
                "retrieved_at": now,
            })
        return snapshots

    async def aggregate(self, urls: list[str]) -> list[dict]:
        """Return historical snapshots for each URL. Never raises."""
        urls = [u for u in (urls or []) if u][:_MAX_URLS]
        if not urls:
            return []

        logger.log_action(f"Archive intel: checking {len(urls)} URL(s) on Wayback")
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                results = await asyncio.gather(
                    *(self._history(client, u) for u in urls),
                    return_exceptions=True,
                )
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"Archive aggregate failed: {exc}")
            return []

        snapshots: list[dict] = []
        for res in results:
            if isinstance(res, Exception):
                logger.log_warning(f"Archive sub-task failed: {res}")
                continue
            snapshots.extend(res)

        # newest first
        snapshots.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
        if snapshots:
            logger.log_success(f"Archive intel: {len(snapshots)} snapshot(s) found")
        return snapshots


# Module-level singleton (mirrors breach_service / domain_intel_service pattern)
archive_service = ArchiveService()

"""
Public Webcam Intelligence Service
==================================
Finds PUBLIC live webcams near a searched location — the cameras a publisher
intentionally streams to the public (traffic, tourism, weather, harbor/square
live feeds).

Two modes:
  - Windy Webcams API v3 (when WINDY_WEBCAMS_API_KEY is set) → nearby public
    cameras with their latest preview frame.
  - Keyless fallback → web search for public live-cam pages (EarthCam, YouTube
    live, webcam directories) returning links only.

SCOPE / ETHICS: Only publisher-public cameras. This service NEVER accesses
private, home/business security, or unsecured/exposed IP/CCTV cameras, and never
tracks individuals. "Watch" links point to the stream's own public page.
"""
from __future__ import annotations

import asyncio
from threading import Lock
from typing import Any

import httpx
from cachetools import TTLCache
from cachetools.keys import hashkey

from app.config import get_settings
from app.services.search_service import SearchService
from app.utils.logger import logger

_USER_AGENT = "JARVIS-OSINT/1.0"
_TIMEOUT = 15.0

# Latest frames change frequently → short TTL. Thread-safe because callers may
# run this from executor threads (osint_tools) as well as the event loop.
_webcam_cache: TTLCache = TTLCache(maxsize=128, ttl=300)
_webcam_lock = Lock()

# Reused for the keyless DuckDuckGo fallback (sync requests → run in executor).
_search = SearchService()


class WebcamService:
    """Locates public live webcams near a geocoded place."""

    async def _geocode(self, place: str) -> dict[str, Any] | None:
        """Resolve a place name to lat/lng via Nominatim (free, no key)."""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=_TIMEOUT) as client:
                resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"format": "json", "q": place, "limit": 1},
                    headers={"user-agent": _USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()
                if data:
                    return {
                        "lat": float(data[0]["lat"]),
                        "lng": float(data[0]["lon"]),
                        "display_name": data[0].get("display_name", place),
                    }
        except (httpx.RequestError, ValueError, KeyError, IndexError) as exc:
            logger.log_warning(f"Geocoding failed for '{place}': {exc}")
        return None

    async def find_public_webcams(self, place: str) -> dict[str, Any]:
        """Return public webcams near ``place``.

        Output: ``{place, coords, source, webcams: [...]}`` where each webcam is
        ``{title, lat, lng, image_current, image_daylight, page_url, source}``.
        """
        key = hashkey(place.lower().strip())
        with _webcam_lock:
            if key in _webcam_cache:
                return _webcam_cache[key]

        logger.log_action("Scanning public webcam directories", target=place)
        coords = await self._geocode(place)
        api_key = get_settings().windy_webcams_api_key

        webcams: list[dict[str, Any]] = []
        source = ""

        if coords and api_key:
            webcams = await self._windy_nearby(coords, api_key)
            source = "Windy Webcams"

        if not webcams:
            # Keyless fallback — public live-cam page links (no frames).
            webcams = await self._keyless_webcam_search(place)
            source = "web"

        result = {
            "place": coords["display_name"] if coords else place,
            "coords": coords,
            "source": source,
            "webcams": webcams,
        }
        with _webcam_lock:
            _webcam_cache[key] = result
        return result

    async def _windy_nearby(self, coords: dict[str, Any], api_key: str) -> list[dict[str, Any]]:
        """Query the Windy Webcams public directory for cameras near ``coords``."""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=_TIMEOUT) as client:
                resp = await client.get(
                    "https://api.windy.com/webcams/api/v3/webcams",
                    params={
                        "nearby": f"{coords['lat']},{coords['lng']},250",
                        "include": "images,location,urls",
                        "limit": 12,
                    },
                    headers={"x-windy-api-key": api_key},
                )
                if resp.status_code != 200:
                    logger.log_warning(
                        f"Windy Webcams API HTTP {resp.status_code} — falling back to web search"
                    )
                    return []

                data = resp.json()
                cams: list[dict[str, Any]] = []
                for w in data.get("webcams", []):
                    images = w.get("images", {}) or {}
                    current = images.get("current", {}) or {}
                    daylight = images.get("daylight", {}) or {}
                    loc = w.get("location", {}) or {}
                    urls = w.get("urls", {}) or {}
                    cams.append({
                        "title": w.get("title", "Untitled webcam"),
                        "lat": loc.get("latitude"),
                        "lng": loc.get("longitude"),
                        "image_current": current.get("preview") or current.get("thumbnail", ""),
                        "image_daylight": daylight.get("preview", ""),
                        "page_url": urls.get("detail") or urls.get("provider") or "",
                        "source": "Windy Webcams",
                    })
                logger.log_success(
                    f"Windy Webcams: {len(cams)} public camera(s) near {coords['display_name']}"
                )
                return cams
        except (httpx.RequestError, ValueError, KeyError) as exc:
            logger.log_warning(f"Windy Webcams lookup failed: {exc}")
            return []

    async def _keyless_webcam_search(self, place: str) -> list[dict[str, Any]]:
        """Find public live-cam pages via web search when no Windy key is set."""
        loop = asyncio.get_running_loop()
        dorks = [
            f'"{place}" live webcam',
            f"site:earthcam.com {place}",
            f"{place} live cam youtube",
        ]
        seen: set[str] = set()
        cams: list[dict[str, Any]] = []
        for dork in dorks:
            try:
                results = await loop.run_in_executor(None, _search._search_duckduckgo, dork, 5)
            except Exception as exc:  # noqa: BLE001 — fallback must never hard-fail
                logger.log_warning(f"Keyless webcam search failed for '{dork}': {exc}")
                continue
            for r in results:
                url = r.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                cams.append({
                    "title": r.get("title", "Public live webcam"),
                    "lat": None,
                    "lng": None,
                    "image_current": "",
                    "image_daylight": "",
                    "page_url": url,
                    "source": "web",
                })
            if len(cams) >= 12:
                break

        if cams:
            logger.log_success(
                f"Keyless webcam search: {len(cams)} public live-cam page(s) for '{place}'"
            )
        else:
            logger.log_warning(f"No public webcams found for '{place}'")
        return cams[:12]


# Module-level singleton
webcam_service = WebcamService()

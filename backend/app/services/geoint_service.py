"""Geographic Intelligence Service — EXIF extraction, IP geolocation, timezone analysis."""

from __future__ import annotations

import io
import re
from collections import Counter
from datetime import datetime
from typing import Any

import httpx
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from app.utils.logger import logger


class GeoLocation:
    """A single geographic point with metadata."""

    def __init__(
        self,
        lat: float,
        lng: float,
        label: str,
        loc_type: str,
        source: str,
        confidence: float = 0.5,
        timestamp: str | None = None,
    ) -> None:
        self.lat = lat
        self.lng = lng
        self.label = label
        self.type = loc_type
        self.source = source
        self.confidence = confidence
        self.timestamp = timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "label": self.label,
            "type": self.type,
            "source": self.source,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


class GeoIntService:
    """Extracts, aggregates, and analyzes geographic intelligence."""

    # ------------------------------------------------------------------
    # EXIF GPS extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _dms_to_decimal(dms_tuple, ref: str) -> float:
        """Convert EXIF DMS (degrees, minutes, seconds) to decimal."""
        d, m, s = dms_tuple
        decimal = float(d) + float(m) / 60.0 + float(s) / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal

    async def extract_exif(self, image_url: str) -> dict[str, Any]:
        """Download an image and extract EXIF GPS data + camera metadata."""
        result: dict[str, Any] = {"has_gps": False, "lat": None, "lng": None, "metadata": {}}

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(image_url)
                if resp.status_code != 200:
                    return result

                img = Image.open(io.BytesIO(resp.content))
                exif_data = img._getexif()
                if not exif_data:
                    return result

                exif: dict[str, Any] = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    exif[tag_name] = value

                # Camera metadata
                for key in ("Make", "Model", "DateTime", "Software"):
                    if key in exif:
                        result["metadata"][key] = str(exif[key])

                # GPS info
                gps_info = exif.get("GPSInfo")
                if gps_info:
                    gps: dict[str, Any] = {}
                    for gps_tag_id, val in gps_info.items():
                        gps_tag_name = GPSTAGS.get(gps_tag_id, gps_tag_id)
                        gps[gps_tag_name] = val

                    lat_dms = gps.get("GPSLatitude")
                    lat_ref = gps.get("GPSLatitudeRef", "N")
                    lng_dms = gps.get("GPSLongitude")
                    lng_ref = gps.get("GPSLongitudeRef", "E")

                    if lat_dms and lng_dms:
                        result["lat"] = self._dms_to_decimal(lat_dms, lat_ref)
                        result["lng"] = self._dms_to_decimal(lng_dms, lng_ref)
                        result["has_gps"] = True

        except Exception as exc:
            logger.log_warning(f"EXIF extraction failed for {image_url}: {exc}")

        return result

    # ------------------------------------------------------------------
    # IP Geolocation
    # ------------------------------------------------------------------

    async def geolocate_ip(self, ip: str) -> dict[str, Any]:
        """Resolve an IP address to geographic coordinates using ip-api.com (free)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"http://ip-api.com/json/{ip}?fields=status,lat,lon,city,regionName,country,isp,org,as,timezone")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        return {
                            "ip": ip,
                            "lat": data.get("lat"),
                            "lng": data.get("lon"),
                            "city": data.get("city"),
                            "region": data.get("regionName"),
                            "country": data.get("country"),
                            "isp": data.get("isp"),
                            "org": data.get("org"),
                            "timezone": data.get("timezone"),
                        }
        except Exception as exc:
            logger.log_warning(f"IP geolocation failed for {ip}: {exc}")

        return {"ip": ip, "lat": None, "lng": None, "error": "Geolocation failed"}

    # ------------------------------------------------------------------
    # Location aggregation
    # ------------------------------------------------------------------

    async def aggregate_locations(
        self,
        location_country: str | None = None,
        location_city: str | None = None,
        company_records: list[dict] | None = None,
        image_urls: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Combine all location signals into a unified list."""
        locations: list[GeoLocation] = []

        # 1. Primary location from profile (geocode via Nominatim)
        if location_city or location_country:
            place = f"{location_city or ''} {location_country or ''}".strip()
            coords = await self._geocode(place)
            if coords:
                locations.append(GeoLocation(
                    lat=coords[0], lng=coords[1],
                    label=place, loc_type="primary",
                    source="profile_location", confidence=0.7,
                ))

        # 2. Company locations
        if company_records:
            for rec in (company_records or [])[:5]:
                city = rec.get("city") or ""
                country = rec.get("country") or ""
                place = f"{city} {country}".strip()
                if place:
                    coords = await self._geocode(place)
                    if coords:
                        locations.append(GeoLocation(
                            lat=coords[0], lng=coords[1],
                            label=f"{rec.get('company_name', 'Unknown')} ({place})",
                            loc_type="company", source="company_registry",
                            confidence=rec.get("confidence", 0.5),
                        ))

        # 3. EXIF from images
        if image_urls:
            for url in (image_urls or [])[:10]:
                exif = await self.extract_exif(url)
                if exif.get("has_gps"):
                    locations.append(GeoLocation(
                        lat=exif["lat"], lng=exif["lng"],
                        label=f"Photo EXIF ({exif.get('metadata', {}).get('DateTime', 'unknown date')})",
                        loc_type="exif", source="image_exif", confidence=0.9,
                        timestamp=exif.get("metadata", {}).get("DateTime"),
                    ))

        return [loc.to_dict() for loc in locations]

    # ------------------------------------------------------------------
    # Activity time analysis
    # ------------------------------------------------------------------

    def analyze_activity_times(self, timestamps: list[str]) -> dict[str, Any]:
        """Analyze a list of ISO timestamps to infer timezone and activity patterns.

        Args:
            timestamps: list of ISO-format datetime strings (e.g. from GitHub commits, posts)

        Returns a dict with inferred_timezone, peak_hours, activity_pattern, hourly_distribution
        """
        if not timestamps:
            return {
                "inferred_timezone": "UNKNOWN",
                "peak_hours": [],
                "activity_pattern": "Insufficient data",
                "hourly_distribution": {},
            }

        hours: list[int] = []
        for ts in timestamps:
            try:
                # Handle various timestamp formats
                ts_clean = re.sub(r"[TZ]", " ", ts).strip()
                dt = datetime.fromisoformat(ts_clean.replace("+00:00", "").replace("Z", ""))
                hours.append(dt.hour)
            except (ValueError, TypeError):
                continue

        if not hours:
            return {
                "inferred_timezone": "UNKNOWN",
                "peak_hours": [],
                "activity_pattern": "Could not parse timestamps",
                "hourly_distribution": {},
            }

        # Hourly distribution
        hour_counts = Counter(hours)
        distribution = {str(h): hour_counts.get(h, 0) for h in range(24)}

        # Peak hours (top 3)
        peak_hours = [h for h, _ in hour_counts.most_common(3)]

        # Infer timezone from activity pattern
        # Assume most people are active 9-23 local time.
        # If peak is at hour X in UTC, their local offset ≈ (15 - X) mod 24
        avg_peak = sum(peak_hours) / len(peak_hours)
        offset = round((15 - avg_peak) % 24)
        if offset > 12:
            offset -= 24
        inferred_tz = f"UTC{'+' if offset >= 0 else ''}{offset}"

        # Activity pattern
        night = sum(hour_counts.get(h, 0) for h in range(0, 6))
        morning = sum(hour_counts.get(h, 0) for h in range(6, 12))
        afternoon = sum(hour_counts.get(h, 0) for h in range(12, 18))
        evening = sum(hour_counts.get(h, 0) for h in range(18, 24))
        total = max(sum([night, morning, afternoon, evening]), 1)

        if night / total > 0.4:
            pattern = "Night owl"
        elif morning / total > 0.4:
            pattern = "Early riser"
        elif evening / total > 0.4:
            pattern = "Evening worker"
        else:
            pattern = "Regular schedule"

        return {
            "inferred_timezone": inferred_tz,
            "peak_hours": sorted(peak_hours),
            "activity_pattern": pattern,
            "hourly_distribution": distribution,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _geocode(place: str) -> tuple[float, float] | None:
        """Geocode a place name using OpenStreetMap Nominatim (free, no key)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": place, "format": "json", "limit": 1},
                    headers={"User-Agent": "JARVIS-OSINT/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data:
                        return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception:
            pass
        return None


geoint_service = GeoIntService()

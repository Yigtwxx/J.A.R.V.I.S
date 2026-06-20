"""
Sanctions / PEP Screening Service
=================================
Screens a name against PUBLIC sanctions lists. Keyless by default.

Sources:
  - OFAC SDN (keyless): https://www.treasury.gov/ofac/downloads/sdn.csv
      Downloaded once and cached (24h), then fuzzy-matched in-process.
  - OpenSanctions (optional key): https://api.opensanctions.org/search/default
      Used only when `opensanctions_api_token` is configured.

IMPORTANT: This is informational only. A hit is a *possible* name match, NOT a
confirmed identification — every hit carries a `match_score` and must be
verified. No match => empty list. Every hit carries a public `source_url`.
Never raises — degrades to an empty list so the pipeline is never broken.
"""

from __future__ import annotations

import asyncio
import csv
import io
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from threading import Lock

import httpx
from cachetools import TTLCache

from app.config import get_settings
from app.utils.logger import logger

_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
_SDN_SOURCE = "https://sanctionssearch.ofac.treas.gov/"
_OPENSANCTIONS = "https://api.opensanctions.org/search/default"
_TIMEOUT = 15.0
_USER_AGENT = "J.A.R.V.I.S-OSINT/2.0"

_MATCH_THRESHOLD = 0.86
_MAX_HITS = 15

# OFAC SDN list rarely changes intra-day; cache the parsed entries for 24h.
_sdn_cache: TTLCache = TTLCache(maxsize=1, ttl=86400)
_sdn_lock = Lock()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    """Lower-case, strip diacritics (NFKD), collapse whitespace."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


class SanctionsService:
    """Screens names against OFAC SDN (keyless) + optional OpenSanctions."""

    async def _load_sdn(self, client: httpx.AsyncClient) -> list[tuple[str, str, str, str]]:
        """Return cached SDN entries as (norm_name, name, sdn_type, program). Never raises."""
        with _sdn_lock:
            cached = _sdn_cache.get("sdn")
        if cached is not None:
            return cached

        try:
            r = await client.get(_SDN_CSV, headers={"user-agent": _USER_AGENT}, timeout=_TIMEOUT)
            if r.status_code != 200:
                return []
            text = r.content.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"OFAC SDN download failed: {exc}")
            return []

        entries: list[tuple[str, str, str, str]] = []
        try:
            # SDN CSV has no header: ent_num, name, sdn_type, program, title, ...
            reader = csv.reader(io.StringIO(text))
            for row in reader:
                if len(row) < 4:
                    continue
                name = (row[1] or "").strip().strip('"')
                if not name or name == "-0-":
                    continue
                sdn_type = (row[2] or "").strip()
                program = (row[3] or "").strip().strip('"')
                entries.append((_normalize(name), name, sdn_type, program))
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"OFAC SDN parse failed: {exc}")
            return []

        with _sdn_lock:
            _sdn_cache["sdn"] = entries
        logger.log_action(f"OFAC SDN list cached: {len(entries)} entries")
        return entries

    def _match_sdn(self, name: str, entries: list[tuple[str, str, str, str]]) -> list[dict]:
        """Fuzzy-match a name against SDN entries (CPU-bound, run in executor)."""
        q = _normalize(name)
        if not q or len(q) < 4:
            return []
        q_tokens = {t for t in q.split() if len(t) > 2}
        now = _utcnow_iso()
        hits: list[dict] = []
        for norm_name, orig_name, sdn_type, program in entries:
            # cheap prefilter: require at least one shared significant token
            if q_tokens and not (q_tokens & set(norm_name.split())):
                continue
            score = SequenceMatcher(None, q, norm_name).ratio()
            if score >= _MATCH_THRESHOLD:
                hits.append({
                    "name": orig_name,
                    "list_name": "OFAC SDN",
                    "program": program,
                    "entity_type": sdn_type,
                    "match_score": round(score, 3),
                    "source_url": _SDN_SOURCE,
                    "retrieved_at": now,
                    "note": "Possible name match — verification required.",
                })
        hits.sort(key=lambda h: h["match_score"], reverse=True)
        return hits[:_MAX_HITS]

    async def _opensanctions(self, client: httpx.AsyncClient, name: str, token: str) -> list[dict]:
        try:
            r = await client.get(
                _OPENSANCTIONS,
                params={"q": name},
                headers={"Authorization": f"ApiKey {token}", "user-agent": _USER_AGENT},
                timeout=_TIMEOUT,
            )
            if r.status_code != 200:
                return []
            results = r.json().get("results", []) or []
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"OpenSanctions failed for {name!r}: {exc}")
            return []

        now = _utcnow_iso()
        hits: list[dict] = []
        for item in results[:_MAX_HITS]:
            topics = item.get("properties", {}).get("topic", []) or item.get("datasets", [])
            hits.append({
                "name": item.get("caption") or item.get("name") or name,
                "list_name": "OpenSanctions",
                "program": ", ".join(topics) if isinstance(topics, list) else str(topics),
                "entity_type": item.get("schema", ""),
                "match_score": round(float(item.get("score", 0.0)), 3),
                "source_url": f"https://www.opensanctions.org/entities/{item.get('id', '')}/",
                "retrieved_at": now,
                "note": "Possible name match — verification required.",
            })
        return hits

    async def check(self, name: str) -> list[dict]:
        """Return possible sanctions/PEP matches for a name. Never raises."""
        name = (name or "").strip()
        if not name or len(name) < 4:
            return []

        settings = get_settings()
        token = settings.opensanctions_api_token

        logger.log_action(f"Sanctions screening: {name!r}")
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                entries = await self._load_sdn(client)
                sdn_hits = (
                    await asyncio.to_thread(self._match_sdn, name, entries)
                    if entries else []
                )
                os_hits = (
                    await self._opensanctions(client, name, token) if token else []
                )
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"Sanctions check failed: {exc}")
            return []

        hits = sdn_hits + os_hits
        if hits:
            logger.log_warning(
                f"SANCTIONS SCREENING: {len(hits)} possible match(es) for {name!r} "
                f"(verification required)"
            )
        else:
            logger.log_success(f"Sanctions screening: no matches for {name!r}")
        return hits


# Module-level singleton
sanctions_service = SanctionsService()

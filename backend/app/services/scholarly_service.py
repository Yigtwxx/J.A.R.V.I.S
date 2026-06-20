"""
Scholarly / Academic Intelligence Service
=========================================
Finds public scholarly output for a person from open academic APIs.
100% public and keyless.

Sources:
  - Semantic Scholar: /graph/v1/author/search -> /author/{id}/papers
  - arXiv:            export.arxiv.org/api/query (Atom XML)
  - Crossref:         api.crossref.org/works

Every record carries a public `source_url` + `retrieved_at`.
Never raises — degrades to an empty list so the pipeline is never broken.
"""

from __future__ import annotations

import asyncio
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from app.utils.logger import logger

_S2_AUTHOR = "https://api.semanticscholar.org/graph/v1/author/search"
_S2_PAPERS = "https://api.semanticscholar.org/graph/v1/author/{aid}/papers"
_ARXIV = "http://export.arxiv.org/api/query"
_CROSSREF = "https://api.crossref.org/works"
_TIMEOUT = 10.0
_USER_AGENT = "J.A.R.V.I.S-OSINT/2.0 (mailto:osint@example.org)"

_MAX_RECORDS = 20
_ARXIV_NS = "{http://www.w3.org/2005/Atom}"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_title(t: str) -> str:
    return "".join(ch.lower() for ch in (t or "") if ch.isalnum())[:80]


class ScholarlyService:
    """Aggregates public scholarly records from Semantic Scholar, arXiv, Crossref."""

    async def _semantic_scholar(self, client: httpx.AsyncClient, name: str) -> list[dict]:
        records: list[dict] = []
        try:
            r = await client.get(
                _S2_AUTHOR,
                params={"query": name, "fields": "name,paperCount,url", "limit": 1},
                headers={"user-agent": _USER_AGENT},
                timeout=_TIMEOUT,
            )
            if r.status_code != 200:
                return []
            authors = r.json().get("data") or []
            if not authors:
                return []
            aid = authors[0].get("authorId")
            if not aid:
                return []
            pr = await client.get(
                _S2_PAPERS.format(aid=aid),
                params={"fields": "title,year,venue,url", "limit": 10},
                headers={"user-agent": _USER_AGENT},
                timeout=_TIMEOUT,
            )
            if pr.status_code != 200:
                return []
            papers = pr.json().get("data") or []
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"Semantic Scholar failed for {name!r}: {exc}")
            return []

        now = _utcnow_iso()
        for p in papers:
            title = p.get("title")
            if not title:
                continue
            records.append({
                "title": title,
                "year": p.get("year"),
                "venue": p.get("venue") or "",
                "authors": [name],
                "source_url": p.get("url") or _S2_AUTHOR,
                "retrieved_at": now,
                "confidence": 0.75,
            })
        return records

    async def _arxiv(self, client: httpx.AsyncClient, name: str) -> list[dict]:
        records: list[dict] = []
        try:
            r = await client.get(
                _ARXIV,
                params={"search_query": f'au:"{name}"', "max_results": 10},
                headers={"user-agent": _USER_AGENT},
                timeout=_TIMEOUT,
            )
            if r.status_code != 200:
                return []
            root = ET.fromstring(r.text)
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"arXiv failed for {name!r}: {exc}")
            return []

        now = _utcnow_iso()
        for entry in root.findall(f"{_ARXIV_NS}entry"):
            title_el = entry.find(f"{_ARXIV_NS}title")
            id_el = entry.find(f"{_ARXIV_NS}id")
            pub_el = entry.find(f"{_ARXIV_NS}published")
            if title_el is None or not title_el.text:
                continue
            authors = [
                a.findtext(f"{_ARXIV_NS}name", "").strip()
                for a in entry.findall(f"{_ARXIV_NS}author")
            ]
            year = None
            if pub_el is not None and pub_el.text:
                year = pub_el.text[:4]
            records.append({
                "title": " ".join(title_el.text.split()),
                "year": int(year) if year and year.isdigit() else None,
                "venue": "arXiv",
                "authors": [a for a in authors if a][:8],
                "source_url": (id_el.text if id_el is not None else _ARXIV) or _ARXIV,
                "retrieved_at": now,
                "confidence": 0.8,
            })
        return records

    async def _crossref(self, client: httpx.AsyncClient, name: str) -> list[dict]:
        records: list[dict] = []
        try:
            r = await client.get(
                _CROSSREF,
                params={
                    "query.author": name,
                    "select": "title,author,URL,published-print,container-title",
                    "rows": 8,
                },
                headers={"user-agent": _USER_AGENT},
                timeout=_TIMEOUT,
            )
            if r.status_code != 200:
                return []
            items = r.json().get("message", {}).get("items", []) or []
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"Crossref failed for {name!r}: {exc}")
            return []

        now = _utcnow_iso()
        for item in items:
            titles = item.get("title") or []
            if not titles:
                continue
            year = None
            dp = item.get("published-print", {}).get("date-parts")
            if dp and dp[0]:
                year = dp[0][0]
            containers = item.get("container-title") or []
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in (item.get("author") or [])
            ]
            records.append({
                "title": titles[0],
                "year": year,
                "venue": containers[0] if containers else "",
                "authors": [a for a in authors if a][:8],
                "source_url": item.get("URL") or _CROSSREF,
                "retrieved_at": now,
                "confidence": 0.7,
            })
        return records

    async def aggregate(self, name: str) -> list[dict]:
        """Return de-duplicated scholarly records for a name. Never raises."""
        name = (name or "").strip()
        if not name:
            return []

        logger.log_action(f"Scholarly intel: searching academic networks for {name!r}")
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                results = await asyncio.gather(
                    self._semantic_scholar(client, name),
                    self._arxiv(client, name),
                    self._crossref(client, name),
                    return_exceptions=True,
                )
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"Scholarly aggregate failed: {exc}")
            return []

        merged: list[dict] = []
        seen: set[str] = set()
        for res in results:
            if isinstance(res, Exception):
                logger.log_warning(f"Scholarly sub-task failed: {res}")
                continue
            for rec in res:
                key = _norm_title(rec.get("title", ""))
                if key and key not in seen:
                    seen.add(key)
                    merged.append(rec)

        merged.sort(key=lambda r: (r.get("year") or 0), reverse=True)
        merged = merged[:_MAX_RECORDS]
        if merged:
            logger.log_success(f"Scholarly intel: {len(merged)} record(s) found")
        return merged


# Module-level singleton
scholarly_service = ScholarlyService()

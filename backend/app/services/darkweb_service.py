"""
Dark Web & Deep Web Intelligence Service
==========================================
Extends breach detection beyond XposedOrNot with:
  1. Paste site scraping (PasteBin-style public pastes via Google dorking)
  2. Username/email search across leak aggregation sites
  3. Credential leak aggregation from free sources

All operations stay within legal boundaries — no Tor access, no paid APIs.
Uses publicly accessible search engines and free APIs only.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.utils.logger import logger

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_TIMEOUT = 15.0


class DarkWebService:
    """Scans paste sites and leak databases for target exposure."""

    # -- Paste Site Search -------------------------------------------------

    async def search_paste_sites(self, query: str) -> list[dict[str, Any]]:
        """
        Search for target mentions in paste sites using Google dorking.
        Searches Pastebin, Ghostbin, Rentry, etc.
        """
        results: list[dict[str, Any]] = []
        paste_domains = [
            "pastebin.com",
            "ghostbin.me",
            "rentry.co",
            "dpaste.org",
            "paste.ee",
            "hastebin.com",
        ]

        logger.log_action("Initiating paste site reconnaissance", target=query)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for domain in paste_domains:
                try:
                    # Use Yahoo search as a dorking proxy
                    search_url = "https://search.yahoo.com/search"
                    params = {"p": f'site:{domain} "{query}"', "n": "5"}
                    resp = await client.get(
                        search_url,
                        params=params,
                        headers={"user-agent": _USER_AGENT},
                        timeout=_TIMEOUT,
                    )

                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "lxml")
                    for item in soup.select("div.algo-sr, div.dd"):
                        link = item.find("a", href=True)
                        if not link:
                            continue
                        href = link.get("href", "")
                        if domain in href:
                            title = link.get_text(strip=True)[:100]
                            snippet_elem = item.find("div", class_="compText") or item.find("p")
                            snippet = snippet_elem.get_text(strip=True)[:200] if snippet_elem else ""
                            results.append({
                                "_type": "paste",
                                "Source": domain,
                                "Id": href,
                                "Title": title or f"Paste on {domain}",
                                "Date": "",
                                "EmailCount": 0,
                                "TargetEmail": query,
                                "url": href,
                                "snippet": snippet,
                            })

                    await asyncio.sleep(1.5)  # Rate limit

                except (httpx.RequestError, Exception) as e:
                    logger.log_warning(f"Paste search failed for {domain}: {e}")

        if results:
            logger.log_warning(f"PASTE EXPOSURE: {len(results)} paste(s) found for '{query}'")
        else:
            logger.log_success(f"PASTE CLEAR: No paste site exposure detected for '{query}'")

        return results

    # -- Username Leak Search ----------------------------------------------

    async def search_username_leaks(self, username: str) -> list[dict[str, Any]]:
        """
        Check if a username appears in known leak databases.
        Uses publicly accessible endpoints only.
        """
        results: list[dict[str, Any]] = []
        logger.log_action("Scanning underground leak databases", target=username)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            # LeakCheck free public search (limited results)
            try:
                resp = await client.get(
                    f"https://leakcheck.io/api/public?check={username}",
                    headers={"user-agent": _USER_AGENT},
                    timeout=_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("found"):
                        results.append({
                            "source": "LeakCheck",
                            "found": True,
                            "details": f"Username '{username}' found in leak databases",
                            "count": data.get("found", 0),
                        })
                        logger.log_warning(f"LeakCheck: '{username}' found in leak database")
            except (httpx.RequestError, Exception) as e:
                logger.log_warning(f"LeakCheck search failed: {e}")

            await asyncio.sleep(1)

            # ProxyNova COMB — free combolist search (replaces the now Cloudflare-walled
            # BreachDirectory endpoint). Returns leaked "identifier:secret" lines.
            # We surface only the EXPOSURE COUNT and a masked sample — never raw secrets.
            try:
                resp = await client.get(
                    "https://api.proxynova.com/comb",
                    params={"query": username, "limit": "15"},
                    headers={"user-agent": _USER_AGENT},
                    timeout=_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    lines = data.get("lines") or []
                    if lines:
                        # Distinct identifiers that actually match the target
                        matched = [ln for ln in lines if username.lower() in ln.lower()]
                        sample = matched or lines
                        identifiers = sorted({ln.split(":", 1)[0] for ln in sample[:15] if ln})
                        results.append({
                            "source": "ProxyNova COMB",
                            "found": True,
                            "details": (
                                f"'{username}' appears in {data.get('count', len(lines))} leaked "
                                f"credential record(s) across breach combolists"
                            ),
                            "count": data.get("count", len(lines)),
                            "exposed_identifiers": identifiers[:10],
                            "hash_password": True,
                        })
                        logger.log_warning(
                            f"COMB EXPOSURE: '{username}' found in {data.get('count', len(lines))} leaked record(s)"
                        )
            except (httpx.RequestError, Exception) as e:
                logger.log_warning(f"ProxyNova COMB search failed: {e}")

        return results

    # -- Deep Web Intel Aggregation ----------------------------------------

    async def aggregate_deep_intel(
        self,
        emails: list[str],
        username: str,
        real_name: str,
    ) -> dict[str, Any]:
        """
        Run all dark web checks and return aggregated results.
        Called by the search orchestrator.
        """
        paste_results: list[dict] = []
        leak_results: list[dict] = []

        # Run paste search for all identifiers
        queries = list(set(filter(None, emails + [username, real_name])))

        tasks = []
        for q in queries[:5]:  # Limit to 5 queries to avoid rate limiting
            tasks.append(self.search_paste_sites(q))

        if username:
            tasks.append(self.search_username_leaks(username))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                continue
            if isinstance(r, list):
                for item in r:
                    if item.get("_type") == "paste":
                        paste_results.append(item)
                    elif item.get("source"):
                        leak_results.append(item)

        # Deduplicate pastes by URL
        seen_urls: set[str] = set()
        unique_pastes = []
        for p in paste_results:
            url = p.get("url", p.get("Id", ""))
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_pastes.append(p)

        return {
            "paste_exposures": unique_pastes,
            "leak_results": leak_results,
            "total_exposures": len(unique_pastes) + len(leak_results),
            "scanned_queries": queries[:5],
        }

    # -- Email Pattern Generator -------------------------------------------

    @staticmethod
    def generate_email_patterns(name: str, domain: str = "gmail.com") -> list[str]:
        """Generate common email patterns from a person's name."""
        parts = re.split(r'[\s\-]+', name.lower().strip())
        if len(parts) < 2:
            return [f"{parts[0]}@{domain}"]

        first, last = parts[0], parts[-1]
        return [
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{last}.{first}@{domain}",
            f"{first}_{last}@{domain}",
        ]


# Module-level singleton
darkweb_service = DarkWebService()

"""
Domain / Infrastructure Intelligence Service
============================================
Enriches a subject by analysing the public domains they are tied to
(derived from their email addresses + GitHub blog/website).

ALL sources are 100% public and keyless:
  - RDAP (WHOIS)            GET https://rdap.org/domain/{domain}
  - DNS-over-HTTPS (Google) GET https://dns.google/resolve?name={domain}&type=A
  - Certificate Transparency GET https://crt.sh/?q={domain}&output=json

OSINT boundary: only public registry / DNS / CT data. No private records.
Every returned record carries a public `source_url` + `retrieved_at`.

The service never raises — on any failure it degrades to an empty result so
the overall search pipeline is never broken.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.utils.logger import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RDAP_BASE  = "https://rdap.org/domain"
_DNS_BASE   = "https://dns.google/resolve"
_CRTSH_BASE = "https://crt.sh"
_TIMEOUT    = 10.0
_USER_AGENT = "J.A.R.V.I.S-OSINT/2.0"

_MAX_DOMAINS    = 5
_MAX_SUBDOMAINS = 25
_DNS_TYPES      = ("A", "MX", "TXT", "NS")

# Free / shared mail providers — a personal address here tells us nothing about
# infrastructure the subject controls, so we never WHOIS them.
_FREE_MAIL_PROVIDERS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "yahoo.com", "yahoo.co.uk", "ymail.com", "icloud.com", "me.com",
    "mac.com", "proton.me", "protonmail.com", "pm.me", "aol.com", "gmx.com",
    "gmx.net", "mail.com", "yandex.com", "yandex.ru", "zoho.com", "fastmail.com",
    "hey.com", "tutanota.com", "tuta.io",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DomainIntelService:
    """Aggregates public RDAP + DNS + Certificate-Transparency intel per domain."""

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def derive_domains(emails: list[str] | None, blog: str | None) -> list[str]:
        """Build a small, de-duplicated list of subject-controlled domains.

        Sources: email address domains + a GitHub blog/website host.
        Free-mail providers are excluded. Returns at most ``_MAX_DOMAINS``.
        """
        found: list[str] = []

        for email in emails or []:
            if not isinstance(email, str) or "@" not in email:
                continue
            domain = email.rsplit("@", 1)[1].strip().lower()
            if domain:
                found.append(domain)

        if blog and isinstance(blog, str):
            raw = blog.strip()
            if raw:
                # urlparse needs a scheme to populate netloc
                parsed = urlparse(raw if "//" in raw else f"//{raw}")
                host = (parsed.netloc or parsed.path).strip().lower()
                host = host.split("/")[0].split(":")[0]
                if host.startswith("www."):
                    host = host[4:]
                if host:
                    found.append(host)

        # de-dup (preserve order), drop free-mail + obviously invalid hosts
        clean: list[str] = []
        for d in found:
            if d in _FREE_MAIL_PROVIDERS:
                continue
            if "." not in d or " " in d or len(d) < 4:
                continue
            if d not in clean:
                clean.append(d)
            if len(clean) >= _MAX_DOMAINS:
                break
        return clean

    # ---------------------------------------------------------------- sources

    async def _rdap(self, client: httpx.AsyncClient, domain: str) -> dict:
        """Registrar, key dates, nameservers and statuses via RDAP."""
        out: dict = {
            "registrar": None, "created": None, "expires": None,
            "nameservers": [], "statuses": [],
        }
        try:
            resp = await client.get(f"{_RDAP_BASE}/{domain}", timeout=_TIMEOUT)
            if resp.status_code != 200:
                return out
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 — degrade, never raise
            logger.log_warning(f"RDAP failed for {domain!r}: {exc}")
            return out

        for entity in data.get("entities", []) or []:
            if "registrar" in (entity.get("roles") or []):
                out["registrar"] = _vcard_name(entity)
                break

        for event in data.get("events", []) or []:
            action = event.get("eventAction")
            if action == "registration":
                out["created"] = event.get("eventDate")
            elif action == "expiration":
                out["expires"] = event.get("eventDate")

        out["nameservers"] = [
            ns.get("ldhName") for ns in (data.get("nameservers") or [])
            if ns.get("ldhName")
        ]
        out["statuses"] = [s for s in (data.get("status") or []) if isinstance(s, str)]
        return out

    async def _dns(self, client: httpx.AsyncClient, domain: str) -> dict:
        """A / MX / TXT / NS records via Google DNS-over-HTTPS."""
        records: dict = {"a": [], "mx": [], "txt": [], "ns": []}
        for rtype in _DNS_TYPES:
            try:
                resp = await client.get(
                    _DNS_BASE,
                    params={"name": domain, "type": rtype},
                    headers={"accept": "application/dns-json"},
                    timeout=_TIMEOUT,
                )
                if resp.status_code != 200:
                    continue
                answers = resp.json().get("Answer") or []
            except Exception as exc:  # noqa: BLE001
                logger.log_warning(f"DNS {rtype} failed for {domain!r}: {exc}")
                continue
            values = [a.get("data", "").strip('"') for a in answers if a.get("data")]
            records[rtype.lower()] = values[:15]
        return records

    async def _crtsh(self, client: httpx.AsyncClient, domain: str) -> list[str]:
        """Subdomains observed in public Certificate Transparency logs."""
        try:
            resp = await client.get(
                _CRTSH_BASE,
                params={"q": domain, "output": "json"},
                headers={"user-agent": _USER_AGENT},
                timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                return []
            entries = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"crt.sh failed for {domain!r}: {exc}")
            return []

        subs: list[str] = []
        seen: set[str] = set()
        for entry in entries or []:
            name_value = entry.get("name_value") or ""
            for name in name_value.split("\n"):
                name = name.strip().lower().lstrip("*.")
                if not name or name == domain:
                    continue
                if not name.endswith(f".{domain}"):
                    continue
                if name not in seen:
                    seen.add(name)
                    subs.append(name)
                if len(subs) >= _MAX_SUBDOMAINS:
                    return sorted(subs)
        return sorted(subs)

    # ---------------------------------------------------------------- public

    async def _fetch_one(self, client: httpx.AsyncClient, domain: str) -> dict:
        rdap, dns, subdomains = await asyncio.gather(
            self._rdap(client, domain),
            self._dns(client, domain),
            self._crtsh(client, domain),
        )
        return {
            "domain": domain,
            "registrar": rdap["registrar"],
            "created": rdap["created"],
            "expires": rdap["expires"],
            "nameservers": rdap["nameservers"],
            "statuses": rdap["statuses"],
            "dns": dns,
            "subdomains": subdomains,
            "source_url": f"{_RDAP_BASE}/{domain}",
            "retrieved_at": _utcnow_iso(),
            "confidence": 0.8,
        }

    async def aggregate(self, domains: list[str]) -> list[dict]:
        """Return a citation-bearing intel record for each domain. Never raises."""
        domains = [d for d in (domains or []) if d][:_MAX_DOMAINS]
        if not domains:
            return []

        logger.log_action(f"Domain intel: analysing {len(domains)} domain(s)")
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                results = await asyncio.gather(
                    *(self._fetch_one(client, d) for d in domains),
                    return_exceptions=True,
                )
        except Exception as exc:  # noqa: BLE001
            logger.log_warning(f"Domain intel aggregate failed: {exc}")
            return []

        records: list[dict] = []
        for res in results:
            if isinstance(res, Exception):
                logger.log_warning(f"Domain intel sub-task failed: {res}")
                continue
            records.append(res)

        if records:
            logger.log_success(f"Domain intel: {len(records)} domain(s) enriched")
        return records


def _vcard_name(entity: dict) -> str | None:
    """Extract the formatted name (fn) from an RDAP entity's vcardArray."""
    vcard = entity.get("vcardArray")
    if not isinstance(vcard, list) or len(vcard) < 2:
        # some registries expose the handle instead of a vcard
        return entity.get("handle")
    for item in vcard[1]:
        if isinstance(item, list) and len(item) >= 4 and item[0] == "fn":
            return item[3]
    return entity.get("handle")


# Module-level singleton (mirrors breach_service / darkweb_service pattern)
domain_intel_service = DomainIntelService()

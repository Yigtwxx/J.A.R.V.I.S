"""
Breach Intelligence Service
============================
Uses the XposedOrNot API (https://xposedornot.com) to check whether
discovered email addresses appear in known public data breaches.

XposedOrNot is completely FREE — no API key required.

API limits (per IP):
  - 2 requests / second
  - 100 requests / day

Endpoints used:
  GET https://api.xposedornot.com/v1/breach-analytics?email={email}
    200 → breach details JSON
    404 → clean (no breaches found for this email)
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.utils.logger import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_XON_BASE   = "https://api.xposedornot.com/v1"
_TIMEOUT    = 12.0
_USER_AGENT = "J.A.R.V.I.S-OSINT/2.0"
_REQ_DELAY  = 1.5   # stay comfortably under 2 req/s


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

def _normalize_breach(raw: dict[str, Any], email: str) -> dict[str, Any]:
    """
    Map a raw XposedOrNot breach object to the SecurityScanWidget shape.

    XON field reference:
      breachID      → breach name
      domain        → e.g. "linkedin.com"
      xposed        → pwned record count
      xposedData    → semicolon-separated data types: "Email;Password"
      verified      → bool
      sensitive     → bool
      year          → int (breach year)
      logo          → logo URL
      passwordRisk  → "Plaintext" | "easytocrack" | "unknown" ...
    """
    xposed_data: str = raw.get("xposedData") or raw.get("exposedData") or ""
    data_classes = [d.strip() for d in xposed_data.split(";") if d.strip()]

    year = raw.get("year")
    breach_date = f"{year}-01-01" if year else ""

    name = raw.get("breachID") or raw.get("breach") or ""

    return {
        "Name":        name,
        "Title":       name,
        "Domain":      raw.get("domain", "unknown"),
        "BreachDate":  breach_date,
        "PwnCount":    raw.get("xposed") or raw.get("xposedRecords") or 0,
        "DataClasses": data_classes,
        "IsVerified":  bool(raw.get("verified", False)),
        "IsSensitive": bool(raw.get("sensitive", False)),
        "IsSpamList":  False,
        "IsFabricated": False,
        "Description": "",
        "LogoPath":    raw.get("logo", ""),
        "TargetEmail": email,
    }


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class BreachService:
    """
    Scans email addresses against the XposedOrNot breach database.
    Completely free — no API key, no mock data.
    """

    async def check_breaches(self, emails: list[str]) -> list[dict[str, Any]]:
        """
        Main entry point called by the search route.

        Returns a flat list of breach dicts sorted newest -> oldest.
        Returns [] when no breaches are found (not an error).
        """
        if not emails:
            return []

        all_breaches: list[dict] = []
        seen: set = set()

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for email in emails:
                email = email.strip().lower()
                if not email:
                    continue

                logger.log_action("XposedOrNot: scanning breach databases", target=email)

                try:
                    resp = await client.get(
                        f"{_XON_BASE}/breach-analytics",
                        params={"email": email},
                        headers={"user-agent": _USER_AGENT},
                        timeout=_TIMEOUT,
                    )

                    if resp.status_code == 404:
                        logger.log_success(f"XON: No breaches found for {email}")

                    elif resp.status_code == 200:
                        data = resp.json()

                        # The API may return results under either key
                        breach_list = (
                            data.get("BreachMetrics", {}).get("breaches_details")
                            or data.get("ExposedBreaches", {}).get("breaches_details")
                            or []
                        )

                        for raw in breach_list:
                            name = raw.get("breachID") or raw.get("breach") or ""
                            sig  = f"{email}_{name}"
                            if sig not in seen:
                                seen.add(sig)
                                all_breaches.append(_normalize_breach(raw, email))

                    elif resp.status_code == 429:
                        logger.log_warning("XON: Rate-limited (429). Waiting 5s...")
                        await asyncio.sleep(5)

                    else:
                        logger.log_warning(
                            f"XON: Unexpected HTTP {resp.status_code} for {email}"
                        )

                except httpx.RequestError as exc:
                    logger.log_warning(f"XON network error for {email}: {exc}")

                # Respect rate limit: 2 req/s max
                await asyncio.sleep(_REQ_DELAY)

        if all_breaches:
            logger.log_warning(
                f"THREAT INTEL [XposedOrNot]: "
                f"{len(all_breaches)} breach(es) found for {len(emails)} identifier(s)."
            )
        else:
            logger.log_success(
                f"CLEAR [XposedOrNot]: No public leaks found for {len(emails)} identifier(s)."
            )

        all_breaches.sort(key=lambda x: x.get("BreachDate", ""), reverse=True)
        return all_breaches


# Module-level singleton
breach_service = BreachService()

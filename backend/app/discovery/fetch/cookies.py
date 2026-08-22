"""Cookies earned by one tier, spent by the other.

The expensive thing the browser tier does is not rendering — it is *passing*.
Solving a Cloudflare interstitial costs 3-8 s and a Chromium page, and the proof
of that work is a cookie (``cf_clearance`` and friends). Before this module that
proof was thrown away when the browser closed, so every search re-solved every
challenge and the cheap HTTP tier never benefited from the expensive one.

Holding the cookies process-wide, keyed on registrable domain, turns a solved
challenge into a shared asset: the same pattern FlareSolverr implements as a
sidecar service, done in-process.

Deliberately **not** a general cookie jar. It stores what a host handed an
anonymous visitor. No user account is ever logged in, so nothing here identifies
a person, and nothing here is written to disk or to a log.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.discovery.fetch.ratelimit import registrable_domain

# A clearance cookie outlives a search but not a day; Cloudflare's own default is
# 30 minutes to a few hours. Serving a stale one just means one wasted cheap
# request that escalates, so err on the long side.
_DEFAULT_TTL_S = 3600.0

# Cookie names worth carrying between tiers. An allow-list rather than "keep
# everything": tracking cookies add fingerprint surface without helping us pass.
_CARRIED_PREFIXES: tuple[str, ...] = (
    "cf_",
    "__cf",
    "csrftoken",
    "datadome",
    "sessionid",
    "mid",
    "ig_did",
    "consent",
    "socs",
    "cookie_consent",
    "euconsent",
    "reddit_session",
    "loid",
    "tt_",
    "msToken",
    "ttwid",
    "pxcts",
    "_px",
)


def is_carried(name: str) -> bool:
    """Whether a cookie name is one we deliberately hand between tiers."""
    lowered = name.strip().lower()
    if not lowered:
        return False
    return any(lowered.startswith(prefix.lower()) for prefix in _CARRIED_PREFIXES)


@dataclass(slots=True)
class DomainCookies:
    """What one host handed us, and the identity that earned it."""

    values: dict[str, str] = field(default_factory=dict)
    useragent: str | None = None
    stored_at: float = 0.0

    def expired(self, *, now: float, ttl: float) -> bool:
        if ttl <= 0:
            return True  # a zero TTL means "never carry anything over"
        return bool(self.stored_at) and (now - self.stored_at) >= ttl


class CookieVault:
    """Per-domain cookie carry-over between fetch tiers and between searches.

    Never raises: a vault problem must degrade to "no cookies", which is exactly
    the behaviour that existed before, and never fail a search.
    """

    def __init__(self, *, enabled: bool = True, ttl_s: float = _DEFAULT_TTL_S) -> None:
        self._enabled = enabled
        self._ttl = ttl_s
        self._by_domain: dict[str, DomainCookies] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def store(
        self,
        url_or_domain: str,
        cookies: Mapping[str, str] | None,
        *,
        useragent: str | None = None,
    ) -> int:
        """Record the carried cookies for a host. Returns how many were kept."""
        if not self._enabled or not cookies:
            return 0
        domain = registrable_domain(url_or_domain)
        if not domain:
            return 0

        kept = {str(k): str(v) for k, v in cookies.items() if k and v and is_carried(str(k))}
        if not kept:
            return 0

        entry = self._by_domain.get(domain)
        if entry is None or entry.expired(now=time.monotonic(), ttl=self._ttl):
            entry = DomainCookies()
            self._by_domain[domain] = entry
        entry.values.update(kept)
        entry.stored_at = time.monotonic()
        if useragent:
            entry.useragent = useragent
        return len(kept)

    def cookies_for(self, url_or_domain: str) -> dict[str, str]:
        """Cookies to send with a request to this host. Empty when we have none."""
        entry = self._entry(url_or_domain)
        return dict(entry.values) if entry else {}

    def useragent_for(self, url_or_domain: str) -> str | None:
        """The UA that earned these cookies.

        Sending a clearance cookie under a different User-Agent than the one it was
        issued to is worse than sending none: it is a mismatch a WAF can see.
        """
        entry = self._entry(url_or_domain)
        return entry.useragent if entry else None

    def clear(self, url_or_domain: str) -> None:
        """Drop a host's cookies — call this when they stopped working."""
        domain = registrable_domain(url_or_domain)
        if domain:
            self._by_domain.pop(domain, None)

    def snapshot(self) -> dict[str, dict[str, object]]:
        """Diagnostics. Reports cookie *names* and counts, never values."""
        now = time.monotonic()
        return {
            domain: {
                "names": sorted(entry.values),
                "age_s": round(now - entry.stored_at, 1) if entry.stored_at else 0.0,
                "has_useragent": entry.useragent is not None,
            }
            for domain, entry in sorted(self._by_domain.items())
        }

    def _entry(self, url_or_domain: str) -> DomainCookies | None:
        if not self._enabled:
            return None
        domain = registrable_domain(url_or_domain)
        if not domain:
            return None
        entry = self._by_domain.get(domain)
        if entry is None:
            return None
        if entry.expired(now=time.monotonic(), ttl=self._ttl):
            self._by_domain.pop(domain, None)
            return None
        return entry


def extract_cookies(response: object) -> dict[str, str]:
    """Best-effort ``{name: value}`` from a Scrapling response.

    ``.cookies`` is a plain dict on the HTTP tier and a list of Playwright cookie
    dicts on the browser tier, so both shapes are handled. Never raises: a shape
    we do not recognise yields nothing rather than aborting the fetch that
    otherwise succeeded.
    """
    raw = getattr(response, "cookies", None)
    if not raw:
        return {}
    out: dict[str, str] = {}
    try:
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key and value is not None:
                    out[str(key)] = str(value)
            return out
        for item in raw:
            if isinstance(item, dict):
                name, value = item.get("name"), item.get("value")
                if name and value is not None:
                    out[str(name)] = str(value)
    except Exception:
        return out
    return out

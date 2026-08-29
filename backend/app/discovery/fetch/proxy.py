"""Optional outbound proxy selection.

Credentials come from the environment only (``discovery_proxy_url`` /
``discovery_proxy_pool``) and are masked before they can reach a log line.
Everything degrades gracefully: no proxy configured means direct connections, and
a proxy that fails is retried once without it rather than killing the search.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Sequence
from urllib.parse import urlsplit, urlunsplit

from app.discovery.fetch.ratelimit import registrable_domain


def mask_proxy(url: str | None) -> str:
    """Render a proxy URL safe to log by stripping userinfo.

    ``http://user:secret@host:8080`` -> ``http://***@host:8080``
    """
    if not url:
        return "none"
    try:
        split = urlsplit(url)
    except ValueError:
        return "***"
    if not split.hostname:
        return "***"
    netloc = split.hostname
    if split.port:
        netloc = f"{netloc}:{split.port}"
    if split.username or split.password:
        netloc = f"***@{netloc}"
    return urlunsplit((split.scheme, netloc, "", "", ""))


class ProxySelector:
    """Decides which proxy (if any) a given URL should go through.

    When ``platforms`` is non-empty the proxy is used *only* for those platforms'
    domains — useful for spending a paid proxy budget on Instagram/TikTok/LinkedIn
    while everything else goes out directly.
    """

    def __init__(
        self,
        *,
        primary: str = "",
        pool: Sequence[str] = (),
        platforms: Sequence[str] = (),
        platform_domains: dict[str, str] | None = None,
    ) -> None:
        candidates = [p.strip() for p in ([primary, *pool] if primary else list(pool)) if p and p.strip()]
        # Preserve order while removing duplicates.
        self._proxies: list[str] = list(dict.fromkeys(candidates))
        self._cycle: Iterator[str] | None = itertools.cycle(self._proxies) if self._proxies else None
        self._platforms = {p.strip().lower() for p in platforms if p and p.strip()}
        self._platform_domains = platform_domains or {}
        self._failed: set[str] = set()

    @property
    def enabled(self) -> bool:
        return bool(self._proxies)

    def _applies_to(self, url: str) -> bool:
        """Empty platform filter means "proxy everything"."""
        if not self._platforms:
            return True
        domain = registrable_domain(url)
        for platform in self._platforms:
            mapped = self._platform_domains.get(platform)
            if mapped and registrable_domain(mapped) == domain:
                return True
            # Fall back to a name match so ``instagram`` works without a mapping.
            if domain.split(".", 1)[0] == platform:
                return True
        return False

    def for_url(self, url: str) -> str | None:
        """Return the proxy to use for ``url``, or None to connect directly."""
        if not self._cycle or not self._applies_to(url):
            return None
        # Skip proxies already known to be dead this run; if all are dead, go direct.
        for _ in range(len(self._proxies)):
            candidate = next(self._cycle)
            if candidate not in self._failed:
                return candidate
        return None

    def mark_failed(self, proxy: str) -> None:
        """Take a proxy out of rotation for the rest of this process."""
        if proxy:
            self._failed.add(proxy)

    def describe(self) -> str:
        """Log-safe summary. Never leaks credentials."""
        if not self._proxies:
            return "proxy: disabled"
        scope = ",".join(sorted(self._platforms)) if self._platforms else "all"
        alive = len(self._proxies) - len(self._failed)
        return f"proxy: {alive}/{len(self._proxies)} alive, scope={scope}, primary={mask_proxy(self._proxies[0])}"

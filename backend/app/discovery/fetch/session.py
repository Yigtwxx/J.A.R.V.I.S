"""The single Scrapling abstraction used by the whole discovery pipeline.

Two transport tiers:

* **HTTP** — a persistent ``FetcherSession`` (curl_cffi with browser TLS
  impersonation). Fast, ~50 ms, no memory cost. Handles most of the web.
* **STEALTH** — ``AsyncStealthySession`` (patchright-driven Chromium; Scrapling
  dropped Camoufox in 0.4). 3-8 s cold start, 50-150 MB per page, solves
  Cloudflare. Reserved for walls that HTTP cannot pass.

The session escalates HTTP -> STEALTH automatically on the signals that actually
mean "you were refused" and never on signals that merely mean "empty". One
browser is created lazily per search: holding one for the process lifetime leaks
memory, while opening one per fetch pays the cold start every time.

Three things make the tiers cooperate rather than merely coexist, which matters
because there is no proxy pool to hide behind:

* the HTTP tier is a *session*, so cookies survive between requests;
* cookies the browser earned — Cloudflare clearance above all — are handed down
  to the HTTP tier through the shared ``CookieVault``, so an expensive challenge
  is solved once and then ridden cheaply;
* the browser reuses a persisted profile directory, so it is not a
  never-before-seen client on every single search.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.discovery.errors import FetchLayerUnavailable
from app.discovery.fetch.cookies import CookieVault, extract_cookies
from app.discovery.fetch.httppool import HttpSessionPool
from app.discovery.fetch.identity import IdentityPicker
from app.discovery.fetch.profiles import BrowserProfilePool
from app.discovery.fetch.proxy import ProxySelector, mask_proxy
from app.discovery.fetch.ratelimit import DomainRateLimiter
from app.discovery.fetch.result import (
    FetchResult,
    classify_http_status,
    detect_block_signal,
)
from app.discovery.fetch.selectors import css_first
from app.discovery.types import FetchStatus, FetchTier
from app.utils.logger import logger

# Process-wide cap on concurrent browsers. Each page is 50-150 MB, so unbounded
# concurrent searches would exhaust 8 GB in about four searches.
_STEALTH_SEMAPHORE: asyncio.Semaphore | None = None
_STEALTH_SEMAPHORE_LOCK = asyncio.Lock()

# HTTP statuses worth a second attempt. Blocked and not-found are authoritative:
# retrying a 403 only deepens the ban, and retrying a 404 is pointless.
_RETRYABLE = frozenset({FetchStatus.TIMEOUT, FetchStatus.ERROR})

# Base seconds for our exponential backoff, jittered so the cadence is not
# machine-perfect. A retry that lands exactly 1.500 s after the failure is a
# signature; a real client's timing wobbles.
_BACKOFF_BASE_S = 1.5
_BACKOFF_JITTER = 0.3


def _retry_delay(attempt: int) -> float:
    """Exponential backoff with jitter, never negative."""
    base = _BACKOFF_BASE_S * (2**attempt)
    return max(0.0, base * random.uniform(1.0 - _BACKOFF_JITTER, 1.0 + _BACKOFF_JITTER))


async def _stealth_semaphore() -> asyncio.Semaphore:
    global _STEALTH_SEMAPHORE
    if _STEALTH_SEMAPHORE is None:
        async with _STEALTH_SEMAPHORE_LOCK:
            if _STEALTH_SEMAPHORE is None:
                limit = max(1, get_settings().discovery_max_concurrent_stealth_sessions)
                _STEALTH_SEMAPHORE = asyncio.Semaphore(limit)
    return _STEALTH_SEMAPHORE


@dataclass(slots=True)
class FetchStats:
    """Per-search accounting, surfaced in the discovery summary."""

    fetches: int = 0
    http_tier: int = 0
    stealth_tier: int = 0
    escalations: int = 0
    blocked: int = 0
    not_found: int = 0
    errors: int = 0
    timeouts: int = 0
    cache_hits: int = 0
    bytes_downloaded: int = 0
    wait_seconds: float = 0.0
    per_domain: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fetches": self.fetches,
            "http_tier": self.http_tier,
            "stealth_tier": self.stealth_tier,
            "escalations": self.escalations,
            "blocked": self.blocked,
            "not_found": self.not_found,
            "errors": self.errors,
            "timeouts": self.timeouts,
            "cache_hits": self.cache_hits,
            "bytes_downloaded": self.bytes_downloaded,
            "wait_seconds": round(self.wait_seconds, 2),
            "per_domain": dict(sorted(self.per_domain.items(), key=lambda kv: -kv[1])[:20]),
        }


class FetchSession:
    """Per-search fetch facade. Construct one per search; never cache it globally."""

    def __init__(
        self,
        *,
        rate_limiter: DomainRateLimiter,
        proxy: ProxySelector | None = None,
        stealth_enabled: bool = True,
        max_stealth_pages: int = 3,
        http_timeout_s: float = 30.0,
        stealth_timeout_ms: int = 60_000,
        cache_size: int = 512,
        max_fetches: int | None = None,
        cookies: CookieVault | None = None,
        profiles: BrowserProfilePool | None = None,
        identity: IdentityPicker | None = None,
        real_chrome: bool = True,
        hide_canvas: bool = False,
    ) -> None:
        self._rate = rate_limiter
        self._proxy = proxy or ProxySelector()
        self._stealth_enabled = stealth_enabled
        self._max_stealth_pages = max(1, max_stealth_pages)
        self._http_timeout_s = http_timeout_s
        self._stealth_timeout_ms = stealth_timeout_ms
        self._max_fetches = max_fetches

        # Shared with the rest of the process: what a host handed us describes
        # that host, not this search. See app/discovery/dependencies.py.
        self._cookies = cookies if cookies is not None else CookieVault(enabled=False)
        self._profiles = profiles
        self._identity = identity or IdentityPicker()
        self._real_chrome = real_chrome
        self._hide_canvas = hide_canvas

        self._http = HttpSessionPool(timeout_s=http_timeout_s, impersonate=self._identity.for_url("").impersonate)

        self._stealth: Any | None = None
        self._stealth_lock = asyncio.Lock()
        self._stealth_unavailable_reason: str | None = None
        self._stealth_slot_held = False
        self._profile_path: Path | None = None

        self._cache: OrderedDict[str, FetchResult] = OrderedDict()
        self._cache_size = cache_size
        self.stats = FetchStats()
        self._closed = False

    # -- lifecycle ------------------------------------------------------------

    async def __aenter__(self) -> FetchSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Tear down the browser and HTTP sessions. Safe to call twice.

        Order matters: the HTTP sessions go first because they are cheap and
        cannot fail in a way that would strand the browser slot, and the semaphore
        permit is released last so it is freed even if teardown above misbehaved.
        """
        if self._closed:
            return
        self._closed = True

        await self._http.aclose()

        stealth, self._stealth = self._stealth, None
        if stealth is not None:
            try:
                await stealth.__aexit__(None, None, None)
            except Exception as exc:  # a browser that fails to close must not fail the search
                logger.log_warning(f"Stealth session close failed: {exc}", broadcast=False)

        if self._profiles is not None and self._profile_path is not None:
            path, self._profile_path = self._profile_path, None
            await self._profiles.release(path)

        if self._stealth_slot_held:
            self._stealth_slot_held = False
            (await _stealth_semaphore()).release()

    # -- public API -----------------------------------------------------------

    async def get(
        self,
        url: str,
        *,
        tier: FetchTier = FetchTier.HTTP,
        escalate: bool = True,
        timeout_s: float | None = None,
        min_html_bytes: int = 2_000,
        expect_selector: str | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
    ) -> FetchResult:
        """Fetch ``url``, escalating to the stealth tier when the HTTP tier is refused.

        Args:
            tier: Starting tier. Pass STEALTH to skip the HTTP attempt entirely.
            escalate: Allow HTTP -> STEALTH promotion.
            min_html_bytes: Below this, a 200 is treated as an interstitial stub.
            expect_selector: When given and absent from a 200, treat it as a stub.
        """
        cached = self._cache.get(url) if use_cache else None
        if cached is not None:
            self._cache.move_to_end(url)
            self.stats.cache_hits += 1
            return cached

        if self._max_fetches is not None and self.stats.fetches >= self._max_fetches:
            return FetchResult.failure(url, FetchStatus.ERROR, tier=tier, error="fetch budget exhausted")

        if tier is FetchTier.STEALTH:
            result = await self._fetch_stealth(url, timeout_ms=None, headers=headers)
        else:
            result = await self._fetch_http(url, timeout_s=timeout_s, headers=headers)
            if escalate and self._should_escalate(
                result, min_html_bytes=min_html_bytes, expect_selector=expect_selector
            ):
                self.stats.escalations += 1
                promoted = await self._fetch_stealth(
                    url,
                    timeout_ms=None,
                    headers=headers,
                    solve_cloudflare=result.block_signal == "cf_challenge",
                )
                # Only keep the promotion when it actually improved matters — a
                # stealth error must not mask a usable (if thin) HTTP response.
                if promoted.ok or not result.ok:
                    result = promoted

        self._record(result)
        if use_cache:
            self._cache[url] = result
            self._cache.move_to_end(url)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result

    async def get_json(
        self,
        url: str,
        *,
        tier: FetchTier = FetchTier.HTTP,
        timeout_s: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[FetchResult, Any | None]:
        """Fetch and parse JSON. Returns ``(result, parsed_or_None)``.

        A parse failure leaves the result untouched — callers can still inspect the
        status to tell "not found" from "blocked" from "served us HTML".
        """
        result = await self.get(
            url,
            tier=tier,
            escalate=False,
            timeout_s=timeout_s,
            min_html_bytes=0,
            headers={"Accept": "application/json", **(headers or {})},
        )
        if not result.html:
            return result, None
        import json as _json

        try:
            return result, _json.loads(result.html)
        except (ValueError, TypeError):
            return result, None

    async def get_bytes(self, url: str, *, timeout_s: float | None = None) -> tuple[FetchResult, bytes | None]:
        """Fetch a binary asset (avatar images). Returns ``(result, raw_bytes)``."""
        result = await self._fetch_http(url, timeout_s=timeout_s, headers=None, binary=True)
        self._record(result)
        raw = result.page if isinstance(result.page, bytes) else None
        return result, raw

    async def get_many(
        self,
        urls: Sequence[str],
        *,
        tier: FetchTier = FetchTier.HTTP,
        concurrency: int = 4,
        escalate: bool = True,
        expect_selector: str | None = None,
    ) -> list[FetchResult]:
        """Fetch several URLs concurrently, preserving input order.

        Never raises: a failure becomes an ERROR result so the caller still learns
        what happened to every URL.
        """
        if not urls:
            return []
        gate = asyncio.Semaphore(max(1, concurrency))

        async def _one(target: str) -> FetchResult:
            async with gate:
                try:
                    return await self.get(target, tier=tier, escalate=escalate, expect_selector=expect_selector)
                except Exception as exc:
                    return FetchResult.failure(target, FetchStatus.ERROR, tier=tier, error=str(exc))

        return list(await asyncio.gather(*(_one(u) for u in urls)))

    async def stealth(
        self,
        url: str,
        *,
        network_idle: bool = True,
        solve_cloudflare: bool = False,
        wait_selector: str | None = None,
        timeout_ms: int | None = None,
    ) -> FetchResult:
        """Force a stealth-tier fetch, bypassing the HTTP attempt.

        ``solve_cloudflare`` is off unless the caller has a reason: running the
        solver on a page with no challenge is not free, and it is retried on its
        own once the fetch actually lands on one.
        """
        result = await self._fetch_stealth(
            url,
            timeout_ms=timeout_ms,
            headers=None,
            network_idle=network_idle,
            solve_cloudflare=solve_cloudflare,
            wait_selector=wait_selector,
        )
        self._record(result)
        return result

    @property
    def stealth_available(self) -> bool:
        """False once we have learned that no browser can start in this environment."""
        return self._stealth_enabled and self._stealth_unavailable_reason is None

    @property
    def stealth_unavailable_reason(self) -> str | None:
        return self._stealth_unavailable_reason

    # -- tiers ----------------------------------------------------------------

    async def _fetch_http(
        self,
        url: str,
        *,
        timeout_s: float | None,
        headers: dict[str, str] | None,
        binary: bool = False,
    ) -> FetchResult:
        timeout = timeout_s if timeout_s is not None else self._http_timeout_s
        proxy = self._proxy.for_url(url)
        attempts = 0
        started = time.monotonic()
        last: FetchResult | None = None

        # Cookies this host handed us earlier — possibly the clearance the browser
        # tier paid several seconds to earn — plus the User-Agent they were issued
        # to, which has to be presented with them or the pair looks forged.
        carried = self._cookies.cookies_for(url)
        identity = self._identity.for_url(url, useragent=self._cookies.useragent_for(url))

        for attempt in range(3):
            attempts = attempt + 1
            self.stats.wait_seconds += await self._rate.acquire(url)

            kwargs: dict[str, Any] = {
                "timeout": timeout,
                "stealthy_headers": True,
                "follow_redirects": True,
                "impersonate": identity.impersonate,
                "headers": {**identity.headers(), **(headers or {})},
            }
            if carried:
                kwargs["cookies"] = carried
            if proxy:
                kwargs["proxy"] = proxy

            try:
                response = await self._http.get(url, **kwargs)
            except Exception as exc:
                last = self._from_exception(url, exc, FetchTier.HTTP, attempts, started)
                if proxy and _looks_like_proxy_failure(exc):
                    # A dead proxy must not kill the search: drop it and go direct.
                    logger.log_warning(f"Proxy failed ({mask_proxy(proxy)}), retrying direct: {exc}", broadcast=False)
                    self._proxy.mark_failed(proxy)
                    proxy = None
                    continue
                if last.status in _RETRYABLE and attempt < 2:
                    await asyncio.sleep(_retry_delay(attempt))
                    continue
                return last

            result = self._from_response(url, response, FetchTier.HTTP, attempts, started, binary=binary)
            self._maybe_penalize(url, response)
            self._harvest(url, response)
            if result.status in _RETRYABLE and attempt < 2:
                last = result
                await asyncio.sleep(_retry_delay(attempt))
                continue
            return result

        return last or FetchResult.failure(url, FetchStatus.ERROR, tier=FetchTier.HTTP, error="exhausted retries")

    async def _fetch_stealth(
        self,
        url: str,
        *,
        timeout_ms: int | None,
        headers: dict[str, str] | None,
        network_idle: bool = True,
        solve_cloudflare: bool = False,
        wait_selector: str | None = None,
    ) -> FetchResult:
        started = time.monotonic()
        if not self._stealth_enabled:
            return FetchResult.failure(
                url,
                FetchStatus.BLOCKED,
                tier=FetchTier.STEALTH,
                error="stealth tier disabled (discovery_stealth_enabled=false)",
                block_signal="stealth_disabled",
            )
        if self._stealth_unavailable_reason:
            return FetchResult.failure(
                url,
                FetchStatus.BLOCKED,
                tier=FetchTier.STEALTH,
                error=self._stealth_unavailable_reason,
                block_signal="stealth_unavailable",
            )

        try:
            session = await self._ensure_stealth()
        except FetchLayerUnavailable as exc:
            return FetchResult.failure(
                url,
                FetchStatus.BLOCKED,
                tier=FetchTier.STEALTH,
                error=str(exc),
                block_signal="stealth_unavailable",
            )

        self.stats.wait_seconds += await self._rate.acquire(url)
        kwargs: dict[str, Any] = {
            "timeout": timeout_ms or self._stealth_timeout_ms,
            "network_idle": network_idle,
            "solve_cloudflare": solve_cloudflare,
        }
        if wait_selector:
            kwargs["wait_selector"] = wait_selector
        if headers:
            kwargs["extra_headers"] = headers
        proxy = self._proxy.for_url(url)
        if proxy:
            kwargs["proxy"] = proxy

        try:
            response = await session.fetch(url, **kwargs)
        except Exception as exc:
            return self._from_exception(url, exc, FetchTier.STEALTH, 1, started)

        # The point of paying for a browser is the cookies it walks away with.
        self._harvest(url, response, browser=True)
        result = self._from_response(url, response, FetchTier.STEALTH, 1, started)

        # Scrapling's solver waits for network idle before it even looks for a
        # challenge, so arming it up front taxes every ordinary page and logs a
        # spurious error on each one. Pay for it only once the page in hand is
        # demonstrably a challenge, and only once — a second miss is a wall we
        # are not getting through.
        if result.block_signal == "cf_challenge" and not solve_cloudflare:
            return await self._fetch_stealth(
                url,
                timeout_ms=timeout_ms,
                headers=headers,
                network_idle=network_idle,
                solve_cloudflare=True,
                wait_selector=wait_selector,
            )
        return result

    async def _ensure_stealth(self) -> Any:
        """Start the browser on first use, at most once, under a process-wide cap."""
        if self._stealth is not None:
            return self._stealth
        async with self._stealth_lock:
            if self._stealth is not None:
                return self._stealth
            if self._stealth_unavailable_reason:
                raise FetchLayerUnavailable(self._stealth_unavailable_reason)

            try:
                from scrapling.fetchers import AsyncStealthySession
            except Exception as exc:
                self._stealth_unavailable_reason = (
                    f"Scrapling stealth tier not importable ({exc}). "
                    "Fix with: pip install 'scrapling[fetchers]' && scrapling install"
                )
                raise FetchLayerUnavailable(self._stealth_unavailable_reason) from exc

            semaphore = await _stealth_semaphore()
            await semaphore.acquire()
            self._stealth_slot_held = True

            # One profile per semaphore permit: Chromium takes an exclusive lock on
            # a user-data directory, so sharing one would make the second concurrent
            # search fail to start a browser at all.
            if self._profiles is not None:
                self._profile_path = await self._profiles.lease()

            # The real Chrome is a better fingerprint than bundled Chromium, but it
            # does not exist in the Docker image. Try it, then fall back once —
            # losing the whole stealth tier over a missing channel would be a far
            # worse trade than launching plain Chromium.
            last_exc: Exception | None = None
            for use_real_chrome in (self._real_chrome, False):
                try:
                    session = AsyncStealthySession(**self._stealth_kwargs(real_chrome=use_real_chrome))
                    self._stealth = await session.__aenter__()
                    return self._stealth
                except Exception as exc:
                    last_exc = exc
                    if use_real_chrome and self._real_chrome:
                        logger.log_warning(
                            f"Browser launch with the real Chrome failed ({exc}); retrying with bundled Chromium",
                            broadcast=False,
                        )
                        continue
                    break

            # A profile we leased may be what poisoned the launch; reset it so the
            # next search does not inherit the same broken directory.
            if self._profiles is not None and self._profile_path is not None:
                path, self._profile_path = self._profile_path, None
                await self._profiles.evict(path)

            semaphore.release()
            self._stealth_slot_held = False
            self._stealth_unavailable_reason = (
                f"Browser failed to start ({last_exc}). "
                "Fix with: scrapling install — discovery continues on the HTTP tier."
            )
            logger.log_warning(self._stealth_unavailable_reason, broadcast=False)
            raise FetchLayerUnavailable(self._stealth_unavailable_reason) from last_exc

    def _stealth_kwargs(self, *, real_chrome: bool) -> dict[str, Any]:
        """Launch options for the browser tier.

        ``allow_webgl`` is deliberately left at Scrapling's default of True: its
        own docs note that disabling WebGL is itself detected by many WAFs.
        """
        kwargs: dict[str, Any] = {
            "max_pages": self._max_stealth_pages,
            "headless": True,
            "block_webrtc": True,
            # Canvas noise is re-randomised per request, which contradicts the
            # stable fingerprint a persisted profile is there to provide.
            "hide_canvas": self._hide_canvas,
            "disable_resources": False,
            "timeout": self._stealth_timeout_ms,
        }
        if real_chrome:
            kwargs["real_chrome"] = True
        if self._profile_path is not None:
            kwargs["user_data_dir"] = str(self._profile_path)
        return kwargs

    # -- helpers --------------------------------------------------------------

    def _should_escalate(
        self,
        result: FetchResult,
        *,
        min_html_bytes: int,
        expect_selector: str | None,
    ) -> bool:
        """Promote to stealth only on signals that mean "refused", never "empty"."""
        if not self.stealth_available:
            return False
        if result.status is FetchStatus.NOT_FOUND:
            return False  # authoritative; a browser will not change a 404
        if result.status in (FetchStatus.BLOCKED, FetchStatus.TIMEOUT, FetchStatus.ERROR):
            return True
        if result.block_signal:
            return True
        if min_html_bytes and result.html_len < min_html_bytes:
            return True
        # A 200 that lacks the marker the caller expected is an interstitial stub.
        return bool(expect_selector and css_first(result.page, expect_selector) is None)

    def _from_response(
        self,
        url: str,
        response: Any,
        tier: FetchTier,
        attempts: int,
        started: float,
        *,
        binary: bool = False,
    ) -> FetchResult:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        code = int(getattr(response, "status", 0) or 0)
        final_url = str(getattr(response, "url", url) or url)

        if binary:
            body = getattr(response, "body", None)
            raw = body if isinstance(body, bytes) else (body or b"")
            status = classify_http_status(code) if code else FetchStatus.ERROR
            return FetchResult(
                url=url,
                final_url=final_url,
                status=status,
                http_status=code or None,
                html=None,
                page=raw if status is FetchStatus.OK else None,
                tier=tier,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
                block_signal=detect_block_signal(http_status=code, final_url=final_url, html=None),
            )

        html = self._body_text(response)
        status = classify_http_status(code) if code else FetchStatus.ERROR
        block_signal = detect_block_signal(http_status=code, final_url=final_url, html=html)

        # A 200 that is really a consent wall or a login bounce is BLOCKED, not OK.
        # Cloudflare's challenge markers alone are only an escalation hint at the
        # HTTP tier; after the stealth tier has already seen them, they are real.
        if (
            status is FetchStatus.OK
            and block_signal in ("consent_redirect", "login_redirect", "http_999")
            or status is FetchStatus.OK
            and block_signal == "cf_challenge"
            and tier is FetchTier.STEALTH
        ):
            status = FetchStatus.BLOCKED

        return FetchResult(
            url=url,
            final_url=final_url,
            status=status,
            http_status=code or None,
            html=html,
            page=response if status is FetchStatus.OK else None,
            tier=tier,
            attempts=attempts,
            elapsed_ms=elapsed_ms,
            block_signal=block_signal,
        )

    def _from_exception(
        self,
        url: str,
        exc: Exception,
        tier: FetchTier,
        attempts: int,
        started: float,
    ) -> FetchResult:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        text = str(exc).lower()
        timed_out = isinstance(exc, TimeoutError | asyncio.TimeoutError) or "timeout" in text or "timed out" in text
        return FetchResult.failure(
            url,
            FetchStatus.TIMEOUT if timed_out else FetchStatus.ERROR,
            tier=tier,
            error=f"{type(exc).__name__}: {exc}"[:400],
            attempts=attempts,
            elapsed_ms=elapsed_ms,
        )

    def _harvest(self, url: str, response: Any, *, browser: bool = False) -> None:
        """Bank whatever cookies this response carried, for both tiers to reuse.

        Only the browser tier's User-Agent is recorded: it is a real browser UA
        that the HTTP tier can then present alongside the cookies. curl generates
        its own UA from the impersonation profile, so recording that one would
        pin us to a string we do not actually control.
        """
        if not self._cookies.enabled:
            return
        try:
            cookies = extract_cookies(response)
            if not cookies:
                return
            useragent = _request_useragent(response) if browser else None
            self._cookies.store(url, cookies, useragent=useragent)
        except Exception as exc:  # harvesting is a bonus; never fail a good fetch
            logger.log_warning(f"Cookie harvest failed for {url}: {exc}", broadcast=False)

    def _maybe_penalize(self, url: str, response: Any) -> None:
        """Respect ``Retry-After`` so the next round does not walk into the same wall."""
        headers = getattr(response, "headers", None)
        if not headers:
            return
        try:
            raw = headers.get("Retry-After") or headers.get("retry-after")
        except Exception:
            return
        if not raw:
            return
        try:
            self._rate.penalize(url, min(300.0, float(str(raw).strip())))
        except (TypeError, ValueError):
            return

    @staticmethod
    def _body_text(response: Any) -> str | None:
        """The unmodified response body.

        ``.body`` must be preferred over ``.html_content``: Scrapling parses every
        response as HTML, so a JSON body comes back from ``html_content`` wrapped in
        ``<html><body><p>…</p></body></html>``, which then fails ``json.loads``.
        The raw body also keeps script contents byte-exact, which the embedded-JSON
        regexes (``ytInitialData`` and friends) depend on.

        ``Response.text`` is *element* text in Scrapling, never the body.
        """
        for attribute in ("body", "html_content"):
            value = getattr(response, attribute, None)
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            if isinstance(value, str) and value:
                return value
        return None

    def _record(self, result: FetchResult) -> None:
        from app.discovery.fetch.ratelimit import registrable_domain

        self.stats.fetches += 1
        if result.tier is FetchTier.STEALTH:
            self.stats.stealth_tier += 1
        else:
            self.stats.http_tier += 1
        if result.status is FetchStatus.BLOCKED:
            self.stats.blocked += 1
            # Teach the limiter that this cadence was rejected. Synthetic blocks
            # never touched the network, so they must not slow the host down.
            if result.http_status or result.tier is FetchTier.HTTP:
                self._rate.note_blocked(result.url)
        elif result.status is FetchStatus.NOT_FOUND:
            self.stats.not_found += 1
            self._rate.note_ok(result.url)
        elif result.status is FetchStatus.TIMEOUT:
            self.stats.timeouts += 1
        elif result.status is FetchStatus.ERROR:
            self.stats.errors += 1
        else:
            self._rate.note_ok(result.url)
        self.stats.bytes_downloaded += result.html_len
        domain = registrable_domain(result.url)
        if domain:
            self.stats.per_domain[domain] = self.stats.per_domain.get(domain, 0) + 1


def _request_useragent(response: Any) -> str | None:
    """The User-Agent the browser actually sent.

    Scrapling exposes it as ``Response.request_headers``
    (``scrapling/engines/toolbelt/convertor.py``). Header names arrive lowercased
    from CDP but are matched case-insensitively here anyway.
    """
    headers = getattr(response, "request_headers", None)
    if not headers:
        return None
    try:
        for key, value in dict(headers).items():
            if str(key).lower() == "user-agent" and value:
                return str(value)
    except Exception:
        return None
    return None


def _looks_like_proxy_failure(exc: Exception) -> bool:
    """Heuristic: did this failure come from the proxy rather than the target?"""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in ("proxy", "tunnel", "407", "connect failed", "socks"))


def build_proxy_selector(platform_domains: dict[str, str] | None = None) -> ProxySelector:
    """Construct the configured proxy selector from settings."""
    settings = get_settings()
    return ProxySelector(
        primary=settings.discovery_proxy_url,
        pool=settings.discovery_proxy_pool,
        platforms=settings.discovery_proxy_platforms,
        platform_domains=platform_domains,
    )

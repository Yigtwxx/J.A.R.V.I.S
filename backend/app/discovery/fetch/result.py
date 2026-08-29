"""The single return type of every fetch in the discovery pipeline.

There is deliberately no "empty page" representation that a caller could confuse
with success: a FetchResult always carries a FetchStatus, and callers must branch
on it. This is what makes "nothing is ever silently empty" structural rather than
a convention someone can forget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.discovery.types import FetchStatus, FetchTier

# Substrings that mark an anti-bot interstitial rather than real content. Used
# ONLY to decide whether to escalate to the stealth tier — never to conclude that
# a profile does not exist.
_CHALLENGE_MARKERS: tuple[str, ...] = (
    "cf-browser-verification",
    "__cf_chl_",
    "cf-please-wait",
    "cf_chl_opt",
    "just a moment...",
    "checking your browser",
    "enable javascript and cookies to continue",
    "px-captcha",
    "captcha-delivery.com",
    "g-recaptcha",
)

# Hosts that serve a consent / interstitial page instead of the requested content.
_INTERSTITIAL_HOSTS: frozenset[str] = frozenset(
    {
        "consent.google.com",
        "consent.youtube.com",
        "sorry.google.com",
        "ipv4.google.com",
    }
)

# Path prefixes that mean "you were bounced to a login wall".
_LOGIN_PATHS: tuple[str, ...] = (
    "/login",
    "/accounts/login",
    "/authwall",
    "/uas/login",
    "/checkpoint",
    "/signin",
    "/sign-in",
    "/i/flow/login",
)


@dataclass(slots=True, frozen=True)
class FetchResult:
    """Outcome of one fetch attempt chain (including any tier escalation)."""

    url: str
    final_url: str
    status: FetchStatus
    http_status: int | None = None
    html: str | None = None
    page: Any | None = None
    """Scrapling ``Selector``/``Response``. Untyped because scrapling is optional at import time."""

    tier: FetchTier = FetchTier.HTTP
    attempts: int = 1
    elapsed_ms: int = 0
    error: str | None = None
    block_signal: str | None = None
    """Why we think we were blocked: ``cf_challenge`` | ``consent_redirect`` | ``http_999`` | ``login_redirect``."""

    robots_disallowed: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def ok(self) -> bool:
        """True only when we actually have a parseable document."""
        return self.status is FetchStatus.OK and self.page is not None

    @property
    def blocked(self) -> bool:
        return self.status is FetchStatus.BLOCKED

    @property
    def html_len(self) -> int:
        return len(self.html or "")

    def describe(self) -> str:
        """One-line human-readable explanation, surfaced as ``status_detail`` in the API."""
        if self.status is FetchStatus.OK:
            return f"HTTP {self.http_status} via {self.tier}"
        if self.status is FetchStatus.NOT_FOUND:
            return f"HTTP {self.http_status or 404} — not found"
        if self.status is FetchStatus.BLOCKED:
            signal = self.block_signal or "anti-bot"
            return f"blocked ({signal}, HTTP {self.http_status or '?'}) via {self.tier}"
        if self.status is FetchStatus.TIMEOUT:
            return f"timed out after {self.elapsed_ms} ms via {self.tier}"
        return f"error via {self.tier}: {self.error or 'unknown'}"

    @classmethod
    def failure(
        cls,
        url: str,
        status: FetchStatus,
        *,
        tier: FetchTier,
        error: str | None = None,
        http_status: int | None = None,
        block_signal: str | None = None,
        attempts: int = 1,
        elapsed_ms: int = 0,
    ) -> FetchResult:
        """Build a non-OK result. Convenience so callers never hand-roll one."""
        return cls(
            url=url,
            final_url=url,
            status=status,
            http_status=http_status,
            tier=tier,
            attempts=attempts,
            elapsed_ms=elapsed_ms,
            error=error,
            block_signal=block_signal,
        )


def classify_http_status(code: int) -> FetchStatus:
    """Map an HTTP status onto a FetchStatus.

    Only codes that genuinely carry meaning are interpreted:

    * 404/410 are authoritative absence.
    * 403/429/503 and LinkedIn's non-standard 999 mean "we were refused" — which
      says nothing about whether the resource exists. Never EXISTS, never NOT_FOUND.
    """
    if 200 <= code < 300:
        return FetchStatus.OK
    if code in (404, 410):
        return FetchStatus.NOT_FOUND
    if code in (401, 403, 429, 451, 503, 999):
        return FetchStatus.BLOCKED
    if code >= 500:
        return FetchStatus.ERROR
    if 300 <= code < 400:
        # Only seen when redirects are disabled; treat as inconclusive.
        return FetchStatus.OK
    return FetchStatus.ERROR


def detect_block_signal(*, http_status: int | None, final_url: str, html: str | None) -> str | None:
    """Return a block-signal name when the response looks like an anti-bot wall.

    Checked in order of certainty. Returns None when nothing suspicious is found.
    """
    if http_status == 999:
        return "http_999"

    split = urlsplit(final_url or "")
    host = (split.hostname or "").lower()
    path = (split.path or "").lower()

    if host in _INTERSTITIAL_HOSTS or path.startswith("/sorry/"):
        return "consent_redirect"
    if any(path.startswith(p) for p in _LOGIN_PATHS):
        return "login_redirect"

    if html:
        lowered = html[:200_000].lower()
        if any(marker in lowered for marker in _CHALLENGE_MARKERS):
            return "cf_challenge"

    if http_status in (401, 403, 429, 451, 503):
        return "http_refused"
    return None


def is_login_redirect(final_url: str) -> bool:
    """True when a URL was redirected onto a login/auth wall."""
    path = (urlsplit(final_url or "").path or "").lower()
    return any(path.startswith(p) for p in _LOGIN_PATHS)

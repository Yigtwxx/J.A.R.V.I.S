"""Does `platform:username` exist?

The old implementation answered this with `_is_url_active`, which returned True on
HTTP 403 and 429 ("bot-blocked but the profile probably exists") and then
string-matched an English "not found" phrase list against the first 5 KB. Both
choices manufactured profiles: every platform that rate-limits bots produced
false positives, and every non-English locale produced false negatives.

This module answers structurally instead, in strict priority order:

1. A dedicated JSON/XML/RSS oracle — no HTML involved at all.
2. HTTP status, but only the codes that genuinely carry meaning.
3. Where the redirect landed.
4. Structural markers on a 200 (canonical URL, JSON-LD, embedded JSON, og:image).
5. One stealth escalation; still nothing conclusive -> AMBIGUOUS, surfaced as a
   "possible match" and never dropped.

`BLOCKED` is never `EXISTS` and never `NOT_FOUND`. Absence of proof is not proof
of absence, and it is certainly not proof of presence.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.discovery.fetch.result import FetchResult, is_login_redirect
from app.discovery.fetch.selectors import (
    canonical_url,
    dig,
    embedded_json,
    json_ld_of_type,
    meta_content,
    script_json,
)
from app.discovery.fetch.session import FetchSession
from app.discovery.platforms.registry import (
    DISCOVERY_ONLY_PLATFORMS,
    UNSUPPORTED_PLATFORMS,
    PlatformRegistry,
)
from app.discovery.platforms.spec import OracleRoute, PlatformSpec
from app.discovery.types import ExistenceVerdict, FetchStatus, FetchTier

# Paths a platform redirects to when the handle does not exist (as opposed to
# when we are refused). Landing on the site root is the classic "no such user".
_ABSENT_PATHS: tuple[str, ...] = ("/", "/explore", "/search", "/home", "/404", "/error")


@dataclass(slots=True, frozen=True)
class ExistenceResult:
    """Outcome of one existence check, with the evidence for the verdict."""

    platform: str
    username: str
    url: str
    verdict: ExistenceVerdict
    http_status: int | None = None
    signals: tuple[str, ...] = ()
    """Human-readable reasons, shown in the UI: "HTTP 200", "canonical path matches @jdoe"."""

    tier_used: FetchTier = FetchTier.HTTP
    detail: str = ""
    fetch: FetchResult | None = None
    """Kept so the extractor can reuse the page instead of fetching it twice."""

    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def exists(self) -> bool:
        return self.verdict is ExistenceVerdict.EXISTS

    @property
    def usable(self) -> bool:
        """Worth running the extractor on: confirmed, or unconfirmed but present."""
        return self.verdict in (ExistenceVerdict.EXISTS, ExistenceVerdict.AMBIGUOUS)

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.username.lower()}"


class ExistenceChecker:
    """Verifies handles against a platform catalogue. Stateless apart from budgets."""

    def __init__(self, fetch: FetchSession, registry: PlatformRegistry) -> None:
        self._fetch = fetch
        self._registry = registry
        self._spent: dict[str, int] = {}

    async def check(self, platform: str, username: str, *, allow_stealth: bool = True) -> ExistenceResult:
        """Verify one handle. Never raises — every failure becomes a verdict.

        Args:
            allow_stealth: Whether this handle has earned a browser. Blind username
                permutations must pass False: a search generates dozens of guesses,
                and a browser page costs 3-8 s and 50-150 MB, so escalating every
                guess turns a 60 s round into a 20 minute one for no extra signal.
                Handles that came from a search hit, the user, or another platform
                pass True.
        """
        url = ""
        try:
            if platform in UNSUPPORTED_PLATFORMS:
                return ExistenceResult(
                    platform=platform,
                    username=username,
                    url="",
                    verdict=ExistenceVerdict.UNSUPPORTED,
                    signals=("platform has no public profile surface",),
                    detail="no public surface without authentication",
                )

            if platform in DISCOVERY_ONLY_PLATFORMS:
                # A backstop, not the enforcement point: `seeds` never generates
                # these pairs and `DiscoveryRound._verify` never forwards them.
                # It matters that the answer is not phrased as absence — a handle
                # here is found from an indexed URL, and every probe answers the
                # same whether the account is real or invented.
                return ExistenceResult(
                    platform=platform,
                    username=username,
                    url=self._registry.get(platform).profile_for(username) if self._registry.get(platform) else "",
                    verdict=ExistenceVerdict.UNSUPPORTED,
                    signals=("not probed: no anonymous route can confirm a handle here",),
                    detail=DISCOVERY_ONLY_PLATFORMS[platform],
                )

            spec = self._registry.get(platform)
            if spec is None or not spec.is_supported:
                return ExistenceResult(
                    platform=platform,
                    username=username,
                    url="",
                    verdict=ExistenceVerdict.UNSUPPORTED,
                    signals=("unknown platform",),
                )

            url = spec.profile_for(username)
            if not spec.accepts_username(username):
                # An illegal handle cannot exist; that is authoritative, not an error.
                return ExistenceResult(
                    platform=platform,
                    username=username,
                    url=url,
                    verdict=ExistenceVerdict.NOT_FOUND,
                    signals=(f"'{username}' is not a legal {spec.display} username",),
                    detail="username violates platform charset/length rules",
                )

            if self._budget_exhausted(spec):
                return ExistenceResult(
                    platform=platform,
                    username=username,
                    url=url,
                    verdict=ExistenceVerdict.BLOCKED,
                    signals=(f"per-session fetch cap ({spec.max_fetches_per_session}) reached",),
                    detail="rate-discipline cap; not evidence of absence",
                )

            if spec.oracle_routes():
                oracle = await self._check_oracle(spec, username, url)
                if oracle is not None:
                    return oracle

            if not allow_stealth and spec.fetch_tier is FetchTier.STEALTH:
                # A stealth-only platform cannot be probed cheaply. Report that
                # honestly rather than guessing — an unchecked handle is "blocked",
                # never "not found".
                return ExistenceResult(
                    platform=platform,
                    username=username,
                    url=url,
                    verdict=ExistenceVerdict.BLOCKED,
                    signals=("skipped: browser tier reserved for corroborated handles",),
                    detail="not checked — this platform needs a browser, kept for handles with support",
                )

            return await self._check_page(spec, username, url, allow_stealth=allow_stealth)
        except Exception as exc:  # a single bad handle must not abort the round
            return ExistenceResult(
                platform=platform,
                username=username,
                url=url,
                verdict=ExistenceVerdict.ERROR,
                signals=(f"{type(exc).__name__}: {exc}"[:200],),
                detail="unexpected error during existence check",
            )

    async def check_many(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        concurrency: int = 6,
        stealth_allowed: Collection[tuple[str, str]] | None = None,
    ) -> list[ExistenceResult]:
        """Verify many handles concurrently, preserving input order.

        ``stealth_allowed`` names the pairs that have earned a browser. When it is
        None every pair may escalate; when it is given, everything outside it is
        checked over plain HTTP only.
        """
        if not pairs:
            return []
        gate = asyncio.Semaphore(max(1, concurrency))

        async def _one(platform: str, username: str) -> ExistenceResult:
            async with gate:
                allow = stealth_allowed is None or (platform, username) in stealth_allowed
                return await self.check(platform, username, allow_stealth=allow)

        return list(await asyncio.gather(*(_one(p, u) for p, u in pairs)))

    # -- rule 1: oracle -------------------------------------------------------

    async def _check_oracle(self, spec: PlatformSpec, username: str, profile_url: str) -> ExistenceResult | None:
        """Ask every configured oracle in turn. None means "fall through to the page".

        A refused oracle ends that *route*, not the question. Reddit answers
        ``/about.json`` with 403 from a residential IP while serving the same
        account's ``.rss`` feed with 200, so stopping at the first refusal
        discarded an answer we could still have had.

        The first refusal is remembered and returned only if every route is
        exhausted, so a blocked platform still reports BLOCKED rather than
        silently degrading into "we did not look".
        """
        routes = spec.oracle_routes()
        if not routes:
            return None

        refused: ExistenceResult | None = None
        for route in routes:
            self._spend(spec)
            outcome = await self._ask_oracle(spec, username, profile_url, route)
            if outcome is None:
                continue  # unusable answer; try the next route, then the page

            # An alternate route we only partly trust may confirm an account, but
            # it may never be the reason we call one absent. Invariant 1.
            if outcome.verdict is ExistenceVerdict.NOT_FOUND and not route.authoritative:
                continue
            if outcome.verdict in (ExistenceVerdict.BLOCKED, ExistenceVerdict.ERROR):
                refused = refused or outcome
                continue
            return outcome

        return refused

    async def _ask_oracle(
        self, spec: PlatformSpec, username: str, profile_url: str, route: OracleRoute
    ) -> ExistenceResult | None:
        """One oracle route. None means it gave us nothing usable."""
        oracle_url = route.for_username(username)
        tag = f"oracle[{route.label}]" if route.label else "oracle"

        def status_signal(result: FetchResult, verdict: ExistenceVerdict) -> str:
            """Describe *why*, not just what the transport thought.

            A code this route treats as absence would otherwise be reported with
            the transport's own wording — TikTok's embed answers 400 for a missing
            handle, which the generic classifier calls an error, and "error" is the
            wrong thing to show a user next to a NOT_FOUND verdict.
            """
            if verdict is ExistenceVerdict.NOT_FOUND and result.http_status in route.not_found_status:
                return f"{tag} answered HTTP {result.http_status} — this endpoint's 'no such account'"
            return f"{tag} {result.describe()}"

        if route.kind == "json":
            result, payload = await self._fetch.get_json(oracle_url)
            verdict = self._verdict_from_status(spec, result, not_found_status=route.not_found_status)
            if verdict is not None and verdict is not ExistenceVerdict.EXISTS:
                return self._build(spec, username, profile_url, verdict, result, (status_signal(result, verdict),))
            if payload is None:
                return None  # served us something unparseable; fall back to the page
            if route.absent_path and dig(payload, route.absent_path) is not None:
                return self._build(
                    spec,
                    username,
                    profile_url,
                    ExistenceVerdict.NOT_FOUND,
                    result,
                    (f"{tag} reports absence at '{route.absent_path}'",),
                )
            if route.exists_path:
                found = dig(payload, route.exists_path)
                if found not in (None, "", [], {}):
                    return self._build(
                        spec,
                        username,
                        profile_url,
                        ExistenceVerdict.EXISTS,
                        result,
                        (f"{tag} JSON has '{route.exists_path}'",),
                    )
                return self._build(
                    spec,
                    username,
                    profile_url,
                    ExistenceVerdict.NOT_FOUND,
                    result,
                    (f"{tag} JSON lacks '{route.exists_path}'",),
                )
            return self._build(spec, username, profile_url, ExistenceVerdict.EXISTS, result, (f"{tag} returned JSON",))

        result = await self._fetch.get(oracle_url, escalate=False, min_html_bytes=0)
        verdict = self._verdict_from_status(spec, result, not_found_status=route.not_found_status)
        if verdict is not None and verdict is not ExistenceVerdict.EXISTS:
            return self._build(spec, username, profile_url, verdict, result, (status_signal(result, verdict),))
        if not result.ok:
            return None

        if route.kind == "embedded_json":
            payload = script_json(result.page, route.selector) if route.selector else None
            if payload is None:
                return None
            if route.exists_path and _dig_escaped(payload, route.exists_path) is None:
                # The page rendered but carries no profile. Not authoritative on its
                # own — the status code above already spoke for absence.
                return None
            return self._build(
                spec,
                username,
                profile_url,
                ExistenceVerdict.EXISTS,
                result,
                (f"{tag} embedded JSON has '{route.exists_path or 'a profile'}'",),
            )

        body = result.html or ""
        if route.kind == "xml":
            if route.absent_path and re.search(rf"<{re.escape(route.absent_path)}\b", body, re.I):
                return self._build(
                    spec,
                    username,
                    profile_url,
                    ExistenceVerdict.NOT_FOUND,
                    result,
                    (f"{tag} XML contains <{route.absent_path}>",),
                )
            if route.exists_path and re.search(rf"<{re.escape(route.exists_path)}\b", body, re.I):
                return self._build(
                    spec,
                    username,
                    profile_url,
                    ExistenceVerdict.EXISTS,
                    result,
                    (f"{tag} XML contains <{route.exists_path}>",),
                )
            return None
        if route.kind == "rss":
            if "<rss" in body[:2000].lower() or "<feed" in body[:2000].lower():
                return self._build(
                    spec, username, profile_url, ExistenceVerdict.EXISTS, result, (f"{tag} feed exists",)
                )
            return None
        # "status": a 2xx from the oracle is itself the answer.
        return self._build(
            spec, username, profile_url, ExistenceVerdict.EXISTS, result, (f"{tag} {result.describe()}",)
        )

    # -- rules 2-5: the profile page -----------------------------------------

    async def _check_page(
        self, spec: PlatformSpec, username: str, url: str, *, allow_stealth: bool = True
    ) -> ExistenceResult:
        self._spend(spec)
        result = await self._fetch.get(
            url,
            tier=spec.fetch_tier if allow_stealth else FetchTier.HTTP,
            escalate=spec.escalate and allow_stealth,
            min_html_bytes=1_500,
        )

        verdict = self._verdict_from_status(spec, result)
        if verdict is ExistenceVerdict.NOT_FOUND:
            return self._build(spec, username, url, verdict, result, (result.describe(),))
        if verdict is ExistenceVerdict.BLOCKED:
            return self._build(
                spec,
                username,
                url,
                verdict,
                result,
                (result.describe(), "refused — this says nothing about whether the account exists"),
            )
        if verdict is ExistenceVerdict.ERROR:
            return self._build(spec, username, url, verdict, result, (result.describe(),))

        # rule 3: where did we land?
        redirect = self._redirect_verdict(result, url)
        if redirect is not None:
            redirect_verdict, reason = redirect
            return self._build(spec, username, url, redirect_verdict, result, (reason,))

        # rule 4: structural markers
        signals = self._structural_signals(spec, username, result)
        if signals:
            return self._build(spec, username, url, ExistenceVerdict.EXISTS, result, (result.describe(), *signals))

        # rule 5: escalate once, then admit we do not know.
        if allow_stealth and result.tier is FetchTier.HTTP and spec.escalate and self._fetch.stealth_available:
            self._spend(spec)
            promoted = await self._fetch.stealth(url)
            if promoted.ok:
                promoted_signals = self._structural_signals(spec, username, promoted)
                if promoted_signals:
                    return self._build(
                        spec,
                        username,
                        url,
                        ExistenceVerdict.EXISTS,
                        promoted,
                        (promoted.describe(), *promoted_signals),
                    )
                result = promoted
            elif promoted.blocked:
                return self._build(
                    spec,
                    username,
                    url,
                    ExistenceVerdict.BLOCKED,
                    promoted,
                    (promoted.describe(), "stealth escalation also refused"),
                )

        return self._build(
            spec,
            username,
            url,
            ExistenceVerdict.AMBIGUOUS,
            result,
            (result.describe(), "HTTP 200 but no structural marker confirms this handle"),
        )

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _verdict_from_status(
        spec: PlatformSpec, result: FetchResult, *, not_found_status: tuple[int, ...] = ()
    ) -> ExistenceVerdict | None:
        """Map a fetch outcome onto a verdict. None means "keep looking".

        ``not_found_status`` lets one route add codes the platform as a whole does
        not treat as absence — the same code can mean different things at different
        endpoints on the same host.
        """
        codes = not_found_status or spec.not_found_status
        if result.http_status is not None and result.http_status in codes:
            return ExistenceVerdict.NOT_FOUND
        if result.status is FetchStatus.NOT_FOUND:
            return ExistenceVerdict.NOT_FOUND
        if result.status is FetchStatus.BLOCKED:
            return ExistenceVerdict.BLOCKED
        if result.status in (FetchStatus.TIMEOUT, FetchStatus.ERROR):
            return ExistenceVerdict.ERROR
        if result.status is FetchStatus.OK:
            return ExistenceVerdict.EXISTS
        return None

    @staticmethod
    def _redirect_verdict(result: FetchResult, requested: str) -> tuple[ExistenceVerdict, str] | None:
        """A redirect can mean "log in" (blocked) or "no such user" (absent)."""
        final = result.final_url or ""
        if not final or final.rstrip("/") == requested.rstrip("/"):
            return None
        if is_login_redirect(final):
            return ExistenceVerdict.BLOCKED, f"redirected to a login wall ({final})"
        path = (urlsplit(final).path or "/").rstrip("/") or "/"
        if path in _ABSENT_PATHS:
            return ExistenceVerdict.NOT_FOUND, f"redirected away from the profile to {path}"
        return None

    @staticmethod
    def _structural_signals(spec: PlatformSpec, username: str, result: FetchResult) -> tuple[str, ...]:
        """Markers that prove the page really is this handle's profile."""
        page = result.page
        if page is None:
            return ()
        found: list[str] = []
        lowered = username.lower()

        if spec.canonical_check:
            canonical = canonical_url(page)
            if canonical and lowered in canonical.lower():
                found.append(f"canonical URL matches '{username}'")

        if json_ld_of_type(page, "Person", "ProfilePage", "Organization", "MusicGroup") is not None:
            found.append("JSON-LD profile object present")

        if spec.embedded_json_selector or spec.embedded_json_pattern:
            payload = None
            if spec.embedded_json_selector:
                payload = script_json(page, spec.embedded_json_selector)
            if payload is None and spec.embedded_json_pattern:
                payload = embedded_json(result.html, spec.embedded_json_pattern)
            if payload is not None:
                if spec.embedded_json_path:
                    if _dig_escaped(payload, spec.embedded_json_path) is not None:
                        found.append(f"embedded JSON has '{spec.embedded_json_path}'")
                else:
                    found.append("embedded profile JSON present")

        title = meta_content(page, "og:title", "twitter:title")
        # A page whose title is just the site's own name is the platform's generic
        # shell, served for handles that do not exist. Observed live on Twitch,
        # where it produced confident false positives. Nothing on such a page can
        # prove existence, so every remaining signal is suppressed.
        placeholder = bool(title) and title.strip().lower() in {spec.display.lower(), spec.key.lower()}
        if placeholder:
            return ()

        if spec.og_image_implies_exists and meta_content(page, "og:image", "twitter:image"):
            found.append("og:image present (absent from this platform's 404 page)")

        # A title that carries the handle is weak on its own, but combined with a
        # 200 and no redirect it is a real signal.
        if title and lowered in title.lower():
            found.append(f"page title contains '{username}'")

        return tuple(found)

    def _budget_exhausted(self, spec: PlatformSpec) -> bool:
        cap = spec.max_fetches_per_session
        return cap is not None and self._spent.get(spec.key, 0) >= cap

    def _spend(self, spec: PlatformSpec) -> None:
        self._spent[spec.key] = self._spent.get(spec.key, 0) + 1

    @staticmethod
    def _build(
        spec: PlatformSpec,
        username: str,
        url: str,
        verdict: ExistenceVerdict,
        result: FetchResult,
        signals: tuple[str, ...],
    ) -> ExistenceResult:
        return ExistenceResult(
            platform=spec.key,
            username=username,
            url=url,
            verdict=verdict,
            http_status=result.http_status,
            signals=signals,
            tier_used=result.tier,
            detail=result.describe(),
            fetch=result if result.ok else None,
        )


def _dig_escaped(data: Any, path: str) -> Any:
    """`dig` with two extras: escaped dots, and a ``*`` wildcard segment.

    ``\\.`` keeps a literal dot inside a key: TikTok's payload has the key
    ``webapp.user-detail``, so ``__DEFAULT_SCOPE__.webapp\\.user-detail.userInfo``
    must not split on that dot.

    ``*`` matches any single key or index and returns the first branch where the
    rest of the path resolves. It exists because some payloads key their content by
    the request path — TikTok's embed state nests the profile under
    ``source.data./embed/@<handle>`` — and hard-coding a key that contains the
    handle would break the moment the site normalised its casing.
    """
    parts = re.split(r"(?<!\\)\.", path)
    return _dig_parts(data, parts)


def _dig_parts(current: Any, parts: list[str]) -> Any:
    for index, part in enumerate(parts):
        key = part.replace("\\.", ".")
        if key == "*":
            rest = parts[index + 1 :]
            branches = current.values() if isinstance(current, dict) else current if isinstance(current, list) else ()
            for branch in branches:
                found = _dig_parts(branch, rest)
                if found is not None:
                    return found
            return None
        if isinstance(current, dict):
            if key not in current:
                return None
            current = current[key]
        elif isinstance(current, list) and key.lstrip("-").isdigit():
            position = int(key)
            if -len(current) <= position < len(current):
                current = current[position]
            else:
                return None
        else:
            return None
    return current

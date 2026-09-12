"""Engine pool: fuse what works, retire what does not.

Two mechanisms carry the whole design.

**Reciprocal Rank Fusion** merges the per-engine rankings without ever comparing
their (incomparable) relevance scores::

    score(url) = Σ_engines  1 / (k + rank_engine(url))        with k = 60

Agreement is what it rewards: a URL ranked #1 by two engines scores 2/61, beating
a URL ranked #1 by one engine at 1/61. The constant ``k`` damps the top of each
list so a single engine's #1 cannot dominate the fused order — which is exactly
the property we want when one engine is having a bad day. RRF is also
score-free, so an engine that reports no scores at all still participates fully.

**A circuit breaker** retires an engine after three consecutive refusals. Without
it, a blocked Google costs every subsequent query a full timeout for nothing; with
it, the pool silently narrows to the engines that are actually answering and says
so in ``health()``.

Nothing in here raises. A dead pool returns ``[]`` and ``health()`` explains why.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from app.discovery.engines.base import (
    EngineHealth,
    EngineResult,
    SearchEngine,
    SearchHit,
    dedupe_hits,
    normalize_hit_url,
)
from app.discovery.engines.bing import BingEngine
from app.discovery.engines.brave import BraveEngine
from app.discovery.engines.duckduckgo import DuckDuckGoEngine
from app.discovery.engines.google import GoogleEngine
from app.discovery.engines.mojeek import MojeekEngine
from app.discovery.engines.queries import canonical_query
from app.discovery.engines.startpage import StartpageEngine
from app.utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover - import kept out of the runtime path
    from app.discovery.fetch.session import FetchSession

# Preference order: reliability first, coverage second. Google last because it is
# the one most likely to cost a timeout and return nothing.
#
# Bing sits below Brave and Mojeek despite being the bigger index. Verified live:
# it answers HTTP 200 with well-formed `li.b_algo` rows whose *content is unrelated
# to the query* — three consecutive runs returned three different sets of unrelated
# pages. The parser is fine; Bing is poisoning this client. That failure mode looks
# healthy to the circuit breaker (it is not an error, a block, or an empty page), so
# the only defence is to rank it lower and let RRF dilute it.
PREFERENCE: tuple[str, ...] = ("duckduckgo", "brave", "mojeek", "bing", "startpage", "google")

RRF_K = 60
"""Damping constant of the RRF formula. 60 is the value from the original paper."""

FAILURE_LIMIT = 3
"""Consecutive ERROR results before an engine is retired.

Three, because an error is *our* side going wrong — a timeout, a parse blip, a
connection reset — and the second attempt genuinely might work."""

BLOCKED_FAILURE_LIMIT = 1
"""Consecutive BLOCKED results before an engine is retired. One is enough.

A refusal is not a blip, it is an answer, and asking again does not change it.
Measured from this machine on 2026-08-29: brave replied HTTP 429, mojeek served
`<title>Captcha</title>`, startpage served an Anubis proof-of-work challenge.
Retrying a 429 is worse than useless — it is more traffic into the limiter that
just refused us, which is how a short rate limit becomes a long one.

At three strikes those three engines burned nine requests per round to learn
what three had already established, and wrote nine warnings into the live feed
to say it."""

DEFAULT_REQUEST_GAP_SECONDS = 1.5
"""Minimum spacing between the *launch* of two outbound search-engine requests.

The per-domain limiter in ``fetch/ratelimit.py`` answers "how often may we hit
duckduckgo.com". Nothing answered "how fast are we hitting the web", because that
limiter hands every fresh domain a full bucket — so six engines each got their
first request for free, in the same instant, and `search_many` ran three such
waves at once. Measured 2026-08-30: five of six engines lost to rate limits and
challenges inside one search, with cooldowns that outlive the run.

The value is a rate cap, so it has to be read against volume, not against a
single round. The six configured per-domain intervals (google 8 s, brave 15 s,
duckduckgo 4 s, …) already allow ~1.3 requests/second in aggregate, i.e. ~0.78 s
between requests when every engine is healthy. 1.5 s roughly halves that, which
is a real reduction in the signal the engines are charging us for, while staying
close enough to the existing cadence that a round does not become the binding
constraint on the search's wall clock.

Raise it if the engines still refuse us; the cost is linear in search time and
the knob is ``DISCOVERY_ENGINE_REQUEST_GAP_SECONDS``. 0 restores the old burst."""

RETIREMENT_SECONDS = 180.0
"""Base cooldown for an engine that *failed* — a timeout, a parse error, a blip."""

BLOCKED_RETIREMENT_SECONDS = 600.0
"""Base cooldown for an engine that *refused* us.

A 429 or a captcha is the remote saying "slow down". Coming back in three
minutes and being refused again does not just waste three requests, it keeps us
in the penalty box. Observed live on 2026-08-29: brave, mojeek and startpage
each retired and revived eleven times in a single search, and the eleven
identical warnings were the most frequent line in the user's live feed."""

MAX_RETIREMENT_SECONDS = 1800.0
"""Ceiling, so an engine can still come back inside one search."""
"""How long a retired engine sits out before it is offered one probe request.

Retirement used to last the whole session, and because a retired engine is never
called it could never produce the `OK` that resets its counter — the one exit was
sealed by the same rule that sent it there. Measured live on 2026-08-29: four
engines retired inside 75 seconds and the search ran on for another quarter of an
hour with no web discovery at all. Rate limits are measured in minutes, searches
in tens of minutes, so a search that gives up permanently on the first bad window
throws away most of its own runtime."""

# User-facing display names for the live search monitor. Keys match ``engine.key``.
ENGINE_DISPLAY_NAMES: dict[str, str] = {
    "duckduckgo": "DuckDuckGo",
    "bing": "Bing",
    "mojeek": "Mojeek",
    "brave": "Brave",
    "startpage": "Startpage",
    "google": "Google",
}


def default_engines() -> list[SearchEngine]:
    """One instance of every engine, in preference order."""
    return [
        DuckDuckGoEngine(),
        BingEngine(),
        MojeekEngine(),
        BraveEngine(),
        StartpageEngine(),
        GoogleEngine(),
    ]


def fuse_results(results: Sequence[EngineResult], *, limit: int = 20) -> list[SearchHit]:
    """Merge per-engine rankings with Reciprocal Rank Fusion.

    ``score(url) = Σ 1 / (RRF_K + rank)``. The returned ``SearchHit`` for each URL
    is the one from the engine that ranked it highest, so ``.engine`` and ``.rank``
    stay meaningful (they answer "who liked this most, and how much?").
    """
    scores: dict[str, float] = {}
    best: dict[str, SearchHit] = {}
    for result in results:
        for hit in result.hits:
            key = normalize_hit_url(hit.url)
            if not key or hit.rank < 1:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + hit.rank)
            current = best.get(key)
            if current is None or hit.rank < current.rank:
                best[key] = hit
    ordered = sorted(best.items(), key=lambda item: (-scores[item[0]], item[1].rank, item[1].url))
    return [hit for _, hit in ordered[: max(1, limit)]]


class EngineHealthStore:
    """The circuit breaker's state, kept for the life of the process.

    Deliberately outliving one search, for the same reason ``DomainRateLimiter``
    and ``CookieVault`` do: a refusal describes the *remote engine*, not the
    search that happened to run into it.

    It used to live on ``EngineRegistry``, which ``runner.run`` builds per search,
    so every cooldown was discarded the moment the run ended. A 600 s retirement
    therefore protected nothing: each new search re-probed Brave (17 s of HTTP
    429) and Mojeek (an ALTCHA page), re-learned the identical refusal and wrote
    the identical warning. The doubling in :meth:`cooldown_for` could not fire at
    all, because a streak cannot survive a reset.

    What stays on the registry is ``_announced`` — that one *is* per search, or
    the live feed would say "Searching Google" once and never again.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._health: dict[str, EngineHealth] = {}
        self._failures: dict[str, int] = {}
        self._retired_until: dict[str, float] = {}
        self._retirements: dict[str, int] = {}
        """Consecutive retirements per engine, so each cooldown can double."""

    def status(self, key: str) -> EngineHealth:
        """An engine nobody has recorded anything about is healthy."""
        return self._health.get(key, EngineHealth.OK)

    def revive_expired(self) -> None:
        """Put retired engines back on probation once their cooldown has elapsed.

        The engine comes back one failure short of the limit, so a single further
        refusal retires it again immediately. That makes the probe cost exactly
        one request rather than another full run of three.
        """
        now = self._clock()
        for key, until in list(self._retired_until.items()):
            if now < until:
                continue
            del self._retired_until[key]
            self._health[key] = EngineHealth.BLOCKED
            self._failures[key] = FAILURE_LIMIT - 1

    def record(self, result: EngineResult) -> None:
        """Advance the circuit breaker. OK resets it; EMPTY is neutral."""
        key = result.engine
        if self.status(key) is EngineHealth.DISABLED:
            return

        if result.health in (EngineHealth.BLOCKED, EngineHealth.ERROR):
            failures = self._failures.get(key, 0) + 1
            self._failures[key] = failures
            limit = BLOCKED_FAILURE_LIMIT if result.health is EngineHealth.BLOCKED else FAILURE_LIMIT
            if failures >= limit:
                self._health[key] = EngineHealth.DISABLED
                self._retired_until[key] = self._clock() + self.cooldown_for(key, result.health, result.detail)
                return
            self._health[key] = result.health
            return

        if result.health is EngineHealth.OK:
            self._failures[key] = 0
            # A working engine has served its sentence: the next cooldown starts
            # from the base again rather than from wherever the last streak ended.
            self._retirements[key] = 0
        self._health[key] = result.health

    def cooldown_for(self, key: str, health: EngineHealth, detail: str = "") -> float:
        """How long this engine sits out, doubling on each repeat.

        A fixed cooldown made the breaker a metronome: retire, revive, get
        refused, retire again — for the whole search, at the same interval, with
        one warning line each time. Doubling means a host that keeps refusing us
        is left alone for progressively longer, which is both what it is asking
        for and what stops the feed filling with the same sentence.
        """
        rounds = self._retirements.get(key, 0)
        base = BLOCKED_RETIREMENT_SECONDS if health is EngineHealth.BLOCKED else RETIREMENT_SECONDS
        cooldown = min(MAX_RETIREMENT_SECONDS, base * (2**rounds))
        self._retirements[key] = rounds + 1

        # Logged once per retirement, naming both the growing number and the
        # cause. "after N consecutive failures" was the whole message, and it
        # reads as "this engine is down" — which is almost never what happened.
        logger.log_warning(f"Search engine '{key}' retired for {cooldown:.0f}s — {retirement_reason(health, detail)}")
        return cooldown


class EngineRegistry:
    """Runs the engine pool, fuses the results and tracks per-engine health."""

    def __init__(
        self,
        engines: Sequence[SearchEngine] | None = None,
        *,
        allow_stealth: bool = True,
        clock: Callable[[], float] | None = None,
        health: EngineHealthStore | None = None,
        request_gap_s: float = DEFAULT_REQUEST_GAP_SECONDS,
    ) -> None:
        chosen = list(engines) if engines is not None else default_engines()
        # Stable sort: engines outside the preference list keep their given order.
        self._engines: list[SearchEngine] = sorted(chosen, key=_preference_index)
        self._allow_stealth = allow_stealth
        # A private store by default, so a registry built in a test is isolated.
        # Only `runner.run` passes the shared one; see `EngineHealthStore`.
        self._health = health if health is not None else EngineHealthStore(clock)
        # Engines already announced to the live monitor, so "Searching Google"
        # is broadcast once per session rather than once per query variation.
        self._announced: set[str] = set()
        self._request_gap_s = max(0.0, request_gap_s)
        # One outbound search request at a time, process-wide. Two concurrent
        # sessions that both want to search must queue behind each other for the
        # same reason two requests within one session do: the engines see one IP.
        self._turnstile = asyncio.Lock()
        self._last_launch_at: float | None = None

    # -- public API -----------------------------------------------------------

    async def search(
        self,
        fetch: FetchSession,
        query: str,
        *,
        engine_count: int = 3,
        limit: int = 20,
    ) -> list[SearchHit]:
        """Run one query across the healthiest engines and return the fused hits."""
        engines = self.healthy_engines(engine_count)
        if not engines:
            return []
        for engine in engines:
            if engine.key not in self._announced:
                self._announced.add(engine.key)
                logger.log_action(f"Searching {ENGINE_DISPLAY_NAMES.get(engine.key, engine.key.title())}")
        # Still a gather: `_paced` spaces the *launches*, so the engines overlap
        # in flight exactly as before. Walking them sequentially would serialise
        # the six per-domain limiters — see `_paced` for what that costs.
        results = await asyncio.gather(*(self._paced(engine, fetch, query, limit) for engine in engines))
        for result in results:
            self._health.record(result)
        return fuse_results(results, limit=limit)

    async def _paced(self, engine: SearchEngine, fetch: FetchSession, query: str, limit: int) -> EngineResult:
        """One engine call, launched at least ``request_gap_s`` after the last one.

        The per-domain limiter cannot do this job: it hands every fresh domain a
        full bucket, so the first request to each of six engines was allowed at
        the same instant, and it has nothing to say about the spacing between two
        *different* hosts. This is the only thing that caps our aggregate rate.

        The turnstile is held for the **wait only**, never for the request. That
        distinction is the whole design. Holding it across the call serialises
        the pool, so the six per-domain limiters can no longer overlap and a
        round's cost becomes their sum instead of their maximum — measured at
        depth 7, +825 s per round against an 1800 s budget for the whole search.
        Releasing it first keeps the requests overlapping in flight while still
        guaranteeing no two of them leave in the same instant.
        """
        async with self._turnstile:
            now = time.monotonic()
            if self._request_gap_s > 0 and self._last_launch_at is not None:
                # Jittered upward only. A machine-perfect cadence is itself a bot
                # signal, and a gap shorter than the configured one is not a gap.
                gap = self._request_gap_s * random.uniform(1.0, 1.4)
                elapsed = now - self._last_launch_at
                if elapsed < gap:
                    await asyncio.sleep(gap - elapsed)
                    now = time.monotonic()
            self._last_launch_at = now
        return await self._run(engine, fetch, query, limit)

    async def search_many(
        self,
        fetch: FetchSession,
        queries: Sequence[str],
        *,
        engine_count: int = 3,
        concurrency: int = 1,
        limit: int = 20,
    ) -> list[SearchHit]:
        """Run several queries; return the deduped union.

        ``concurrency`` defaults to 1. It used to be 3, which multiplied the
        engine fan-out by three: nine requests to six hosts in the opening
        instant of a round. The turnstile in :meth:`_paced` now serialises the
        requests whatever this is set to, so raising it buys overlap in parsing
        and nothing on the wire.
        """
        unique = _unique_queries(queries)
        if not unique:
            return []
        gate = asyncio.Semaphore(max(1, concurrency))

        async def _one(query: str) -> list[SearchHit]:
            async with gate:
                try:
                    return await self.search(fetch, query, engine_count=engine_count, limit=limit)
                except Exception as exc:  # a single bad query must not kill the sweep
                    logger.log_warning(f"Search query failed ({query!r}): {type(exc).__name__}: {exc}")
                    return []

        batches = await asyncio.gather(*(_one(query) for query in unique))
        return dedupe_hits(hit for batch in batches for hit in batch)

    def health(self) -> dict[str, str]:
        """Engine key -> health value.

        Engines that require stealth while ``allow_stealth`` is False report
        ``disabled``: they are unavailable for this session, and saying so is what
        makes an empty result set explainable rather than mysterious.
        """
        out: dict[str, str] = {}
        for engine in self._engines:
            if engine.requires_stealth and not self._allow_stealth:
                out[engine.key] = EngineHealth.DISABLED.value
                continue
            out[engine.key] = self._health.status(engine.key).value
        return out

    def healthy_engines(self, count: int) -> list[SearchEngine]:
        """The first ``count`` engines that are neither retired nor policy-excluded."""
        if count <= 0:
            return []
        self._health.revive_expired()
        out: list[SearchEngine] = []
        for engine in self._engines:
            if len(out) >= count:
                break
            if self._health.status(engine.key) is EngineHealth.DISABLED:
                continue
            if engine.requires_stealth and not self._allow_stealth:
                continue
            out.append(engine)
        return out

    # -- internals ------------------------------------------------------------

    async def _run(self, engine: SearchEngine, fetch: FetchSession, query: str, limit: int) -> EngineResult:
        """Call one engine, converting any escape into an ERROR result."""
        try:
            return await engine.search(fetch, query, limit=limit)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"[:200]
            logger.log_warning(f"Search engine '{engine.key}' raised: {detail}")
            return EngineResult(engine=engine.key, query=query, hits=[], health=EngineHealth.ERROR, detail=detail)


def retirement_reason(health: EngineHealth, detail: str = "") -> str:
    """Why an engine is sitting out: a stable token, then the raw detail.

    ``rate_limited (HTTP 429)`` — the token is what the console presenter matches
    on, so the sentence the user reads can be translated; the parenthetical is
    for whoever is reading the terminal.

    Naming the cause is the point. A rate limit, a captcha and a parse failure
    say three different things about whether this search can be trusted, and
    ``EngineResult.detail`` already knew which one it was — the retirement
    warning simply threw it away and said "not answering" for all three.
    """
    lowered = (detail or "").lower()
    if health is EngineHealth.BLOCKED:
        if "429" in lowered:
            token = "rate_limited"
        elif any(word in lowered for word in ("interstitial", "captcha", "challenge")):
            token = "challenge"
        else:
            token = "refused"
    else:
        token = "failed"
    return f"{token} ({detail})" if detail else token


def _preference_index(engine: SearchEngine) -> int:
    try:
        return PREFERENCE.index(engine.key)
    except ValueError:
        return len(PREFERENCE)


def _unique_queries(queries: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        cleaned = " ".join((query or "").split())
        canonical = canonical_query(cleaned)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        out.append(cleaned)
    return out

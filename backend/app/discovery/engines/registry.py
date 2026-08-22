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
from collections.abc import Sequence
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
"""Consecutive BLOCKED/ERROR results before an engine is retired for the session."""

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


class EngineRegistry:
    """Runs the engine pool, fuses the results and tracks per-engine health."""

    def __init__(self, engines: Sequence[SearchEngine] | None = None, *, allow_stealth: bool = True) -> None:
        chosen = list(engines) if engines is not None else default_engines()
        # Stable sort: engines outside the preference list keep their given order.
        self._engines: list[SearchEngine] = sorted(chosen, key=_preference_index)
        self._allow_stealth = allow_stealth
        self._health: dict[str, EngineHealth] = {engine.key: EngineHealth.OK for engine in self._engines}
        self._failures: dict[str, int] = {engine.key: 0 for engine in self._engines}
        # Engines already announced to the live monitor, so "Searching Google"
        # is broadcast once per session rather than once per query variation.
        self._announced: set[str] = set()

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
        results = await asyncio.gather(*(self._run(engine, fetch, query, limit) for engine in engines))
        for result in results:
            self._record(result)
        return fuse_results(results, limit=limit)

    async def search_many(
        self,
        fetch: FetchSession,
        queries: Sequence[str],
        *,
        engine_count: int = 3,
        concurrency: int = 3,
        limit: int = 20,
    ) -> list[SearchHit]:
        """Run several queries with bounded concurrency; return the deduped union."""
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
            out[engine.key] = self._health.get(engine.key, EngineHealth.OK).value
        return out

    def healthy_engines(self, count: int) -> list[SearchEngine]:
        """The first ``count`` engines that are neither retired nor policy-excluded."""
        if count <= 0:
            return []
        out: list[SearchEngine] = []
        for engine in self._engines:
            if len(out) >= count:
                break
            if self._health.get(engine.key) is EngineHealth.DISABLED:
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

    def _record(self, result: EngineResult) -> None:
        """Advance the circuit breaker. OK resets it; EMPTY is neutral."""
        key = result.engine
        if self._health.get(key) is EngineHealth.DISABLED:
            return

        if result.health in (EngineHealth.BLOCKED, EngineHealth.ERROR):
            failures = self._failures.get(key, 0) + 1
            self._failures[key] = failures
            if failures >= FAILURE_LIMIT:
                self._health[key] = EngineHealth.DISABLED
                logger.log_warning(
                    f"Search engine '{key}' disabled for this session after "
                    f"{failures} consecutive failures — last: {result.detail or result.health.value}"
                )
                return
            self._health[key] = result.health
            return

        if result.health is EngineHealth.OK:
            self._failures[key] = 0
        self._health[key] = result.health


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

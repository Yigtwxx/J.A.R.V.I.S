"""DuckDuckGo — the primary engine.

The ``html.duckduckgo.com/html/`` endpoint is a server-rendered, JavaScript-free
mirror of the SERP: no consent wall, no API key, stable markup. It is the highest
yield-per-request source in the pool, so it runs first on every query.

Its one failure mode is the rate-limit page ("unfortunately, bots use DuckDuckGo
too"), which is served with HTTP 200 and an otherwise ordinary layout. Parsing it
naively yields zero results, which is why it is detected explicitly and reported
as BLOCKED — an engine that was refused must never look like an engine that found
nothing.

When that happens there is a second, much older endpoint — ``lite.duckduckgo.com``
— which is throttled separately and was verified live still answering while the
main HTML endpoint refused us. It is used as an *internal* retry rather than
registered as its own engine, and that distinction is load-bearing: it is the same
operator over the same index, so a separate ``engine.key`` would let Reciprocal
Rank Fusion count one source's opinion twice and read it as independent
corroboration.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from app.discovery.engines.base import (
    EngineHealth,
    EngineResult,
    HtmlSearchEngine,
    clean_result_url,
    element_text,
    iter_nodes,
    node_attr,
    node_text,
)
from app.discovery.fetch.selectors import css_attr
from app.discovery.fetch.session import FetchSession

_SEARCH_URL = "https://html.duckduckgo.com/html/?q={q}"
_LITE_URL = "https://lite.duckduckgo.com/lite/?q={q}"

_BLOCKED_MARKERS: tuple[str, ...] = (
    "anomaly-modal",
    "anomaly_modal",
    "unfortunately, bots use duckduckgo too",
    "if this error persists, please let us know",
)


class LiteDuckDuckGoEngine(HtmlSearchEngine):
    """The ``lite.duckduckgo.com`` table layout.

    Reported under the primary's key on purpose — see the module docstring. Not
    exported in ``default_engines()``; it exists only as ``DuckDuckGoEngine``'s
    second attempt.
    """

    key = "duckduckgo"
    requires_stealth = False
    expect_selector = "a.result-link"
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("duckduckgo.com",)

    def build_url(self, query: str) -> str:
        return _LITE_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        """The lite SERP is one table: a link row followed by its snippet row."""
        rows: list[tuple[str, str, str]] = []
        links = list(iter_nodes(page, "a.result-link"))
        snippets = [node_text(node) for node in iter_nodes(page, "td.result-snippet")]
        for index, node in enumerate(links):
            href = node_attr(node, "href")
            url = clean_result_url(href or "", base=base)
            if not url:
                continue
            snippet = snippets[index] if index < len(snippets) else ""
            rows.append((url, node_text(node), snippet))
        return rows


class DuckDuckGoEngine(HtmlSearchEngine):
    """Scrapes the no-JavaScript DuckDuckGo HTML endpoint."""

    key = "duckduckgo"
    requires_stealth = False
    expect_selector = "div.result"
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("duckduckgo.com",)

    def __init__(self) -> None:
        self._lite = LiteDuckDuckGoEngine()

    async def search(self, fetch: FetchSession, query: str, *, limit: int = 20) -> EngineResult:
        """Try the main endpoint, then the lite one if we were refused.

        Only a refusal earns the retry. EMPTY means DuckDuckGo answered and had
        nothing, and asking the same index a second time will not change that.
        """
        result = await super().search(fetch, query, limit=limit)
        if result.health is not EngineHealth.BLOCKED:
            return result

        fallback = await self._lite.search(fetch, query, limit=limit)
        if fallback.health is EngineHealth.OK:
            return fallback
        # Keep the original refusal: it is the more accurate description of what
        # happened, and the circuit breaker should see the block, not an empty page.
        return result

    def build_url(self, query: str) -> str:
        return _SEARCH_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for node in iter_nodes(page, "div.result"):
            classes = node_attr(node, "class")
            # Sponsored rows carry the same markup as organic ones.
            if "result--ad" in classes or "result--no-result" in classes:
                continue
            href = css_attr(node, "a.result__a", "href")
            url = clean_result_url(href or "", base=base)
            if not url:
                continue
            rows.append((url, element_text(node, "a.result__a"), element_text(node, ".result__snippet")))
        return rows

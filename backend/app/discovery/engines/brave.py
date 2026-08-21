"""Brave Search — a second independent index.

Brave runs its own crawler, so like Mojeek it fails differently from the
Bing-derived engines. Its SERP is server-rendered and usually readable over plain
HTTP, but it sits behind its own bot scoring and intermittently answers with a
challenge page. ``requires_stealth`` stays False — we do not want to *start* a
browser for Brave — while ``escalate`` stays True so the fetch layer can promote
the single request that actually hit a wall.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from app.discovery.engines.base import (
    HtmlSearchEngine,
    clean_result_url,
    element_text,
    iter_nodes,
)
from app.discovery.fetch.selectors import css_attr

_SEARCH_URL = "https://search.brave.com/search?q={q}"

_BLOCKED_MARKERS: tuple[str, ...] = (
    "challenge-platform",
    "verify you are human",
    "are you a robot",
)


class BraveEngine(HtmlSearchEngine):
    """Scrapes Brave's web result snippets."""

    key = "brave"
    requires_stealth = False
    escalate = True
    expect_selector = '.snippet[data-type="web"]'
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("brave.com",)

    def build_url(self, query: str) -> str:
        return _SEARCH_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for node in iter_nodes(page, '.snippet[data-type="web"]'):
            href = css_attr(node, "a", "href")
            url = clean_result_url(href or "", base=base)
            if not url:
                continue
            # Brave ships a Svelte build whose class hashes rotate; only the
            # semantic classes below are stable, so each has a fallback and an
            # anchor-text last resort rather than one brittle selector.
            title = (
                element_text(node, ".search-snippet-title")
                or element_text(node, ".snippet-title")
                or element_text(node, "a")
            )
            snippet = element_text(node, ".snippet-description") or element_text(node, ".generic-snippet .content")
            rows.append((url, title, snippet))
        return rows

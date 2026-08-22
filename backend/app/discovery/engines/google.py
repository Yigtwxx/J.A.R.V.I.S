"""Google — budgeted to fail.

Google has the best index and the most hostile scraping surface. Without a browser
it answers a datacentre IP with a consent interstitial or ``/sorry/`` captcha
essentially every time; with a browser it works for a while and then does not.
Its result markup is also obfuscated and rotated, so the selectors below are a
best-effort snapshot rather than a contract.

**This engine is expected to return BLOCKED most of the time, and the pipeline is
designed to be correct without it.** It sits last in the preference order, the
circuit breaker retires it after three refusals, and nothing downstream treats its
absence as meaningful. It is here to opportunistically add the results only Google
has — never to be depended on.
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

_SEARCH_URL = "https://www.google.com/search?q={q}&num=20&hl=en"

_BLOCKED_MARKERS: tuple[str, ...] = (
    "our systems have detected unusual traffic",
    "before you continue to google",
    'id="captcha-form"',
    "consent.google.com",
    "/sorry/index",
    "enablejsdialog",
)

_RESULT_SELECTORS: tuple[str, ...] = ("div.g", "div[data-sokoban-container]")


class GoogleEngine(HtmlSearchEngine):
    """Scrapes the classic Google web SERP. Opportunistic, never load-bearing."""

    key = "google"
    requires_stealth = True
    expect_selector = "div#search"
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("google.com", "gstatic.com", "googleusercontent.com")

    def build_url(self, query: str) -> str:
        return _SEARCH_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for selector in _RESULT_SELECTORS:
            for node in iter_nodes(page, selector):
                href = css_attr(node, 'a[href^="/url?q="]', "href") or css_attr(node, 'a[href^="http"]', "href")
                url = clean_result_url(href or "", base=base)
                if not url:
                    continue
                title = element_text(node, "h3")
                if not title:
                    continue
                rows.append((url, title, element_text(node, "div[data-sncf]") or element_text(node, ".VwiC3b")))
            if rows:
                break
        return rows

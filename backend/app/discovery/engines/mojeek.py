"""Mojeek — the independent index.

Mojeek crawls the web itself rather than reselling Bing or Google results, so it
is the only engine in the pool whose blind spots are uncorrelated with the others'.
That makes it disproportionately valuable for long-tail personal pages: forum
profiles, university staff listings and small blogs that the big two have dropped.

It also renders without JavaScript and does not fight scrapers, so it is the most
reliable engine here even though its raw coverage is the smallest.
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

_SEARCH_URL = "https://www.mojeek.com/search?q={q}"

# Mojeek answers a suspicious client with a captcha page served as HTTP 200 and an
# otherwise ordinary layout, so the only reliable tell is the title. Without this
# the page parses to zero rows and would be reported as EMPTY — i.e. "the web has
# nothing on this person", which is the exact confusion this pipeline exists to avoid.
_BLOCKED_MARKERS: tuple[str, ...] = (
    "<title>captcha</title>",
    "too many requests",
    "rate limited",
)


class MojeekEngine(HtmlSearchEngine):
    """Scrapes Mojeek's standard result list."""

    key = "mojeek"
    requires_stealth = False
    expect_selector = "ul.results-standard"
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("mojeek.com",)

    def build_url(self, query: str) -> str:
        return _SEARCH_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for node in iter_nodes(page, "ul.results-standard li"):
            href = css_attr(node, "a.ob", "href")
            url = clean_result_url(href or "", base=base)
            if not url:
                continue
            rows.append((url, element_text(node, "a.ob"), element_text(node, "p.s")))
        return rows

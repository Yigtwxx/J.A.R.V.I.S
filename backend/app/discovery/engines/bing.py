"""Bing — the second opinion.

Bing's index overlaps DuckDuckGo's (DDG sources much of its web result set from
Bing) but its ranking differs enough to surface pages DDG buries, and it tolerates
scraping better than Google does.

Every organic link is wrapped in a click tracker: ``bing.com/ck/a?…&u=a1<base64url>``.
The payload is base64url with the padding stripped and an ``a1`` version prefix.
An undecodable payload is dropped rather than guessed at — a mangled URL fetched
later would produce a fake "profile not found".
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

_SEARCH_URL = "https://www.bing.com/search?q={q}&count=30&setlang=en&setmkt=en-US"

_BLOCKED_MARKERS: tuple[str, ...] = (
    "sorry, we are unable to process your request",
    "ref=blocked",
    "b_captcha",
)


class BingEngine(HtmlSearchEngine):
    """Scrapes the classic Bing web SERP."""

    key = "bing"
    requires_stealth = False
    expect_selector = "li.b_algo"
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("bing.com", "microsofttranslator.com")

    def build_url(self, query: str) -> str:
        return _SEARCH_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for node in iter_nodes(page, "li.b_algo"):
            # Only the heading link is the result. `a.tilk` in the `b_tpcn` header
            # chip points at the site *root*, so using it as a fallback would report
            # `telerik.com` as the hit for a page at `telerik.com/fiddler`.
            href = css_attr(node, "h2 a", "href") or css_attr(node, ".b_title a", "href")
            url = clean_result_url(href or "", base=base)
            if not url:
                continue
            snippet = element_text(node, ".b_caption p") or element_text(node, ".b_algoSlug")
            rows.append((url, element_text(node, "h2 a") or element_text(node, "h2"), snippet))
        return rows

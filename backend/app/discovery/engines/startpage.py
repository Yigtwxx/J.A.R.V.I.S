"""Startpage — opportunistic Google proxy.

Startpage serves Google's index without Google's consent wall, which makes it the
cheapest route to Google-quality results when it works. It frequently does not:
the site fingerprints clients aggressively and answers unfamiliar ones with a
captcha, so ``requires_stealth`` is True and BLOCKED is the expected outcome
rather than an anomaly.

It is therefore ranked below the engines that answer reliably. Treat anything it
returns as a bonus, never as a dependency.
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

_SEARCH_URL = "https://www.startpage.com/sp/search?query={q}"

_BLOCKED_MARKERS: tuple[str, ...] = (
    "captcha",
    "we're sorry, but you or someone",
    "unusual traffic from your",
    "do-not-track-me",
)


class StartpageEngine(HtmlSearchEngine):
    """Scrapes Startpage's web result list. Expect frequent BLOCKED."""

    key = "startpage"
    requires_stealth = True
    expect_selector = ".w-gl__result"
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("startpage.com",)

    def build_url(self, query: str) -> str:
        return _SEARCH_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for node in iter_nodes(page, ".w-gl__result"):
            href = css_attr(node, "a.w-gl__result-title", "href") or css_attr(node, "a", "href")
            url = clean_result_url(href or "", base=base)
            if not url:
                continue
            rows.append((url, element_text(node, ".w-gl__result-title"), element_text(node, ".w-gl__description")))
        return rows

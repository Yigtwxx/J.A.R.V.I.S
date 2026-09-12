"""Startpage — Google's index without Google's redirect.

The cheapest route to Google-quality results, and measured on 2026-08-29 the
*best* one: the same query that Google answers with opaque `/goto?url=` tokens,
Startpage answers with plain `https://` links straight to the target.

It has to be reached through the browser tier. Over plain HTTP it now serves an
Anubis proof-of-work interstitial (a 22 KB document whose body is
`{"rules":{"algorithm":"fast","difficulty":4},"challenge":{...}}`); rendered in
a real browser the challenge is completed and a 329 KB results page arrives.

`.w-gl__result`, the selector that used to be here, matches zero nodes on that
page. The live markup is `div.result` rows with an `a.result-link` and an `h2`.
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
from app.discovery.types import FetchTier

_SEARCH_URL = "https://www.startpage.com/sp/search?query={q}"

_BLOCKED_MARKERS: tuple[str, ...] = (
    "captcha",
    "we're sorry, but you or someone",
    "unusual traffic from your",
    "do-not-track-me",
    # Startpage now fronts results with a proof-of-work interstitial, observed
    # live 2026-08-29: a 22 KB document with no <title> and no results, whose
    # body is `{"rules":{"algorithm":"fast","difficulty":5},"challenge":{...}}`.
    # Without this marker it parsed as a page with zero results, so a refusal was
    # reported as an absence — the one conflation this pipeline exists to prevent.
    '"challenge":{"issuedat"',
    '"rules":{"algorithm"',
)


class StartpageEngine(HtmlSearchEngine):
    """Scrapes Startpage's web result list through the browser tier."""

    key = "startpage"
    requires_stealth = True
    # The HTTP tier only ever earns a proof-of-work challenge here, so paying for
    # it is a guaranteed wasted request plus the latency of finding that out.
    start_tier = FetchTier.STEALTH
    escalate = False
    expect_selector = "div.result"
    stealth_wait_selector = "div.result"
    stealth_timeout_s = 25.0
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("startpage.com",)

    def build_url(self, query: str) -> str:
        return _SEARCH_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for node in iter_nodes(page, "div.result"):
            href = css_attr(node, "a.result-link", "href") or css_attr(node, "a", "href")
            url = clean_result_url(href or "", base=base)
            if not url:
                continue
            title = element_text(node, "h2") or element_text(node, "a.result-link")
            rows.append((url, title, element_text(node, "p.description")))
        return rows

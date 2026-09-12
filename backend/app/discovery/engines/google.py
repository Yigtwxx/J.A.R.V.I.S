"""Google — reachable, but only through a browser and a redirect.

Two things about Google's current SERP decide everything in this module, both
measured from this machine on 2026-08-29:

1. **Plain HTTP gets nothing.** The response is HTTP 200 with 91 KB of
   JavaScript shell, one ``href`` in the whole document and an ``enablejs``
   marker. It is not a block and not an empty result set — there is simply no
   content in it. So the engine starts at the stealth tier: the browser renders
   the same query into a real 785 KB SERP with results in it.

2. **The result URLs are not in the page.** ``/url?q=`` is gone; every organic
   anchor now points at ``/goto?url=<token>`` where the token is opaque — 105
   bytes of high-entropy data with no URL inside, so it cannot be decoded here.
   The address is recovered by asking Google for the redirect and reading
   ``Location``, which costs one cheap request per row and resolves eight of
   them concurrently in 0.4 s.

The rows themselves are found structurally — *an anchor that contains a heading*
— rather than by class name. `div.g` and `div[data-sokoban-container]`, the
selectors that used to be here, both match zero nodes on the live page; Google's
class names are obfuscated and rotate (`div.eFM0qc` today), while the
anchor-wraps-heading relationship has outlived every redesign so far.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus

from app.discovery.engines.base import (
    HtmlSearchEngine,
    clean_result_url,
    element_text,
    iter_nodes,
    node_attr,
)
from app.discovery.types import FetchTier

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.discovery.fetch.session import FetchSession

_SEARCH_URL = "https://www.google.com/search?q={q}&num=20&hl=en"

_BLOCKED_MARKERS: tuple[str, ...] = (
    "our systems have detected unusual traffic",
    "before you continue to google",
    'id="captcha-form"',
    "consent.google.com",
    "/sorry/index",
)

_REDIRECT_PREFIXES: tuple[str, ...] = ("/goto?url=",)
"""Only ``/goto`` needs the network. The legacy ``/url?q=`` wrapper carries its
target in the query string, so ``clean_result_url`` unwraps it for free."""

_MAX_RESOLUTIONS = 8
"""Redirects resolved per query.

Every one is a request to google.com, and google.com is the host in this pool
most willing to answer HTTP 429. Eight is a page of results, which RRF then
fuses with everything the other engines found — there is nothing to gain from
chasing the long tail of a single engine."""


class GoogleEngine(HtmlSearchEngine):
    """Scrapes the Google web SERP through the browser tier."""

    key = "google"
    requires_stealth = True
    # Straight to the browser: the HTTP tier is not merely unreliable here, it is
    # a guaranteed wasted request and the latency that comes with it.
    start_tier = FetchTier.STEALTH
    escalate = False
    # `div#search` is gone from the rendered page. A heading is what an organic
    # result has and the JavaScript shell does not.
    expect_selector = "h3"
    # Google's SERP keeps polling in the background and never falls idle, so
    # waiting for idle cost the whole 60 s ceiling for a page whose results were
    # on screen in three. Measured 2026-08-29: 64.1 s -> a few seconds.
    stealth_wait_selector = "h3"
    stealth_timeout_s = 25.0
    blocked_markers = _BLOCKED_MARKERS
    own_hosts = ("google.com", "gstatic.com", "googleusercontent.com")

    def build_url(self, query: str) -> str:
        return _SEARCH_URL.format(q=quote_plus(query))

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for node in iter_nodes(page, "a:has(h3)"):
            href = node_attr(node, "href")
            title = element_text(node, "h3")
            if not href or not title or href in seen:
                continue
            seen.add(href)
            # A redirect is kept as-is for `resolve_rows`; a plain URL (an older
            # layout, or a locale that still serves them) is cleaned here and
            # skips the resolution entirely.
            if href.startswith(_REDIRECT_PREFIXES):
                rows.append((href, title, ""))
                continue
            if url := clean_result_url(href, base=base):
                rows.append((url, title, ""))
        return rows

    async def resolve_rows(self, fetch: FetchSession, rows: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
        """Swap Google's redirects for the addresses they point at.

        Unresolvable rows are dropped rather than kept pointing at google.com:
        a hit whose URL is the search engine itself is not a finding, and the
        pipeline matches on host, so it would corroborate nothing and pollute
        everything.
        """
        pending = [(i, row) for i, row in enumerate(rows) if row[0].startswith(_REDIRECT_PREFIXES)]
        if not pending:
            return rows

        base = "https://www.google.com"
        batch = pending[:_MAX_RESOLUTIONS]
        locations = await fetch.resolve_redirects([f"{base}{row[0]}" for _, row in batch])

        resolved = dict(zip((i for i, _ in batch), locations, strict=False))
        out: list[tuple[str, str, str]] = []
        for i, (href, title, snippet) in enumerate(rows):
            if not href.startswith(_REDIRECT_PREFIXES):
                out.append((href, title, snippet))
                continue
            location = resolved.get(i)
            if location and (url := clean_result_url(location, base=base)):
                out.append((url, title, snippet))
        return out

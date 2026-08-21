"""Shared vocabulary and machinery for the search-engine layer.

Every engine is expected to fail sometimes, so the contract here is built around
*reporting* failure rather than hiding it: a parse that finds nothing is ``EMPTY``
(never an exception, never a silent empty list), while an anti-bot wall is
``BLOCKED`` — "we were refused" is a different fact from "we looked and there was
nothing there", and conflating them is how a scraper starts inventing absences.

``clean_result_url`` is the single place redirect wrappers are unwrapped, so a new
engine never has to re-learn DuckDuckGo's ``uddg=`` or Bing's base64 ``u=a1``.
"""

from __future__ import annotations

import base64
import binascii
import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from app.discovery.fetch.result import FetchResult
from app.discovery.fetch.selectors import css_first
from app.discovery.platforms.urlmatch import registrable_host
from app.discovery.types import FetchStatus, FetchTier

if TYPE_CHECKING:  # pragma: no cover - import kept out of the runtime path
    from app.discovery.fetch.session import FetchSession

# Query parameters that only exist to track the click. Dropping them is what makes
# the same page discovered via two engines dedupe to one hit.
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {"ref", "ref_src", "ref_url", "fbclid", "gclid", "dclid", "msclkid", "yclid", "igshid", "mc_cid", "mc_eid"}
)

_REJECTED_SCHEMES: tuple[str, ...] = ("javascript:", "mailto:", "tel:", "data:", "about:")

# How many nested redirect wrappers to peel before declaring the URL hostile.
_MAX_UNWRAPS = 4


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One organic result row, already unwrapped and cleaned."""

    url: str
    title: str
    snippet: str
    engine: str
    rank: int
    """1-based position within that engine's own result list."""

    query: str = ""

    @property
    def domain(self) -> str:
        """Registrable host of the URL — ``www.`` and mobile prefixes stripped."""
        return registrable_host(self.url)


class EngineHealth(StrEnum):
    """Why an engine produced (or failed to produce) results.

    ``EMPTY`` and ``BLOCKED`` are deliberately distinct: conflating them is how a
    scraper starts reporting "no such person" for a page it was never shown.
    """

    OK = "ok"
    BLOCKED = "blocked"
    EMPTY = "empty"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass(slots=True)
class EngineResult:
    """Everything one engine has to say about one query."""

    engine: str
    query: str
    hits: list[SearchHit]
    health: EngineHealth
    detail: str = ""
    """Human-readable explanation, e.g. ``"HTTP 429 via http"``."""

    elapsed_ms: int = 0


class SearchEngine(Protocol):
    """Structural contract every engine module satisfies."""

    key: str
    requires_stealth: bool

    async def search(self, fetch: FetchSession, query: str, *, limit: int = 20) -> EngineResult: ...


def build_engine_result(
    engine: str,
    query: str,
    hits: Iterable[SearchHit] | None = None,
    *,
    health: EngineHealth,
    detail: str = "",
    started: float | None = None,
) -> EngineResult:
    """Assemble an ``EngineResult``, timing it from ``started`` (a ``monotonic()`` stamp)."""
    elapsed_ms = int((time.monotonic() - started) * 1000) if started is not None else 0
    return EngineResult(
        engine=engine,
        query=query,
        hits=list(hits or []),
        health=health,
        detail=detail,
        elapsed_ms=elapsed_ms,
    )


def health_for_fetch(result: FetchResult) -> tuple[EngineHealth, str]:
    """Map a non-OK ``FetchResult`` onto engine health plus a readable detail."""
    if result.status is FetchStatus.BLOCKED:
        return EngineHealth.BLOCKED, result.describe()
    if result.status is FetchStatus.NOT_FOUND:
        return EngineHealth.EMPTY, result.describe()
    return EngineHealth.ERROR, result.describe()


# -- URL cleaning -------------------------------------------------------------


def clean_result_url(raw: str, *, base: str) -> str | None:
    """Turn a raw SERP anchor into a usable absolute target URL, or ``None``.

    Unwraps every redirect wrapper the supported engines emit, resolves relative
    hrefs against ``base``, and rejects junk anchors. A wrapper we recognise but
    cannot decode yields ``None`` — a half-decoded URL is worse than no URL.
    """
    if not raw or not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate or candidate.startswith("#"):
        return None
    if candidate.lower().startswith(_REJECTED_SCHEMES):
        return None

    candidate = _absolutize(candidate, base)
    for _ in range(_MAX_UNWRAPS):
        is_wrapper, target = _unwrap_once(candidate)
        if not is_wrapper:
            break
        if not target:
            return None
        candidate = _absolutize(target, base)
    else:
        # Four wrappers deep is a redirect chain nobody legitimate builds.
        return None

    try:
        split = urlsplit(candidate)
    except ValueError:
        return None
    if split.scheme not in ("http", "https") or not split.hostname:
        return None
    parts = (split.scheme.lower(), split.netloc.lower(), split.path or "/", _strip_tracking(split.query))
    return urlunsplit((*parts, split.fragment))


def normalize_hit_url(url: str) -> str:
    """Identity key for de-duplication: lowercase host, no ``www.``, no trailing slash."""
    if not url:
        return ""
    try:
        split = urlsplit(url)
    except ValueError:
        return ""
    host = registrable_host(split.netloc)
    if not host:
        return ""
    path = (split.path or "/").rstrip("/")
    key = f"{host}{path}"
    return f"{key}?{split.query}" if split.query else key


def dedupe_hits(hits: Iterable[SearchHit]) -> list[SearchHit]:
    """Collapse hits pointing at the same page, keeping the best (lowest) rank."""
    best: dict[str, SearchHit] = {}
    for hit in hits:
        key = normalize_hit_url(hit.url)
        if not key:
            continue
        current = best.get(key)
        if current is None or hit.rank < current.rank:
            best[key] = hit
    return list(best.values())


def _absolutize(url: str, base: str) -> str:
    candidate = url.strip()
    if candidate.startswith("//"):
        return "https:" + candidate
    if candidate.lower().startswith(("http://", "https://")):
        return candidate
    return urljoin(base or "https://example.invalid/", candidate)


def _unwrap_once(url: str) -> tuple[bool, str | None]:
    """Peel one redirect wrapper. Returns ``(was_a_wrapper, target_or_None)``."""
    try:
        split = urlsplit(url)
    except ValueError:
        return True, None
    host = registrable_host(split.netloc)
    path = split.path or ""
    query = split.query or ""

    # DuckDuckGo: //duckduckgo.com/l/?uddg=<urlencoded>&rut=<hmac>
    if host == "duckduckgo.com" and path.startswith("/l"):
        return True, _query_param(query, "uddg")

    # Bing: https://www.bing.com/ck/a?…&u=a1<base64url>&ntb=1
    if host == "bing.com" and path.startswith("/ck/"):
        return True, _decode_bing_u(_query_param(query, "u"))

    # Google: /url?q=<urlencoded>&sa=U&ved=…
    if host == "google.com" and path.startswith("/url"):
        return True, _query_param(query, "q") or _query_param(query, "url")

    # Yahoo / Startpage: the target sits in an `RU=` slot, either as a query
    # parameter or as a path segment (`/RU=https%3a%2f%2f…/RK=2/RS=…`).
    ru = _query_param(query, "RU") or _query_param(query, "ru")
    if ru:
        return True, ru
    for segment in path.split("/"):
        if segment.startswith("RU="):
            return True, unquote(segment[3:]).strip() or None
    return False, None


def _query_param(query: str, name: str) -> str | None:
    """Percent-decoded value of ``name``. Deliberately not ``parse_qsl``, which
    also turns ``+`` into a space and would corrupt targets containing one."""
    for part in query.split("&"):
        if not part:
            continue
        key, sep, value = part.partition("=")
        if key == name:
            return unquote(value).strip() if sep else ""
    return None


def _decode_bing_u(raw: str | None) -> str | None:
    """Decode Bing's ``u=a1<base64url>`` click parameter. ``None`` when it is garbage."""
    if not raw:
        return None
    payload = raw[2:] if raw[:2].lower() == "a1" else raw
    if not payload:
        return None
    padded = payload + "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    decoded = decoded.strip()
    return decoded if decoded.lower().startswith(("http://", "https://")) else None


def _strip_tracking(query: str) -> str:
    if not query:
        return ""
    kept = []
    for part in query.split("&"):
        if not part:
            continue
        key = part.partition("=")[0].lower()
        if key.startswith("utm_") or key in _TRACKING_PARAMS:
            continue
        kept.append(part)
    return "&".join(kept)


# -- parsing helpers ----------------------------------------------------------


def iter_nodes(page: Any, selector: str) -> list[Any]:
    """All elements matching ``selector``. Never raises — a bad selector yields ``[]``."""
    if page is None:
        return []
    try:
        return list(page.css(selector))
    except Exception:
        return []


def element_text(node: Any, selector: str) -> str:
    """Whitespace-collapsed text of the first match, including nested ``<b>`` markup."""
    element = css_first(node, selector)
    if element is None:
        return ""
    try:
        raw = element.get_all_text(strip=True)
    except Exception:
        return ""
    return " ".join(str(raw or "").split())


def node_text(node: Any) -> str:
    """Whitespace-collapsed text of ``node`` itself, including nested markup.

    The selector-taking sibling of this helper is ``element_text``; this one is for
    when you already hold the element (e.g. iterating anchors on a results page).
    """
    if node is None:
        return ""
    try:
        raw = node.get_all_text(strip=True)
    except Exception:
        return ""
    return " ".join(str(raw or "").split())


def node_attr(node: Any, attribute: str) -> str:
    """Attribute of ``node`` itself, ``""`` when absent."""
    if node is None:
        return ""
    try:
        return str(node.attrib.get(attribute) or "").strip()
    except Exception:
        return ""


class HtmlSearchEngine:
    """Template for every HTML-scraping engine.

    Subclasses supply a URL builder and a row extractor; this class owns fetching,
    block detection, ranking, de-duplication and — crucially — the guarantee that
    a selector change degrades to ``EMPTY`` instead of raising mid-search.
    """

    key: str = ""
    requires_stealth: bool = False
    expect_selector: str | None = None
    """Marker that must be present in a 200, otherwise the fetch layer escalates."""

    blocked_markers: tuple[str, ...] = ()
    own_hosts: tuple[str, ...] = ()
    """Hosts belonging to the engine itself; its own navigation is not a result."""

    min_html_bytes: int = 2_000
    start_tier: FetchTier = FetchTier.HTTP
    escalate: bool = True

    def build_url(self, query: str) -> str:
        raise NotImplementedError

    def extract(self, page: Any, base: str) -> list[tuple[str, str, str]]:
        """Return ``(url, title, snippet)`` rows in the engine's own order."""
        raise NotImplementedError

    async def search(self, fetch: FetchSession, query: str, *, limit: int = 20) -> EngineResult:
        started = time.monotonic()
        cleaned = " ".join((query or "").split())

        def outcome(health: EngineHealth, detail: str, hits: list[SearchHit] | None = None) -> EngineResult:
            return build_engine_result(self.key, cleaned, hits, health=health, detail=detail, started=started)

        if not cleaned:
            return outcome(EngineHealth.EMPTY, "empty query")

        url = self.build_url(cleaned)
        try:
            result = await fetch.get(
                url,
                tier=self.start_tier,
                escalate=self.escalate,
                expect_selector=self.expect_selector,
                min_html_bytes=self.min_html_bytes,
            )
        except Exception as exc:
            return outcome(EngineHealth.ERROR, f"fetch raised {type(exc).__name__}: {exc}"[:200])

        # Checked before `result.ok`: an interstitial is usually served as HTTP 200.
        if self._has_blocked_marker(result.html):
            return outcome(EngineHealth.BLOCKED, f"anti-bot interstitial ({result.describe()})")
        if not result.ok:
            return outcome(*health_for_fetch(result))

        try:
            rows = self.extract(result.page, result.final_url or url)
        except Exception as exc:
            return outcome(EngineHealth.ERROR, f"parser raised {type(exc).__name__}: {exc}"[:200])

        hits = self._rank(rows, cleaned, limit)
        if not hits:
            return outcome(EngineHealth.EMPTY, f"no results parsed ({result.describe()}, {result.html_len} bytes)")
        return outcome(EngineHealth.OK, f"{len(hits)} hits — {result.describe()}", hits)

    def _rank(self, rows: Iterable[tuple[str, str, str]], query: str, limit: int) -> list[SearchHit]:
        seen: set[str] = set()
        hits: list[SearchHit] = []
        for url, title, snippet in rows:
            if len(hits) >= max(1, limit):
                break
            key = normalize_hit_url(url)
            if not key or key in seen or self._is_own_host(url):
                continue
            seen.add(key)
            hits.append(SearchHit(url, title, snippet, engine=self.key, rank=len(hits) + 1, query=query))
        return hits

    def _is_own_host(self, url: str) -> bool:
        if not self.own_hosts:
            return False
        host = registrable_host(url)
        return any(host == owned or host.endswith("." + owned) for owned in self.own_hosts)

    def _has_blocked_marker(self, html: str | None) -> bool:
        if not html or not self.blocked_markers:
            return False
        lowered = html[:200_000].lower()
        return any(marker in lowered for marker in self.blocked_markers)

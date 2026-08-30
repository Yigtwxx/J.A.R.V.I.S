"""Reverse image search by image URL — no upload, no account, no API key.

Three engines, each with a different failure mode, which is why more than one is
worth running:

* **yandex** — by a wide margin the best at finding *people*, and the only one
  that reliably surfaces social profiles. It is also the most aggressive about
  anti-bot walls, so it needs the stealth tier; when no browser is available the
  engine is skipped and says so rather than silently returning nothing.
* **bing** — decent recall, tolerates the HTTP tier, wraps every link in a
  ``bing.com/ck/a`` click tracker that ``clean_result_url`` already unwraps.
* **tineye** — exact-copy matches only. Poor for "who is this", excellent for
  "where else has this exact file been published".

Every candidate link is passed through ``match_profile_url``. A hit that is not a
profile URL is still returned — a personal site or a press page is a perfectly
good lead — but the caller can tell the two apart and weigh them differently.

Nothing here raises: a blocked engine, a redesigned SERP or a parse failure all
degrade to an empty list.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote

from app.discovery.engines.base import clean_result_url, iter_nodes, node_attr, node_text, normalize_hit_url
from app.discovery.platforms.urlmatch import match_profile_url, registrable_host
from app.discovery.types import SourceKind
from app.utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover - import kept out of the runtime path
    from app.discovery.fetch.result import FetchResult
    from app.discovery.fetch.session import FetchSession

SOURCE_KIND = SourceKind.REVERSE_IMAGE
"""Where these hits came from, for the confidence weighting."""

_YANDEX_URL = "https://yandex.com/images/search?rpt=imageview&url={u}"
_BING_URL = "https://www.bing.com/images/search?view=detailv2&iss=sbi&q=imgurl:{u}&form=IRSBIQ"
_TINEYE_URL = "https://tineye.com/search?url={u}"

# Hosts belonging to the engine itself, plus the boilerplate every SERP links to.
# Their presence in the results says nothing about the image.
_OWN_HOSTS: dict[str, tuple[str, ...]] = {
    "yandex": ("yandex.com", "yandex.ru", "yandex.net", "ya.ru", "yastatic.net", "dzen.ru"),
    "bing": ("bing.com", "microsoft.com", "microsofttranslator.com", "msn.com", "live.com", "windows.net"),
    "tineye": ("tineye.com", "ideeinc.com"),
}
_BOILERPLATE_HOSTS: tuple[str, ...] = (
    "w3.org",
    "schema.org",
    "gstatic.com",
    "googleapis.com",
    "googleadservices.com",
    "doubleclick.net",
)

_SUPPORTED = ("yandex", "bing", "tineye")


@dataclass(frozen=True, slots=True)
class ReverseHit:
    """One page that appears to carry the same image."""

    url: str
    title: str
    engine: str
    thumbnail: str | None = None


class ReverseImageSearcher:
    """Queries reverse-image engines with an image URL and normalises the links."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    async def search(
        self,
        fetch: FetchSession,
        image_url: str,
        *,
        engines: Sequence[str] = ("yandex", "bing"),
        limit: int = 20,
    ) -> list[ReverseHit]:
        """Run the requested engines in order and return de-duplicated hits."""
        target = (image_url or "").strip()
        if not self._enabled or not target or limit <= 0:
            return []

        hits: list[ReverseHit] = []
        seen: set[str] = set()
        for engine in engines:
            key = str(engine).strip().lower()
            if key not in _SUPPORTED:
                logger.log_warning(f"Reverse image: unknown engine {engine!r}, skipped")
                continue
            try:
                found = await self._run(fetch, key, target, limit)
            except Exception as exc:
                logger.log_warning(f"Reverse image: {key} raised {type(exc).__name__}: {exc}")
                continue
            for hit in found:
                identity = normalize_hit_url(hit.url)
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                hits.append(hit)
                if len(hits) >= limit:
                    return hits
        return hits[:limit]

    async def _run(self, fetch: FetchSession, engine: str, image_url: str, limit: int) -> list[ReverseHit]:
        encoded = quote(image_url, safe="")
        if engine == "yandex":
            if not fetch.stealth_available:
                reason = fetch.stealth_unavailable_reason or "stealth tier disabled"
                logger.log_warning(f"Reverse image: skipping Yandex — {reason}")
                return []
            url = _YANDEX_URL.format(u=encoded)
            result = await fetch.stealth(url, network_idle=True, solve_cloudflare=True)
        else:
            url = _BING_URL.format(u=encoded) if engine == "bing" else _TINEYE_URL.format(u=encoded)
            result = await fetch.get(url, escalate=True, min_html_bytes=0)

        if not result.ok:
            logger.log_warning(f"Reverse image: {engine} unusable — {result.describe()}")
            return []
        return _extract_hits(result, engine=engine, limit=limit)


def _extract_hits(result: FetchResult, *, engine: str, limit: int) -> list[ReverseHit]:
    """Pull outbound links off a SERP. Defensive: a redesign yields ``[]``, not a crash."""
    base = result.final_url or result.url
    own = _OWN_HOSTS.get(engine, ()) + _BOILERPLATE_HOSTS
    hits: list[ReverseHit] = []
    seen: set[str] = set()

    for node in iter_nodes(result.page, "a[href]"):
        target = clean_result_url(node_attr(node, "href"), base=base)
        if not target:
            continue
        host = registrable_host(target)
        if not host or any(host == owned or host.endswith("." + owned) for owned in own):
            continue
        identity = normalize_hit_url(target)
        if not identity or identity in seen:
            continue
        seen.add(identity)

        title = node_text(node) or node_attr(node, "title")
        thumbnail = None
        for image in iter_nodes(node, "img"):
            title = title or node_attr(image, "alt")
            thumbnail = node_attr(image, "src") or None
            break
        hits.append(ReverseHit(url=target, title=title, engine=engine, thumbnail=thumbnail))
        if len(hits) >= limit:
            break
    return hits


def is_generic_image(hits: Sequence[ReverseHit], *, distinct_person_threshold: int = 3) -> bool:
    """True when the same image appears under 3+ clearly different identities.

    A stock photo, a celebrity press shot or a platform default avatar shows up
    everywhere, so matching it proves nothing about *who* an account belongs to.
    Feeding such an image into the identity scorer is how one picture merges five
    unrelated people into a single fabricated profile — hence this guard, and
    hence the rule that a generic image is never identity evidence.

    Two counts decide it: how many distinct profile *usernames* the image is
    attached to (the same handle on five sites is one person, not five), and how
    many distinct registrable domains carry it. Many domains but no identity
    anywhere is the signature of a stock/press photo.
    """
    identities: set[str] = set()
    domains: set[str] = set()
    for hit in hits or ():
        host = registrable_host(hit.url)
        if host:
            domains.add(host)
        match = match_profile_url(hit.url)
        if match is not None:
            identities.add(match.username.lower())

    threshold = max(2, distinct_person_threshold)
    if len(identities) >= threshold:
        return True
    return not identities and len(domains) >= threshold * 2

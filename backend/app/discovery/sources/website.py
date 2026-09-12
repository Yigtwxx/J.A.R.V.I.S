"""Personal-website crawl: the highest-value non-platform source there is.

A person's own site is where the identity graph is written down by the person
themselves — the about page names the employer, the contact page carries the real
email, and ``rel="me"`` links are *bidirectional* (IndieAuth): a site that links to
a profile which links back is mutual confirmation, not a name coincidence. The
crawl is deliberately tiny — one entry URL plus at most ``max_pages - 1``
same-registrable-domain about/contact/CV pages — and is not a site mirror.

**SSRF is the real risk here**, because the URL arrives from search results, i.e.
from the open web. ``is_safe_url`` is the mandatory gate, applied three times: to
the entry URL, to every followed link, and to ``final_url`` after every redirect.
The last matters most — a public host can 302 straight to ``169.254.169.254``.
Only ``text/html`` and ``application/pdf`` are accepted.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urljoin, urlsplit

from app.discovery.engines.base import iter_nodes, node_text, normalize_hit_url
from app.discovery.fetch.selectors import css_all_attr, css_text, json_ld_of_type
from app.discovery.identity import contacts as contacts_module
from app.discovery.identity.contacts import ContactHit
from app.discovery.platforms.urlmatch import match_profile_url, registrable_host
from app.discovery.types import EvidenceKind, FetchStatus, SourceKind

if TYPE_CHECKING:  # pragma: no cover - import kept out of the runtime path
    from app.discovery.fetch.result import FetchResult
    from app.discovery.fetch.session import FetchSession

SOURCE_KIND = SourceKind.WEBSITE

# Carrier-grade NAT. `ipaddress.is_private` does not cover it on every Python.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")

_BLOCKED_HOSTS = frozenset({"localhost", "metadata", "instance-data", "metadata.google.internal"})
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".intranet", ".lan", ".home.arpa")
_ALLOWED_CONTENT = ("text/html", "application/xhtml", "application/pdf")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,24}")
# `logo@2x.png` and friends match the e-mail shape; their "TLD" gives them away.
_NON_TLD = frozenset({"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "html", "php", "woff", "ico", "json"})

# Path segments worth following. The Turkish spellings are not optional: on a
# Turkish personal site the about page is `/hakkimda`, never `/about`.
# fmt: off
_ABOUT_SEGMENTS = frozenset({
    "about", "hakkimda", "hakkinda", "hakkında", "bio", "cv", "resume", "ozgecmis",
    "özgeçmiş", "contact", "iletisim", "iletişim", "me", "team",
})
# fmt: on
_CV_TOKENS = ("cv", "resume", "résumé", "ozgecmis", "özgeçmiş", "curriculum", "vitae", "lebenslauf")


@dataclass(slots=True)
class SiteFindings:
    """Everything one small crawl learned. Never silently empty: see ``detail``.

    ``profile_urls`` are canonical, each confirmed by ``match_profile_url``;
    ``org_mentions`` holds JSON-LD ``jobTitle``/``worksFor``/``alumniOf``.
    """

    url: str
    emails: list[str] = field(default_factory=list)
    """Kept as plain strings for the existing callers; see ``contacts``."""
    contacts: list[ContactHit] = field(default_factory=list)
    """Addresses and numbers with the *page* that carried each one.

    ``emails`` records only the value, so everything downstream had to attribute
    it to ``findings.url`` — the entry page — even when it was found three hops
    away on ``/iletisim``. These carry the real source."""
    profile_urls: list[str] = field(default_factory=list)
    rel_me_urls: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    org_mentions: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    pages_fetched: int = 0
    blocked: bool = False
    detail: str = ""


def is_safe_url(url: str) -> bool:
    """True only for a URL that is safe for a *server* to fetch.

    Rejects non-http(s) schemes, userinfo (``http://evil@internal/``, which several
    parsers read as host ``evil``), bare IP literals, single-label and
    ``.local``/``.internal`` names, and any host resolving to loopback, RFC1918,
    link-local 169.254/16, CGNAT 100.64/10, IPv6 ULA fc00::/7 or IPv6 loopback.
    A name that does not resolve for us is allowed: the fetcher cannot reach it
    either, and failing closed on our resolver's hiccups would refuse real sites.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        split = urlsplit(url.strip())
    except ValueError:
        return False
    if (split.scheme or "").lower() not in ("http", "https") or "@" in (split.netloc or ""):
        return False
    try:
        host = (split.hostname or "").strip().lower().rstrip(".")
    except ValueError:
        return False
    if not host or host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        return False
    # A bare IP is never a personal site; a single-label name is internal-only.
    if "." not in host or _is_ip_literal(host):
        return False
    return all(not _is_blocked_address(address) for address in _resolve_addresses(host))


class WebsiteChain:
    """Crawls a handful of identity-bearing pages on a personal website."""

    def __init__(self, *, max_pages: int = 10) -> None:
        self._max_pages = max(1, max_pages)

    async def crawl(self, fetch: FetchSession, url: str, *, name_tokens: Sequence[str] = ()) -> SiteFindings:
        """Fetch the entry page plus up to ``max_pages - 1`` about-ish pages."""
        entry = (url or "").strip()
        findings = SiteFindings(url=entry)
        if not is_safe_url(entry):
            findings.blocked = True
            findings.detail = "entry URL rejected by the SSRF guard"
            return findings

        root = registrable_host(entry)
        tokens = tuple(str(t).strip().lower() for t in (name_tokens or ()) if str(t).strip())
        queue: list[str] = [entry]
        seen: set[str] = set()

        while queue and findings.pages_fetched < self._max_pages:
            target = queue.pop(0)
            identity = normalize_hit_url(target)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            if not is_safe_url(target):
                continue

            try:
                result = await fetch.get(target, escalate=False, min_html_bytes=0)
            except Exception as exc:
                findings.detail = findings.detail or f"fetch raised {type(exc).__name__}: {exc}"[:200]
                continue
            if result.status is FetchStatus.BLOCKED:
                findings.blocked = True
                findings.detail = result.describe()
                continue
            if not result.ok:
                findings.detail = findings.detail or result.describe()
                continue

            final = result.final_url or target
            if not is_safe_url(final):
                # A public host redirecting into private space is the whole reason
                # the guard is re-applied after the fetch.
                findings.detail = "redirect landed on a host rejected by the SSRF guard"
                continue

            content_type = _content_type(result)
            if content_type and not content_type.startswith(_ALLOWED_CONTENT):
                continue
            findings.pages_fetched += 1
            if content_type == "application/pdf":
                _add(findings.documents, final)
                continue

            candidates = _harvest(findings, result, final, root, tokens)
            if findings.pages_fetched < self._max_pages:
                queue.extend(url for url in candidates if normalize_hit_url(url) not in seen)

        if not findings.detail:
            findings.detail = f"{findings.pages_fetched} page(s) crawled on {root or entry}"
        return findings


def _harvest(findings: SiteFindings, result: FetchResult, base: str, root: str, tokens: tuple[str, ...]) -> list[str]:
    """Read one page into ``findings`` and return the links worth following next."""
    page = result.page
    _add(findings.titles, css_text(page, "title::text") or "")
    for node in iter_nodes(page, "h1")[:3]:
        _add(findings.titles, node_text(node))

    # `base`, not `findings.url`: an address on the contact page belongs to the
    # contact page. Attributing it to the entry URL is a provenance error that
    # nothing downstream could detect.
    hrefs = css_all_attr(page, 'a[href^="mailto:"]', "href") + css_all_attr(page, 'a[href^="tel:"]', "href")
    html_body = result.html or ""
    found = contacts_module.dedupe(
        [
            *contacts_module.from_hrefs(hrefs, source_url=base),
            *contacts_module.emails_from(html_body, source_url=base),
            *contacts_module.phones_from(html_body, source_url=base),
        ]
    )
    findings.contacts.extend(found)
    for hit in found:
        if hit.kind is EvidenceKind.EMAIL:
            _add(findings.emails, hit.value)

    for href in css_all_attr(page, 'a[rel~="me"]', "href") + css_all_attr(page, 'link[rel~="me"]', "href"):
        _add(findings.rel_me_urls, _absolutize(href, base))

    person = json_ld_of_type(page, "Person")
    if isinstance(person, dict):
        _add(findings.titles, person.get("name"))
        _add(findings.org_mentions, person.get("jobTitle"))
        for key in ("worksFor", "alumniOf", "affiliation"):
            for name in _org_names(person.get(key)):
                _add(findings.org_mentions, name)

    # One pass over the anchors: a profile, a CV, a page worth following, or junk.
    preferred: list[str] = []
    secondary: list[str] = []
    for href in css_all_attr(page, "a", "href"):
        absolute = _absolutize(href, base)
        if not absolute:
            continue
        profile = match_profile_url(absolute)
        if profile is not None and profile.canonical_url:
            _add(findings.profile_urls, profile.canonical_url)
            continue
        path = unquote(urlsplit(absolute).path or "/").lower()
        if path.endswith(".pdf"):
            if any(token in path for token in _CV_TOKENS):
                _add(findings.documents, absolute)
            continue
        if registrable_host(absolute) != root:
            continue
        if _looks_like_about_path(path):
            preferred.append(absolute)
        elif tokens and any(token in path for token in tokens):
            secondary.append(absolute)
    return preferred + secondary


def _looks_like_about_path(path: str) -> bool:
    """``/about``, ``/en/hakkimda``, ``/about-me.html`` — but not ``/media/x``."""
    for segment in path.rstrip("/").split("/"):
        stem = segment.rsplit(".", 1)[0] if segment else ""
        if stem and (stem in _ABOUT_SEGMENTS or any(stem.startswith((f"{t}-", f"{t}_")) for t in _ABOUT_SEGMENTS)):
            return True
    return False


def _content_type(result: FetchResult) -> str:
    """Lowercase MIME type from the response headers, ``""`` when unknown."""
    headers = getattr(result.page, "headers", None)
    try:
        raw = str(headers.get("content-type") or headers.get("Content-Type") or "") if headers else ""
    except Exception:
        return ""
    return raw.split(";", 1)[0].strip().lower()


def _absolutize(href: str, base: str) -> str:
    candidate = (href or "").strip()
    if not candidate or candidate.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return ""
    resolved = urljoin(base, "https:" + candidate if candidate.startswith("//") else candidate)
    return resolved if resolved.lower().startswith(("http://", "https://")) else ""


def _clean_email(raw: str) -> str:
    email = unquote((raw or "").strip()).strip(".,;:<>()[]").lower()
    if "@" not in email or email.rsplit(".", 1)[-1] in _NON_TLD:
        return ""
    return email if _EMAIL_RE.fullmatch(email) else ""


def _org_names(value: Any) -> list[str]:
    """JSON-LD organisations arrive as a string, an object, or a list of either."""
    if isinstance(value, list):
        return [name for item in value for name in _org_names(item)]
    if isinstance(value, dict):
        value = value.get("name")
    return [value] if isinstance(value, str) else []


def _add(target: list[str], value: Any) -> None:
    """Append a whitespace-collapsed string, keeping the list unique and ordered."""
    cleaned = " ".join(value.split()) if isinstance(value, str) else ""
    if cleaned and cleaned not in target:
        target.append(cleaned)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _is_blocked_address(address: str) -> bool:
    """True for loopback, RFC1918, link-local, CGNAT, ULA and anything unparseable."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    reserved = ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast
    return bool(reserved) or (ip.version == 4 and ip in _CGNAT)


@lru_cache(maxsize=1024)
def _resolve_addresses(host: str) -> tuple[str, ...]:
    """Every address ``host`` resolves to. Empty when it does not resolve."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError, ValueError):
        return ()
    return tuple({str(info[4][0]).split("%", 1)[0] for info in infos if info and info[4]})

"""Public e-mail addresses and phone numbers, each tied to the page that said it.

Both `EvidenceKind.EMAIL` and `EvidenceKind.PHONE` existed for months with four
consumers — the grounding gate, the query generator, the graph and the seed
expander — and **zero producers**. `SiteFindings.emails` was even collected on
every personal-site crawl and then dropped on the floor. This module is the
producer, and it exists once rather than three times because the deny-list has to
be shared: two copies is how the same address gets published from one page and
suppressed from another.

Two rules carry it:

1. **A contact with no source is not a finding.** Every hit carries the URL of
   the page that published it, so a phone number is exactly as auditable as a
   sentence in the biography.
2. **A phone number is admitted on its dialling prefix, never on "digits with
   punctuation".** A bare seven-to-fifteen digit run is indistinguishable from a
   price, an invoice id, a date or a coordinate — the legacy
   `scraper_service._PHONE_PATTERNS` makes both the ``+`` and every separator
   optional and therefore matches `12.03.2024 15`. Missing a bare `532 123 45 67`
   is the price of never printing an order number as somebody's mobile.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from app.discovery.types import EvidenceKind

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,24}")

# `logo@2x.png` and friends match the e-mail shape; their "TLD" gives them away.
_NON_TLD = frozenset({"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "html", "php", "woff", "ico", "json"})

# Obfuscation is concentrated on exactly the pages that matter — a contact page
# is where someone both publishes an address and tries to hide it from crawlers.
_OBFUSCATED_RE = re.compile(
    r"([A-Za-z0-9._%+\-]+)\s*(?:\[|\()?\s*(?:at|@|nospam)\s*(?:\]|\))?\s*"
    r"([A-Za-z0-9\-]+(?:\s*(?:\[|\()?\s*(?:dot|\.)\s*(?:\]|\))?\s*[A-Za-z0-9\-]+)+)",
    re.IGNORECASE,
)
_DOT_RE = re.compile(r"\s*(?:\[|\()?\s*(?:dot|\.)\s*(?:\]|\))?\s*", re.IGNORECASE)

_DENY_LOCALS = frozenset(
    {
        "noreply",
        "no-reply",
        "donotreply",
        "do-not-reply",
        "postmaster",
        "mailer-daemon",
        "abuse",
        "webmaster",
        "hostmaster",
        "email",
        "youremail",
        "your-email",
        "name",
        "user",
        "example",
    }
)
# RFC 2606 reserves example.com/net/org, and they are also this repo's fixture
# convention for a perfectly ordinary site. They are deliberately NOT here: the
# realistic placeholder is `you@example.com`, and `_DENY_LOCALS` already refuses
# every local part a template ships with. Denying the domain outright would buy
# very little and make every test fixture disagree with production.
_DENY_DOMAINS = frozenset(
    {
        "domain.com",
        "yourdomain.com",
        "email.com",
        "localhost",
        "test.com",
        "sentry.io",
        "wixpress.com",
        "sentry.wixpress.com",
        "sentry-next.wixpress.com",
        "godaddy.com",
        "squarespace.com",
        "wordpress.com",
    }
)
_DENY_SUFFIXES = ("@users.noreply.github.com",)

# Wix injects a Sentry DSN whose public key is 32 hex characters and whose shape
# is a valid e-mail. Turkish personal sites are heavily Wix, so this is the most
# common single false positive in the whole extractor.
_HEX_LOCAL_RE = re.compile(r"^[0-9a-f]{32}$")

_ZERO_WIDTH = str.maketrans("", "", "​‌‍﻿­")

_PHONE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # E.164 / international: +90 532 123 45 67, +1 (555) 123-4567, +442079460958
    re.compile(r"(?<![\w+])\+\d{1,3}[\s.\- ]?(?:\(\d{1,4}\)[\s.\- ]?)?\d(?:[\s.\- ]?\d){6,13}(?!\w)"),
    # Turkish national, trunk zero required: 0532 123 45 67, 0(212) 123 45 67
    re.compile(r"(?<![\w+])0[\s.\-]?\(?(?:5\d{2}|[234]\d{2})\)?[\s.\-]?\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2}(?!\w)"),
    # NANP with an explicit area-code parenthesis: (555) 123-4567
    re.compile(r"(?<![\w+])\(\d{3}\)[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\w)"),
)

_CONTACT_WORDS = (
    "tel",
    "telefon",
    "phone",
    "gsm",
    "cep",
    "mobil",
    "mobile",
    "iletisim",
    "iletişim",
    "contact",
    "call",
    "whatsapp",
)
"""Words that turn a dialable-looking number into a number meant to be dialled."""

_CONTEXT_WINDOW = 60
"""Characters before a match searched for a contact word. About one clause."""

_CURRENCY = ("₺", "$", "€", "£", "tl", "try", "usd", "eur", "gbp")
_ID_PREFIXES = ("iban", "tckn", "t.c.", "vkn", "vergi", "isbn", "sipariş", "siparis", "order", "invoice", "fatura")
_DATE_RE = re.compile(r"^\d{1,4}[./-]\d{1,2}[./-]\d{2,4}$")

PHONE_FLOOR = 0.6
"""Below this a number is dropped. A footer number with no contact word nearby is
usually the hosting company's, and printing it as the subject's is worse than
missing it."""


@dataclass(frozen=True, slots=True)
class ContactHit:
    """One address or number, with the page that stated it."""

    kind: EvidenceKind
    value: str
    """Normalised: lower-cased address, or E.164 where the region is known."""
    display: str
    """As written on the page. The needle a grounding check can actually find."""
    source_url: str
    extractor: str
    confidence: float

    @property
    def subject(self) -> str:
        """The evidence subject, matching the ``employer``/``location`` convention."""
        return "email" if self.kind is EvidenceKind.EMAIL else "phone"


def normalize_email(raw: str) -> str | None:
    """Lower-case and strip an address, or None when it is not one worth keeping.

    Plus-addressing is deliberately preserved: ``yigit+jobs@`` and ``yigit@`` are
    two different published facts, and which service an address was handed to is
    real signal. Rewriting it would also mean printing an address the page never
    contained, which is the same category of error as an ungrounded sentence.
    """
    candidate = unquote(html.unescape(raw or "")).translate(_ZERO_WIDTH).strip().strip(".,;:<>()[]\"'")
    if not candidate or candidate.count("@") != 1:
        return None
    local, _, domain = candidate.partition("@")
    local, domain = local.strip().lower(), domain.strip().lower().rstrip(".")
    if not local or not domain or "." not in domain:
        return None
    tld = domain.rsplit(".", 1)[-1]
    if tld in _NON_TLD or not tld.isalpha() or not 2 <= len(tld) <= 24:
        return None
    if local in _DENY_LOCALS or domain in _DENY_DOMAINS or _HEX_LOCAL_RE.match(local):
        return None
    address = f"{local}@{domain}"
    if address.endswith(_DENY_SUFFIXES):
        return None
    return address


def normalize_phone(raw: str, *, default_region: str = "TR") -> tuple[str, bool] | None:
    """Return ``(normalised, is_international)`` or None when it is not a number.

    A Turkish trunk-zero number becomes E.164; anything else with no region
    signal stays in its national form rather than having a country code invented
    for it. The flag lets the caller say which it produced.
    """
    text = (raw or "").translate(_ZERO_WIDTH).strip()
    digits = re.sub(r"[^\d+]", "", text)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    plus = digits.startswith("+")
    bare = digits.lstrip("+")
    if not bare.isdigit() or not 7 <= len(bare) <= 15:
        return None
    if len(set(bare)) <= 2:
        return None
    if bare in ("1234567890", "0123456789", "9876543210"):
        return None
    if plus:
        return f"+{bare}", True
    if default_region == "TR" and len(bare) == 11 and bare.startswith("0"):
        return f"+90{bare[1:]}", True
    return bare, False


def _looks_like_something_else(text: str, start: int, end: int) -> bool:
    """True when the surrounding characters say this run of digits is not a phone."""
    before = text[max(0, start - _CONTEXT_WINDOW) : start].lower()
    after = text[end : end + 12].lower()
    match = text[start:end]

    if _DATE_RE.match(match.strip()):
        return True
    if any(prefix in before[-24:] for prefix in _ID_PREFIXES):
        return True
    if any(mark in before[-6:] or mark in after[:6] for mark in _CURRENCY):
        return True
    # Inside a URL or a query parameter: an id, a sku, an order number.
    if "http" in before[-80:] and " " not in before[before.rfind("http") :]:
        return True
    if re.search(r"[?&](id|sku|order|no|ref|p)=\s*$", before):
        return True
    # A signed decimal pair is a coordinate, not two phone numbers.
    return bool(re.search(r"-?\d+\.\d+\s*,\s*$", before))


def _phone_confidence(text: str, start: int, *, path_is_about: bool) -> float:
    """0.55 for the shape alone, more when the page says it is a phone number."""
    before = text[max(0, start - _CONTEXT_WINDOW) : start].lower()
    score = 0.55
    if any(word in before for word in _CONTACT_WORDS):
        score += 0.20
    if path_is_about:
        score += 0.10
    return min(0.9, score)


def emails_from(text: str, *, source_url: str, extractor: str = "text") -> list[ContactHit]:
    """Every address in ``text``, plain or lightly obfuscated."""
    hits: list[ContactHit] = []
    unescaped = html.unescape(text or "")

    for raw in _EMAIL_RE.findall(unescaped):
        address = normalize_email(raw)
        if address:
            hits.append(
                ContactHit(
                    kind=EvidenceKind.EMAIL,
                    value=address,
                    display=raw,
                    source_url=source_url,
                    extractor=extractor,
                    confidence=0.85,
                )
            )

    # `@` is one of the obfuscation separators, so this pass also re-matches
    # every plain address — including `name @ domain . com`, which the strict
    # pattern above cannot see. Deduping keeps the plain reading, which scores
    # higher, and lets the loose pattern earn its keep on the spaced-out ones.
    for local, domain_part in _OBFUSCATED_RE.findall(unescaped):
        address = normalize_email(f"{local}@{_DOT_RE.sub('.', domain_part)}")
        if address:
            hits.append(
                ContactHit(
                    kind=EvidenceKind.EMAIL,
                    value=address,
                    display=address,
                    source_url=source_url,
                    extractor="obfuscated",
                    confidence=0.8,
                )
            )
    return dedupe(hits)


def phones_from(text: str, *, source_url: str, default_region: str = "TR", extractor: str = "text") -> list[ContactHit]:
    """Every number in ``text`` that both looks dialable and reads as one."""
    body = (text or "").translate(_ZERO_WIDTH)
    path_is_about = _path_looks_like_contact(source_url)
    hits: list[ContactHit] = []

    for pattern in _PHONE_PATTERNS:
        for match in pattern.finditer(body):
            if _looks_like_something_else(body, match.start(), match.end()):
                continue
            normalised = normalize_phone(match.group(0), default_region=default_region)
            if normalised is None:
                continue
            value, international = normalised
            confidence = _phone_confidence(body, match.start(), path_is_about=path_is_about)
            if confidence < PHONE_FLOOR:
                continue
            hits.append(
                ContactHit(
                    kind=EvidenceKind.PHONE,
                    value=value,
                    display=match.group(0).strip(),
                    source_url=source_url,
                    extractor=extractor if international else f"{extractor}:national",
                    confidence=confidence,
                )
            )
    return hits


def from_hrefs(hrefs: Sequence[str], *, source_url: str) -> list[ContactHit]:
    """``mailto:`` and ``tel:`` links, which need no context gate.

    The document has already declared the type. Requiring a nearby contact word
    would be second-guessing a machine-readable claim, so a ``tel:`` href starts
    well above the floor a regex match has to climb to.
    """
    hits: list[ContactHit] = []
    for href in hrefs:
        lowered = (href or "").strip().lower()
        if lowered.startswith("mailto:"):
            raw = href[len("mailto:") :].split("?", 1)[0]
            address = normalize_email(raw)
            if address:
                hits.append(
                    ContactHit(
                        kind=EvidenceKind.EMAIL,
                        value=address,
                        display=unquote(raw),
                        source_url=source_url,
                        extractor="mailto",
                        confidence=0.9,
                    )
                )
        elif lowered.startswith("tel:"):
            raw = unquote(href[len("tel:") :]).strip()
            normalised = normalize_phone(raw)
            if normalised is not None:
                hits.append(
                    ContactHit(
                        kind=EvidenceKind.PHONE,
                        value=normalised[0],
                        display=raw,
                        source_url=source_url,
                        extractor="tel",
                        confidence=0.85,
                    )
                )
    return hits


def dedupe(hits: Iterable[ContactHit]) -> list[ContactHit]:
    """One hit per ``(kind, value, source host)``, keeping the most confident.

    Deliberately the same key `Evidence.fingerprint` uses. The same address on
    two different sites must stay two rows: that is corroboration, and the scorer
    counts distinct source domains.
    """
    best: dict[tuple[EvidenceKind, str, str], ContactHit] = {}
    for hit in hits:
        key = (hit.kind, hit.value, _host_of(hit.source_url))
        current = best.get(key)
        if current is None or hit.confidence > current.confidence:
            best[key] = hit
    return list(best.values())


def _host_of(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _path_looks_like_contact(url: str) -> bool:
    """True for `/contact`, `/iletisim`, `/hakkimda` and their neighbours.

    The Turkish spellings are not optional: on a Turkish personal site the
    contact page is `/iletisim`, never `/contact`.
    """
    try:
        path = (urlsplit(url).path or "").lower()
    except ValueError:
        return False
    return any(
        segment in path
        for segment in ("contact", "iletisim", "iletişim", "hakkimda", "hakkında", "about", "impressum", "kunye")
    )

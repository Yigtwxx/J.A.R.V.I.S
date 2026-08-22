"""Dork templates — the questions we ask the open web.

Two ideas drive every template here.

**Diacritics are a discovery problem, not a display problem.** A Turkish name is
indexed under both spellings: the page title says ``Yağmur Özgan`` while the
username and the email local-part say ``yagmurozgan``. Searching one spelling
loses whichever half of the web used the other, so templates emit both whenever
they differ — quoted phrases keep the diacritics, handle-shaped forms are folded.

**Operator support is not uniform.** ``site:`` with a path (``site:linkedin.com/in``)
is a Google-only extension; every other engine returns nothing for it, which reads
exactly like "this person has no LinkedIn". So the path form is opt-in via
``google_syntax``, and everyone else gets a host-only ``site:`` plus a phrase query.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.discovery.types import EntityType

# Characters NFKD cannot decompose on its own. Turkish dotless-i in particular has
# no combining form, so it must be mapped explicitly or it vanishes entirely.
_FOLD_MAP = str.maketrans(
    {"ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U", "ö": "o", "Ö": "O"}
    | {"ç": "c", "Ç": "C", "ø": "o", "Ø": "O", "ß": "ss", "æ": "ae", "Æ": "AE", "ð": "d", "ł": "l", "Ł": "L"}
)

_QUOTE_CHARS = "\"'“”‘’«»"

# Splits a query into tokens while keeping quoted phrases intact.
_TOKEN_RE = re.compile(r'"[^"]*"|\S+')


@dataclass(frozen=True, slots=True)
class QueryTerms:
    """Everything known about the target before any searching has happened."""

    raw: str
    name: str
    """Cleaned display name, diacritics intact."""

    tokens: tuple[str, ...]
    """Lowercase ASCII-folded name tokens — the handle-shaped view of the name."""

    entity: EntityType
    usernames: tuple[str, ...] = ()
    location: str | None = None
    employer: str | None = None
    school: str | None = None
    email: str | None = None
    domain: str | None = None

    @property
    def folded_name(self) -> str:
        """The display name with diacritics removed, casing preserved."""
        return ascii_fold(self.name)

    @property
    def handle(self) -> str:
        """``yagmurozgan`` — the shape a username usually takes."""
        return "".join(self.tokens)


def normalize_query(text: str) -> str:
    """Collapse whitespace and strip wrapping quotes."""
    collapsed = " ".join((text or "").split())
    return collapsed.strip(_QUOTE_CHARS).strip()


def ascii_fold(text: str) -> str:
    """Fold to plain ASCII: ``Yiğit`` -> ``Yigit``, ``Özgan`` -> ``Ozgan``."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text.translate(_FOLD_MAP))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.encode("ascii", "ignore").decode("ascii")


def build_query_terms(
    raw: str,
    entity: EntityType,
    *,
    usernames: Sequence[str] = (),
    location: str | None = None,
    employer: str | None = None,
    school: str | None = None,
    email: str | None = None,
    domain: str | None = None,
) -> QueryTerms:
    """Construct ``QueryTerms`` with the name cleaned and tokens folded."""
    name = normalize_query(raw)
    tokens = tuple(part for part in ascii_fold(name).lower().split() if part)
    return QueryTerms(
        raw=raw,
        name=name,
        tokens=tokens,
        entity=entity,
        usernames=tuple(dict.fromkeys(u.strip() for u in usernames if u and u.strip())),
        location=location,
        employer=employer,
        school=school,
        email=email,
        domain=domain,
    )


def canonical_query(q: str) -> str:
    """Canonical form used for de-duplication only — never sent to an engine.

    Lowercases, collapses whitespace and sorts operator tokens, so
    ``site:x.com "a b"`` and ``"a b" site:x.com`` are recognised as one query.
    """
    lowered = " ".join((q or "").lower().split())
    if not lowered:
        return ""
    tokens = _TOKEN_RE.findall(lowered)
    operators = sorted(t for t in tokens if _is_operator(t))
    plain = [t for t in tokens if not _is_operator(t)]
    return " ".join(operators + plain)


def entity_queries(terms: QueryTerms, *, limit: int = 12) -> list[str]:
    """Broad discovery dorks for the entity itself, most valuable first."""
    phrase = quoted(terms.name)
    if not phrase:
        return []
    out: list[str] = [phrase]

    folded = terms.folded_name
    if folded and folded.casefold() != terms.name.casefold():
        # Turkish pages index both spellings; asking for only one halves recall.
        out.append(quoted(folded))

    if terms.entity is EntityType.COMPANY:
        out += _company_queries(terms, phrase)
    elif terms.entity is EntityType.PLACE:
        out += _place_queries(terms, phrase)
    else:
        out += _person_queries(terms, phrase)

    return _finalize(out, limit)


def platform_queries(
    terms: QueryTerms,
    platform_host: str,
    *,
    usernames: Sequence[str] = (),
    limit: int = 8,
    path_hint: str | None = None,
    google_syntax: bool = False,
) -> list[str]:
    """Dorks that pin the search to one platform.

    ``path_hint`` (``"in"`` for LinkedIn profiles, ``"user"`` for Reddit) narrows
    the search to the profile section of the site. It is only emitted as
    ``site:host/path`` when ``google_syntax`` is set, because every other engine
    treats a path in ``site:`` as an unmatchable literal and returns zero results —
    indistinguishable from "no profile exists". For those engines the hint becomes
    a plain quoted phrase instead, which they do match against the URL text.
    """
    host = (platform_host or "").strip().lower().lstrip("/")
    if not host or not terms.name:
        return []
    phrase = quoted(terms.name)
    path = (path_hint or "").strip("/")

    out: list[str] = [f"site:{host} {phrase}"]
    if path:
        out.append(f"site:{host}/{path} {phrase}" if google_syntax else f"{phrase} {quoted(f'{host}/{path}')}")

    folded = terms.folded_name
    if folded and folded.casefold() != terms.name.casefold():
        out.append(f"site:{host} {quoted(folded)}")

    handles = list(dict.fromkeys([*usernames, *terms.usernames, terms.handle]))
    for handle in handles:
        candidate = (handle or "").strip()
        if len(candidate) < 3:
            continue
        out.append(f"site:{host} {candidate}")
        if path and google_syntax:
            out.append(f"site:{host}/{path} {candidate}")

    return _finalize(out, limit)


def evidence_queries(terms: QueryTerms, *, kind: str, value: str, limit: int = 6) -> list[str]:
    """Dorks that chase one concrete piece of evidence back to its other homes."""
    needle = (value or "").strip()
    if not needle:
        return []
    phrase = quoted(terms.name)
    quoted_value = quoted(needle)
    normalized_kind = (kind or "").strip().lower()

    out: list[str] = [quoted_value]
    if normalized_kind == "email":
        local = needle.split("@", 1)[0]
        out += [f"{quoted_value} {phrase}", quoted(local), f"{quoted(local)} {phrase}", f"{quoted_value} contact"]
    elif normalized_kind == "username":
        out += [f"{quoted_value} {phrase}", f"{quoted_value} profile", f"{quoted_value} github", f"{quoted_value} bio"]
    elif normalized_kind == "domain":
        out += [f"site:{needle}", f"{quoted_value} {phrase}", f"{quoted_value} contact", f"link:{needle}"]
    elif normalized_kind == "phone":
        out += [f"{quoted_value} {phrase}", f"{quoted_value} contact"]
    else:
        out += [f"{quoted_value} {phrase}", f"{quoted_value} {normalized_kind}" if normalized_kind else quoted_value]

    return _finalize(out, limit)


def quoted(text: str) -> str:
    """Wrap ``text`` in a phrase quote, dropping any quotes it already contains."""
    inner = " ".join((text or "").replace('"', " ").split())
    return f'"{inner}"' if inner else ""


def _person_queries(terms: QueryTerms, phrase: str) -> list[str]:
    out = [
        f"{phrase} linkedin",
        f"{phrase} instagram",
        f"{phrase} github",
        f"{phrase} twitter",
    ]
    if terms.location:
        out.append(f"{phrase} {terms.location}")
    if terms.employer:
        out.append(f"{phrase} {terms.employer}")
    if terms.school:
        out.append(f"{phrase} {terms.school}")
    out += [
        f"{phrase} cv OR resume",
        f"{phrase} biography",
        f"{phrase} @",
    ]
    if terms.email:
        out.append(quoted(terms.email))
    if terms.domain:
        out.append(f"{phrase} {terms.domain}")
    handle = terms.handle
    if len(handle) >= 4:
        out.append(f"{quoted(handle)} {phrase}")
    for username in terms.usernames[:2]:
        out.append(f"{phrase} {quoted(username)}")
    return out


def _company_queries(terms: QueryTerms, phrase: str) -> list[str]:
    out = [
        f"{phrase} official site",
        f"{phrase} linkedin company",
        f"{phrase} about",
        f"{phrase} headquarters",
        f"{phrase} founded",
    ]
    if terms.location:
        out.append(f"{phrase} {terms.location}")
    if terms.domain:
        out.append(f"site:{terms.domain}")
    return out


def _place_queries(terms: QueryTerms, phrase: str) -> list[str]:
    out = [f"{phrase} address", f"{phrase} official", f"{phrase} opening hours", f"{phrase} reviews"]
    if terms.location:
        out.append(f"{phrase} {terms.location}")
    return out


def _finalize(queries: Sequence[str], limit: int) -> list[str]:
    """De-duplicate by canonical form, preserving order, then cap at ``limit``."""
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        cleaned = " ".join((query or "").split())
        if not cleaned:
            continue
        canonical = canonical_query(cleaned)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        out.append(cleaned)
        if len(out) >= max(1, limit):
            break
    return out


def _is_operator(token: str) -> bool:
    """``site:x.com`` is an operator; ``"a: b"`` is a quoted phrase that merely contains a colon."""
    return ":" in token and not token.startswith('"')

"""Employment and education extraction from sources we can actually reach.

The highest-value extractor here is :func:`from_linkedin_serp_title`: LinkedIn
answers bots with HTTP 999, but its SERP titles carry name, role, employer and
school in a fixed shape and cost **zero** linkedin.com requests.

Everything in this module is conservative by design. A wrong employer is worse
than a missing one: it corroborates the wrong person, which then drags every
later round off-target. Hence the name-mismatch guard, and hence
:func:`is_grounded`, which rejects any claim naming an entity that does not
appear in the source text at all.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from app.discovery.identity.normalize import fold_ascii, normalize_org
from app.discovery.identity.normalize import name_tokens as tokens_of

_SEPARATORS = re.compile(r"\s+[-–—|]\s+")
_TRAILING_BRAND = re.compile(r"\s*[-–—|]?\s*\|?\s*linkedin\s*$", re.IGNORECASE)
_AT_SPLIT = re.compile(r"\s+(?:at|@)\s+", re.IGNORECASE)
_SCHOOL_YEAR = re.compile(r"\b(?P<inst>[^\W\d_]{2,40}(?:\s+[^\W\d_]{2,40}){0,3})\s*['’](?P<yy>\d{2})\b")
# "Software Engineer at Getir" and "Software Engineer @Getir" both count; the `@`
# form usually has no space after it, which an `\s+` after the alternation would
# miss. A *bare* "@handle" with no role in front is not matched here on purpose —
# see the note in `from_bio_text`.
_ROLE_AT_ORG = re.compile(
    r"(?P<role>[A-ZÇĞİÖŞÜ][\w .&/-]{2,40}?)\s+(?:at\s+|@\s*)(?P<org>[^\W\d_][\w.&-]*(?:\s+[^\W\d_][\w.&-]*){0,3})"
)
_PIPE_PAIR = re.compile(r"^(?P<org>[^|@]{2,40})\|(?P<role>[^|]{2,40})$")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _words(text: str) -> frozenset[str]:
    """Whitespace-separated keyword list -> lookup set. Keeps the tables readable."""
    return frozenset(text.split())


# University/school markers in BOTH English and Turkish: a segment matching any of
# these is education, never an employer.
_EDU_KEYWORDS: frozenset[str] = _words(
    "university universitesi universite college school okulu lisesi institute enstitu enstitusu"
    " akademi academy faculty fakultesi polytechnic kolej"
)

# Role vocabulary. Only used to decide whether a LONE trailing segment is a job
# title rather than an employer; position decides everything else.
_ROLE_HINTS: frozenset[str] = _words(
    "engineer developer analyst manager designer scientist consultant director founder intern lead owner officer"
    " head coordinator associate assistant editor teacher architect researcher student specialist muhendisi"
    " yazilim uzmani danismani"
)

# Claim words that are capitalised but assert nothing about identity.
_GROUNDING_STOPWORDS: frozenset[str] = frozenset({"the", "a", "an", "i", "he", "she", "they", "it", "at", "in", "of"})


@dataclass(frozen=True, slots=True)
class WorkRecord:
    """One employment claim, with the source that produced it."""

    organization: str
    organization_normalized: str
    role: str | None = None
    start: str | None = None
    end: str | None = None
    is_current: bool | None = None
    source_url: str = ""
    extractor: str = ""
    confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class EducationRecord:
    """One education claim, with the source that produced it."""

    institution: str
    institution_normalized: str
    degree: str | None = None
    field_of_study: str | None = None
    start: str | None = None
    end: str | None = None
    source_url: str = ""
    extractor: str = ""
    confidence: float = 0.5


def _is_education(text: str) -> bool:
    return any(keyword in fold_ascii(text).split() for keyword in _EDU_KEYWORDS)


def _looks_like_role(text: str) -> bool:
    return any(word in _ROLE_HINTS for word in fold_ascii(text).split())


def _work(
    org: str, *, role: str | None, url: str, extractor: str, confidence: float, current: bool | None = None
) -> WorkRecord:
    return WorkRecord(
        organization=org.strip(),
        organization_normalized=normalize_org(org),
        role=(role or "").strip() or None,
        is_current=current,
        source_url=url,
        extractor=extractor,
        confidence=confidence,
    )


def _education(inst: str, *, url: str, extractor: str, confidence: float, end: str | None = None) -> EducationRecord:
    return EducationRecord(
        institution=inst.strip(),
        institution_normalized=normalize_org(inst),
        end=end,
        source_url=url,
        extractor=extractor,
        confidence=confidence,
    )


def from_linkedin_serp_title(
    title: str, snippet: str, url: str, *, name_tokens: Sequence[str]
) -> tuple[list[WorkRecord], list[EducationRecord]]:
    """Parse a LinkedIn SERP title without ever requesting linkedin.com.

    Returns empty lists when the leading name segment shares no token with the
    subject's name — that title belongs to a different person, and accepting it
    is precisely how same-name identities get merged.
    """
    cleaned = _TRAILING_BRAND.sub("", (title or "").strip()).strip(" -–—|")
    segments = [s.strip() for s in _SEPARATORS.split(cleaned) if s.strip()]
    if len(segments) < 2:
        return [], []

    subject = set(name_tokens)
    if not subject or not subject & set(tokens_of(segments[0])):
        return [], []

    work: list[WorkRecord] = []
    education: list[EducationRecord] = []
    body = segments[1:]
    corroborated = 0.7 if any(fold_ascii(s) in fold_ascii(snippet or "") for s in body) else 0.6

    def record(org: str, role: str | None) -> WorkRecord:
        return _work(org, role=role, url=url, extractor="linkedin_serp_title", confidence=corroborated)

    plain: list[str] = []
    for segment in body:
        if _is_education(segment):
            education.append(_education(segment, url=url, extractor="linkedin_serp_title", confidence=corroborated))
            continue
        at_match = _AT_SPLIT.search(segment)
        if at_match:
            role, _, org = segment.partition(at_match.group(0))
            if org.strip():
                work.append(record(org, role))
                continue
        plain.append(segment)

    # Position, not vocabulary, decides what a segment is. LinkedIn's shape is
    # `Name - Role - Company`, so the last segment is the employer even when the
    # role is one no keyword list happens to contain ("Product Owner").
    if not work and plain:
        if len(plain) >= 2:
            work.append(record(plain[-1], plain[0]))
        elif not _looks_like_role(plain[0]):
            # A lone segment is only an employer when it carries no role vocabulary
            # at all — inventing an employer is worse than reporting none.
            work.append(record(plain[0], None))

    return work, education


def from_github_profile(data: dict[str, Any], url: str) -> list[WorkRecord]:
    """The GitHub ``company`` field, which is self-reported but API-authoritative."""
    company = str((data or {}).get("company") or "").strip().lstrip("@").strip()
    if len(company) < 2:
        return []
    return [_work(company, role=None, url=url, extractor="github_api", confidence=0.85, current=True)]


def from_json_ld(obj: dict[str, Any], url: str) -> tuple[list[WorkRecord], list[EducationRecord]]:
    """schema.org ``Person``: ``worksFor`` / ``alumniOf`` / ``jobTitle``."""

    def names(value: Any) -> list[str]:
        items = value if isinstance(value, list) else [value]
        out: list[str] = []
        for item in items:
            label = item.get("name") if isinstance(item, dict) else item
            if isinstance(label, str) and len(label.strip()) >= 2:
                out.append(label.strip())
        return out

    if not isinstance(obj, dict):
        return [], []
    role = obj.get("jobTitle")
    role = role.strip() if isinstance(role, str) else None
    work = [
        _work(org, role=role, url=url, extractor="json_ld", confidence=0.8, current=True)
        for org in names(obj.get("worksFor"))
    ]
    education = [_education(inst, url=url, extractor="json_ld", confidence=0.8) for inst in names(obj.get("alumniOf"))]
    return work, education


def from_bio_text(bio: str, url: str, *, extractor: str) -> tuple[list[WorkRecord], list[EducationRecord]]:
    """Conservative bio mining: ``Role at Org``, ``@Org``, ``Org | Role``, ``ITU '22``."""
    text = (bio or "").strip()
    if not text:
        return [], []
    work: list[WorkRecord] = []
    education: list[EducationRecord] = []

    for match in _ROLE_AT_ORG.finditer(text):
        org = match.group("org").strip(" .,")
        if _is_education(org):
            education.append(_education(org, url=url, extractor=extractor, confidence=0.5))
        else:
            work.append(_work(org, role=match.group("role"), url=url, extractor=extractor, confidence=0.55))

    # A bare "@handle" in a bio is deliberately NOT read as an employer. Observed
    # live: it turned every friend, brand and cross-promoted account into an
    # employment record, and the pipeline then asked the user "sources disagree
    # about employer" with a list of usernames. A wrong employer is worse than a
    # missing one. The "Role at @org" form is already covered by _ROLE_AT_ORG.

    for line in re.split(r"[\n;·•]+", text):
        pair = _PIPE_PAIR.match(line.strip())
        if pair and not _is_education(pair.group("org")):
            work.append(
                _work(pair.group("org"), role=pair.group("role"), url=url, extractor=extractor, confidence=0.45)
            )

    for match in _SCHOOL_YEAR.finditer(text):
        year = int(match.group("yy"))
        end = f"{1900 + year if year > 50 else 2000 + year}"
        education.append(_education(match.group("inst"), url=url, extractor=extractor, confidence=0.45, end=end))

    return dedupe_work(work), dedupe_education(education)


def is_grounded(claim: str, source_text: str) -> bool:
    """Whether every proper noun and number in ``claim`` appears in ``source_text``.

    This is the gate that rejects hallucinated LLM output: a model that invents an
    employer names an organisation the source never mentions, and that is exactly
    what this catches. Both sides are ASCII-folded first so Turkish spelling
    differences do not read as fabrication.
    """
    if not (claim or "").strip():
        return False
    markers = {
        fold_ascii(word)
        for word in _WORD.findall(claim)
        if (word[0].isupper() or word.isdigit()) and fold_ascii(word) not in _GROUNDING_STOPWORDS
    }
    markers = {m for m in markers if len(m) > 1}
    if not markers:
        return True
    source = set(_WORD.findall(fold_ascii(source_text or "")))
    return markers <= source


def dedupe_work(records: Iterable[WorkRecord]) -> list[WorkRecord]:
    """Collapse duplicate employers, keeping the highest-confidence record."""
    best: dict[tuple[str, str], WorkRecord] = {}
    for record in records:
        if not record.organization_normalized:
            continue
        key = (record.organization_normalized, fold_ascii(record.role or ""))
        current = best.get(key)
        if current is None or record.confidence > current.confidence:
            best[key] = record
    return list(best.values())


def dedupe_education(records: Iterable[EducationRecord]) -> list[EducationRecord]:
    """Collapse duplicate institutions, keeping the highest-confidence record."""
    best: dict[tuple[str, str], EducationRecord] = {}
    for record in records:
        if not record.institution_normalized:
            continue
        key = (record.institution_normalized, fold_ascii(record.degree or ""))
        current = best.get(key)
        if current is None or record.confidence > current.confidence:
            best[key] = record
    return list(best.values())

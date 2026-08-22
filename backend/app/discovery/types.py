"""Shared enums and small value types for the discovery pipeline.

Kept dependency-free on purpose: every other discovery module imports from here,
so anything heavier would create import cycles.
"""

from __future__ import annotations

from enum import StrEnum


class EntityType(StrEnum):
    """What the user is looking for. Drives dork templates and which platforms apply."""

    PERSON = "person"
    COMPANY = "company"
    PLACE = "place"


class FetchStatus(StrEnum):
    """Outcome of a single HTTP/browser fetch.

    The distinction between NOT_FOUND and BLOCKED is the whole point: the old
    scraper treated 403/429 as "profile exists", which manufactured fake results.
    Absence of proof is not proof of absence, so BLOCKED is never EXISTS and never
    NOT_FOUND.
    """

    OK = "ok"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    ERROR = "error"


class FetchTier(StrEnum):
    """Which transport served a fetch."""

    HTTP = "http"
    """AsyncFetcher — curl_cffi with browser TLS impersonation. Fast, cheap."""

    STEALTH = "stealth"
    """AsyncStealthySession — patchright Chromium. Slow, memory-hungry, solves Cloudflare."""


class PlatformStatus(StrEnum):
    """Per-platform outcome reported to the user. Never silently empty."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"
    ERROR = "error"
    UNSUPPORTED = "unsupported"
    """Platform has no public surface at all (Discord, Tinder, Bumble)."""


class ExistenceVerdict(StrEnum):
    """Result of checking whether `platform:username` exists."""

    EXISTS = "exists"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"
    AMBIGUOUS = "ambiguous"
    """HTTP 200 but no structural marker. Surfaced as a "possible match", never dropped."""

    ERROR = "error"
    UNSUPPORTED = "unsupported"


class SourceKind(StrEnum):
    """Where a piece of evidence came from. Feeds the confidence weighting."""

    SERP = "serp"
    PROFILE_PAGE = "profile_page"
    API = "api"
    WEBSITE = "website"
    ARCHIVE = "archive"
    REVERSE_IMAGE = "reverse_image"
    USER_ANSWER = "user_answer"
    DERIVED = "derived"


class EvidenceKind(StrEnum):
    """What an evidence item asserts."""

    PROFILE = "profile"
    AVATAR = "avatar"
    USERNAME = "username"
    REAL_NAME = "real_name"
    EMAIL = "email"
    PHONE = "phone"
    LOCATION = "location"
    EMPLOYER = "employer"
    ROLE = "role"
    SCHOOL = "school"
    DOMAIN = "domain"
    BIO = "bio"
    LINK = "link"
    """Outbound link on a profile — the strongest keyless corroborator there is."""

    MENTION = "mention"
    BREACH = "breach"
    ANSWER = "answer"
    NEGATIVE = "negative"
    """A verified absence. "Not found" is itself evidence."""


class MatchBand(StrEnum):
    """Confidence bucket. Every band is returned, including REJECTED — labelled, never dropped."""

    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"
    WEAK = "weak"
    REJECTED = "rejected"


def band_for(score: int) -> MatchBand:
    """Map a 0-100 score onto its band. Single source of truth for the thresholds."""
    if score >= 80:
        return MatchBand.CONFIRMED
    if score >= 60:
        return MatchBand.LIKELY
    if score >= 40:
        return MatchBand.POSSIBLE
    if score >= 20:
        return MatchBand.WEAK
    return MatchBand.REJECTED


class PlatformTier(StrEnum):
    """How eagerly a platform is checked.

    CORE is swept on every search. EXTENDED is a long tail of ~100 niche sites that
    only runs at higher depth or once a real handle is in hand — checking hundreds
    of sites against a name permutation is a false-positive factory.
    """

    CORE = "core"
    EXTENDED = "extended"

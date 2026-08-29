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


class Gender(StrEnum):
    """A gender the **user stated** as a search constraint, never one we inferred.

    It lives here rather than in ``brief/`` so the scorer and the clusterer can
    read it without importing the brief package, which imports them back.

    ``UNKNOWN`` is the default and the only honest value for "not stated". It is
    never derived from a given name: Turkish carries a long list of unisex ones
    (Deniz, Evren, Yağmur, Özgür, Umut, Şevval), and guessing would manufacture a
    contradiction against the very person being searched for.
    """

    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"

    @property
    def is_stated(self) -> bool:
        return self is not Gender.UNKNOWN

    def contradicts(self, other: Gender) -> bool:
        """True only when both sides are stated and they disagree.

        Silence is never disagreement — most profiles say nothing about gender,
        and reading that as a conflict would reject almost everyone.
        """
        return self.is_stated and other.is_stated and self is not other


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

    BROWSE = "browse"
    """The interactive tier: a driven page that scrolled, dismissed and clicked
    before the HTML was taken. Named separately from STEALTH because it is not
    the same claim — the same URL reached by a different route, after actions
    that a plain GET never performed."""


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

    BROWSE = "browse"
    """Read from a page a driven browser manoeuvred to. The *parse* is the same
    deterministic one PROFILE_PAGE uses — it is literally the same extractor —
    but the navigation is one step less certain, so the label has to survive
    into the journal for anything downstream to weigh it honestly."""


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
    GENDER = "gender"
    """Read off a bio marker or estimated from an avatar. Always says which."""

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

"""The search brief: everything the user already knows about the target.

A search used to be one opaque string, so a user who *knew* the target's
Instagram, or that she is a woman, had no way to say so and the pipeline
re-derived everything from the name alone. The brief is that missing input.

Two rules shape every type here:

* **A known profile is parsed, never trusted as a string.** ``KnownProfile`` can
  only be built from :func:`app.discovery.platforms.urlmatch.match_profile_url`,
  which compares hosts for equality and matches anchored path patterns. Accepting
  a raw URL here would re-open the bug where ``roblox.com/users/1`` was read as an
  X profile.
* **A brief narrows, it never invents.** Anything the parser could not place goes
  into :attr:`SearchBrief.unparsed` and is shown back to the user, rather than
  being guessed into a field that would silently steer the search.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from app.discovery.platforms.urlmatch import UrlMatch
from app.discovery.types import EntityType, Gender

__all__ = [
    "EMPTY_BRIEF",
    "Gender",
    "KnownProfile",
    "ReferenceAvatar",
    "ReferenceSource",
    "SearchBrief",
]


class ReferenceSource(StrEnum):
    """Where the reference picture came from."""

    UPLOAD = "upload"
    KNOWN_PROFILE = "known_profile"


@dataclass(frozen=True, slots=True)
class KnownProfile:
    """An account the user says belongs to the target.

    Build it with :func:`from_url` so the platform and username can only ever come
    out of the URL matcher.
    """

    platform: str
    username: str
    canonical_url: str
    variant: str | None = None
    raw_url: str = ""

    @property
    def key(self) -> str:
        """Same candidate key the rest of the pipeline uses: ``platform:username``."""
        return f"{self.platform}:{self.username.lower()}"

    @classmethod
    def from_match(cls, match: UrlMatch) -> KnownProfile:
        return cls(
            platform=match.platform,
            username=match.username,
            canonical_url=match.canonical_url,
            variant=match.variant,
            raw_url=match.source_url or match.canonical_url,
        )


@dataclass(frozen=True, slots=True)
class ReferenceAvatar:
    """A picture the user says is the target, reduced to two file fingerprints.

    **This is file comparison, not face recognition.** ``sha256`` answers "is this
    the identical file?" and ``dhash`` answers "is this the same picture after a
    resize or a re-encode?". Neither one recognises a person across two different
    photographs, and the UI has to say so.
    """

    sha256: str
    dhash: str = ""
    local_url: str = ""
    source: ReferenceSource = ReferenceSource.UPLOAD


@dataclass(frozen=True, slots=True)
class SearchBrief:
    """The structured half of a search request. Every field is optional but the name."""

    name: str
    entity: EntityType = EntityType.PERSON
    gender: Gender = Gender.UNKNOWN
    known_profiles: tuple[KnownProfile, ...] = ()
    usernames: tuple[str, ...] = ()
    location: str | None = None
    employer: str | None = None
    school: str | None = None
    email: str | None = None
    domain: str | None = None
    reference_avatar: ReferenceAvatar | None = None
    unparsed: tuple[str, ...] = field(default_factory=tuple)
    """Segments the parser could not place. Surfaced to the user, never guessed at."""

    @property
    def is_empty(self) -> bool:
        """True when the brief carries nothing beyond the name itself."""
        return not any(
            (
                self.gender.is_stated,
                self.known_profiles,
                self.usernames,
                self.location,
                self.employer,
                self.school,
                self.email,
                self.domain,
                self.reference_avatar,
            )
        )

    @property
    def pinned_platforms(self) -> dict[str, str]:
        """``platform -> username`` for every platform the user already knows.

        These platforms are never searched: the account is given, so enumerating
        username permutations against them can only produce strangers.
        """
        return {profile.platform: profile.username for profile in self.known_profiles}

    def seed_usernames(self) -> tuple[str, ...]:
        """Handles worth trying on *other* platforms, best first, de-duplicated.

        A known profile's handle is the single most valuable seed a search can
        start with — it is what turns "find Eylul Akduman" into "find the accounts
        belonging to @eylulakduman".
        """
        seen: set[str] = set()
        out: list[str] = []
        for value in (*(p.username for p in self.known_profiles), *self.usernames):
            cleaned = (value or "").strip()
            lowered = cleaned.lower()
            if not cleaned or lowered in seen:
                continue
            seen.add(lowered)
            out.append(cleaned)
        return tuple(out)

    def with_reference_avatar(self, avatar: ReferenceAvatar) -> SearchBrief:
        """Return a copy carrying ``avatar``. An uploaded picture is never replaced.

        The user's own upload outranks anything scraped from a known profile: they
        chose it deliberately, and the profile picture may well be a logo.
        """
        current = self.reference_avatar
        if current is not None and current.source is ReferenceSource.UPLOAD:
            return self
        return replace(self, reference_avatar=avatar)

    def summary(self) -> str:
        """One-line description for logs and the live-status feed."""
        parts: list[str] = [f"name '{self.name}'"]
        if self.gender.is_stated:
            parts.append(f"gender {self.gender.value}")
        for profile in self.known_profiles:
            parts.append(f"known {profile.platform}:@{profile.username}")
        if self.location:
            parts.append(f"location '{self.location}'")
        if self.employer:
            parts.append(f"employer '{self.employer}'")
        if self.school:
            parts.append(f"school '{self.school}'")
        if self.reference_avatar:
            parts.append(f"reference photo ({self.reference_avatar.source.value})")
        return "; ".join(parts)


EMPTY_BRIEF = SearchBrief(name="")
"""Placeholder for a search started without any structured input."""

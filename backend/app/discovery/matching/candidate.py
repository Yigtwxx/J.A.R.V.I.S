"""A candidate account and its running assessment.

One `ProfileCandidate` per `platform:username` seen during a search, whatever its
verdict. Candidates that turned out not to exist, or that were refused, are kept
too — the API reports every platform's outcome, so "not found" and "blocked" must
survive all the way to the response instead of quietly vanishing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.discovery.platforms.extract import ProfileData
from app.discovery.types import ExistenceVerdict, MatchBand, PlatformStatus, PlatformTier


@dataclass(frozen=True, slots=True)
class ScoreReason:
    """One named, human-readable contribution to a confidence score."""

    code: str
    text: str
    points: float
    evidence_fingerprints: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "text": self.text, "points": round(self.points, 1)}


@dataclass(frozen=True, slots=True)
class MatchScore:
    """A 0-100 confidence with the full reasoning that produced it."""

    value: int
    band: MatchBand
    reasons: tuple[ScoreReason, ...] = ()

    @property
    def positive_reasons(self) -> tuple[ScoreReason, ...]:
        return tuple(r for r in self.reasons if r.points > 0)

    @property
    def negative_reasons(self) -> tuple[ScoreReason, ...]:
        return tuple(r for r in self.reasons if r.points < 0)

    def explain(self) -> str:
        """One-line summary, e.g. ``72 (likely): reciprocal link +30, name match +16``."""
        top = ", ".join(f"{r.code} {r.points:+.0f}" for r in self.reasons[:3])
        return f"{self.value} ({self.band}){': ' + top if top else ''}"


EMPTY_SCORE = MatchScore(value=0, band=MatchBand.REJECTED, reasons=())


@dataclass(slots=True)
class ProfileCandidate:
    """A possible account for the target, with everything learned about it."""

    platform: str
    username: str
    url: str
    verdict: ExistenceVerdict = ExistenceVerdict.AMBIGUOUS
    tier: PlatformTier = PlatformTier.CORE
    variant: str | None = None

    data: ProfileData | None = None
    score: MatchScore = EMPTY_SCORE
    cluster_id: str | None = None

    status_detail: str = ""
    signals: tuple[str, ...] = ()
    discovered_round: int = 0
    discovered_via: str = ""
    """``serp``, ``username_permutation``, ``outbound_link``, ``reverse_image``, ``user_answer``."""

    avatar_sha256: str | None = None
    avatar_dhash: str | None = None
    avatar_local_url: str | None = None
    archived_only: bool = False
    """Profile is gone but the archive still has it. Never counted as existing."""

    user_confirmed: bool = False
    user_rejected: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.username.lower()}"

    @property
    def platform_status(self) -> PlatformStatus:
        """Map the existence verdict onto the status reported to the user.

        AMBIGUOUS deliberately maps to FOUND: we did reach a live page, we just
        could not structurally confirm the handle. It is surfaced with a low
        confidence band and an `unverified_existence` penalty rather than hidden.
        """
        if self.user_rejected:
            return PlatformStatus.NOT_FOUND
        return {
            ExistenceVerdict.EXISTS: PlatformStatus.FOUND,
            ExistenceVerdict.AMBIGUOUS: PlatformStatus.FOUND,
            ExistenceVerdict.NOT_FOUND: PlatformStatus.NOT_FOUND,
            ExistenceVerdict.BLOCKED: PlatformStatus.BLOCKED,
            ExistenceVerdict.ERROR: PlatformStatus.ERROR,
            ExistenceVerdict.UNSUPPORTED: PlatformStatus.UNSUPPORTED,
        }[self.verdict]

    @property
    def is_live(self) -> bool:
        """We reached a real page for this handle."""
        return self.verdict in (ExistenceVerdict.EXISTS, ExistenceVerdict.AMBIGUOUS) and not self.user_rejected

    @property
    def display_name(self) -> str | None:
        return self.data.display_name if self.data else None

    @property
    def bio(self) -> str | None:
        return self.data.bio if self.data else None

    @property
    def outbound_links(self) -> list[str]:
        return list(self.data.outbound_links) if self.data else []

    @property
    def employer(self) -> str | None:
        return self.data.employer if self.data else None

    @property
    def location(self) -> str | None:
        return self.data.location if self.data else None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)

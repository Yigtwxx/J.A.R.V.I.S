"""Chronology of the elected identity, oldest first.

One rule decides what belongs here: **every event must name the URL it came
from**. An undated, unsourced timeline is decoration — it looks like intelligence
and cannot be checked, which is the worst combination a report can offer. Events
that cannot supply a source are dropped rather than shown with a blank citation.

Partial dates are kept as partial dates. A profile that says "2022" and nothing
more sorts as ``2022-01-01`` so it lands in the right place, but ``when`` still
reads ``2022`` — inventing January 1st to make the row look complete is a lie
about precision.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.discovery.evidence.model import Evidence
from app.discovery.identity.workedu import EducationRecord, WorkRecord
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.types import EvidenceKind

_YEAR_ONLY = re.compile(r"^\d{4}$")
_YEAR_MONTH = re.compile(r"^\d{4}-\d{2}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")

_KIND_FOR_EVIDENCE: dict[EvidenceKind, str] = {
    EvidenceKind.BREACH: "breach",
    EvidenceKind.MENTION: "activity",
}


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """One dated fact, with the source that asserts it."""

    when: str
    """ISO date, ``YYYY-MM``, or ``YYYY`` when only the year is known."""

    kind: str
    """``account_created`` | ``employment`` | ``education`` | ``activity`` | ``breach`` | ``archive_snapshot``."""

    label: str
    source_url: str
    confidence: int = 50
    platform: str | None = None

    @property
    def sort_key(self) -> str:
        """Full ISO date used only for ordering. ``when`` keeps the real precision."""
        return _expand(self.when)

    def as_dict(self) -> dict[str, Any]:
        return {
            "when": self.when,
            "kind": self.kind,
            "label": self.label,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "platform": self.platform,
        }


def _expand(when: str) -> str:
    """Pad a partial date to a sortable full ISO date. Display never uses this."""
    if _YEAR_ONLY.match(when):
        return f"{when}-01-01"
    if _YEAR_MONTH.match(when):
        return f"{when}-01"
    return when


def _normalize_when(value: Any) -> str | None:
    """Coerce a date-ish value into ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``.

    Returns None for anything unrecognisable — an event whose date we cannot read
    is not placeable on a chronology, so it does not belong on one.
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return None
    if _YEAR_ONLY.match(text) or _YEAR_MONTH.match(text):
        return text
    match = _ISO_DATE.match(text)
    return match.group(0) if match else None


def _event(
    when: Any,
    kind: str,
    label: str,
    source_url: str,
    *,
    confidence: float = 0.5,
    platform: str | None = None,
) -> TimelineEvent | None:
    """Build an event, or None when it lacks a readable date or a source URL."""
    normalized = _normalize_when(when)
    if normalized is None or not (source_url or "").strip():
        return None
    return TimelineEvent(
        when=normalized,
        kind=kind,
        label=label,
        source_url=source_url.strip(),
        confidence=round(100 * confidence) if confidence <= 1 else int(confidence),
        platform=platform,
    )


def build_timeline(
    profiles: Sequence[ProfileCandidate],
    work: Sequence[WorkRecord],
    education: Sequence[EducationRecord],
    evidence: Sequence[Evidence],
    *,
    archive_snapshots: Sequence[Any] = (),
) -> list[TimelineEvent]:
    """Assemble the chronology, oldest first. Unsourced or undated events are dropped."""
    events: list[TimelineEvent | None] = []

    for profile in profiles:
        weight = max(0.1, profile.score.value / 100)
        # Only some platforms publish a creation date (GitHub's API does, in
        # `raw["created_at"]`). No date means no event — the account still appears
        # in the accounts list, it simply cannot be placed on a chronology.
        raw = profile.data.raw if profile.data else {}
        events.append(
            _event(
                (raw or {}).get("created_at"),
                "account_created",
                f"{profile.platform} account @{profile.username} created",
                profile.url,
                confidence=weight,
                platform=profile.platform,
            )
        )
        events.append(
            _event(
                profile.data.last_activity if profile.data else None,
                "activity",
                f"Last observed activity on {profile.platform} @{profile.username}",
                profile.url,
                confidence=weight,
                platform=profile.platform,
            )
        )

    for record in work:
        role = f" as {record.role}" if record.role else ""
        events.append(
            _event(
                record.start or record.end,
                "employment",
                f"{'Joined' if record.start else 'Left'} {record.organization}{role}",
                record.source_url,
                confidence=record.confidence,
            )
        )

    for record in education:
        events.append(
            _event(
                record.start or record.end,
                "education",
                f"{'Started at' if record.start else 'Graduated from'} {record.institution}",
                record.source_url,
                confidence=record.confidence,
            )
        )

    for item in evidence:
        kind = _KIND_FOR_EVIDENCE.get(item.kind)
        if kind is None:
            continue
        events.append(
            _event(
                item.observed_at,
                kind,
                f"{item.subject}: {item.value}",
                item.source_url,
                confidence=item.confidence,
                platform=item.platform,
            )
        )

    for snapshot in archive_snapshots:
        events.append(
            _event(
                getattr(snapshot, "timestamp", None) or getattr(snapshot, "when", None),
                "archive_snapshot",
                f"Archived copy of {getattr(snapshot, 'url', '') or 'page'}",
                getattr(snapshot, "snapshot_url", "") or getattr(snapshot, "url", ""),
                confidence=0.9,
            )
        )

    kept = [event for event in events if event is not None]
    kept.sort(key=lambda e: (e.sort_key, e.kind, e.label))
    return kept

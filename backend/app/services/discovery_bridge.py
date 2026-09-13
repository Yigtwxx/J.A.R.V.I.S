"""Adapter between the new discovery pipeline and the existing API contract.

This is the load-bearing compatibility shim. It lets the rewrite ship without
breaking the frontend: the new structured fields are added, and the fifteen legacy
``*_url`` strings keep being populated from the elected identity so every existing
component carries on working while the UI catches up.

One rule it enforces that the old code did not: a legacy URL field is only filled
from a profile whose status is ``found``. The old pipeline injected
``[SEARCH]`` placeholder entries for every empty platform, which inflated the
counts, leaked search-page URLs into the LLM context, and left the typed fields
empty anyway.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.discovery.evidence.model import Evidence
from app.discovery.loop.runner import DiscoveryResult
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.types import EvidenceKind, PlatformStatus
from app.schemas.discovery import (
    ContactOut,
    DiscoverySummary,
    EducationRecord,
    EvidenceItem,
    MatchReason,
    NarrativeClaim,
    ProfilePicture,
    SocialProfile,
    WorkRecord,
)

# Discovery platform key -> legacy SearchResponse field name.
_LEGACY_FIELDS: dict[str, str] = {
    "github": "github_url",
    "instagram": "instagram_url",
    "x": "twitter_url",
    "linkedin": "linkedin_url",
    "spotify": "spotify_url",
    "tiktok": "tiktok_url",
    "snapchat": "snapchat_url",
    "tumblr": "tumblr_url",
    "youtube": "youtube_url",
    "reddit": "reddit_url",
    "facebook": "facebook_url",
    "pinterest": "pinterest_url",
    "threads": "threads_url",
    "steam": "steam_url",
}


def to_social_profiles(candidates: Sequence[ProfileCandidate]) -> list[SocialProfile]:
    """Render candidates as API profiles, keeping every status — including failures."""
    out: list[SocialProfile] = []
    for candidate in candidates:
        status = candidate.platform_status
        data = candidate.data
        out.append(
            SocialProfile(
                platform=candidate.platform,
                url=candidate.url if status is PlatformStatus.FOUND else None,
                username=candidate.username,
                display_name=data.display_name if data else None,
                avatar_url=candidate.avatar_local_url or (data.avatar_url if data else None),
                bio=data.bio if data else None,
                followers=data.followers if data else None,
                following=data.following if data else None,
                posts=data.posts if data else None,
                verified=data.verified if data else None,
                last_activity=data.last_activity.isoformat() if data and data.last_activity else None,
                status=str(status),  # type: ignore[arg-type]
                status_detail=candidate.status_detail or (candidate.signals[0] if candidate.signals else None),
                confidence=candidate.score.value,
                band=str(candidate.score.band),  # type: ignore[arg-type]
                reasons=[MatchReason(code=r.code, text=r.text, points=r.points) for r in candidate.score.reasons[:6]],
                outbound_links=candidate.outbound_links[:10],
                checked_at=candidate.updated_at.isoformat(),
            )
        )
    out.sort(key=lambda p: (-p.confidence, p.platform, p.username or ""))
    return out


def to_pictures(candidates: Sequence[ProfileCandidate]) -> list[ProfilePicture]:
    """Every downloaded avatar, most-trusted first, deduplicated by file hash."""
    seen: set[str] = set()
    pictures: list[ProfilePicture] = []
    for candidate in sorted(candidates, key=lambda c: -c.score.value):
        if not candidate.avatar_local_url or not candidate.is_live:
            continue
        digest = candidate.avatar_sha256 or candidate.avatar_local_url
        if digest in seen:
            continue
        seen.add(digest)
        pictures.append(
            ProfilePicture(
                url=candidate.avatar_local_url,
                platform=candidate.platform,
                source_url=candidate.data.avatar_url if candidate.data else None,
                sha256=candidate.avatar_sha256,
                dhash=candidate.avatar_dhash,
                is_primary=not pictures,
            )
        )
    return pictures


def legacy_social_urls(profiles: Sequence[SocialProfile]) -> dict[str, str | None]:
    """Fill the fifteen legacy ``*_url`` fields from confirmed accounts only.

    Multiple accounts on one platform are comma-joined, matching the old contract
    the frontend already splits on. Nothing that is not ``found`` is ever emitted —
    no placeholders, no search-page URLs.
    """
    grouped: dict[str, list[str]] = {}
    for profile in profiles:
        field = _LEGACY_FIELDS.get(profile.platform)
        if not field or profile.status != "found" or not profile.url:
            continue
        grouped.setdefault(field, []).append(profile.url)
    return {field: ", ".join(urls) for field, urls in grouped.items()}


def to_evidence_items(result: DiscoveryResult, *, limit: int = 400) -> list[EvidenceItem]:
    ordered = sorted(result.evidence, key=lambda e: (-e.confidence, str(e.kind), e.subject))[:limit]
    return [
        EvidenceItem(
            kind=str(ev.kind),
            subject=ev.subject,
            value=ev.value[:500],
            platform=ev.platform,
            source_url=ev.source_url,
            source_domain=ev.source_domain,
            source_kind=str(ev.source_kind),
            extractor=ev.extractor,
            confidence=round(float(ev.confidence), 3),
            observed_at=ev.observed_at.isoformat(),
            round=ev.round_no,
            fingerprint=ev.fingerprint,
        )
        for ev in ordered
    ]


def to_work(records: Sequence[Any]) -> list[WorkRecord]:
    return [
        WorkRecord(
            organization=r.organization,
            organization_normalized=r.organization_normalized,
            role=r.role,
            start=r.start,
            end=r.end,
            is_current=r.is_current,
            source_url=r.source_url,
            extractor=r.extractor,
            confidence=int(round(float(r.confidence) * 100)),
        )
        for r in records
    ]


def to_education(records: Sequence[Any]) -> list[EducationRecord]:
    return [
        EducationRecord(
            institution=r.institution,
            institution_normalized=r.institution_normalized,
            degree=r.degree,
            field_of_study=r.field_of_study,
            start=r.start,
            end=r.end,
            source_url=r.source_url,
            extractor=r.extractor,
            confidence=int(round(float(r.confidence) * 100)),
        )
        for r in records
    ]


def to_summary(result: DiscoveryResult) -> DiscoverySummary:
    return DiscoverySummary(
        session_id=result.session_id,
        entity_type=str(result.entity_type),  # type: ignore[arg-type]
        rounds=result.rounds,
        termination_reason=result.termination_reason,
        evidence_total=len(result.evidence),
        evidence_reused=result.resumed_evidence,
        questions=[],
        platform_status={k: str(v) for k, v in result.platform_status.items()},  # type: ignore[misc]
        engine_status=dict(result.engine_status),
        fetch_stats=result.fetch_stats,
        notices=list(result.notices),
        duration_ms=result.duration_ms,
    )


def to_narrative_claims(result: DiscoveryResult) -> list[NarrativeClaim]:
    """The biography, one grounded sentence at a time.

    Lives here rather than in the runner so both entry points serve the same
    biography. While it was runner-only, `POST /api/search/` presented the old
    ungrounded essay as the biography and sent an empty claim list with it.
    """
    narrative = result.narrative
    return [
        NarrativeClaim(
            text=claim.text,
            evidence_fingerprints=list(claim.evidence_fingerprints),
            source_urls=list(claim.source_urls),
            confidence=claim.confidence,
        )
        for claim in (narrative.claims if narrative else ())
    ]


def to_contacts(result: DiscoveryResult) -> list[ContactOut]:
    """Every e-mail and phone in the evidence, best first, deduped by value.

    `corroborations` counts distinct source domains rather than rows: two sites
    publishing the same address is the signal, two pages of one site is not.
    """
    by_value: dict[tuple[str, str], list[Evidence]] = {}
    for item in result.evidence:
        if item.kind not in (EvidenceKind.EMAIL, EvidenceKind.PHONE):
            continue
        by_value.setdefault((str(item.kind), item.value), []).append(item)

    out: list[ContactOut] = []
    for (kind, value), items in by_value.items():
        best = max(items, key=lambda ev: ev.confidence)
        out.append(
            ContactOut(
                kind=kind,  # type: ignore[arg-type]
                value=value,
                display=str((best.raw or {}).get("display") or "") or None,
                source_url=best.source_url,
                source_domain=best.source_domain,
                extractor=best.extractor,
                confidence=best.confidence,
                corroborations=len({ev.source_domain for ev in items if ev.source_domain}) or 1,
                observed_at=best.observed_at.isoformat(),
                fingerprint=best.fingerprint,
            )
        )
    out.sort(key=lambda c: (-c.corroborations, -c.confidence, c.value))
    return out


def to_api(result: DiscoveryResult) -> dict[str, Any]:
    """Everything the new API surface needs, as plain keyword arguments."""
    profiles = to_social_profiles(result.profiles)
    pictures = to_pictures(result.profiles)
    payload: dict[str, Any] = {
        "entity_type": str(result.entity_type),
        "social_profiles": profiles,
        "profile_pictures": pictures,
        "primary_profile_picture": pictures[0].url if pictures else None,
        "work_history": to_work(result.work),
        "education": to_education(result.education),
        "evidence": to_evidence_items(result),
        "subject_confidence": result.subject_confidence.value if result.subject_confidence else 0,
        "subject_confidence_reasons": [
            MatchReason(code=r.code, text=r.text, points=r.points)
            for r in (result.subject_confidence.reasons if result.subject_confidence else ())
        ],
        "discovery": to_summary(result),
        "narrative_claims": to_narrative_claims(result),
    }
    contacts = to_contacts(result)
    payload["contacts"] = contacts
    # Emitted only when non-empty, for the same reason `ai_response` is: the
    # blocking route copies every key returned here onto its response object, so
    # an empty list would erase what the legacy analyser found rather than saying
    # nothing about it.
    emails = [c.value for c in contacts if c.kind == "email"]
    phones = [c.value for c in contacts if c.kind == "phone"]
    if emails:
        payload["email_addresses"] = emails
    if phones:
        payload["phone_numbers"] = phones
    # Absent, not null: the blocking route copies every key returned here onto its
    # response object, so emitting None would erase the prose the legacy analyser
    # already wrote. No narrative means "no opinion on this field".
    if result.narrative is not None:
        payload["ai_response"] = result.narrative.text
    payload.update(legacy_social_urls(profiles))
    return payload

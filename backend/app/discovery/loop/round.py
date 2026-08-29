"""One round of iterative deepening.

Six phases, each publishing progress so the user can watch a long search work:

    SEED -> EXPAND -> VERIFY -> ENRICH -> SCORE -> REFLECT

The phase that matters most is VERIFY: it records an outcome for *every* handle it
checks, including `not_found`, `blocked` and `error`. That is what makes "nothing
is ever silently empty" structural — the response cannot omit a platform, because
the platform's status is written down whether or not anything was found.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.discovery.engines.base import SearchHit
from app.discovery.engines.registry import EngineRegistry
from app.discovery.evidence.model import Evidence, make_evidence
from app.discovery.evidence.store import EvidenceStore
from app.discovery.fetch.session import FetchSession
from app.discovery.identity import workedu
from app.discovery.loop import seeds
from app.discovery.loop.state import DiscoveryState
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.matching.scoring import require_independent_sources, score_profile
from app.discovery.media.store import AvatarStore
from app.discovery.platforms.existence import ExistenceChecker, ExistenceResult
from app.discovery.platforms.extract import ProfileData, ProfileExtractor
from app.discovery.platforms.registry import PlatformRegistry
from app.discovery.platforms.urlmatch import match_profile_url
from app.discovery.session.bus import SessionEventBus
from app.discovery.session.events import (
    EventType,
    candidate_payload,
    evidence_payload,
    platform_status_payload,
    progress_payload,
)
from app.discovery.sources.archive import ARCHIVE_CONFIDENCE_MULTIPLIER, ArchivedSnapshot, ArchiveRecovery
from app.discovery.types import EvidenceKind, ExistenceVerdict, PlatformTier, SourceKind
from app.utils.logger import logger


@dataclass(slots=True)
class RoundOutcome:
    """What one round achieved. Drives the loop's stop decision."""

    round_no: int
    new_evidence: list[Evidence]
    new_candidates: int
    band_changed: bool
    platform_recovered: bool
    blocked_platforms: list[str]
    duration_ms: int

    @property
    def productive(self) -> bool:
        """A round counts as productive if it moved the picture at all.

        Three ways to move it: new evidence, a candidate changing confidence band,
        or a platform recovering from blocked/error into a real answer.
        """
        return bool(self.new_evidence) or self.band_changed or self.platform_recovered


class DiscoveryRound:
    """Runs one round against the shared services."""

    def __init__(
        self,
        *,
        fetch: FetchSession,
        engines: EngineRegistry,
        registry: PlatformRegistry,
        store: EvidenceStore,
        bus: SessionEventBus,
        avatars: AvatarStore,
        extended_min_depth: int = 6,
        engine_count: int = 3,
        validation_passes: int = 1,
        archive: ArchiveRecovery | None = None,
        max_archive_lookups: int = 4,
    ) -> None:
        self._fetch = fetch
        self._engines = engines
        self._registry = registry
        self._store = store
        self._bus = bus
        self._avatars = avatars
        self._archive = archive
        self._max_archive_lookups = max(0, max_archive_lookups)
        """Each recovery costs two or three fetches, so a refused round cannot
        spend the whole budget on the Wayback Machine."""

        self._extended_min_depth = extended_min_depth
        self._engine_count = max(1, engine_count)
        """How many search engines a query is put to — `DepthConfig.search_engines_to_use`."""

        self._validation_passes = max(1, validation_passes)
        """Independent source domains needed before a candidate may be `confirmed`."""
        self._checker = ExistenceChecker(fetch, registry)
        self._extractor = ProfileExtractor(fetch, registry)

    async def run(self, state: DiscoveryState, fresh_from_last_round: Sequence[Evidence]) -> RoundOutcome:
        started = time.monotonic()
        state.reset_round_counters()

        queries = await self._seed(state, fresh_from_last_round)
        await self._expand(state, queries)
        results = await self._verify(state)
        await self._enrich(state, results)
        await self._recover(state, results)
        self._score(state)

        band_changed = state.band_changed()
        platform_recovered = any(state.note_platform(r.platform, self._status_for(r)) for r in results)
        blocked = sorted({r.platform for r in results if r.verdict is ExistenceVerdict.BLOCKED})

        return RoundOutcome(
            round_no=state.round_no,
            new_evidence=list(state.evidence[-state.new_evidence_this_round :])
            if state.new_evidence_this_round
            else [],
            new_candidates=state.new_candidates_this_round,
            band_changed=band_changed,
            platform_recovered=platform_recovered,
            blocked_platforms=blocked,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    # -- 1. SEED -------------------------------------------------------------

    async def _seed(self, state: DiscoveryState, fresh: Sequence[Evidence]) -> list[str]:
        await self._progress(state, "seed", "planning queries")
        if state.round_no == 0:
            for candidate in seeds.seed_usernames(state):
                state.usernames[candidate.value] = candidate
            return seeds.round_zero_queries(state, self._registry)

        confirmed = [c.username for c in state.candidates.values() if c.is_live]
        for candidate in seeds.expand_usernames(state, confirmed[:10]):
            state.usernames.setdefault(candidate.value, candidate)
        return seeds.followup_queries(state, fresh)

    # -- 2. EXPAND -----------------------------------------------------------

    async def _expand(self, state: DiscoveryState, queries: list[str]) -> list[SearchHit]:
        if not queries:
            return []
        await self._progress(state, "expand", f"querying {len(queries)} dork(s)", total=len(queries))
        hits = await self._engines.search_many(
            self._fetch, queries, engine_count=self._engine_count, concurrency=3, limit=20
        )

        evidence: list[Evidence] = []
        for hit in hits:
            if hit.url in state.urls_seen:
                continue
            state.urls_seen.add(hit.url)
            matched = match_profile_url(hit.url)
            if matched is None:
                state.web_sources.append(hit)
                evidence.extend(self._work_from_hit(state, hit))
                continue

            spec = self._registry.get(matched.platform)
            candidate = ProfileCandidate(
                platform=matched.platform,
                username=matched.username,
                url=matched.canonical_url,
                variant=matched.variant,
                tier=spec.tier if spec else PlatformTier.CORE,
                discovered_round=state.round_no,
                discovered_via="serp",
            )
            state.upsert_candidate(candidate)
            state.context.serp_engines.setdefault(candidate.key, set()).add(hit.engine)
            state.usernames_tried.discard((matched.platform, matched.username))
            evidence.append(
                make_evidence(
                    EvidenceKind.PROFILE,
                    candidate.key,
                    matched.canonical_url,
                    source_url=hit.url,
                    source_kind=SourceKind.SERP,
                    extractor=f"serp:{hit.engine}",
                    confidence=0.55,
                    platform=matched.platform,
                    round_no=state.round_no,
                )
            )

        await self._store_evidence(state, evidence)
        return hits

    def _work_from_hit(self, state: DiscoveryState, hit: SearchHit) -> list[Evidence]:
        """LinkedIn SERP titles are the highest-value work source and cost zero fetches."""
        if "linkedin.com" not in hit.url:
            return []
        work, education = workedu.from_linkedin_serp_title(
            hit.title, hit.snippet, hit.url, name_tokens=state.terms.tokens
        )
        state.work.extend(work)
        state.education.extend(education)
        out: list[Evidence] = []
        for record in work:
            out.append(
                make_evidence(
                    EvidenceKind.EMPLOYER,
                    "employer",
                    record.organization,
                    source_url=hit.url,
                    source_kind=SourceKind.SERP,
                    extractor=record.extractor or "linkedin_serp_title",
                    confidence=record.confidence,
                    round_no=state.round_no,
                )
            )
        for record in education:
            out.append(
                make_evidence(
                    EvidenceKind.SCHOOL,
                    "school",
                    record.institution,
                    source_url=hit.url,
                    source_kind=SourceKind.SERP,
                    extractor=record.extractor or "linkedin_serp_title",
                    confidence=record.confidence,
                    round_no=state.round_no,
                )
            )
        return out

    # -- 3. VERIFY -----------------------------------------------------------

    async def _verify(self, state: DiscoveryState) -> list[ExistenceResult]:
        include_extended = seeds.extended_unlocked(state, min_depth=self._extended_min_depth)
        pairs = seeds.platform_probe_pairs(state, self._registry, include_extended=include_extended)
        # Anything already discovered from a SERP still needs verifying.
        for candidate in state.candidates.values():
            pair = (candidate.platform, candidate.username)
            if candidate.verdict is ExistenceVerdict.AMBIGUOUS and pair not in pairs:
                pairs.append(pair)
                state.usernames_tried.add(pair)
        if not pairs:
            return []

        await self._progress(state, "verify", f"checking {len(pairs)} handle(s)", total=len(pairs))
        results = await self._checker.check_many(
            pairs, concurrency=6, stealth_allowed=self._stealth_allowed(state, pairs)
        )

        for result in results:
            spec = self._registry.get(result.platform)
            candidate = state.candidates.get(result.key) or ProfileCandidate(
                platform=result.platform,
                username=result.username,
                url=result.url,
                tier=spec.tier if spec else PlatformTier.CORE,
                discovered_round=state.round_no,
                discovered_via="username_permutation",
            )
            candidate.verdict = result.verdict
            candidate.signals = result.signals
            candidate.status_detail = result.detail
            state.upsert_candidate(candidate)
            await self._store.record_platform_outcome(state.session_id, result)
            await self._bus.publish(EventType.platform_status, platform_status_payload(result))

        return results

    @staticmethod
    def _stealth_allowed(state: DiscoveryState, pairs: Sequence[tuple[str, str]]) -> set[tuple[str, str]]:
        """Which handles have earned a browser this round.

        A browser page costs 3-8 s and 50-150 MB. A round generates dozens of blind
        name permutations; escalating all of them turns a one-minute round into a
        twenty-minute one and finds nothing extra, because a guessed handle that is
        wrong is wrong at both tiers. So stealth is spent only where something
        already points at the handle: a search hit, the user, or another platform.
        """
        supported: set[tuple[str, str]] = set()
        for platform, username in pairs:
            key = f"{platform}:{username.lower()}"
            candidate = state.candidates.get(key)
            if candidate is not None and candidate.discovered_via in ("serp", "outbound_link", "user_answer"):
                supported.add((platform, username))
                continue
            source = state.usernames.get(username)
            if source is not None and source.prior >= 0.9:
                supported.add((platform, username))
        return supported

    # -- 4. ENRICH -----------------------------------------------------------

    async def _enrich(self, state: DiscoveryState, results: Sequence[ExistenceResult]) -> None:
        usable = [r for r in results if r.usable]
        if not usable:
            return
        await self._progress(state, "enrich", f"reading {len(usable)} profile(s)", total=len(usable))

        evidence: list[Evidence] = []
        for index, result in enumerate(usable, start=1):
            candidate = state.candidates.get(result.key)
            if candidate is None:
                continue
            data = await self._extractor.extract(result)
            if data is None:
                continue
            candidate.data = data
            evidence.extend(self._evidence_from_profile(state, candidate, data))
            await self._save_avatar(state, candidate, data)
            await self._bus.publish(EventType.candidate_updated, candidate_payload(candidate))
            if index % 5 == 0:
                await self._progress(state, "enrich", "reading profiles", completed=index, total=len(usable))

        await self._store_evidence(state, evidence)

    def _evidence_from_profile(
        self, state: DiscoveryState, candidate: ProfileCandidate, data: ProfileData
    ) -> list[Evidence]:
        out: list[Evidence] = []

        def add(kind: EvidenceKind, subject: str, value: str | None, confidence: float) -> None:
            if not value:
                return
            out.append(
                make_evidence(
                    kind,
                    subject,
                    value,
                    source_url=candidate.url,
                    source_kind=SourceKind.PROFILE_PAGE,
                    extractor=data.extractor or "profile",
                    confidence=confidence,
                    platform=candidate.platform,
                    round_no=state.round_no,
                )
            )

        add(EvidenceKind.PROFILE, candidate.key, candidate.url, 0.9)
        add(EvidenceKind.REAL_NAME, "real_name", data.display_name, 0.7)
        add(EvidenceKind.BIO, candidate.key, data.bio, 0.6)
        add(EvidenceKind.LOCATION, "location", data.location, 0.7)
        add(EvidenceKind.EMPLOYER, "employer", data.employer, 0.75)
        add(EvidenceKind.AVATAR, candidate.key, data.avatar_url, 0.6)
        add(EvidenceKind.USERNAME, "username", candidate.username, 0.8)
        for link in data.outbound_links[:12]:
            add(EvidenceKind.LINK, candidate.key, link, 0.7)

        if data.bio:
            work, education = workedu.from_bio_text(data.bio, candidate.url, extractor=f"bio:{candidate.platform}")
            state.work.extend(work)
            state.education.extend(education)
            for record in work:
                add(EvidenceKind.EMPLOYER, "employer", record.organization, record.confidence)
            for record in education:
                add(EvidenceKind.SCHOOL, "school", record.institution, record.confidence)
        return out

    # -- 4b. RECOVER ---------------------------------------------------------

    async def _recover(self, state: DiscoveryState, results: Sequence[ExistenceResult]) -> None:
        """Ask the archive about handles the live web refused us.

        A refusal is not an absence, and it is also not the end of the enquiry: the
        Wayback Machine may still hold what the account looked like. That is
        supplementary evidence about the *past*, never a live verdict — the
        platform stays BLOCKED and the candidate is flagged ``archived_only`` so
        nothing downstream can read it as a confirmed account.

        Spent only on handles something already points at — a search hit, an
        outbound link, or the user — which is the same test the browser tier uses
        in ``_stealth_allowed`` and is reused here rather than restated. Merely
        *having* a candidate is not that test: ``_verify`` creates one for every
        handle it checks, blind permutations included, so gating on the candidate's
        existence would spend the archive on guesses that were never archived.
        """
        if self._archive is None or self._max_archive_lookups <= 0:
            return

        refused = [
            result
            for result in results
            # The archive does not change between rounds, so asking twice about
            # the same URL spends fetches on an answer we already have.
            if result.verdict is ExistenceVerdict.BLOCKED and result.url not in state.archived_checked
        ]
        if not refused:
            return

        earned = self._stealth_allowed(state, [(r.platform, r.username) for r in refused])
        blocked = [r for r in refused if (r.platform, r.username) in earned][: self._max_archive_lookups]
        if not blocked:
            return

        await self._progress(state, "recover", f"asking the archive about {len(blocked)} refused profile(s)")

        evidence: list[Evidence] = []
        for result in blocked:
            candidate = state.candidates.get(result.key)
            if candidate is None:
                continue
            state.archived_checked.add(result.url)
            snapshot = await self._archive.recover_profile(self._fetch, result.url, platform=result.platform)
            if snapshot is None:
                continue

            candidate.archived_only = True
            candidate.status_detail = (
                f"{candidate.status_detail} · archived {snapshot.timestamp:%Y-%m-%d}".strip(" ·")
                if candidate.status_detail
                else f"archived {snapshot.timestamp:%Y-%m-%d}"
            )
            evidence.extend(self._evidence_from_snapshot(state, candidate, snapshot))
            await self._bus.publish(EventType.candidate_updated, candidate_payload(candidate))

        await self._store_evidence(state, evidence)

    def _evidence_from_snapshot(
        self, state: DiscoveryState, candidate: ProfileCandidate, snapshot: ArchivedSnapshot
    ) -> list[Evidence]:
        """Turn one capture into dated, discounted evidence.

        Deliberately emits no ``PROFILE`` evidence: that is the kind the rest of
        the pipeline reads as "this account is real and reachable", which is the
        one thing a snapshot cannot establish.
        """
        out: list[Evidence] = []
        observed = f"{snapshot.timestamp:%Y-%m-%d}"
        raw = {"snapshot_url": snapshot.snapshot_url, "snapshot_date": observed}

        def add(kind: EvidenceKind, subject: str, value: str | None, confidence: float) -> None:
            if not value:
                return
            out.append(
                make_evidence(
                    kind,
                    subject,
                    value,
                    source_url=snapshot.snapshot_url,
                    source_kind=SourceKind.ARCHIVE,
                    extractor=f"archive:{candidate.platform}@{observed}",
                    confidence=confidence * ARCHIVE_CONFIDENCE_MULTIPLIER,
                    platform=candidate.platform,
                    round_no=state.round_no,
                    raw=raw,
                )
            )

        add(EvidenceKind.REAL_NAME, "real_name", snapshot.display_name, 0.7)
        add(EvidenceKind.BIO, candidate.key, snapshot.bio, 0.6)
        add(EvidenceKind.AVATAR, candidate.key, snapshot.avatar_url, 0.6)

        if snapshot.bio:
            work, education = workedu.from_bio_text(
                snapshot.bio, snapshot.snapshot_url, extractor=f"archive-bio:{candidate.platform}@{observed}"
            )
            state.work.extend(work)
            state.education.extend(education)
            for record in work:
                add(EvidenceKind.EMPLOYER, "employer", record.organization, record.confidence)
            for record in education:
                add(EvidenceKind.SCHOOL, "school", record.institution, record.confidence)
        return out

    async def _save_avatar(self, state: DiscoveryState, candidate: ProfileCandidate, data: ProfileData) -> None:
        """Download the picture so it survives the CDN URL expiring within hours."""
        if not data.avatar_url or candidate.avatar_sha256:
            return
        stored = await self._avatars.save(
            self._fetch, data.avatar_url, platform=candidate.platform, username=candidate.username
        )
        if stored is None:
            return
        candidate.avatar_sha256 = stored.sha256
        candidate.avatar_dhash = stored.dhash
        candidate.avatar_local_url = stored.local_url
        state.context.avatar_sha_index.setdefault(stored.sha256, set()).add(candidate.key)
        if stored.dhash:
            state.context.avatar_dhash_index.setdefault(stored.dhash, set()).add(candidate.key)

    # -- 5. SCORE ------------------------------------------------------------

    def _score(self, state: DiscoveryState) -> None:
        self._refresh_context(state)
        domains = self._source_domains_by_candidate(state)
        for candidate in state.candidates.values():
            score = score_profile(candidate, state.anchor, state.evidence, state.context)
            candidate.score = require_independent_sources(
                score,
                source_domains=len(domains.get(candidate.key, ())),
                required=self._validation_passes,
            )

    @staticmethod
    def _source_domains_by_candidate(state: DiscoveryState) -> dict[str, set[str]]:
        """Candidate key -> the distinct sites that said something about it.

        Deliberately keyed on the evidence *subject*: a fact recorded against the
        candidate itself. Platform-wide evidence is excluded, because it would
        credit one candidate with corroboration earned by a namesake on the same
        platform.
        """
        out: dict[str, set[str]] = {}
        for ev in state.evidence:
            if ev.source_domain:
                out.setdefault(ev.subject, set()).add(ev.source_domain)
        return out

    def _refresh_context(self, state: DiscoveryState) -> None:
        """Recompute the cross-candidate facts the scorer needs."""
        ctx = state.context
        ctx.handle_counts = {}
        ctx.confirmed_urls = set()
        ctx.confirmed_domains = set()
        ctx.reciprocal_pairs = set()
        self._flag_generic_images(state)

        links: dict[str, set[str]] = {}
        for candidate in state.candidates.values():
            if not candidate.is_live:
                continue
            handle = candidate.username.lower()
            ctx.handle_counts[handle] = ctx.handle_counts.get(handle, 0) + 1
            if candidate.score.value >= 60 or candidate.user_confirmed:
                ctx.confirmed_urls.add(candidate.url)
            targets: set[str] = set()
            for href in candidate.outbound_links:
                matched = match_profile_url(href)
                if matched is not None:
                    targets.add(matched.key)
            links[candidate.key] = targets

        for key, targets in links.items():
            for target in targets:
                if key in links.get(target, set()):
                    ctx.reciprocal_pairs.add((key, target) if key <= target else (target, key))

    @staticmethod
    def _flag_generic_images(state: DiscoveryState) -> None:
        """Mark images that clearly are not a personal photo.

        Default avatars, platform placeholders and stock photos are byte- or
        near-identical across totally unrelated accounts. Left unflagged they act
        as an agreement edge in clustering and merge strangers into one identity —
        observed live, where a default picture pulled ``yerdogan`` (a different
        person entirely) into the same cluster as ``yigiterdogan``.

        The rule: an image appearing under three or more distinct *usernames* is
        not evidence of anything. It is excluded from both scoring and clustering.
        """
        ctx = state.context
        generic: set[str] = set()

        def usernames_for(keys: set[str]) -> set[str]:
            return {key.split(":", 1)[1] for key in keys if ":" in key}

        for digest, keys in ctx.avatar_sha_index.items():
            if len(usernames_for(keys)) >= 3:
                generic.add(digest)
        for digest, keys in ctx.avatar_dhash_index.items():
            if len(usernames_for(keys)) >= 3:
                # dhash is a *perceptual* hash, so a shared one is even weaker
                # evidence than a shared file. Flag every sha behind it.
                for key in keys:
                    candidate = state.candidates.get(key)
                    if candidate and candidate.avatar_sha256:
                        generic.add(candidate.avatar_sha256)
                generic.add(digest)
        ctx.generic_images |= generic

    # -- shared helpers ------------------------------------------------------

    async def _store_evidence(self, state: DiscoveryState, evidence: list[Evidence]) -> None:
        if not evidence:
            return
        fresh = state.record_evidence(evidence)
        if not fresh:
            return
        await self._store.add_many(state.target_key, state.session_id, fresh)
        for ev in fresh[:60]:
            await self._bus.publish(EventType.evidence_found, evidence_payload(ev))

    async def _progress(
        self,
        state: DiscoveryState,
        phase: str,
        label: str,
        *,
        completed: int = 0,
        total: int = 0,
    ) -> None:
        await self._bus.publish(
            EventType.progress,
            progress_payload(phase=phase, round=state.round_no, label=label, completed=completed, total=total),
        )

    @staticmethod
    def _status_for(result: ExistenceResult):  # noqa: ANN205 - PlatformStatus, avoids a circular import
        from app.discovery.types import PlatformStatus

        return {
            ExistenceVerdict.EXISTS: PlatformStatus.FOUND,
            ExistenceVerdict.AMBIGUOUS: PlatformStatus.FOUND,
            ExistenceVerdict.NOT_FOUND: PlatformStatus.NOT_FOUND,
            ExistenceVerdict.BLOCKED: PlatformStatus.BLOCKED,
            ExistenceVerdict.ERROR: PlatformStatus.ERROR,
            ExistenceVerdict.UNSUPPORTED: PlatformStatus.UNSUPPORTED,
        }[result.verdict]


def utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = ["DiscoveryRound", "RoundOutcome", "logger", "utcnow"]

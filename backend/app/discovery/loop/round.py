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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.discovery.brief.apply import DISCOVERED_VIA_USER_SUPPLIED, prime_context
from app.discovery.brief.model import ReferenceAvatar, ReferenceSource
from app.discovery.browse.harvest import (
    BROWSE_CONFIDENCE_MULTIPLIER,
    ground,
    may_claim_profile,
    to_fetch_result,
)
from app.discovery.browse.runner import BrowseRunner
from app.discovery.browse.types import BrowseReport, BrowseTask
from app.discovery.engines.base import SearchHit
from app.discovery.engines.registry import EngineRegistry
from app.discovery.evidence.model import Evidence, make_evidence
from app.discovery.evidence.store import EvidenceStore
from app.discovery.fetch.session import FetchSession
from app.discovery.identity import contacts as contacts_module
from app.discovery.identity import workedu
from app.discovery.identity.normalize import name_tokens
from app.discovery.loop import seeds
from app.discovery.loop.state import DiscoveryState
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.matching.cluster import names_contradict
from app.discovery.matching.scoring import (
    demote_on_brief_conflict,
    exclusion_subject,
    require_independent_sources,
    score_profile,
)
from app.discovery.media.gender import MIN_CONFIDENCE as MIN_GENDER_CONFIDENCE
from app.discovery.media.gender import AvatarGenderReading, read_avatar_gender
from app.discovery.media.reverse import ReverseImageSearcher
from app.discovery.media.store import AvatarStore
from app.discovery.platforms.existence import ExistenceChecker, ExistenceResult
from app.discovery.platforms.extract import ProfileData, ProfileExtractor
from app.discovery.platforms.registry import DISCOVERY_ONLY_PLATFORMS, PlatformRegistry, is_discovery_only
from app.discovery.platforms.urlmatch import match_profile_url, registrable_host
from app.discovery.session.bus import SessionEventBus
from app.discovery.session.events import (
    EventType,
    browse_finished_payload,
    browse_started_payload,
    browse_step_payload,
    candidate_payload,
    evidence_payload,
    platform_status_payload,
    progress_payload,
)
from app.discovery.sources import github_commits
from app.discovery.sources.archive import ARCHIVE_CONFIDENCE_MULTIPLIER, ArchivedSnapshot, ArchiveRecovery
from app.discovery.sources.website import WebsiteChain
from app.discovery.types import EvidenceKind, ExistenceVerdict, Gender, PlatformStatus, PlatformTier, SourceKind
from app.utils.logger import logger

GENDER_SCREEN_MIN_SCORE = 20
"""Below `weak`, an account is not going into the answer whatever its picture
shows, so a vision call spent on it buys nothing."""


EVIDENCED_DISCOVERY: frozenset[str] = frozenset(
    {"serp", "outbound_link", "user_answer", "personal_site", "reverse_image", DISCOVERED_VIA_USER_SUPPLIED}
)
"""``discovered_via`` values that arrive with their own proof the URL is real.

The rest — ``username_permutation`` above all — are guesses, and a guess is only
worth what the existence check makes of it. The distinction is what lets a
platform-level "cannot probe" verdict be refused: it is a statement about the
platform, and it must not be allowed to overwrite a handle something else already
pointed at.
"""


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
        reverse: ReverseImageSearcher | None = None,
        website: WebsiteChain | None = None,
        max_reverse_lookups: int = 2,
        browse: BrowseRunner | None = None,
        browse_stop: Callable[[], bool] | None = None,
        avatar_gender_enabled: bool = False,
        max_gender_checks: int = 12,
        min_gender_confidence: float = MIN_GENDER_CONFIDENCE,
        avatar_gender_model: str = "",
        gender_keep_alive: str = "30s",
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
        self._reverse = reverse
        self._website = website
        self._max_reverse_lookups = max(0, max_reverse_lookups)
        """A Yandex lookup runs on the browser tier and costs seconds and megabytes,
        so it is spent only on candidates already worth corroborating."""

        # Named `_browse_runner`, not `_browse`: the phase method is `_browse`,
        # and an attribute of the same name silently shadows it on every
        # instance — the round would call the collaborator instead of the phase.
        self._browse_runner = browse
        """The interactive tier. ``None`` whenever it is switched off or no
        browser can start, and the phase is simply inert."""

        self._browse_stop = browse_stop or (lambda: False)

        self._gender_screen_enabled = avatar_gender_enabled
        self._max_gender_checks = max(0, max_gender_checks)
        """Vision calls the avatar-gender screen may spend in a whole search.

        Each one is 4-8 s on this hardware and evicts the narrative model on an
        8 GB card, so the screen is capped rather than run over every avatar."""

        self._gender_min_confidence = min_gender_confidence
        self._gender_model = avatar_gender_model or None
        self._gender_keep_alive = gender_keep_alive

        self._checker = ExistenceChecker(fetch, registry)
        self._extractor = ProfileExtractor(fetch, registry)

    async def run(self, state: DiscoveryState, fresh_from_last_round: Sequence[Evidence]) -> RoundOutcome:
        started = time.monotonic()
        state.reset_round_counters()

        # Every phase boundary is a stopping point. The wall-clock budget used to
        # be consulted only between rounds, so a round that began with a second
        # left still ran all six phases — the enrich and recover phases alone can
        # spend minutes on stealth fetches. Stopping here loses nothing already
        # collected: each phase writes its findings into `state` as it goes.
        # Reads the accounts the user gave us - one fetch each, round 0 only.
        # Guarded like every other fetching phase: a round with no time left must
        # not start network work.
        if state.round_no == 0 and not state.out_of_time:
            await self._adopt_brief(state)
        queries = await self._seed(state, fresh_from_last_round)
        results: list[ExistenceResult] = []
        if not state.out_of_time:
            await self._expand(state, queries)
        if not state.out_of_time:
            results = await self._verify(state)
        if not state.out_of_time:
            await self._enrich(state, results)
        if not state.out_of_time:
            await self._recover(state, results)
        if not state.out_of_time:
            await self._browse(state, results)
        if not state.out_of_time:
            await self._corroborate(state)
        # Scoring is pure CPU over what is already in `state`, so it runs even out
        # of time: skipping it would leave the candidates collected this round
        # unscored and invisible to the answer.
        self._score(state)
        # After scoring, because the screen only looks at candidates that are
        # actually in contention, and nothing has a score until `_score` has run.
        if not state.out_of_time:
            await self._gender_screen(state)

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

    # -- 0. ADOPT THE BRIEF ---------------------------------------------------

    async def _adopt_brief(self, state: DiscoveryState) -> None:
        """Read, exactly once, each account the user handed us.

        The account itself is already a candidate — `brief.apply.seed_state` built
        it before round 0 — so this is not a search and never becomes one. It is
        one page fetch per known profile, for what that page can lend the *rest*
        of the search: the avatar (a reference every other platform is compared
        against), the bio, the display name, and above all the outbound links,
        which are the strongest keyless corroborator there is.

        Being refused is not a reason to go looking. Instagram walls a logged-out
        profile view, and falling back to enumerating usernames there would do the
        precise thing the user asked us not to. The candidate keeps the existence
        the user asserted, the platform reports what actually happened, and the
        search carries on with one fewer reference.
        """
        profiles = state.brief.known_profiles
        if not profiles:
            return
        await self._progress(state, "brief", f"reading {len(profiles)} account(s) you gave", total=len(profiles))

        evidence: list[Evidence] = []
        for index, profile in enumerate(profiles, start=1):
            candidate = state.candidates.get(profile.key)
            if candidate is None:
                continue

            result = await self._checker.check(profile.platform, profile.username)
            state.record_pair_verdict(profile.platform, profile.username, result.verdict)

            if result.verdict is ExistenceVerdict.NOT_FOUND:
                # Real evidence against what the user told us — a typo, or a
                # deleted account. Recorded rather than argued with: the verdict
                # moves, the candidate stays, and the notice says so.
                candidate.verdict = ExistenceVerdict.NOT_FOUND
                candidate.status_detail = "you gave this account, but the platform says it does not exist"
                state.note_platform(profile.platform, PlatformStatus.NOT_FOUND)
                logger.log_warning(f"[BRIEF] {profile.key} was given by the user but returned not_found")
                continue

            if not result.usable:
                candidate.status_detail = (
                    f"you gave this account; the platform would not let us read it ({result.verdict})"
                )
                state.note_platform(profile.platform, PlatformStatus.FOUND)
                continue

            data = await self._extractor.extract(result)
            if data is None:
                continue
            candidate.data = data
            self._adopt_personal_site(state, candidate, data)
            evidence.extend(self._evidence_from_profile(state, candidate, data))
            await self._save_avatar(state, candidate, data)
            self._promote_reference_avatar(state, candidate)
            await self._bus.publish(EventType.candidate_updated, candidate_payload(candidate))
            await self._progress(state, "brief", "reading the accounts you gave", completed=index, total=len(profiles))

        await self._store_evidence(state, evidence)

    @staticmethod
    def _promote_reference_avatar(state: DiscoveryState, candidate: ProfileCandidate) -> None:
        """Use a known account's picture as the reference, unless the user uploaded one.

        An upload is a deliberate choice and always wins: the profile picture may
        well be a logo, and silently preferring it would compare every other
        platform against the wrong image.
        """
        if not candidate.avatar_sha256:
            return
        state.brief = state.brief.with_reference_avatar(
            ReferenceAvatar(
                sha256=candidate.avatar_sha256,
                dhash=candidate.avatar_dhash or "",
                local_url=candidate.avatar_local_url or "",
                source=ReferenceSource.KNOWN_PROFILE,
            )
        )
        prime_context(state.brief, state.context)

    # -- 1. SEED -------------------------------------------------------------

    async def _seed(self, state: DiscoveryState, fresh: Sequence[Evidence]) -> list[str]:
        await self._progress(state, "seed", "planning queries")
        if state.round_no == 0:
            for candidate in seeds.seed_usernames(state):
                state.usernames[candidate.value] = candidate
            return seeds.round_zero_queries(state, self._registry)

        # `is_live` only says the account exists, which is not the same as saying
        # it is the target's. A single unrelated SERP row — Bing serves those with
        # a straight face — used to seed a dozen variants of a stranger's handle
        # and those were then probed across every platform, spending the rest of
        # the budget on the wrong person. Watched happening live on 2026-08-29.
        #
        # Same definition of "confirmed" the scorer uses for `confirmed_urls`.
        confirmed = [
            c.username for c in state.candidates.values() if c.is_live and (c.score.value >= 60 or c.user_confirmed)
        ]
        for candidate in seeds.expand_usernames(state, confirmed[:10]):
            state.usernames.setdefault(candidate.value, candidate)
        return seeds.followup_queries(state, fresh)

    # -- 2. EXPAND -----------------------------------------------------------

    async def _expand(self, state: DiscoveryState, queries: list[str]) -> list[SearchHit]:
        if not queries:
            return []
        await self._progress(state, "expand", f"querying {len(queries)} dork(s)", total=len(queries))
        # No `concurrency` override: the engine pool serialises requests itself
        # now, and three queries in flight only ever multiplied the burst.
        hits = await self._engines.search_many(self._fetch, queries, engine_count=self._engine_count, limit=20)

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

            if state.is_pinned_stranger(matched.platform, matched.username):
                # Dropped outright rather than kept as a web source: it is a
                # stranger's profile page, so letting it corroborate anything
                # would corroborate the wrong person. Note this also has to run
                # before the `usernames_tried.discard` below, which would
                # otherwise re-open that stranger's handle for probing.
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
        # Anything already discovered from a SERP still needs verifying. Candidates
        # predating a pin are the exception: a platform settled mid-run by a "yes"
        # answer must not keep spending probes on the handles it displaced.
        for candidate in state.candidates.values():
            pair = (candidate.platform, candidate.username)
            if state.is_pinned_stranger(*pair):
                continue
            if is_discovery_only(candidate.platform):
                # This handle did not come from a guess — it came from a URL a
                # search engine, an outbound link or the user gave us, and that
                # URL is the evidence. Probing it cannot confirm it and cannot
                # deny it, so the only thing a probe changes is the verdict we
                # then overwrite the candidate with. That overwrite is how a
                # Spotify account we had the profile URL for was reported as
                # `unsupported` and dropped from the results entirely.
                await self._report_discovery_only(state, candidate)
                continue
            if candidate.verdict is ExistenceVerdict.AMBIGUOUS and pair not in pairs:
                pairs.append(pair)
                state.usernames_tried.add(pair)
        if not pairs:
            return []

        await self._progress(state, "verify", f"checking {len(pairs)} handle(s)", total=len(pairs))
        results = await self._checker.check_many(
            pairs, concurrency=6, stealth_allowed=self._stealth_allowed(state, pairs)
        )

        evidence: list[Evidence] = []
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
            if result.verdict is ExistenceVerdict.UNSUPPORTED and candidate.discovered_via in EVIDENCED_DISCOVERY:
                # `unsupported` describes the platform's probe surface, not this
                # handle. Writing it onto a candidate that arrived with a real
                # URL turns a finding into a non-answer.
                candidate.signals = result.signals
            else:
                candidate.verdict = result.verdict
                candidate.signals = result.signals
                candidate.status_detail = result.detail
            state.upsert_candidate(candidate)
            # Remembered per pair, not just per platform: `note_platform` keeps one
            # status for the whole platform, which cannot say which handle was
            # refused. `seeds.platform_probe_pairs` needs the pair to decide
            # whether trying again could learn anything.
            state.record_pair_verdict(result.platform, result.username, result.verdict)
            await self._store.record_platform_outcome(state.session_id, result)
            await self._bus.publish(EventType.platform_status, platform_status_payload(result))

            # "We checked this platform and the handle is taken" is a fact about
            # the target with a source, so it is recorded as one. Only the profile
            # *page* used to produce evidence, which meant an account found by
            # existence check alone — the normal outcome when the search engines
            # refuse us and nothing can be parsed — left its cluster with no
            # evidence at all. The biography then reported that nothing could be
            # established while the account list sat right beside it.
            #
            # Deliberately a different assertion from the profile read: subject is
            # the candidate, value is the handle. The page read keys on
            # (PROFILE, candidate, url), so the two never collide and the richer
            # one never loses its confidence to this one.
            if result.verdict is ExistenceVerdict.EXISTS and candidate.url:
                evidence.append(
                    make_evidence(
                        EvidenceKind.USERNAME,
                        candidate.key,
                        candidate.username,
                        source_url=candidate.url,
                        source_kind=SourceKind.PROFILE_PAGE,
                        extractor=f"existence:{result.platform}",
                        confidence=0.5,
                        platform=result.platform,
                        round_no=state.round_no,
                    )
                )
        await self._store_evidence(state, evidence)

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

    async def _report_discovery_only(self, state: DiscoveryState, candidate: ProfileCandidate) -> None:
        """Announce an account on a platform that is found but never probed.

        The verdict stays AMBIGUOUS — "we have a live URL for this handle, we
        could not structurally confirm it" — which is exactly what a discovered
        profile URL supports, and which `platform_status` already surfaces as
        `found` behind the low-confidence band it has earned. Clustering still
        decides whether the account belongs to the target; this only stops the
        pipeline from throwing it away before clustering ever sees it.
        """
        if candidate.verdict is ExistenceVerdict.UNSUPPORTED:
            # Left behind by a run from before this platform was reclassified.
            candidate.verdict = ExistenceVerdict.AMBIGUOUS
        if not candidate.signals:
            candidate.signals = (f"profile URL discovered via {candidate.discovered_via or 'search'}",)
        if not candidate.status_detail:
            candidate.status_detail = DISCOVERY_ONLY_PLATFORMS.get(candidate.platform, "")
        state.upsert_candidate(candidate)

        status = candidate.platform_status
        if status is not PlatformStatus.FOUND:
            # "That is not me" outranks "a search engine indexed it", and it is
            # the one judgement skipping the probe must not skip.
            return
        if state.platform_status.get(candidate.platform) is PlatformStatus.FOUND:
            # Announced in an earlier round; repeating it would redraw the live
            # grid every round with news it already has.
            return
        state.note_platform(candidate.platform, status)
        outcome = ExistenceResult(
            platform=candidate.platform,
            username=candidate.username,
            url=candidate.url,
            verdict=candidate.verdict,
            signals=candidate.signals,
            detail=candidate.status_detail,
        )
        await self._store.record_platform_outcome(state.session_id, outcome)
        await self._bus.publish(EventType.platform_status, platform_status_payload(outcome))

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
            self._adopt_personal_site(state, candidate, data)
            evidence.extend(self._evidence_from_profile(state, candidate, data))
            await self._save_avatar(state, candidate, data)
            await self._bus.publish(EventType.candidate_updated, candidate_payload(candidate))
            if index % 5 == 0:
                await self._progress(state, "enrich", "reading profiles", completed=index, total=len(usable))

        await self._store_evidence(state, evidence)

    @staticmethod
    def _adopt_personal_site(state: DiscoveryState, candidate: ProfileCandidate, data: ProfileData) -> None:
        """Take the website a GitHub profile declares as the anchor's domain.

        `anchor.domain` decides whether `personal_site_backlink` (+25) can fire and
        whether the subject's own site is crawled at all, but the only code that
        set it was `build_anchor(github_data=...)` — an argument the discovery
        pipeline never passes. The field was empty on every search ever run, so
        both features were unreachable.

        Guarded by `names_contradict`, not by token overlap. A shared token is not
        a match when the token is a surname: a live run on 2026-08-29 adopted
        `engin-erdogan.com` from a stranger's GitHub profile during a search for
        "Yigit Erdogan", then paid that stranger `personal_site_backlink` (+25)
        while the scorer was calling `name_conflict` (-16) on the same candidate.
        The mutual-difference test is the one that separates two people who share
        a surname, and it still accepts one person written two ways.
        """
        if state.anchor.domain or candidate.platform != "github":
            return
        declared = data.display_name or ""
        anchor_name = " ".join(state.anchor.tokens)
        if not name_tokens(declared) or not set(name_tokens(declared)) & set(state.anchor.tokens):
            return
        if names_contradict(declared, anchor_name):
            return
        for link in data.outbound_links:
            if match_profile_url(link) is not None:
                continue
            host = registrable_host(link)
            if host:
                state.anchor.domain = host
                return

    def _evidence_from_profile(
        self,
        state: DiscoveryState,
        candidate: ProfileCandidate,
        data: ProfileData,
        *,
        source_kind: SourceKind = SourceKind.PROFILE_PAGE,
        confidence_scale: float = 1.0,
    ) -> list[Evidence]:
        """Turn parsed profile data into evidence.

        ``source_kind`` and ``confidence_scale`` exist for the browse tier, which
        runs this exact parser over a document a driven page produced. The per-
        field numbers below are the same either way — it is the same extractor on
        the same kind of bytes — but the *route* to the page is one step less
        certain, so the label has to survive into the journal and the weight is
        discounted. Defaults leave the enrich phase's behaviour untouched.
        """
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
                    source_kind=source_kind,
                    extractor=data.extractor or "profile",
                    confidence=max(0.0, min(1.0, confidence * confidence_scale)),
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
        for address in data.emails[:5]:
            add(EvidenceKind.EMAIL, "email", address, 0.8)
        for number in data.phones[:3]:
            add(EvidenceKind.PHONE, "phone", number, 0.75)
        for link in data.outbound_links[:12]:
            add(EvidenceKind.LINK, candidate.key, link, 0.7)

        if data.bio:
            # Bio text is mined for addresses only — see `ProfileData.phones`.
            for hit in contacts_module.emails_from(data.bio, source_url=candidate.url, extractor="bio"):
                add(EvidenceKind.EMAIL, "email", hit.value, hit.confidence)
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

    # -- 4b2. BROWSE ----------------------------------------------------------

    async def _browse(self, state: DiscoveryState, results: Sequence[ExistenceResult]) -> None:
        """Drive a browser at the few pages the cheap tiers could not read.

        The last resort, and it behaves like one. It runs **once per search**
        rather than once per round: a browse step costs a local vision inference,
        and on an 8 GB card the vision model and the narrative model cannot both
        be resident, so browsing every round would make ollama evict and reload
        one of them every round for targets that have not changed.

        It also refuses to start without ``min_time_left_seconds`` still on the
        clock. A phase that can spend three minutes must never be the thing that
        leaves no budget for the biography.
        """
        runner = self._browse_runner
        if runner is None or not runner.settings.enabled or state.browse_used:
            return
        if state.time_left_s < runner.settings.min_time_left_seconds:
            return

        targets = self._browse_targets(state, results, runner.settings.max_tasks_per_search)
        if not targets:
            return

        state.browse_used = True
        await self._progress(state, "browse", f"opening a browser on {len(targets)} page(s)", total=len(targets))

        evidence: list[Evidence] = []
        for index, result in enumerate(targets, start=1):
            candidate = state.candidates.get(result.key)
            if candidate is None:
                continue
            state.browsed.add(result.key)

            task = BrowseTask(
                task_id=f"{state.round_no}-{result.platform}-{result.username}",
                url=result.url,
                platform=result.platform,
                username=result.username,
                reason=result.detail or f"{result.verdict} at the {result.tier_used} tier",
            )
            await self._bus.publish(
                EventType.browse_started,
                browse_started_payload(
                    task_id=task.task_id,
                    url=task.url,
                    platform=task.platform,
                    username=task.username,
                    reason=task.reason,
                    max_steps=runner.settings.max_steps,
                    max_seconds=runner.settings.max_seconds,
                ),
            )

            report = await runner.run(
                task,
                session_id=state.session_id,
                emit=self._publish_browse_step,
                should_stop=self._browse_stop,
            )
            found = self._evidence_from_browse(state, candidate, report)
            evidence.extend(found)

            await self._bus.publish(
                EventType.browse_finished,
                browse_finished_payload(
                    task_id=task.task_id,
                    outcome=str(report.outcome),
                    detail=report.detail,
                    steps_used=report.steps_used,
                    duration_ms=report.duration_ms,
                    model_calls=report.model_calls,
                    evidence_added=len(found),
                    dropped_ungrounded=report.dropped_ungrounded,
                ),
            )
            await self._bus.publish(EventType.candidate_updated, candidate_payload(candidate))
            await self._progress(state, "browse", "reading with a browser", completed=index, total=len(targets))

        await self._store_evidence(state, evidence)

    async def _publish_browse_step(self, event_type: str, payload: dict) -> None:
        """Relay one agent step onto the bus. Telemetry must not stop the work."""
        del event_type  # the agent only ever emits steps
        task_id = str(payload.pop("task_id", ""))
        await self._bus.publish(EventType.browse_step, browse_step_payload(task_id, payload))

    def _browse_targets(
        self,
        state: DiscoveryState,
        results: Sequence[ExistenceResult],
        limit: int,
    ) -> list[ExistenceResult]:
        """The handles that have earned a browser, in priority order.

        Three kinds of unfinished business qualify:

        * ``BLOCKED`` — the cheap tiers were refused;
        * ``ERROR`` — the check fell over before reaching any verdict at all,
          which is the case a real page most often fixes: a render that needed
          JavaScript, a response that arrived truncated, a redirect chain the
          plain client would not follow. The risk is a parser bug the browser
          cannot fix either, and then the tier spends a few inferences learning
          that; the budgets are what make that affordable, not certainty;
        * ``EXISTS``/``AMBIGUOUS`` whose page yielded nothing readable.

        And one exclusion that saves more time than the rest combined: a target
        whose block signal was a login redirect is skipped. An anonymous browser
        will not get past an auth wall, we already hold the honest ``BLOCKED``
        verdict, and paying a dozen inferences to re-learn it is the most
        wasteful thing this tier could do.
        """
        earned = self._stealth_allowed(state, [(r.platform, r.username) for r in results])
        picked: list[ExistenceResult] = []

        for result in results:
            if result.key in state.browsed or (result.platform, result.username) not in earned:
                continue
            signal = result.fetch.block_signal if result.fetch is not None else None
            if signal in ("login_redirect", "consent_redirect"):
                continue

            unfinished = result.verdict in (ExistenceVerdict.BLOCKED, ExistenceVerdict.ERROR)
            candidate = state.candidates.get(result.key)
            unread = (
                result.verdict in (ExistenceVerdict.EXISTS, ExistenceVerdict.AMBIGUOUS)
                and candidate is not None
                and (candidate.data is None or candidate.data.is_empty)
            )
            if unfinished or unread:
                picked.append(result)
            if len(picked) >= max(0, limit):
                break
        return picked

    def _evidence_from_browse(
        self,
        state: DiscoveryState,
        candidate: ProfileCandidate,
        report: BrowseReport,
    ) -> list[Evidence]:
        """Read the harvested document with the pipeline's own extractor.

        Nothing the model said reaches this path. The HTML captured at ``extract``
        goes through ``ProfileExtractor``, every value it produces is checked
        against those same bytes, and the existence claim needs a 2xx on a URL
        that still names the handle we set out to read.
        """
        candidate.status_detail = (
            f"{candidate.status_detail} · browse {report.outcome}".strip(" ·")
            if candidate.status_detail
            else f"browse {report.outcome}"
        )

        fetch_result = to_fetch_result(report)
        if not fetch_result.ok:
            return []

        data = self._extractor.from_result(candidate.platform, candidate.username, candidate.url, fetch_result)
        if data is None or data.is_empty:
            return []

        allow_profile = may_claim_profile(report)
        produced = [
            item
            for item in self._evidence_from_profile(
                state,
                candidate,
                data,
                source_kind=SourceKind.BROWSE,
                confidence_scale=BROWSE_CONFIDENCE_MULTIPLIER,
            )
            if allow_profile or item.kind is not EvidenceKind.PROFILE
        ]

        kept, dropped = ground(produced, report.html)
        report.dropped_ungrounded = dropped
        if kept:
            candidate.data = data
        return kept

    # -- 4c. CORROBORATE ------------------------------------------------------

    async def _corroborate(self, state: DiscoveryState) -> None:
        """Look for the target somewhere that is not its own profile page.

        Every other step reads a candidate's own page, so every fact recorded
        against it carries that one domain. `require_independent_sources` asks for
        two distinct sites at depth 7-8 and three at 9-10, which made `confirmed`
        unreachable outright above depth 6 — the count could never exceed one.
        These are the two sources that genuinely produce a second and third.
        """
        evidence: list[Evidence] = []
        evidence.extend(await self._from_personal_site(state))
        evidence.extend(await self._from_github_commits(state))
        evidence.extend(await self._from_reverse_image(state))
        if evidence:
            await self._store_evidence(state, evidence)

    async def _from_personal_site(self, state: DiscoveryState) -> list[Evidence]:
        """The person's own site listing an account is the site vouching for it."""
        domain = (getattr(state.anchor, "domain", "") or "").strip()
        if self._website is None or not domain or domain in state.sites_crawled:
            return []
        state.sites_crawled.add(domain)
        entry = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"

        await self._progress(state, "enrich", f"reading {registrable_host(entry)}")
        try:
            findings = await self._website.crawl(self._fetch, entry, name_tokens=state.terms.tokens)
        except Exception as exc:
            logger.log_warning(f"Personal site crawl failed for {domain}: {type(exc).__name__}: {exc}")
            return []
        if findings.blocked:
            logger.log_warning(f"Personal site {domain} refused the crawl: {findings.detail}")
            return []

        out: list[Evidence] = []
        # `rel_me_urls` first: the site marking a link as "me" is a stronger claim
        # than merely mentioning it, and duplicates collapse on the fingerprint.
        for url in list(findings.rel_me_urls) + list(findings.profile_urls):
            matched = match_profile_url(url)
            if matched is None:
                continue
            if state.is_pinned_stranger(matched.platform, matched.username):
                # Even a rel=me claim loses to the pin. The site is claiming a
                # handle on a platform the user has already told us the answer
                # for, so the site is describing somebody else.
                continue
            candidate = state.candidates.get(matched.key)
            if candidate is None:
                spec = self._registry.get(matched.platform)
                candidate = ProfileCandidate(
                    platform=matched.platform,
                    username=matched.username,
                    url=matched.canonical_url,
                    variant=matched.variant,
                    tier=spec.tier if spec else PlatformTier.CORE,
                    discovered_round=state.round_no,
                    discovered_via="personal_site",
                )
                state.upsert_candidate(candidate)
            out.append(
                make_evidence(
                    EvidenceKind.LINK,
                    candidate.key,
                    candidate.url,
                    source_url=findings.url,
                    source_kind=SourceKind.WEBSITE,
                    extractor=f"website:{registrable_host(findings.url)}",
                    confidence=0.85,
                    platform=matched.platform,
                    round_no=state.round_no,
                )
            )
        for hit in findings.contacts:
            # `platform=None` on purpose: a website is not a platform, and
            # `cluster._evidence_for` admits platform-free evidence to the
            # elected cluster, which is where a contact detail belongs.
            # `raw["display"]` keeps the as-written form, which is the needle the
            # browse grounding gate has to search a page for.
            out.append(
                make_evidence(
                    hit.kind,
                    hit.subject,
                    hit.value,
                    source_url=hit.source_url,
                    source_kind=SourceKind.WEBSITE,
                    extractor=f"contact:{hit.extractor}",
                    confidence=hit.confidence,
                    round_no=state.round_no,
                    raw={"display": hit.display},
                )
            )
        return out

    async def _from_github_commits(self, state: DiscoveryState) -> list[Evidence]:
        """A settled GitHub account's public commits, for the address behind them.

        Gated hard, because unauthenticated `api.github.com` allows 60 requests
        an hour per IP and the existence checker already spends some of them.
        One account, one request, one session — and only for an account the run
        is already confident about, since a commit address attributed to the
        wrong developer is a stranger's contact detail published as the
        subject's.
        """
        if state.github_commits_checked:
            return []
        live = [
            c
            for c in state.candidates.values()
            if c.platform == "github"
            and c.is_live
            and c.username
            and not state.is_pinned_stranger("github", c.username)
        ]
        if len(live) != 1:
            return []
        candidate = live[0]
        if not (candidate.user_confirmed or candidate.score.value >= 60):
            return []

        state.github_commits_checked = True
        await self._progress(state, "enrich", f"reading public commits for {candidate.username}")
        try:
            hits = await github_commits.commit_emails(self._fetch, candidate.username, name_tokens=state.terms.tokens)
        except Exception as exc:
            logger.log_warning(f"GitHub commit e-mail lookup failed: {type(exc).__name__}: {exc}", broadcast=False)
            return []

        return [
            make_evidence(
                hit.kind,
                hit.subject,
                hit.value,
                source_url=hit.source_url,
                source_kind=SourceKind.API,
                extractor=f"contact:{hit.extractor}",
                confidence=hit.confidence,
                platform="github",
                round_no=state.round_no,
                raw={"display": hit.display},
            )
            for hit in hits
        ]

    async def _from_reverse_image(self, state: DiscoveryState) -> list[Evidence]:
        """Pages carrying the same picture, each on a site that is not the profile."""
        if self._reverse is None or self._max_reverse_lookups <= 0:
            return []
        targets = sorted(
            (
                c
                for c in state.candidates.values()
                if c.is_live and c.avatar_url and c.key not in state.reverse_searched and c.score.value >= 40
            ),
            key=lambda c: (-c.score.value, c.platform, c.username),
        )
        out: list[Evidence] = []
        for candidate in targets[: self._max_reverse_lookups]:
            state.reverse_searched.add(candidate.key)
            await self._progress(state, "enrich", f"reverse image: {candidate.platform}/{candidate.username}")
            try:
                hits = await self._reverse.search(self._fetch, candidate.avatar_url or "", limit=12)
            except Exception as exc:
                logger.log_warning(f"Reverse image failed for {candidate.key}: {type(exc).__name__}: {exc}")
                continue
            for hit in hits:
                host = registrable_host(hit.url)
                if not host or host == registrable_host(candidate.url):
                    continue
                matched = match_profile_url(hit.url)
                subject = matched.key if matched is not None else candidate.key
                if matched is not None:
                    state.context.reverse_image_hits.setdefault(candidate.key, set()).add(matched.platform)
                out.append(
                    make_evidence(
                        EvidenceKind.MENTION,
                        subject,
                        hit.url,
                        source_url=hit.url,
                        source_kind=SourceKind.REVERSE_IMAGE,
                        extractor=f"reverse:{hit.engine}",
                        confidence=0.5,
                        platform=matched.platform if matched is not None else None,
                        round_no=state.round_no,
                    )
                )
        return out

    # -- 5. SCORE ------------------------------------------------------------

    def _score(self, state: DiscoveryState) -> None:
        self._refresh_context(state)
        domains = self._source_domains_by_candidate(state)
        for candidate in state.candidates.values():
            score = score_profile(candidate, state.anchor, state.evidence, state.context)
            score = require_independent_sources(
                score,
                source_domains=len(domains.get(candidate.key, ())),
                required=self._validation_passes,
            )
            # `score_profile` is pure and knows nothing about a reading taken by
            # the vision model, so an exclusion established in an earlier round
            # has to be re-applied or the next re-score would quietly undo it.
            if candidate.excluded_by:
                score = demote_on_brief_conflict(score, code=candidate.excluded_by, other=exclusion_subject(candidate))
            candidate.score = score

    # -- 7b. AVATAR GENDER SCREEN --------------------------------------------

    async def _gender_screen(self, state: DiscoveryState) -> None:
        """Rule out accounts whose picture contradicts the gender the user gave.

        Only runs when the user actually stated one. Everything about it is built
        to fail *towards keeping* a candidate, because a wrong exclusion is the
        one error this pipeline cannot let pass silently:

        * candidates that are not in contention are never read at all;
        * an account the user gave or confirmed is never screened — they told us
          it is theirs, and a picture does not outrank that;
        * an avatar is read once per distinct file, not once per account;
        * the reading must be a single, clearly-seen face at high confidence, or
          it changes nothing (see `media.gender.AvatarGenderReading.is_actionable`);
        * the whole search has a hard call budget, because each read costs 4-8 s
          and evicts the narrative model on an 8 GB card.

        An excluded account is not deleted. Its band drops to ``rejected``, which
        takes it out of the biography and the accounts list, and the reason is
        written next to it so a wrong call is visible and correctable.
        """
        if not self._gender_screen_enabled or not state.brief.gender.is_stated:
            return
        if state.gender_checks_used >= self._max_gender_checks:
            return

        targets = self._gender_screen_targets(state)
        if not targets:
            return
        await self._progress(state, "screen", f"checking {len(targets)} profile picture(s)", total=len(targets))

        readings: dict[str, AvatarGenderReading] = {}
        evidence: list[Evidence] = []
        for index, candidate in enumerate(targets, start=1):
            if state.out_of_time or state.gender_checks_used >= self._max_gender_checks:
                break
            digest = candidate.avatar_sha256 or ""
            reading = readings.get(digest)
            if reading is None:
                data = self._avatar_bytes(candidate)
                if data is None:
                    continue
                state.gender_checks_used += 1
                reading = await read_avatar_gender(
                    data,
                    model=self._gender_model,
                    keep_alive=self._gender_keep_alive,
                )
                if reading is None:
                    # The model never answered. Not a finding, and never a reason
                    # to drop anyone - the candidate keeps the score it earned.
                    continue
                readings[digest] = reading

            candidate.avatar_gender = reading.gender
            evidence.append(self._gender_evidence(state, candidate, reading))
            if reading.contradicts(state.brief.gender, min_confidence=self._gender_min_confidence):
                candidate.excluded_by = "photo_gender_conflict"
                candidate.score = demote_on_brief_conflict(
                    candidate.score, code="photo_gender_conflict", other=reading.describe()
                )
                logger.log_warning(
                    f"[SCREEN] {candidate.key} excluded - picture reads as {reading.describe()} "
                    f"at {reading.confidence:.2f}, you said {state.brief.gender.value}"
                )
                await self._bus.publish(EventType.candidate_updated, candidate_payload(candidate))
            await self._progress(state, "screen", "checking profile pictures", completed=index, total=len(targets))

        await self._store_evidence(state, evidence)

    def _gender_screen_targets(self, state: DiscoveryState) -> list[ProfileCandidate]:
        """Candidates worth spending a vision call on, strongest first.

        The score floor is what keeps the budget on accounts that could actually
        be attributed: an account below `weak` is not going into the answer
        whatever its picture shows, so reading it would buy nothing.
        """
        budget = self._max_gender_checks - state.gender_checks_used
        eligible = [
            candidate
            for candidate in state.candidates.values()
            if candidate.is_live
            and candidate.avatar_sha256
            and candidate.score.value >= GENDER_SCREEN_MIN_SCORE
            and candidate.avatar_gender is Gender.UNKNOWN
            and not candidate.excluded_by
            and not candidate.user_confirmed
            and candidate.discovered_via != DISCOVERED_VIA_USER_SUPPLIED
        ]
        eligible.sort(key=lambda c: (-c.score.value, c.key))
        return eligible[: max(0, budget)]

    def _avatar_bytes(self, candidate: ProfileCandidate) -> bytes | None:
        """Read our own stored copy of the avatar. None when it is not on disk."""
        local = candidate.avatar_local_url or ""
        basename = local.rsplit("/", 1)[-1] if local else ""
        path = self._avatars.resolve(basename) if basename else None
        if path is None:
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    @staticmethod
    def _gender_evidence(state: DiscoveryState, candidate: ProfileCandidate, reading: AvatarGenderReading) -> Evidence:
        """Record the reading, whatever it said, so the exclusion traces to it."""
        return make_evidence(
            EvidenceKind.GENDER,
            candidate.key,
            reading.gender.value,
            source_url=candidate.avatar_local_url or candidate.url,
            source_kind=SourceKind.DERIVED,
            extractor="vision_avatar_gender",
            confidence=round(reading.confidence, 2),
            platform=candidate.platform,
            round_no=state.round_no,
            raw={"has_face": reading.has_face, "face_count": reading.face_count},
        )

    @staticmethod
    def _source_domains_by_candidate(state: DiscoveryState) -> dict[str, set[str]]:
        """Candidate key -> the distinct sites that said something about it.

        Deliberately keyed on the evidence *subject*: a fact recorded against the
        candidate itself. Platform-wide evidence is excluded, because it would
        credit one candidate with corroboration earned by a namesake on the same
        platform.

        Evidence alone can never reach two. Everything recorded against a
        candidate — profile, bio, avatar, outbound links, and the SERP hit that
        found it — is read off that one page and carries its URL, so the set held
        exactly one member for every candidate that ever existed. That turned
        `require_independent_sources` from a graded requirement into an
        unconditional ban above depth 6: nothing could be confirmed, so the
        anchor never strengthened, so nothing else could be confirmed either.

        A second site linking to the account is the corroboration the gate is
        actually asking about, so cross-platform links count as the sources they
        are. A self-link does not: a page vouching for itself is still one site.
        """
        out: dict[str, set[str]] = {}
        for ev in state.evidence:
            if ev.source_domain:
                out.setdefault(ev.subject, set()).add(ev.source_domain)

        for candidate in state.candidates.values():
            if not candidate.is_live:
                continue
            linking_domain = registrable_host(candidate.url)
            if not linking_domain:
                continue
            for href in candidate.outbound_links:
                matched = match_profile_url(href)
                if matched is None or matched.key == candidate.key:
                    continue
                out.setdefault(matched.key, set()).add(linking_domain)
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
        rel_me: dict[str, set[str]] = {}
        for candidate in state.candidates.values():
            if not candidate.is_live:
                continue
            handle = candidate.username.lower()
            ctx.handle_counts[handle] = ctx.handle_counts.get(handle, 0) + 1
            if candidate.score.value >= 60 or candidate.user_confirmed:
                ctx.confirmed_urls.add(candidate.url)
                ctx.confirmed_domains.add(registrable_host(candidate.url))
            targets: set[str] = set()
            for href in candidate.outbound_links:
                matched = match_profile_url(href)
                if matched is not None:
                    targets.add(matched.key)
            links[candidate.key] = targets
            claimed: set[str] = set()
            for href in candidate.rel_me_links:
                matched = match_profile_url(href)
                if matched is not None:
                    claimed.add(matched.key)
            rel_me[candidate.key] = claimed

        for key, targets in links.items():
            for target in targets:
                if key in links.get(target, set()):
                    ctx.reciprocal_pairs.add((key, target) if key <= target else (target, key))

        # Mutual only. A one-way `rel="me"` is an assertion by whoever wrote the
        # page, and anyone can claim to be anyone; `rel_me_verified` is worth +28,
        # which only the two-sided IndieAuth handshake earns.
        for key, claimed in rel_me.items():
            for target in claimed:
                if key in rel_me.get(target, set()):
                    ctx.rel_me_pairs.add(ctx.pair(key, target))

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
        # Contacts jump the publish cap. The cap keeps a bulk round from flooding
        # the feed, but an address stored and silently left off the wire is the
        # "nothing is ever silently empty" rule broken at the one value a user
        # actually goes looking for.
        contact_kinds = (EvidenceKind.EMAIL, EvidenceKind.PHONE)
        ordered = sorted(fresh, key=lambda ev: ev.kind not in contact_kinds)
        for ev in ordered[:60]:
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

"""The iterative-deepening driver.

Rounds run until two consecutive rounds produce nothing new, or until a named
budget runs out. Between rounds the pipeline may pause and ask the user a
question — the await genuinely suspends the coroutine, so the event loop keeps
serving the answer endpoint while the search waits.

The subtle part is **re-anchoring**. If the user picks a different person half way
through, everything written for the previous identity is wrong. Rather than
patching it, the runner discards the draft narrative, marks the rejected
cluster's evidence superseded, resets the dry-round counter and keeps going from
the new anchor. Neutral evidence (web sources tied to nobody) survives, which is
what makes the correction cheap instead of a restart.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from app.config import Settings, get_settings
from app.discovery.analysis.graph import RelationshipGraph, build_graph
from app.discovery.analysis.timeline import TimelineEvent, build_timeline
from app.discovery.brief.apply import build_brief_anchor, build_terms, evidence_for, seed_state
from app.discovery.brief.model import SearchBrief
from app.discovery.brief.parse import parse_brief
from app.discovery.browse.control import BrowseControl
from app.discovery.browse.runner import build_browse_runner
from app.discovery.engines.registry import EngineHealthStore, EngineRegistry
from app.discovery.evidence.model import Evidence, make_evidence
from app.discovery.evidence.store import EvidenceStore
from app.discovery.fetch.cookies import CookieVault
from app.discovery.fetch.profiles import BrowserProfilePool
from app.discovery.fetch.ratelimit import DomainRateLimiter
from app.discovery.fetch.session import FetchSession, build_proxy_selector
from app.discovery.hitl.broker import QuestionBroker
from app.discovery.hitl.questions import Answer, Question, apply_answer, maybe_ask
from app.discovery.identity.anchor import Anchor, strengthen
from app.discovery.identity.normalize import fold_ascii
from app.discovery.identity.workedu import dedupe_education, dedupe_work
from app.discovery.loop.round import DiscoveryRound, RoundOutcome
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import MatchScore, ProfileCandidate
from app.discovery.matching.cluster import IdentityCluster, build_clusters, elect, limit_per_platform
from app.discovery.matching.scoring import (
    demote_on_brief_conflict,
    exclusion_subject,
    hold_back_unattributed,
    score_profile,
    score_subject,
)
from app.discovery.media.reverse import ReverseImageSearcher
from app.discovery.media.shots import FrameStore
from app.discovery.media.store import AvatarStore
from app.discovery.narrative.builder import (
    ATTRIBUTABLE_BANDS,
    NOTHING_ESTABLISHED,
    Narrative,
    NarrativeBuilder,
)
from app.discovery.narrative.grounding import Claim, GroundingReport
from app.discovery.platforms.registry import get_registry, registry_for_selection
from app.discovery.session.bus import SessionEventBus
from app.discovery.session.events import (
    EventType,
    anchor_changed_payload,
    candidate_payload,
    done_payload,
    error_payload,
    hello_payload,
    narrative_delta_payload,
    progress_payload,
    result_invalidated_payload,
    round_finished_payload,
    round_started_payload,
)
from app.discovery.session.manager import SessionManager
from app.discovery.sources.archive import ArchiveRecovery
from app.discovery.sources.website import WebsiteChain
from app.discovery.types import EntityType, EvidenceKind, MatchBand, PlatformStatus, SourceKind
from app.services.depth_config import DepthConfig
from app.utils.logger import logger


def target_key_for(name: str, entity: EntityType) -> str:
    """Stable key for "the same search, run again".

    Two different people who share a name also share this key. That is a real
    limitation, mitigated (not solved) by `EvidenceStore.load_prior`, which halves
    the confidence of prior evidence recorded under a conflicting anchor.
    """
    slug = "-".join(part for part in fold_ascii(name).lower().split() if part)
    return f"{slug}:{entity}"


# Writing the biography happens after the loop, so it used to sit outside the
# wall-clock budget entirely: `llm_json` makes a constrained call and then, for a
# thinking model, an unconstrained retry, each up to
# `llm_extraction_timeout_seconds` (300 s). A 1800 s budget that finishes at 2165 s
# is not a budget, so the write-up gets whatever collection left over, clamped.
NARRATIVE_MAX_BUDGET_S = 120.0
NARRATIVE_MIN_BUDGET_S = 30.0
NARRATIVE_STREAM_MARGIN = 0.9
"""The share of the budget the stream polices itself with.

`asyncio.wait_for` stays as the backstop, but it must not be the thing that
fires: cancelling the builder mid-stream throws away the accumulated
`GroundingReport`, where the stream's own deadline returns cleanly with every
sentence it managed to verify."""
"""A floor, because a run that spent its whole budget collecting still deserves a
biography — the deterministic template alone needs no model at all. The overshoot
is bounded and named, unlike the ten unaccounted minutes it replaces."""


@dataclass(slots=True)
class DiscoveryResult:
    """The finished search: exactly one identity, plus everything that supports it."""

    session_id: str
    target_key: str
    entity_type: EntityType
    profiles: list[ProfileCandidate] = field(default_factory=list)
    # Clusters the election rejected. Internal only: they are never serialised
    # or shown, and exist so a run can be checked for a namesake leaking into
    # the elected identity.
    alternates: list[IdentityCluster] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    web_sources: list[Any] = field(default_factory=list)
    work: list[Any] = field(default_factory=list)
    education: list[Any] = field(default_factory=list)
    platform_status: dict[str, PlatformStatus] = field(default_factory=dict)
    engine_status: dict[str, str] = field(default_factory=dict)
    anchor: Anchor | None = None
    elected: IdentityCluster | None = None
    subject_confidence: MatchScore | None = None
    questions: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0
    termination_reason: str = ""
    duration_ms: int = 0
    resumed_evidence: int = 0
    fetch_stats: dict[str, Any] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)
    """Honest caveats shown to the user: blocked platforms, disabled stealth, …"""

    narrative: Narrative | None = None
    """The grounded biography. Every sentence traces to stored evidence."""

    graph: RelationshipGraph | None = None
    timeline: list[TimelineEvent] = field(default_factory=list)


class DiscoveryRunner:
    """Owns a single search from start to finish."""

    def __init__(
        self,
        *,
        store: EvidenceStore,
        broker: QuestionBroker,
        manager: SessionManager,
        rate_limiter: DomainRateLimiter,
        settings: Settings | None = None,
        cookies: CookieVault | None = None,
        profiles: BrowserProfilePool | None = None,
        frames: FrameStore | None = None,
        browse_control: BrowseControl | None = None,
        engine_health: EngineHealthStore | None = None,
    ) -> None:
        self._store = store
        self._broker = broker
        self._manager = manager
        self._rate = rate_limiter
        self._settings = settings or get_settings()
        self._frames = frames or FrameStore(
            self._settings.discovery_browse_frame_dir,
            max_edge=self._settings.discovery_browse_frame_max_edge,
            quality=self._settings.discovery_browse_frame_quality,
            ttl_seconds=self._settings.discovery_browse_frame_ttl_seconds,
            max_files=self._settings.discovery_browse_frame_max_files,
        )
        self._browse_control = browse_control or BrowseControl()
        """Must be the same object the stop endpoint holds, or pressing Stop
        would set a flag nothing reads. Injected for the same reason the question
        broker is."""
        # Injected rather than imported: app.discovery.dependencies imports this
        # module, so reaching back into it here would close an import cycle.
        # All three are process-wide caches of what remote hosts told us, so a
        # missing one degrades to "no carry-over", never to a failure.
        self._cookies = cookies
        self._profiles = profiles
        self._engine_health = engine_health or EngineHealthStore()
        """Survives the run, so an engine that refused us is not re-probed by the
        next search. Held per registry it was discarded at the end of every run,
        which made the 600 s cooldown protect nothing."""

    async def run(
        self,
        *,
        session_id: str,
        raw_query: str,
        entity_type: EntityType = EntityType.PERSON,
        depth: int = 5,
        interactive: bool = True,
        platforms: Collection[str] | None = None,
        include_extended: bool = True,
        brief: SearchBrief | None = None,
        bus: SessionEventBus | None = None,
    ) -> DiscoveryResult:
        settings = self._settings
        live = self._manager.get(session_id)
        event_bus = bus or (live.bus if live else SessionEventBus(session_id))
        target_key = target_key_for(raw_query, entity_type)
        started = time.monotonic()

        # A caller that sent no brief still gets one: the same deterministic parse
        # the UI previews with. Otherwise `?q=` replay and the blocking fallback
        # would behave differently from the interactive path for the same text.
        brief = brief if brief is not None else parse_brief(raw_query, entity=entity_type)
        state = self._new_state(session_id, target_key, raw_query, entity_type, depth, brief)
        await self._store.create_session(
            session_id=session_id,
            target_key=target_key,
            raw_query=raw_query,
            entity_type=str(entity_type),
            depth=depth,
            interactive=interactive,
        )

        prior = await self._store.load_prior(target_key, exclude_session=session_id, current_anchor=state.anchor.handle)
        state.resumed_evidence = len(prior)
        state.record_evidence(list(prior))

        # Pins the platforms the user already knows, pre-builds their candidates
        # and primes the scoring context. Done before round 0 so `seeds` never
        # plans a query for a platform whose account we were handed.
        for created in seed_state(state):
            logger.log_detail(f"[BRIEF] {created.key} supplied by the user - {created.platform} will not be searched")
        state.record_evidence([evidence_for(p) for p in brief.known_profiles])
        if not brief.is_empty:
            logger.log_detail(f"[BRIEF] {brief.summary()}")

        await event_bus.publish(
            EventType.hello,
            hello_payload(
                session_id=session_id,
                query=raw_query,
                entity_type=str(entity_type),
                depth=depth,
                interactive=interactive,
                resumed_evidence=state.resumed_evidence,
                started_at=_iso_now(),
            ),
        )

        proxy = build_proxy_selector(get_registry().host_map())
        engines = EngineRegistry(
            allow_stealth=settings.discovery_stealth_enabled,
            health=self._engine_health,
            request_gap_s=settings.discovery_engine_request_gap_seconds,
        )
        # The user's platform pick narrows CORE; the long tail stays governed by
        # depth, with `include_extended` able to switch it off but never on.
        registry = registry_for_selection(
            selected=platforms,
            include_extended=include_extended and depth >= settings.discovery_extended_platforms_min_depth,
        )
        # The user's 1-10 depth setting decides how wide each query goes and how
        # much independent agreement a candidate needs to be called confirmed.
        depth_config = DepthConfig(depth)

        async with FetchSession(
            rate_limiter=self._rate,
            proxy=proxy,
            stealth_enabled=settings.discovery_stealth_enabled,
            max_stealth_pages=settings.discovery_max_stealth_pages,
            max_fetches=state.budget.max_fetches,
            cookies=self._cookies,
            profiles=self._profiles,
            real_chrome=settings.discovery_real_chrome,
            hide_canvas=settings.discovery_hide_canvas,
        ) as fetch:
            round_runner = DiscoveryRound(
                fetch=fetch,
                engines=engines,
                registry=registry,
                store=self._store,
                bus=event_bus,
                avatars=AvatarStore(),
                extended_min_depth=settings.discovery_extended_platforms_min_depth,
                engine_count=depth_config.search_engines_to_use,
                validation_passes=depth_config.validation_passes,
                archive=ArchiveRecovery(enabled=settings.discovery_archive_recovery_enabled),
                # The two sources that can produce a *second* domain for a
                # candidate. Without them `require_independent_sources` could
                # never be satisfied above depth 6, because everything else the
                # round records comes off the candidate's own page.
                reverse=ReverseImageSearcher(enabled=settings.discovery_reverse_image_enabled),
                website=WebsiteChain(max_pages=settings.discovery_website_crawl_max_pages),
                browse=build_browse_runner(fetch, settings, self._frames),
                browse_stop=lambda: self._browse_control.is_stopped(session_id),
                # Inert unless the brief states a gender, so the settings are
                # passed unconditionally and the phase decides for itself.
                avatar_gender_enabled=settings.discovery_avatar_gender_enabled,
                max_gender_checks=settings.discovery_avatar_gender_max_checks,
                min_gender_confidence=settings.discovery_avatar_gender_min_confidence,
                avatar_gender_model=(
                    settings.discovery_avatar_gender_model or settings.discovery_browse_model or settings.vision_model
                ),
                gender_keep_alive=settings.discovery_browse_keep_alive,
            )
            try:
                await self._loop(state, round_runner, event_bus, interactive=interactive)
            except Exception as exc:
                state.termination_reason = "error"
                logger.log_error(f"Discovery failed for {target_key}: {type(exc).__name__}: {exc}")
                await event_bus.publish(
                    EventType.error,
                    error_payload(f"{type(exc).__name__}: {exc}", fatal=True),
                )

            # Frames are telemetry and the search is over: keeping them would
            # turn a per-session directory into an unbounded one.
            self._frames.purge(session_id)
            self._browse_control.clear(session_id)

            result = self._build_result(state, engines, fetch, started)
            # The biography is written LAST, once the identity is settled. Anything
            # drafted mid-search was provisional and was discarded on every
            # re-anchor, so a switch of identity can never leave stale prose behind.
            # `started` goes with it so the reported duration can be re-stamped to
            # include this step rather than ending before the most expensive one.
            await self._finalize_narrative(state, result, event_bus, started=started)

        result.questions = await self._store.load_answers(target_key)
        await self._store.update_session(
            session_id,
            status="completed" if state.termination_reason != "error" else "failed",
            rounds_completed=state.rounds_completed,
            termination_reason=state.termination_reason,
            anchor_handle=state.anchor.handle,
            elected_cluster_id=state.elected.cluster_id if state.elected else None,
            # The full answer is persisted so `GET /sessions/{id}/result` can serve
            # the same profile the blocking route returns. Without it the
            # interactive path — now the default — would end with a live panel and
            # no durable result to show or export.
            result_json=_serialisable_result(result),
        )
        await event_bus.publish(
            EventType.done,
            done_payload(
                termination_reason=state.termination_reason,
                rounds=state.rounds_completed,
                duration_ms=result.duration_ms,
                summary={
                    "profiles": len(result.profiles),
                    "evidence": len(result.evidence),
                    "notices": result.notices,
                },
            ),
        )
        await self._manager.finish(session_id, "completed")
        return result

    # -- the loop -------------------------------------------------------------

    async def _loop(
        self,
        state: DiscoveryState,
        round_runner: DiscoveryRound,
        bus: SessionEventBus,
        *,
        interactive: bool,
    ) -> None:
        fresh: list[Evidence] = []
        while True:
            exhausted = state.exhausted()
            if exhausted:
                state.termination_reason = exhausted
                return

            await bus.publish(
                EventType.round_started,
                round_started_payload(
                    round=state.round_no,
                    planned_queries=state.query_allowance(),
                    planned_checks=len(state.usernames),
                ),
            )
            outcome = await round_runner.run(state, fresh)
            # Counted here, where a round has provably finished, so every reader
            # of "rounds" gets the same figure whichever exit path is taken.
            state.rounds_completed += 1
            fresh = outcome.new_evidence

            self._recluster(state)
            await self._maybe_reanchor_from_scores(state, bus)

            if outcome.productive:
                state.dry_rounds = 0
            else:
                state.dry_rounds += 1

            await bus.publish(
                EventType.round_finished,
                round_finished_payload(
                    round=state.round_no,
                    new_evidence=len(outcome.new_evidence),
                    new_candidates=outcome.new_candidates,
                    blocked_platforms=outcome.blocked_platforms,
                    dry_rounds=state.dry_rounds,
                    duration_ms=outcome.duration_ms,
                ),
            )

            if interactive and state.questions_left > 0:
                await self._reflect(state, bus, outcome)

            if state.dry_rounds >= state.budget.dry_rounds_to_stop:
                state.termination_reason = "two_dry_rounds"
                return
            state.round_no += 1

    # -- HITL ------------------------------------------------------------------

    async def _reflect(self, state: DiscoveryState, bus: SessionEventBus, outcome: RoundOutcome) -> None:
        """Ask at most one question, then apply whatever the user told us.

        Question generation is best-effort: a bug in a generator must cost us the
        question, not the search. Found the hard way — a mismatched attribute name
        raised out of `maybe_ask` and killed an eight-minute run outright.
        """
        try:
            question = maybe_ask(_QuestionState(state))
        except Exception as exc:
            logger.log_warning(f"Question generation failed (continuing without asking): {type(exc).__name__}: {exc}")
            return
        if question is None:
            return
        state.questions_asked.add(question.semantic_hash)
        state.questions_used += 1

        # The wait has no deadline, so it is held outside the wall-clock budget:
        # otherwise a user who took ten minutes to read the question would come
        # back to a search that had spent its remaining budget standing still.
        # `finally`, because a cancelled session must not leave the clock paused.
        asked_at = time.monotonic()
        try:
            answer = await self._broker.ask(
                state.session_id, question, bus=bus, store=self._store, target_key=state.target_key
            )
        finally:
            state.paused_s += time.monotonic() - asked_at
        await self._apply_answer(state, bus, question, answer)

    async def _apply_answer(
        self,
        state: DiscoveryState,
        bus: SessionEventBus,
        question: Question,
        answer: Answer,
    ) -> None:
        """Turn an answer into evidence and steering.

        An unknown / skipped / timed-out answer yields no effects at all: it adds
        nothing and — critically — penalises nothing. Silence is not denial.
        """
        effects = apply_answer(question, answer)
        if not effects:
            return

        evidence: list[Evidence] = []
        touched: set[str] = set()
        """Candidates whose score the answer just invalidated. See `_rescore`."""
        for effect, value in effects:
            if effect == "confirm_candidate":
                candidate = state.candidates.get(value)
                if candidate is not None:
                    candidate.user_confirmed = True
                    # An exclusion recorded in an earlier round outlives the
                    # screen that wrote it, because `_score` re-applies it every
                    # round. The gender screen already refuses to read an account
                    # the user vouched for; this is the same rule applied
                    # backwards in time, and it is what stops a picture the vision
                    # model misread from surviving the user's own answer.
                    candidate.excluded_by = ""
                    # The platform is settled now, exactly as if the account had
                    # been given in the brief: every remaining permutation probed
                    # against it can only turn up somebody else. `setdefault`
                    # because a pin that came from the brief is the stronger claim.
                    state.pinned_platforms.setdefault(candidate.platform, candidate.username)
                    state.usernames_tried.add((candidate.platform, candidate.username))
                    # Said out loud in the same shape `seed_state` uses for a
                    # brief pin: the user just changed what the search will do,
                    # and a steering decision they cannot see is one they cannot
                    # correct.
                    logger.log_detail(
                        f"[BRIEF] {candidate.key} confirmed by you - {candidate.platform} will not be searched"
                    )
                    touched.update(self._settle_platform(state, candidate))
                    touched.add(value)
                    evidence.append(self._answer_evidence(state, EvidenceKind.PROFILE, value, candidate.url))
                    await self._reanchor(state, bus, candidate.username, candidate.platform, "user_answer")
            elif effect == "reject_candidate":
                candidate = state.candidates.get(value)
                if candidate is not None:
                    candidate.user_rejected = True
                    touched.add(value)
            elif effect == "set_anchor_cluster":
                await self._switch_cluster(state, bus, value)
            elif effect == "add_fact":
                key, _, raw = value.partition("=")
                kind = {"employer": EvidenceKind.EMPLOYER, "school": EvidenceKind.SCHOOL}.get(
                    key, EvidenceKind.LOCATION
                )
                setattr(state.anchor, key if key in ("employer", "school") else "employer", raw)
                evidence.append(self._answer_evidence(state, kind, key, raw))
            elif effect == "select_avatar":
                # The option id is the chosen picture's sha256. Every account
                # carrying that exact image is one the user has just pointed at,
                # so confirm those rather than punishing the rest: one person
                # legitimately uses different pictures on different platforms.
                chosen = [c for c in state.candidates.values() if c.avatar_sha256 == value]
                for candidate in chosen:
                    candidate.user_confirmed = True
                    touched.add(candidate.key)
                # Settled after the whole loop, never inside it: two accounts on
                # one platform can share the picture, and settling the platform
                # while only the first had been marked would rule out the second
                # on the strength of the answer that confirmed it.
                for candidate in chosen:
                    state.pinned_platforms.setdefault(candidate.platform, candidate.username)
                    touched.update(self._settle_platform(state, candidate))
                evidence.append(self._answer_evidence(state, EvidenceKind.AVATAR, "avatar", value))
            elif effect == "focus_platform":
                # The user picked a platform worth another attempt. A pair is
                # probed once per session, so without clearing it the answer
                # changed nothing at all.
                for pair in [p for p in state.usernames_tried if p[0] == value]:
                    state.usernames_tried.discard(pair)
                evidence.append(self._answer_evidence(state, EvidenceKind.ANSWER, "focus_platform", value))
            elif effect == "reject_fact":
                self._retract_fact(state, value)
            elif effect == "hint":
                evidence.append(self._answer_evidence(state, EvidenceKind.ANSWER, "hint", value))

        fresh = state.record_evidence(evidence)
        if fresh:
            await self._store.add_many(state.target_key, state.session_id, fresh)
        await self._rescore(state, bus, touched)
        state.dry_rounds = 0  # the user just gave us something new to chase

    @staticmethod
    def _settle_platform(state: DiscoveryState, confirmed: ProfileCandidate) -> set[str]:
        """Rule out the handles already collected on a platform the user just settled.

        The pin `confirm_candidate` sets stops *new* handles arriving; these were
        already here when the question was asked. `is_pinned_stranger` states the
        rule they now fail: the pin means "this platform's account is the one I
        pointed at", so any other handle on it is a different person.

        Excluded rather than deleted, and excluded rather than marked
        `user_rejected`. The user said yes to one account; they did not say no to
        sixteen others, and recording words they never said would be a lie in the
        audit trail. `excluded_by` is the existing shape for "contradicts
        something you told us": the band drops to `rejected` so the account
        leaves the identity, while the account and its reason stay visible —
        a wrong exclusion nobody can see is one nobody can correct.

        A second *confirmed* account on the same platform is left alone: one
        person can legitimately hold two, and only the user may say so.
        """
        touched: set[str] = set()
        for sibling in state.candidates.values():
            if sibling.platform != confirmed.platform or sibling.key == confirmed.key:
                continue
            if sibling.user_confirmed or sibling.excluded_by:
                continue
            sibling.excluded_by = "platform_settled"
            touched.add(sibling.key)
        if touched:
            logger.log_detail(
                f"[BRIEF] {confirmed.platform} settled on {confirmed.username} - "
                f"{len(touched)} other handle(s) on it are somebody else"
            )
        return touched

    async def _rescore(self, state: DiscoveryState, bus: SessionEventBus, keys: Collection[str]) -> None:
        """Re-score the candidates an answer changed, and say so on the wire.

        Without this the answer changed a flag and nothing else until the *next*
        round's `_score`, and a round is minutes away — if one runs at all. Watched
        live: the user was asked about a TikTok account, answered yes, and the card
        went on reading "REJECTED · 0" because that score had been computed before
        the question was even asked. The one account they had personally vouched
        for was the worst-rated thing on screen.

        Same pure `score_profile` the round uses and `brief.apply.seed_state` calls
        for exactly the same reason, so the number cannot jump when the next round
        finishes. The two post-adjusters stay in `round._score`: both need the
        whole evidence set, and neither can change a user-asserted verdict.
        """
        for key in sorted(keys):
            candidate = state.candidates.get(key)
            if candidate is None:
                continue
            score = score_profile(candidate, state.anchor, state.evidence, state.context)
            # `score_profile` is pure and cannot see an exclusion, so re-applying
            # it here is what stops the answer *raising* a sibling it just ruled
            # out — the same reason `round._score` re-applies it every round.
            if candidate.excluded_by:
                score = demote_on_brief_conflict(score, code=candidate.excluded_by, other=exclusion_subject(candidate))
            candidate.score = score
            await bus.publish(EventType.candidate_updated, candidate_payload(candidate))

    @staticmethod
    def _retract_fact(state: DiscoveryState, value: str) -> None:
        """Drop a fact the user said is wrong. ``value`` is ``"<kind>=<text>"``.

        Stored evidence is append-only and stays as the record of what was seen,
        but a rejected employer or school must stop driving the answer: it is
        removed from the structured records the biography and the anchor read,
        so it can no longer be restated as fact.
        """
        kind, _, text = value.partition("=")
        text = text.strip()
        if not text:
            return
        folded = text.casefold()
        if kind == "school":
            state.education = [e for e in state.education if e.institution.casefold() != folded]
        else:
            state.work = [w for w in state.work if w.organization.casefold() != folded]
        if getattr(state.anchor, kind, None) and str(getattr(state.anchor, kind)).casefold() == folded:
            setattr(state.anchor, kind, None)

    def _answer_evidence(self, state: DiscoveryState, kind: EvidenceKind, subject: str, value: str) -> Evidence:
        return make_evidence(
            kind,
            subject,
            value,
            source_url=f"user-answer://{state.session_id}",
            source_kind=SourceKind.USER_ANSWER,
            extractor="user_answer",
            confidence=1.0,
            round_no=state.round_no,
        )

    # -- identity management ---------------------------------------------------

    def _recluster(self, state: DiscoveryState) -> None:
        state.clusters = build_clusters(list(state.candidates.values()), state.anchor, state.evidence, state.context)
        state.elected, state.alternates = elect(state.clusters)

    async def _maybe_reanchor_from_scores(self, state: DiscoveryState, bus: SessionEventBus) -> None:
        """Promote the strongest confirmed handle to be the anchor.

        This is the point of iterative deepening: round 1's weak name-only anchor
        becomes round 3's confirmed handle, which then re-scores everything.
        """
        if state.anchor.is_confident or state.elected is None:
            return
        top = state.elected.top_member()
        if top is None or top.score.band is not MatchBand.CONFIRMED:
            return
        await self._reanchor(state, bus, top.username, top.platform, "strongest_confirmed_profile")

    async def _reanchor(
        self,
        state: DiscoveryState,
        bus: SessionEventBus,
        handle: str,
        platform: str,
        reason: str,
    ) -> None:
        previous = state.anchor.handle
        if previous.lower() == handle.lower():
            return
        state.anchor = strengthen(state.anchor, handle=handle, platform=platform, reason=reason)
        state.reanchor_count += 1
        await bus.publish(
            EventType.anchor_changed,
            anchor_changed_payload(from_handle=previous, to_handle=handle, reason=reason, round=state.round_no),
        )
        if state.draft_narrative:
            state.draft_narrative = None
            await bus.publish(
                EventType.result_invalidated,
                result_invalidated_payload(reason="anchor_changed", discarded=["draft_narrative"]),
            )
        state.dry_rounds = 0
        self._recluster(state)

    async def _switch_cluster(self, state: DiscoveryState, bus: SessionEventBus, cluster_id: str) -> None:
        """The user chose a different identity — go back and correct course."""
        chosen = next((c for c in state.clusters if c.cluster_id == cluster_id), None)
        if chosen is None:
            return
        previous = state.elected

        for cluster in state.clusters:
            if cluster.cluster_id == cluster_id:
                continue
            for member in cluster.members:
                member.user_rejected = True
        if previous is not None and previous.cluster_id != cluster_id:
            fingerprints = [ev.fingerprint for ev in previous.evidence]
            await self._store.supersede(fingerprints)

        state.elected = chosen
        state.alternates = [c for c in state.clusters if c.cluster_id != cluster_id]
        state.draft_narrative = None
        await bus.publish(
            EventType.result_invalidated,
            result_invalidated_payload(
                reason="user_selected_different_identity",
                discarded=["draft_narrative", "primary_picture", "work_history"],
            ),
        )
        top = chosen.top_member()
        if top is not None:
            await self._reanchor(state, bus, top.username, top.platform, "user_disambiguation")
        state.dry_rounds = 0

    @staticmethod
    def _narrative_budget(state: DiscoveryState) -> float:
        """Seconds the write-up may spend: what the search left, clamped both ways."""
        return min(NARRATIVE_MAX_BUDGET_S, max(NARRATIVE_MIN_BUDGET_S, state.time_left_s))

    async def _finalize_narrative(
        self,
        state: DiscoveryState,
        result: DiscoveryResult,
        bus: SessionEventBus,
        *,
        started: float,
    ) -> None:
        """Write the grounded biography, graph and timeline for the elected identity."""
        await bus.publish(
            EventType.progress,
            progress_payload(
                phase="finalize", round=state.round_no, label="assembling the profile", completed=0, total=0
            ),
        )
        if state.elected is None:
            result.narrative = None
            result.duration_ms = int((time.monotonic() - started) * 1000)
            return
        budget = self._narrative_budget(state)
        # Owned here, not inside the builder, because it has to survive the
        # builder being cancelled: without it a timeout would store `None` while
        # the client had already rendered five sentences, and the wire and the
        # stored result would disagree about what the search said.
        streamed: list[Claim] = []

        async def publish(claim: Claim, source: str) -> None:
            await bus.publish(
                EventType.narrative_delta,
                narrative_delta_payload(index=len(streamed), claim=claim, source=source),
            )
            streamed.append(claim)

        try:
            builder = NarrativeBuilder()
            # Only the model call is bounded. The graph and timeline below are
            # pure CPU over evidence already in hand, so they stay outside the
            # timeout and cannot be lost to a stalled daemon.
            result.narrative = await asyncio.wait_for(
                builder.stream(
                    cluster=state.elected,
                    profiles=[p for p in result.profiles if p.is_live],
                    work=result.work,
                    education=result.education,
                    subject_name=state.terms.name,
                    entity_type=str(state.entity),
                    budget_s=budget * NARRATIVE_STREAM_MARGIN,
                    on_claim=publish,
                ),
                timeout=budget,
            )
        except TimeoutError:
            logger.log_warning(f"Narrative assembly exceeded its {budget:.0f}s budget and was abandoned")
            result.narrative = _partial_narrative(streamed)
        except Exception as exc:  # a failed biography must not lose the findings
            logger.log_warning(f"Narrative assembly failed: {type(exc).__name__}: {exc}")
            result.narrative = _partial_narrative(streamed)
        result.notices.extend(narrative_notices(result.narrative))
        try:
            result.graph = build_graph(state.elected, result.evidence)
            result.timeline = build_timeline(
                [p for p in result.profiles if p.is_live], result.work, result.education, result.evidence
            )
        except Exception as exc:
            logger.log_warning(f"Analysis assembly failed: {type(exc).__name__}: {exc}")
        # `_build_result` stamps the duration before any of this runs, so the
        # number the user is shown used to stop short of the most expensive step.
        result.duration_ms = int((time.monotonic() - started) * 1000)

    # -- assembly --------------------------------------------------------------

    def _build_result(
        self,
        state: DiscoveryState,
        engines: EngineRegistry,
        fetch: FetchSession,
        started: float,
    ) -> DiscoveryResult:
        max_per_platform = self._settings.discovery_max_profiles_per_platform
        profiles: list[ProfileCandidate] = []
        if state.elected is not None:
            profiles = limit_per_platform(state.elected, max_per_platform=max_per_platform)

        # Every platform still reports an outcome, so the response can never imply
        # that a platform was simply not looked at. But the report is per PLATFORM,
        # not per guessed handle: a search tries dozens of name permutations, and
        # emitting one "blocked" row per guess produced 59 rows for a single search
        # — noise that buries the handful of real accounts it is meant to caveat.
        # One representative row per platform, carrying the most informative status.
        #
        # LIVE accounts are part of that, and used to be skipped here. The skip
        # assumed a live account is always in the elected cluster, which is false
        # for exactly the candidates that cannot be corroborated: a discovery-only
        # platform is never fetched or probed, so its candidate has no avatar, no
        # outbound link and no display name, nothing `_agreement_edges` can tie to
        # the elected identity. It clustered alone, lost the election, and then
        # fell through both branches — which is how a search holding
        # `open.spotify.com/user/<id>` reported no Spotify account at all, three
        # times over. The row is a status, not an attribution: everything reaching
        # this loop is on a platform the elected identity has no account on, so a
        # live one is held out of the confirmed band by `hold_back_unattributed`.
        reported_platforms = {c.platform for c in profiles}
        representative: dict[str, ProfileCandidate] = {}
        for candidate in state.candidates.values():
            if candidate.platform in reported_platforms:
                continue
            current = representative.get(candidate.platform)
            if current is None or _representative_rank(candidate) > _representative_rank(current):
                representative[candidate.platform] = candidate
        profiles.extend(_as_unattributed(representative[platform]) for platform in sorted(representative))

        evidence = state.elected.evidence if state.elected else list(state.evidence)
        subject = score_subject(state.anchor, evidence, profiles)

        notices = self._notices(state, fetch)
        return DiscoveryResult(
            session_id=state.session_id,
            target_key=state.target_key,
            entity_type=state.entity,
            profiles=profiles,
            alternates=state.alternates,
            evidence=evidence,
            web_sources=state.web_sources,
            work=dedupe_work(state.work),
            education=dedupe_education(state.education),
            platform_status=dict(state.platform_status),
            engine_status=engines.health(),
            anchor=state.anchor,
            elected=state.elected,
            subject_confidence=subject,
            rounds=state.rounds_completed,
            termination_reason=state.termination_reason or "completed",
            duration_ms=int((time.monotonic() - started) * 1000),
            resumed_evidence=state.resumed_evidence,
            fetch_stats=fetch.stats.as_dict(),
            notices=notices,
        )

    def _notices(self, state: DiscoveryState, fetch: FetchSession) -> list[str]:
        """Caveats the user deserves to see rather than a silently thinner answer."""
        notices: list[str] = []
        blocked = sorted(p for p, s in state.platform_status.items() if s is PlatformStatus.BLOCKED)
        if blocked:
            notices.append(
                f"{len(blocked)} platform(s) refused automated access ({', '.join(blocked[:6])}); "
                "absence there is not evidence of absence."
            )
        if not fetch.stealth_available and fetch.stealth_unavailable_reason:
            notices.append(fetch.stealth_unavailable_reason)
        if state.resumed_evidence:
            notices.append(f"{state.resumed_evidence} evidence item(s) reused from an earlier search of this name.")
        # `elect` always returns a winner, so a run that established nothing still
        # ends holding a cluster. Saying so is the difference between an honest
        # empty answer and a confident wrong one: on 2026-08-29 a refused run
        # elected the bare surname `erdogan` across twelve platforms, every member
        # scored out, and presented it as the person.
        if state.elected is not None and not [
            m for m in state.elected.live_members if m.score.band in ATTRIBUTABLE_BANDS
        ]:
            notices.append(
                "No account scored high enough to be attributed to this person; "
                "the accounts below exist but were not tied to the target."
            )
        return notices

    def _new_state(
        self,
        session_id: str,
        target_key: str,
        raw_query: str,
        entity: EntityType,
        depth: int,
        brief: SearchBrief,
    ) -> DiscoveryState:
        settings = self._settings
        budget = RoundBudget.for_depth(
            depth,
            wall_clock_s=float(settings.discovery_max_wall_clock_seconds),
            max_questions=settings.discovery_max_questions,
            max_extended=settings.discovery_max_extended_checks,
        )
        # `build_query_terms` and `build_anchor` have always accepted the hints
        # below and were always called without them, which left `Anchor.handle`
        # empty on every search ever run and made eight scoring signals dead.
        # `brief/apply.py` is the producer they were missing.
        return DiscoveryState(
            session_id=session_id,
            target_key=target_key,
            entity=entity,
            terms=build_terms(brief, raw_query),
            anchor=build_brief_anchor(brief, raw_query),
            budget=budget,
            depth=depth,
            brief=brief,
        )


@dataclass(frozen=True, slots=True)
class _PictureView:
    """A candidate's avatar in the shape the question generators read."""

    sha256: str
    dhash: str
    local_url: str
    platform: str
    username: str
    url: str
    """The public profile, so the question can offer a link to go and look."""

    settled: bool
    """The user has already ruled on this account, so it is not in question.

    Without it they were asked to choose between an Instagram account they had
    given in the brief and a LinkedIn one they had just confirmed — two accounts
    they had already told us were the target, offered as if only one could be."""

    def __init__(self, candidate: ProfileCandidate) -> None:
        object.__setattr__(self, "sha256", candidate.avatar_sha256 or "")
        object.__setattr__(self, "dhash", candidate.avatar_dhash or "")
        object.__setattr__(self, "local_url", candidate.avatar_local_url or "")
        object.__setattr__(self, "url", candidate.url or "")
        object.__setattr__(self, "settled", candidate.user_confirmed or candidate.user_rejected)
        object.__setattr__(self, "platform", candidate.platform)
        object.__setattr__(self, "username", candidate.username)


class _QuestionState:
    """Adapter exposing exactly the attributes the question generators read."""

    def __init__(self, state: DiscoveryState) -> None:
        self.clusters = state.clusters
        self.candidates = list(state.candidates.values())
        self.anchor = state.anchor
        self.round_no = state.round_no
        self.questions_asked = state.questions_asked
        self.budget_questions_left = state.questions_left
        self.evidence = state.evidence
        # The generators expect picture-shaped records (.sha256/.dhash/.local_url),
        # not candidates (.avatar_sha256/...). Adapting here rather than teaching
        # the generators about candidates keeps them testable against plain data.
        self.pictures = [_PictureView(c) for c in state.candidates.values() if c.avatar_sha256 and c.is_live]
        self.elected = state.elected
        self.platform_status = state.platform_status
        # Read by `_confirm_profile`, which must not ask about a platform whose
        # account the user has already given or confirmed.
        self.pinned_platforms = state.pinned_platforms


def _iso_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def narrative_notices(narrative: Narrative | None) -> list[str]:
    """Say out loud when the biography is weaker than it looks.

    `used_llm`, `acceptance_rate` and the rejected-claim ledger were computed on
    every run and never left the process, so a biography assembled from nothing
    but structured records read exactly like one the model wrote and the evidence
    upheld. A reader cannot judge a claim they were not told was degraded.
    """
    if narrative is None:
        return ["The biography could not be assembled; the findings below are unaffected."]
    notices: list[str] = []
    if narrative.text == NOTHING_ESTABLISHED:
        notices.append("No claim could be tied to stored evidence, so no biography was written.")
    elif not narrative.used_llm:
        notices.append("The biography states only the structured records found; it was not written from prose.")
    if narrative.truncated:
        notices.append("The biography was cut short by its time budget; only the sentences already verified are shown.")
    dropped = len(narrative.grounding.rejected)
    if dropped:
        notices.append(f"{dropped} proposed sentence(s) were dropped for naming something the evidence never said.")
    return notices


def _partial_narrative(claims: Sequence[Claim]) -> Narrative | None:
    """The sentences that were both written and grounded before time ran out.

    Keeping them is not a softening of "an abandoned biography is reported as
    absent, not half-written". That rule was written when the output was one blob
    of prose, where half meant a sentence cut mid-word. Streaming makes each claim
    atomic and independently grounded, so the accepted prefix is a shorter true
    biography — and `narrative_notices` says it was cut. With nothing accepted the
    old behaviour is unchanged: `None`.
    """
    if not claims:
        return None
    return Narrative(
        text=" ".join(claim.text for claim in claims),
        claims=tuple(claims),
        grounding=GroundingReport(accepted=tuple(claims), rejected=()),
        used_llm=True,
        truncated=True,
    )


def _serialisable_result(result: DiscoveryResult) -> dict[str, Any]:
    """The finished search as plain JSON, matching the blocking route's fields.

    Imported locally: `discovery_bridge` imports `DiscoveryResult` from this
    module, so a top-level import would be circular.
    """
    from app.services.discovery_bridge import to_api

    try:
        payload = to_api(result)
    except Exception as exc:  # a serialisation failure must not lose the search
        logger.log_warning(f"Could not serialise discovery result: {type(exc).__name__}: {exc}")
        return {}

    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, list):
            out[key] = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
        elif hasattr(value, "model_dump"):
            out[key] = value.model_dump(mode="json")
        else:
            out[key] = value

    out["name"] = result.target_key.split(":", 1)[0].replace("-", " ").title()
    # `to_api` supplies the biography and its claims for both routes. It leaves
    # `ai_response` absent when there is no narrative at all; the session payload
    # needs the field regardless, because the frontend schema requires a string.
    out.setdefault("ai_response", "No verified information could be established for this target.")
    if result.graph is not None:
        out["relationship_graph"] = result.graph.as_dict()
    out["discovery_timeline"] = [
        {
            "when": event.when,
            "kind": event.kind,
            "label": event.label,
            "source_url": event.source_url,
            "confidence": event.confidence,
            "platform": event.platform,
        }
        for event in result.timeline
    ]
    return out


# Above every failure rank below, so a live account always speaks for its platform.
_LIVE_RANK = 4


def _representative_rank(candidate: ProfileCandidate) -> tuple[int, int]:
    """Which candidate speaks for a platform the elected identity has no row on.

    A live account outranks every failure. Reporting `not_found` from a guessed
    permutation while the search actually reached a real page conflates "we
    looked and there is no account" with "there is one, it is just not this
    person's" — the conflation invariant 1 exists to forbid. Among live accounts
    the best-scoring one speaks for the platform, so the row a reader sees is the
    closest thing to the target that was actually reached.
    """
    if candidate.is_live:
        return (_LIVE_RANK, candidate.score.value)
    return (_failure_rank(candidate), 0)


def _as_unattributed(candidate: ProfileCandidate) -> ProfileCandidate:
    """The platform's representative row, which is never this identity's account.

    A copy, not a mutation: `state.candidates` keeps the score the evidence
    earned, and only the row leaving in the answer is held back.
    """
    if not candidate.is_live:
        return candidate
    held = hold_back_unattributed(candidate.score)
    return candidate if held is candidate.score else replace(candidate, score=held)


def _failure_rank(candidate: ProfileCandidate) -> int:
    """Which failure is worth reporting for a platform.

    "Blocked" outranks "not found": being refused is a caveat the user must weigh,
    whereas a guessed handle not existing is expected and says nothing. An error
    outranks both because it points at something we should fix.
    """
    return {
        PlatformStatus.ERROR: 3,
        PlatformStatus.BLOCKED: 2,
        PlatformStatus.UNSUPPORTED: 1,
        PlatformStatus.NOT_FOUND: 0,
    }.get(candidate.platform_status, 0)


__all__ = ["DiscoveryResult", "DiscoveryRunner", "target_key_for"]

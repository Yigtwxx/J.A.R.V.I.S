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

import time
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.discovery.analysis.graph import RelationshipGraph, build_graph
from app.discovery.analysis.timeline import TimelineEvent, build_timeline
from app.discovery.engines.queries import build_query_terms
from app.discovery.engines.registry import EngineRegistry
from app.discovery.evidence.model import Evidence, make_evidence
from app.discovery.evidence.store import EvidenceStore
from app.discovery.fetch.cookies import CookieVault
from app.discovery.fetch.profiles import BrowserProfilePool
from app.discovery.fetch.ratelimit import DomainRateLimiter
from app.discovery.fetch.session import FetchSession, build_proxy_selector
from app.discovery.hitl.broker import QuestionBroker
from app.discovery.hitl.questions import Answer, Question, apply_answer, maybe_ask
from app.discovery.identity.anchor import Anchor, build_anchor, strengthen
from app.discovery.identity.normalize import fold_ascii
from app.discovery.identity.workedu import dedupe_education, dedupe_work
from app.discovery.loop.round import DiscoveryRound, RoundOutcome
from app.discovery.loop.state import DiscoveryState, RoundBudget
from app.discovery.matching.candidate import MatchScore, ProfileCandidate
from app.discovery.matching.cluster import IdentityCluster, build_clusters, elect, limit_per_platform
from app.discovery.matching.scoring import score_subject
from app.discovery.media.store import AvatarStore
from app.discovery.narrative.builder import Narrative, NarrativeBuilder
from app.discovery.platforms.registry import get_registry, registry_for_selection
from app.discovery.session.bus import SessionEventBus
from app.discovery.session.events import (
    EventType,
    anchor_changed_payload,
    done_payload,
    error_payload,
    hello_payload,
    progress_payload,
    result_invalidated_payload,
    round_finished_payload,
    round_started_payload,
)
from app.discovery.session.manager import SessionManager
from app.discovery.sources.archive import ArchiveRecovery
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


@dataclass(slots=True)
class DiscoveryResult:
    """The finished search: exactly one identity, plus everything that supports it."""

    session_id: str
    target_key: str
    entity_type: EntityType
    profiles: list[ProfileCandidate] = field(default_factory=list)
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
    ) -> None:
        self._store = store
        self._broker = broker
        self._manager = manager
        self._rate = rate_limiter
        self._settings = settings or get_settings()
        # Injected rather than imported: app.discovery.dependencies imports this
        # module, so reaching back into it here would close an import cycle.
        # Both are process-wide caches of what remote hosts told us, so a missing
        # one degrades to "no carry-over", never to a failure.
        self._cookies = cookies
        self._profiles = profiles

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
        bus: SessionEventBus | None = None,
    ) -> DiscoveryResult:
        settings = self._settings
        live = self._manager.get(session_id)
        event_bus = bus or (live.bus if live else SessionEventBus(session_id))
        target_key = target_key_for(raw_query, entity_type)
        started = time.monotonic()

        state = self._new_state(session_id, target_key, raw_query, entity_type, depth)
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
        engines = EngineRegistry(allow_stealth=settings.discovery_stealth_enabled)
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

            result = self._build_result(state, engines, fetch, started)
            # The biography is written LAST, once the identity is settled. Anything
            # drafted mid-search was provisional and was discarded on every
            # re-anchor, so a switch of identity can never leave stale prose behind.
            await self._finalize_narrative(state, result, event_bus)

        result.questions = await self._store.load_answers(target_key)
        await self._store.update_session(
            session_id,
            status="completed" if state.termination_reason != "error" else "failed",
            rounds_completed=state.round_no,
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
                rounds=state.round_no,
                duration_ms=result.duration_ms,
                summary={
                    "profiles": len(result.profiles),
                    "evidence": len(result.evidence),
                    "alternates": len(result.alternates),
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

        answer = await self._broker.ask(
            state.session_id, question, bus=bus, store=self._store, target_key=state.target_key
        )
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
        for effect, value in effects:
            if effect == "confirm_candidate":
                candidate = state.candidates.get(value)
                if candidate is not None:
                    candidate.user_confirmed = True
                    evidence.append(self._answer_evidence(state, EvidenceKind.PROFILE, value, candidate.url))
                    await self._reanchor(state, bus, candidate.username, candidate.platform, "user_answer")
            elif effect == "reject_candidate":
                candidate = state.candidates.get(value)
                if candidate is not None:
                    candidate.user_rejected = True
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
                for candidate in state.candidates.values():
                    if candidate.avatar_sha256 and candidate.avatar_sha256 != value:
                        candidate.avatar_sha256 = candidate.avatar_sha256
            elif effect == "hint":
                evidence.append(self._answer_evidence(state, EvidenceKind.ANSWER, "hint", value))

        fresh = state.record_evidence(evidence)
        if fresh:
            await self._store.add_many(state.target_key, state.session_id, fresh)
        state.dry_rounds = 0  # the user just gave us something new to chase

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

    async def _finalize_narrative(
        self,
        state: DiscoveryState,
        result: DiscoveryResult,
        bus: SessionEventBus,
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
            return
        try:
            builder = NarrativeBuilder()
            result.narrative = await builder.build(
                cluster=state.elected,
                profiles=[p for p in result.profiles if p.is_live],
                work=result.work,
                education=result.education,
                subject_name=state.terms.name,
                entity_type=str(state.entity),
            )
        except Exception as exc:  # a failed biography must not lose the findings
            logger.log_warning(f"Narrative assembly failed: {type(exc).__name__}: {exc}")
            result.narrative = None
        try:
            result.graph = build_graph(state.elected, result.evidence)
            result.timeline = build_timeline(
                [p for p in result.profiles if p.is_live], result.work, result.education, result.evidence
            )
        except Exception as exc:
            logger.log_warning(f"Analysis assembly failed: {type(exc).__name__}: {exc}")

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
        reported_platforms = {c.platform for c in profiles}
        best_failure: dict[str, ProfileCandidate] = {}
        for candidate in state.candidates.values():
            if candidate.is_live or candidate.platform in reported_platforms:
                continue
            current = best_failure.get(candidate.platform)
            if current is None or _failure_rank(candidate) > _failure_rank(current):
                best_failure[candidate.platform] = candidate
        profiles.extend(best_failure[platform] for platform in sorted(best_failure))

        evidence = state.elected.evidence if state.elected else list(state.evidence)
        subject = score_subject(state.anchor, evidence, profiles)

        notices = self._notices(state, fetch)
        return DiscoveryResult(
            session_id=state.session_id,
            target_key=state.target_key,
            entity_type=state.entity,
            profiles=profiles,
            alternates=_notable_alternates(state.alternates),
            evidence=evidence,
            web_sources=state.web_sources,
            work=dedupe_work(state.work),
            education=dedupe_education(state.education),
            platform_status=dict(state.platform_status),
            engine_status=engines.health(),
            anchor=state.anchor,
            elected=state.elected,
            subject_confidence=subject,
            rounds=state.round_no + 1,
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
        if _notable_alternates(state.alternates):
            notices.append(
                f"{len(_notable_alternates(state.alternates))} other identity/identities share this name; "
                "they are listed separately and are NOT part of this profile."
            )
        return notices

    def _new_state(
        self,
        session_id: str,
        target_key: str,
        raw_query: str,
        entity: EntityType,
        depth: int,
    ) -> DiscoveryState:
        settings = self._settings
        budget = RoundBudget.for_depth(
            depth,
            wall_clock_s=float(settings.discovery_max_wall_clock_seconds),
            max_questions=settings.discovery_max_questions,
            max_extended=settings.discovery_max_extended_checks,
        )
        terms = build_query_terms(raw_query, entity)
        return DiscoveryState(
            session_id=session_id,
            target_key=target_key,
            entity=entity,
            terms=terms,
            anchor=build_anchor(raw_query, entity),
            budget=budget,
            depth=depth,
        )


@dataclass(frozen=True, slots=True)
class _PictureView:
    """A candidate's avatar in the shape the question generators read."""

    sha256: str
    dhash: str
    local_url: str
    platform: str
    username: str

    def __init__(self, candidate: ProfileCandidate) -> None:
        object.__setattr__(self, "sha256", candidate.avatar_sha256 or "")
        object.__setattr__(self, "dhash", candidate.avatar_dhash or "")
        object.__setattr__(self, "local_url", candidate.avatar_local_url or "")
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


def _iso_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# An unverified singleton handle is not an "identity"; it is one unconfirmed hit.
# A live run of a common Turkish name produced 81 of them, which buries the two or
# three genuine namesakes the user actually needs to distinguish. A cluster earns a
# place in `alternate_identities` only if it holds together across more than one
# account or scores well enough to be worth a second look.
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

    narrative = result.narrative
    out["name"] = result.target_key.split(":", 1)[0].replace("-", " ").title()
    out["ai_response"] = (
        narrative.text if narrative else "No verified information could be established for this target."
    )
    out["narrative_claims"] = [
        {
            "text": claim.text,
            "evidence_fingerprints": list(claim.evidence_fingerprints),
            "source_urls": list(claim.source_urls),
            "confidence": claim.confidence,
        }
        for claim in (narrative.claims if narrative else ())
    ]
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


_ALTERNATE_MIN_MEMBERS = 2
_ALTERNATE_MIN_SCORE = 40
_ALTERNATE_LIMIT = 8


def _notable_alternates(clusters: list[IdentityCluster]) -> list[IdentityCluster]:
    """Namesakes worth showing, strongest first."""
    notable = [
        cluster
        for cluster in clusters
        if len(cluster.live_members) >= _ALTERNATE_MIN_MEMBERS or cluster.score.value >= _ALTERNATE_MIN_SCORE
    ]
    notable.sort(key=lambda c: (-c.score.value, -len(c.live_members), c.cluster_id))
    return notable[:_ALTERNATE_LIMIT]


__all__ = ["DiscoveryResult", "DiscoveryRunner", "target_key_for"]

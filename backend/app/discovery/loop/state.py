"""Mutable state and budgets for one iterative-deepening search.

The user asked for depth over speed — a search may legitimately run 15-20 minutes.
"Unlimited time" is not the same as "unkillable", so every way the loop can stop
is an explicit, named budget that ends up in ``termination_reason``. A search that
stops must always be able to say why.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.discovery.brief.model import EMPTY_BRIEF, SearchBrief
from app.discovery.engines.base import SearchHit
from app.discovery.engines.queries import QueryTerms
from app.discovery.evidence.model import Evidence
from app.discovery.identity.anchor import Anchor
from app.discovery.identity.usernames import UsernameCandidate
from app.discovery.identity.workedu import EducationRecord, WorkRecord
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.matching.cluster import IdentityCluster
from app.discovery.matching.scoring import ScoringContext
from app.discovery.types import EntityType, ExistenceVerdict, MatchBand, PlatformStatus

# A refusal and a transport error both mean "we did not get to look", so the pair
# is worth one more attempt later in the session. NOT_FOUND is deliberately absent:
# that is the one verdict we actually established, and re-probing it is pure waste.
_RETRYABLE_VERDICTS: frozenset[ExistenceVerdict] = frozenset({ExistenceVerdict.BLOCKED, ExistenceVerdict.ERROR})


@dataclass(slots=True)
class RoundBudget:
    """Every limit that can end a search, each with a name for the summary."""

    max_rounds: int = 11
    max_queries: int = 200
    max_queries_per_round: int = 120
    """Ceiling on one round's queries, separate from the whole search's.

    Without it a single round could spend nearly the entire search budget:
    measured 2026-08-29 at depth 7, round 1 planned **619** queries against a
    `max_queries` of 760, and `_expand` fires every one of them at
    `engine_count` engines — about 2 500 requests from one residential IP in a
    single round.

    That does not merely risk a ban, it *destroys* the coverage it was trying to
    buy: the engines retire, and every later round runs with nothing left to
    search. Iterative deepening only works if each round leaves the engines
    willing to answer the next one."""
    max_fetches: int = 1000
    max_candidates: int = 400
    max_wall_clock_s: float = 1800.0
    max_questions: int = 6
    max_extended_checks: int = 120
    max_username_variations: int = 15
    dry_rounds_to_stop: int = 2

    @classmethod
    def for_depth(cls, depth: int, *, wall_clock_s: float, max_questions: int, max_extended: int) -> RoundBudget:
        """Scale the effort budget with the user's 1-10 depth setting."""
        depth = max(1, min(10, depth))
        return cls(
            max_rounds=6 + depth,
            # Round 0 alone plans ~14 entity dorks plus 3-4 per platform, so a
            # purely multiplicative budget starved the search at low depth: it
            # terminated with `max_queries` before round 1 could follow anything up.
            # The flat term covers the opening sweep; the multiplier funds the
            # follow-ups that iterative deepening actually depends on.
            max_queries=200 + 80 * depth,
            # Deliberately sublinear against `max_queries`: depth should buy more
            # *rounds* of narrowing, not one enormous opening salvo.
            max_queries_per_round=40 + 10 * depth,
            max_fetches=200 * depth,
            max_wall_clock_s=wall_clock_s,
            max_questions=max_questions,
            max_extended_checks=max_extended,
            max_username_variations=max(4, min(24, 2 + depth * 2)),
        )


@dataclass(slots=True)
class DiscoveryState:
    """Everything the loop knows, carried across rounds."""

    session_id: str
    target_key: str
    entity: EntityType
    terms: QueryTerms
    anchor: Anchor
    budget: RoundBudget
    depth: int = 5

    brief: SearchBrief = EMPTY_BRIEF
    """What the user already knew: gender, known accounts, a reference photo.

    Read all over the loop but never written after construction, so a phase
    cannot quietly widen a constraint the user set.
    """

    pinned_platforms: dict[str, str] = field(default_factory=dict)
    """``platform -> username`` the user gave. These platforms are never searched.

    Enumerating username permutations against a platform whose account we were
    handed cannot find that account — it can only find strangers who happen to
    hold a name-shaped handle there. The one page we do want is fetched once, by
    `_adopt_brief`.
    """

    round_no: int = 0
    rounds_completed: int = 0
    """Rounds that actually finished. Deliberately separate from ``round_no``,
    which is the *index* of the round being run and is incremented at the end of
    the loop body: the two exit paths straddle that increment, so reading
    ``round_no`` gave a number that was right on one path and wrong on the other."""

    dry_rounds: int = 0
    started_at: float = field(default_factory=time.monotonic)
    paused_s: float = 0.0
    """Seconds this run spent parked on a question, waiting for a human.

    Subtracted from :attr:`elapsed_s`, because the wall-clock budget exists to
    bound *our* work — fetches, models, rounds — and a user reading the question
    is not our work. Since the question lost its deadline that wait is unbounded,
    so counting it would let someone who took a coffee break come back to a
    search that had answered itself and quit.
    """

    termination_reason: str = ""

    # -- accumulated findings -------------------------------------------------
    evidence: list[Evidence] = field(default_factory=list)
    fingerprints: set[str] = field(default_factory=set)
    candidates: dict[str, ProfileCandidate] = field(default_factory=dict)
    bands: dict[str, MatchBand] = field(default_factory=dict)
    platform_status: dict[str, PlatformStatus] = field(default_factory=dict)
    web_sources: list[SearchHit] = field(default_factory=list)
    work: list[WorkRecord] = field(default_factory=list)
    education: list[EducationRecord] = field(default_factory=list)
    usernames: dict[str, UsernameCandidate] = field(default_factory=dict)
    context: ScoringContext = field(default_factory=ScoringContext)

    clusters: list[IdentityCluster] = field(default_factory=list)
    elected: IdentityCluster | None = None
    alternates: list[IdentityCluster] = field(default_factory=list)
    draft_narrative: str | None = None
    """Discarded whenever the identity changes — a biography written for the wrong
    person is worse than none, so it never survives a re-anchor."""

    # -- work already done (the duplicate-work guards) ------------------------
    queries_run: set[str] = field(default_factory=set)
    urls_seen: set[str] = field(default_factory=set)
    usernames_tried: set[tuple[str, str]] = field(default_factory=set)
    pair_verdicts: dict[tuple[str, str], ExistenceVerdict] = field(default_factory=dict)
    """Last existence verdict per ``(platform, username)``.

    ``usernames_tried`` records only *that* a pair was probed, which is why a
    platform that refused round 0 stayed dead for the whole session. The verdict
    is what decides whether trying again could learn anything.
    """

    pairs_retried: set[tuple[str, str]] = field(default_factory=set)
    """Pairs that have already spent their one retry. Caps a permanently walled
    platform at one extra probe per session instead of one per round."""

    questions_asked: set[str] = field(default_factory=set)
    reverse_searched: set[str] = field(default_factory=set)
    sites_crawled: set[str] = field(default_factory=set)
    github_commits_checked: bool = False
    """One unauthenticated GitHub API request per session, not per round."""
    archived_checked: set[str] = field(default_factory=set)
    browsed: set[str] = field(default_factory=set)
    """Targets a browser has already been spent on. A page that refused us in
    round 2 refuses us in round 4, and the second attempt costs the same
    inferences as the first."""

    browse_used: bool = False
    """The browse phase runs at most once per search. On an 8 GB card the vision
    model and the narrative model cannot both be resident, so browsing every
    round would make ollama evict and reload one of them every round."""

    # -- counters -------------------------------------------------------------
    queries_used: int = 0
    queries_used_this_round: int = 0
    extended_checks_used: int = 0
    questions_used: int = 0
    gender_checks_used: int = 0
    """Vision calls spent reading avatars. Each one costs 4-8 s and evicts the
    narrative model on an 8 GB card, so the screen runs against a hard cap."""

    resumed_evidence: int = 0
    new_evidence_this_round: int = 0
    new_candidates_this_round: int = 0
    reanchor_count: int = 0

    @property
    def elapsed_s(self) -> float:
        """Wall-clock spent working, with the human's thinking time taken out."""
        return time.monotonic() - self.started_at - self.paused_s

    @property
    def out_of_time(self) -> bool:
        """True once the wall-clock budget is spent.

        Checked *inside* a round as well as between them. The loop used to consult
        the budget only at the top, so a round that started with one second left
        still ran all six of its phases to completion — which is how an 1800 s
        budget produced live runs of 2165 s and 2075 s.
        """
        return self.elapsed_s >= self.budget.max_wall_clock_s

    @property
    def time_left_s(self) -> float:
        """Seconds still inside the wall-clock budget, never negative."""
        return max(0.0, self.budget.max_wall_clock_s - self.elapsed_s)

    @property
    def questions_left(self) -> int:
        return max(0, self.budget.max_questions - self.questions_used)

    def exhausted(self) -> str | None:
        """Name of the first budget that has run out, or None."""
        if self.round_no >= self.budget.max_rounds:
            return "max_rounds"
        if self.queries_used >= self.budget.max_queries:
            return "max_queries"
        if len(self.candidates) >= self.budget.max_candidates:
            return "max_candidates"
        if self.out_of_time:
            return "max_wall_clock"
        return None

    def record_evidence(self, items: list[Evidence]) -> list[Evidence]:
        """Store evidence, returning only what was genuinely new.

        Novelty is by fingerprint, which is keyed on the source *domain*: the same
        fact from a different page of the same site is not new, but the same fact
        from a different site is — that is corroboration, and it is what makes the
        loop converge instead of oscillating.
        """
        fresh: list[Evidence] = []
        for ev in items:
            if ev.fingerprint in self.fingerprints:
                continue
            self.fingerprints.add(ev.fingerprint)
            self.evidence.append(ev)
            fresh.append(ev)
        self.new_evidence_this_round += len(fresh)
        return fresh

    def upsert_candidate(self, candidate: ProfileCandidate) -> bool:
        """Add or refresh a candidate. Returns True when it is newly seen."""
        existing = self.candidates.get(candidate.key)
        if existing is None:
            self.candidates[candidate.key] = candidate
            self.new_candidates_this_round += 1
            return True
        # Keep the richer record: a later round may have fetched the profile body.
        if candidate.data is not None and existing.data is None:
            existing.data = candidate.data
        if candidate.verdict is not existing.verdict and candidate.is_live:
            existing.verdict = candidate.verdict
        existing.signals = candidate.signals or existing.signals
        existing.status_detail = candidate.status_detail or existing.status_detail
        existing.touch()
        return False

    def band_changed(self) -> bool:
        """True when any candidate moved between confidence bands this round."""
        changed = False
        for key, candidate in self.candidates.items():
            previous = self.bands.get(key)
            if previous != candidate.score.band:
                self.bands[key] = candidate.score.band
                if previous is not None:
                    changed = True
        return changed

    def note_platform(self, platform: str, status: PlatformStatus) -> bool:
        """Record a platform outcome. True when it improved on a previous failure."""
        previous = self.platform_status.get(platform)
        self.platform_status[platform] = status
        return previous in (PlatformStatus.BLOCKED, PlatformStatus.ERROR) and status in (
            PlatformStatus.FOUND,
            PlatformStatus.NOT_FOUND,
        )

    def is_pinned_stranger(self, platform: str, username: str) -> bool:
        """True for a handle on a platform whose account the user already gave us.

        The pin means "this platform's account is the one I handed you", so any
        *other* handle arriving on it is a different person by definition.

        This guards the way in. `seeds` has always honoured `pinned_platforms` on
        the way out, but a stranger's profile URL coming back from a search engine
        or a personal-site crawl became a candidate regardless — which is how a
        search that was handed an Instagram account still reported a second,
        unrelated Instagram account.
        """
        pinned = self.pinned_platforms.get(platform)
        return pinned is not None and pinned.lower() != username.lower()

    def record_pair_verdict(self, platform: str, username: str, verdict: ExistenceVerdict) -> None:
        """Remember how the last probe of this pair went."""
        self.pair_verdicts[(platform, username)] = verdict

    def take_retry_pairs(self, limit: int) -> list[tuple[str, str]]:
        """Up to ``limit`` pairs whose last verdict was BLOCKED or ERROR.

        Claiming a pair here spends its single retry, so a platform that is walled
        for good cannot consume the probe budget round after round. A zero or
        negative limit claims nothing — the retry is kept for a round that can
        afford it.
        """
        if limit <= 0:
            return []
        out: list[tuple[str, str]] = []
        for pair, verdict in sorted(self.pair_verdicts.items()):
            if verdict not in _RETRYABLE_VERDICTS or pair in self.pairs_retried:
                continue
            self.pairs_retried.add(pair)
            out.append(pair)
            if len(out) >= limit:
                break
        return out

    def reset_round_counters(self) -> None:
        self.new_evidence_this_round = 0
        self.new_candidates_this_round = 0
        self.queries_used_this_round = 0

    def query_allowance(self) -> int:
        """Queries still available, bounded by the round as well as the search."""
        search_left = self.budget.max_queries - self.queries_used
        round_left = self.budget.max_queries_per_round - self.queries_used_this_round
        return max(0, min(search_left, round_left))

    def mark_queries(self, queries: list[str]) -> list[str]:
        """Filter out queries already run and charge the rest to the budget."""
        allowance = self.query_allowance()
        fresh = [q for q in queries if q not in self.queries_run][:allowance]
        for query in fresh:
            self.queries_run.add(query)
        self.queries_used += len(fresh)
        self.queries_used_this_round += len(fresh)
        return fresh

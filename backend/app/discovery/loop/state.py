"""Mutable state and budgets for one iterative-deepening search.

The user asked for depth over speed — a search may legitimately run 15-20 minutes.
"Unlimited time" is not the same as "unkillable", so every way the loop can stop
is an explicit, named budget that ends up in ``termination_reason``. A search that
stops must always be able to say why.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.discovery.engines.base import SearchHit
from app.discovery.engines.queries import QueryTerms
from app.discovery.evidence.model import Evidence
from app.discovery.identity.anchor import Anchor
from app.discovery.identity.usernames import UsernameCandidate
from app.discovery.identity.workedu import EducationRecord, WorkRecord
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.matching.cluster import IdentityCluster
from app.discovery.matching.scoring import ScoringContext
from app.discovery.types import EntityType, MatchBand, PlatformStatus


@dataclass(slots=True)
class RoundBudget:
    """Every limit that can end a search, each with a name for the summary."""

    max_rounds: int = 11
    max_queries: int = 200
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

    round_no: int = 0
    dry_rounds: int = 0
    started_at: float = field(default_factory=time.monotonic)
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
    questions_asked: set[str] = field(default_factory=set)
    reverse_searched: set[str] = field(default_factory=set)
    sites_crawled: set[str] = field(default_factory=set)
    archived_checked: set[str] = field(default_factory=set)

    # -- counters -------------------------------------------------------------
    queries_used: int = 0
    extended_checks_used: int = 0
    questions_used: int = 0
    resumed_evidence: int = 0
    new_evidence_this_round: int = 0
    new_candidates_this_round: int = 0
    reanchor_count: int = 0

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at

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
        if self.elapsed_s >= self.budget.max_wall_clock_s:
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

    def reset_round_counters(self) -> None:
        self.new_evidence_this_round = 0
        self.new_candidates_this_round = 0

    def query_allowance(self) -> int:
        return max(0, self.budget.max_queries - self.queries_used)

    def mark_queries(self, queries: list[str]) -> list[str]:
        """Filter out queries already run and charge the rest to the budget."""
        allowance = self.query_allowance()
        fresh = [q for q in queries if q not in self.queries_run][:allowance]
        for query in fresh:
            self.queries_run.add(query)
        self.queries_used += len(fresh)
        return fresh

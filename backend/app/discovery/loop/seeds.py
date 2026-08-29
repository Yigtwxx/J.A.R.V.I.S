"""Query planning: what to ask the search engines in each round.

Round 0 casts the entity net plus platform dorks for the best username guesses.
Every later round derives its queries **only from evidence first seen in the
previous round**. That restriction is what stops the loop oscillating between the
same two query sets forever, and it is why "two rounds with nothing new" is a
meaningful stopping condition rather than an arbitrary one.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.discovery.engines.queries import entity_queries, evidence_queries, platform_queries
from app.discovery.evidence.model import Evidence
from app.discovery.identity import usernames as un
from app.discovery.loop.state import DiscoveryState
from app.discovery.platforms.registry import PlatformRegistry
from app.discovery.platforms.spec import PlatformSpec
from app.discovery.types import EntityType, EvidenceKind, PlatformTier

# Which part of a site holds profiles. Only Google understands `site:host/path`,
# so `platform_queries` turns this into a plain phrase for every other engine.
_PATH_HINTS: dict[str, str] = {
    "linkedin": "in",
    "reddit": "user",
    "steam": "id",
    "spotify": "user",
    "flickr": "people",
    "stackoverflow": "users",
}

# Evidence that is worth turning into new queries. A bio or a mention is too
# noisy; a username or an employer genuinely opens new ground.
_EXPANDABLE_KINDS: frozenset[EvidenceKind] = frozenset(
    {
        EvidenceKind.USERNAME,
        EvidenceKind.EMAIL,
        EvidenceKind.EMPLOYER,
        EvidenceKind.SCHOOL,
        EvidenceKind.LOCATION,
        EvidenceKind.DOMAIN,
        EvidenceKind.REAL_NAME,
        EvidenceKind.ANSWER,
    }
)


def seed_usernames(state: DiscoveryState) -> list[un.UsernameCandidate]:
    """Round-0 username candidates from the name, plus anything already known."""
    budget = state.budget.max_username_variations * 3
    if state.entity is EntityType.PERSON:
        candidates = un.from_full_name(state.terms.name, limit=budget)
    else:
        # Brands and places do not follow person-name shapes. Running the personal
        # permutations over "Trendyol" produced `trendyol99` and turned "Peak
        # Games" into `gamespeak` — handles nobody registered — while missing the
        # forms companies actually use (`…official`, `…app`, `…tr`, `we…`).
        candidates = un.from_company_name(state.terms.name, limit=budget)
    if state.terms.email:
        candidates.extend(un.from_email(state.terms.email))
    if state.terms.domain:
        candidates.extend(un.from_domain(state.terms.domain))
    for given in state.terms.usernames:
        candidates.append(un.UsernameCandidate(value=given, source=un.UsernameSource.GIVEN, generation=0, prior=1.0))
    if state.anchor.handle:
        candidates.append(
            un.UsernameCandidate(value=state.anchor.handle, source=un.UsernameSource.OBSERVED, generation=0, prior=0.95)
        )
    return un.merge(state.usernames, candidates)


def expand_usernames(state: DiscoveryState, confirmed: Sequence[str]) -> list[un.UsernameCandidate]:
    """Variants of handles we have actually confirmed somewhere.

    Only generation <= 3 is ever expanded further; without that cap the search
    drifts into variants of variants of variants and never converges.
    """
    grown: list[un.UsernameCandidate] = []
    for handle in confirmed:
        parent = state.usernames.get(handle)
        generation = (parent.generation if parent else 0) + 1
        if generation > 3:
            continue
        grown.extend(un.from_seed_username(handle, limit=12, generation=generation))
    return un.merge(state.usernames, grown) if grown else []


def round_zero_queries(state: DiscoveryState, registry: PlatformRegistry) -> list[str]:
    """The opening sweep: entity dorks plus platform dorks for the top handles."""
    queries: list[str] = entity_queries(state.terms, limit=14)
    top = un.top_n(state.usernames.values(), state.budget.max_username_variations)
    handles = [c.value for c in top]

    for spec in _platforms_for(state, registry, tier=PlatformTier.CORE):
        if not spec.host:
            continue
        queries.extend(
            platform_queries(
                state.terms,
                spec.host,
                usernames=handles[:6],
                limit=4,
                path_hint=_PATH_HINTS.get(spec.key),
            )
        )
    return state.mark_queries(queries)


def followup_queries(state: DiscoveryState, fresh: Sequence[Evidence]) -> list[str]:
    """Queries derived from evidence first seen in the previous round."""
    queries: list[str] = []
    for ev in fresh:
        if ev.kind not in _EXPANDABLE_KINDS:
            continue
        value = (ev.value or "").strip()
        if len(value) < 3:
            continue
        queries.extend(evidence_queries(state.terms, kind=str(ev.kind), value=value, limit=4))
    return state.mark_queries(queries)


def platform_probe_pairs(
    state: DiscoveryState,
    registry: PlatformRegistry,
    *,
    include_extended: bool,
) -> list[tuple[str, str]]:
    """`(platform, username)` pairs still worth an existence check this round."""
    top = un.top_n(state.usernames.values(), state.budget.max_username_variations)
    pairs: list[tuple[str, str]] = []

    tiers = [PlatformTier.CORE] + ([PlatformTier.EXTENDED] if include_extended else [])
    for tier in tiers:
        extended = tier is PlatformTier.EXTENDED
        for spec in _platforms_for(state, registry, tier=tier):
            for candidate in top:
                if extended and state.extended_checks_used >= state.budget.max_extended_checks:
                    return pairs
                normalized = un.normalize_for_platform(candidate.value, spec.key)
                if not normalized:
                    continue
                pair = (spec.key, normalized)
                if pair in state.usernames_tried:
                    continue
                state.usernames_tried.add(pair)
                pairs.append(pair)
                if extended:
                    state.extended_checks_used += 1
    return pairs


def extended_unlocked(state: DiscoveryState, *, min_depth: int) -> bool:
    """Should the ~120-site long tail run?

    Only once we have a real handle to check, or the user asked for real depth.
    Sweeping a hundred niche sites against a *guessed* name permutation produces
    far more false positives than findings.
    """
    if state.depth >= min_depth:
        return True
    return any(
        candidate.source in (un.UsernameSource.GIVEN, un.UsernameSource.OBSERVED, un.UsernameSource.ANSWER)
        for candidate in state.usernames.values()
    )


def _platforms_for(state: DiscoveryState, registry: PlatformRegistry, *, tier: PlatformTier) -> list[PlatformSpec]:
    return list(registry.select(entity=state.entity, tier=tier))

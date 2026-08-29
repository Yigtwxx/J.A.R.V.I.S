"""Wire a :class:`SearchBrief` into the machinery that was already waiting for it.

Almost nothing here is new behaviour. ``build_query_terms`` has always taken
``usernames``/``location``/``employer``/``school``/``email``/``domain``, ``Anchor``
has always carried a handle and a ``confirmed_by``, ``seeds.seed_usernames`` has
always read ``terms.usernames`` at ``prior=1.0``, and ``CONFIRMED_USER_ANSWER`` has
existed since the anchor did. Every one of those was called with its optional
arguments empty, so eight scoring signals worth +9 to +30 were unreachable at
round 0 and the loop restarted from the bare name on every search. This module is
the producer they never had.

The one genuinely new idea is **pinning**: a platform whose account the user has
already given is not searched. Enumerating username permutations against it
cannot find the account we were handed, so every hit it produces is a stranger.
"""

from __future__ import annotations

from app.discovery.brief.model import KnownProfile, SearchBrief
from app.discovery.engines.queries import QueryTerms, build_query_terms
from app.discovery.evidence.model import Evidence, make_evidence
from app.discovery.identity.anchor import CONFIRMED_USER_ANSWER, Anchor, build_anchor, strengthen
from app.discovery.identity.normalize import name_tokens, normalize_org
from app.discovery.matching.candidate import ProfileCandidate
from app.discovery.matching.scoring import ScoringContext, score_profile
from app.discovery.types import EvidenceKind, ExistenceVerdict, PlatformStatus, SourceKind

DISCOVERED_VIA_USER_SUPPLIED = "user_supplied"
"""``discovered_via`` for an account the user handed us at the start of the search.

Distinct from ``user_answer``, which means "confirmed mid-run when we asked". Both
earn the browser tier in ``round._stealth_allowed``; only this one is present
before round 0 has run.
"""

USER_SUPPLIED_SIGNAL = "user_supplied"
"""Recorded on the candidate so its ``EXISTS`` verdict never reads as ours.

Existence here is asserted by the user, not established by a probe. The pipeline's
first invariant is that a status always says how it was reached, and this is how
this one says it.
"""

_ASSERTED_DETAIL = "you gave this account at the start of the search"


def build_terms(brief: SearchBrief, raw_query: str) -> QueryTerms:
    """The query terms, with every hint slot finally populated.

    ``raw_query`` stays the source of ``QueryTerms.raw`` so de-duplication and the
    journal keep referring to what the user actually typed, while ``name`` is the
    parsed name — "Eylul Akduman", not "Eylul Akduman, kız, instagram.com/...".
    """
    return build_query_terms(
        brief.name or raw_query,
        brief.entity,
        usernames=brief.seed_usernames(),
        location=brief.location,
        employer=brief.employer,
        school=brief.school,
        email=brief.email,
        domain=brief.domain,
    )


def build_brief_anchor(brief: SearchBrief, raw_query: str) -> Anchor:
    """The anchor, carrying the user's own attributes from the first round.

    A handle from a known profile is confirmed by ``user_answer`` — the same
    reason an in-run confirmation uses — so ``Anchor.is_confident`` is true before
    any searching happens. That single fact is what makes ``exact_username_anchor``
    (+18) and ``username_variant_anchor`` (+9) reachable on every other platform,
    which is exactly the "use the Instagram handle to find the rest" behaviour.
    """
    anchor = build_anchor(brief.name or raw_query, brief.entity)
    anchor.location_tokens = name_tokens(brief.location or "")
    anchor.employer = normalize_org(brief.employer or "")
    anchor.school = normalize_org(brief.school or "")
    anchor.email = (brief.email or "").strip().lower()
    anchor.domain = (brief.domain or "").strip().lower()

    first = _anchor_profile(brief)
    if first is not None:
        anchor = strengthen(
            anchor,
            handle=first.username,
            platform=first.platform,
            reason=CONFIRMED_USER_ANSWER,
        )
    return anchor


def _anchor_profile(brief: SearchBrief) -> KnownProfile | None:
    """Which known profile supplies the anchor handle: the first one given.

    Deliberately not "the most authoritative platform". The user controls the
    order, and a rule they cannot see would silently prefer a handle they did not
    intend as the primary one.
    """
    return brief.known_profiles[0] if brief.known_profiles else None


def candidate_for(profile: KnownProfile) -> ProfileCandidate:
    """The pre-built candidate for an account the user gave us.

    ``user_confirmed`` is set, which is worth +35 and, in ``cluster._cluster_rank``,
    +50 to the cluster holding it — so the identity is elected around the account
    the user vouched for rather than around whatever the web happened to return.
    """
    return ProfileCandidate(
        platform=profile.platform,
        username=profile.username,
        url=profile.canonical_url,
        variant=profile.variant,
        # Asserted, not probed. `signals` and `status_detail` carry the provenance
        # so nothing downstream mistakes this for a verdict we established.
        verdict=ExistenceVerdict.EXISTS,
        signals=(USER_SUPPLIED_SIGNAL,),
        status_detail=_ASSERTED_DETAIL,
        discovered_via=DISCOVERED_VIA_USER_SUPPLIED,
        user_confirmed=True,
    )


def evidence_for(profile: KnownProfile) -> Evidence:
    """One PROFILE evidence item recording that the user named this account.

    ``USER_ANSWER`` at confidence 1.0: the user is the most authoritative source
    the pipeline has, and the biography's grounding check needs a stored item to
    tie the account to, or it would drop every sentence mentioning it.
    """
    return make_evidence(
        EvidenceKind.PROFILE,
        profile.key,
        profile.canonical_url,
        source_url=profile.canonical_url,
        source_kind=SourceKind.USER_ANSWER,
        extractor="search_brief",
        confidence=1.0,
        platform=profile.platform,
        round_no=0,
    )


def prime_context(brief: SearchBrief, context: ScoringContext) -> None:
    """Load the brief's constraints into the scoring context. Mutates in place."""
    context.brief_gender = brief.gender
    for profile in brief.known_profiles:
        context.confirmed_urls.add(profile.canonical_url)
    avatar = brief.reference_avatar
    if avatar is not None:
        context.reference_avatar_sha = avatar.sha256
        context.reference_avatar_dhash = avatar.dhash


def seed_state(state) -> list[ProfileCandidate]:  # noqa: ANN001 - DiscoveryState, imported lazily by the caller
    """Apply the brief to a fresh :class:`DiscoveryState`. Returns the new candidates.

    Called once, before round 0. Everything it does is idempotent, so a resumed
    session cannot double-count.
    """
    brief = state.brief
    prime_context(brief, state.context)
    created: list[ProfileCandidate] = []

    for profile in brief.known_profiles:
        state.pinned_platforms[profile.platform] = profile.username
        # Belt and braces alongside `pinned_platforms`: `platform_probe_pairs`
        # skips a pair it has already seen, so even a code path that ignored the
        # pin cannot re-probe this exact handle.
        state.usernames_tried.add((profile.platform, profile.username))

        candidate = candidate_for(profile)
        if state.upsert_candidate(candidate):
            created.append(candidate)
        # These candidates reach the UI before round 0 has scored anything, and
        # `ProfileCandidate.score` defaults to EMPTY_SCORE - value 0, band
        # `rejected`. Left alone it showed the one account the user vouched for
        # as "rejected at 0 confidence", and since `rejected` sits outside
        # ATTRIBUTABLE_BANDS it also kept that account out of the narrative and
        # the accounts list until the first round got round to re-scoring it.
        # Scored here with the same pure function the round uses, so there is
        # one scorer and the number cannot jump when round 0 finishes.
        stored = state.candidates[candidate.key]
        stored.score = score_profile(stored, state.anchor, state.evidence, state.context)
        state.note_platform(profile.platform, PlatformStatus.FOUND)

    return created

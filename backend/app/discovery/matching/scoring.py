"""Deterministic confidence scoring.

`score_profile` is a pure function of `(candidate, anchor, evidence, context)`:
zero I/O, zero randomness, zero clock reads. The same inputs always produce the
same number and the same ordered reasons, which is what makes it testable and
what makes the number safe to show a user.

Two rules that are easy to get wrong and are enforced here:

* **A timeout or an "I don't know" answer is not a rejection.** Only an explicit
  "no" applies `user_rejected`. Treating silence as denial would let an absent
  user destroy correct results.
* **Blocked is not absent.** `blocked_existence` reduces confidence a little
  because we could not verify, but it never zeroes a candidate. Absence of proof
  is not proof of absence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.discovery.evidence.model import Evidence
from app.discovery.identity.anchor import Anchor
from app.discovery.identity.normalize import (
    is_similar_handle,
    name_tokens,
    normalize_handle,
    normalize_org,
    token_overlap,
)
from app.discovery.matching.candidate import MatchScore, ProfileCandidate, ScoreReason
from app.discovery.matching.signals import cap_for, points_for, text_for
from app.discovery.platforms.urlmatch import is_generic_handle, match_profile_url
from app.discovery.types import EvidenceKind, ExistenceVerdict, MatchBand, PlatformTier, band_for


@dataclass(slots=True)
class ScoringContext:
    """Cross-candidate facts the scorer needs but cannot derive from one candidate."""

    handle_counts: dict[str, int] = field(default_factory=dict)
    """normalized handle -> how many platforms it was confirmed on."""

    serp_engines: dict[str, set[str]] = field(default_factory=dict)
    """candidate key -> engines that returned it for the target's name."""

    confirmed_urls: set[str] = field(default_factory=set)
    """Canonical URLs already believed to belong to the target."""

    confirmed_domains: set[str] = field(default_factory=set)
    reciprocal_pairs: set[tuple[str, str]] = field(default_factory=set)
    """Unordered pairs (stored sorted) of candidate keys that link to each other."""

    rel_me_pairs: set[tuple[str, str]] = field(default_factory=set)
    avatar_sha_index: dict[str, set[str]] = field(default_factory=dict)
    """sha256 -> candidate keys sharing that exact image."""

    avatar_dhash_index: dict[str, set[str]] = field(default_factory=dict)
    generic_images: set[str] = field(default_factory=set)
    """sha256 values judged to be stock/shared images."""

    reverse_image_hits: dict[str, set[str]] = field(default_factory=dict)
    """candidate key -> platforms the same picture was found on."""

    def pair(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if a <= b else (b, a)


def score_profile(
    candidate: ProfileCandidate,
    anchor: Anchor,
    evidence: Sequence[Evidence] = (),
    context: ScoringContext | None = None,
) -> MatchScore:
    """Score one candidate account against the anchor. Pure and deterministic."""
    ctx = context or ScoringContext()
    reasons: list[ScoreReason] = []
    seen_totals: dict[str, float] = {}

    def add(code: str, *, other: str = "", fingerprints: Sequence[str] = (), scale: float = 1.0) -> None:
        base = points_for(code) * scale
        if base == 0.0:
            return
        cap = cap_for(code)
        if cap is not None:
            spent = seen_totals.get(code, 0.0)
            remaining = cap - spent
            if remaining <= 0:
                return
            base = min(base, remaining) if base > 0 else max(base, -remaining)
            seen_totals[code] = spent + abs(base)
        reasons.append(
            ScoreReason(
                code=code, text=text_for(code, other), points=round(base, 1), evidence_fingerprints=tuple(fingerprints)
            )
        )

    key = candidate.key
    handle = normalize_handle(candidate.username)

    # -- explicit user verdicts dominate everything else ----------------------
    if candidate.user_confirmed:
        add("user_confirmed")
    if candidate.user_rejected:
        add("user_rejected")

    # -- link topology: the strongest keyless signals -------------------------
    for other_key in sorted(k for pair in ctx.reciprocal_pairs if key in pair for k in pair if k != key):
        add("reciprocal_link", other=other_key)
    for other_key in sorted(k for pair in ctx.rel_me_pairs if key in pair for k in pair if k != key):
        add("rel_me_verified", other=other_key)

    for link in sorted(candidate.outbound_links):
        matched = match_profile_url(link)
        target = matched.canonical_url if matched else link
        if target in ctx.confirmed_urls and (not matched or matched.key != key):
            add("outbound_link_match", other=target)
        elif anchor.domain and anchor.domain in link:
            add("personal_site_backlink", other=anchor.domain)

    # -- handle relationship to the anchor ------------------------------------
    anchor_handle = normalize_handle(anchor.handle)
    if anchor_handle:
        if handle == anchor_handle:
            add("exact_username_anchor", other=anchor.handle)
        elif is_similar_handle(handle, anchor_handle):
            add("username_variant_anchor", other=anchor.handle)

    recurrence = ctx.handle_counts.get(handle, 0)
    if recurrence > 1:
        for _ in range(recurrence - 1):
            add("cross_platform_handle_recurrence", other=f"{recurrence} platforms")

    if is_generic_handle(handle) or (len(handle) <= 3 and not handle.isdigit()):
        add("generic_handle")

    # -- name comparison ------------------------------------------------------
    display = candidate.display_name or ""
    if display and anchor.tokens:
        display_tokens = name_tokens(display)
        overlap = token_overlap(anchor.tokens, display_tokens)
        anchor_set, display_set = set(anchor.tokens), set(display_tokens)
        if display_tokens and anchor_set <= display_set:
            add("display_name_exact", other=display)
        elif anchor_set & display_set and (anchor_set - display_set) and (display_set - anchor_set):
            # Shares a surname but carries a different given name — the classic
            # namesake. Scored as a contradiction, not a partial match, because a
            # partial score here is what let "Yılmaz Erdoğan" ride along with
            # "Yiğit Erdoğan" all the way into the biography.
            add("name_conflict", other=display)
        elif overlap >= 0.5:
            add("display_name_partial", other=display)
        elif overlap == 0.0 and not _has_other_anchor_link(candidate, ctx, anchor):
            add("name_mismatch", other=display)

    bio = candidate.bio or ""
    if bio and anchor.tokens and set(anchor.tokens) <= set(name_tokens(bio)):
        add("bio_contains_name")

    # -- attribute agreement --------------------------------------------------
    if anchor.employer and candidate.employer:
        if normalize_org(candidate.employer) == normalize_org(anchor.employer):
            add("employer_match", other=anchor.employer)
        else:
            add("conflicting_employer", other=candidate.employer)
    if anchor.location_tokens and candidate.location:
        if token_overlap(anchor.location_tokens, name_tokens(candidate.location)) > 0:
            add("location_match", other=candidate.location)
        else:
            add("conflicting_location", other=candidate.location)
    if anchor.email and handle and handle == normalize_handle(anchor.email.split("@", 1)[0]):
        add("email_local_match")

    # -- imagery (file comparison, never face recognition) --------------------
    sha = candidate.avatar_sha256
    if sha:
        if sha in ctx.generic_images:
            add("generic_image")
        else:
            others = sorted(ctx.avatar_sha_index.get(sha, set()) - {key})
            for other_key in others:
                add("avatar_sha256_identical", other=other_key)
    if candidate.avatar_dhash and not (sha and sha in ctx.generic_images):
        near = sorted(ctx.avatar_dhash_index.get(candidate.avatar_dhash, set()) - {key})
        for other_key in near:
            if not sha or other_key not in ctx.avatar_sha_index.get(sha, set()):
                add("avatar_phash_near", other=other_key)
    for platform in sorted(ctx.reverse_image_hits.get(key, set())):
        add("reverse_image_hit", other=platform)

    # -- corroboration from search engines ------------------------------------
    for engine in sorted(ctx.serp_engines.get(key, set())):
        add("serp_corroboration", other=engine)

    # -- evidence-derived signals ---------------------------------------------
    _apply_evidence(candidate, anchor, evidence, add)

    # -- verification quality --------------------------------------------------
    if candidate.verdict is ExistenceVerdict.AMBIGUOUS:
        add("unverified_existence")
    elif candidate.verdict is ExistenceVerdict.BLOCKED:
        add("blocked_existence")
    if candidate.tier is PlatformTier.EXTENDED and not _has_independent_corroboration(reasons):
        add("extended_platform_uncorroborated")
    if candidate.data and candidate.data.verified:
        add("verified_badge")

    return finalize(reasons)


def require_independent_sources(score: MatchScore, *, source_domains: int, required: int) -> MatchScore:
    """Hold back a ``confirmed`` verdict that rests on too few independent sites.

    This is what depth's ``validation_passes`` means: how many *distinct source
    domains* must agree before a candidate is allowed into the top band. One site
    saying something twice is one source, not two.

    It is applied *after* :func:`score_profile` rather than inside it on purpose.
    The domain count is a property of the evidence set as a whole, not of the one
    candidate the scorer sees, so folding it in would make `score_profile` depend
    on state it does not receive. This function is itself pure: same inputs, same
    output, no I/O.

    Only the band moves — the numeric value is untouched, so the confidence shown
    to the user stays exactly what the evidence earned.
    """
    if required <= 1 or score.band is not MatchBand.CONFIRMED or source_domains >= required:
        return score
    reason = ScoreReason(
        code="insufficient_independent_sources",
        text=f"held at 'likely': {source_domains} independent source(s), {required} required at this depth",
        points=0.0,
    )
    return MatchScore(value=score.value, band=MatchBand.LIKELY, reasons=(*score.reasons, reason))


def finalize(reasons: Sequence[ScoreReason]) -> MatchScore:
    """Sum, clamp to 0-100, sort reasons, and pick the band."""
    total = sum(r.points for r in reasons)
    value = max(0, min(100, round(total)))
    ordered = tuple(sorted(reasons, key=lambda r: (-abs(r.points), r.code)))
    return MatchScore(value=value, band=band_for(value), reasons=ordered)


def score_subject(
    anchor: Anchor,
    evidence: Sequence[Evidence],
    candidates: Sequence[ProfileCandidate],
) -> MatchScore:
    """How confident are we in the *subject* — the identity as a whole?

    This is what the UI shows next to the biography. It is driven by breadth of
    independent corroboration, not by any single account.
    """
    reasons: list[ScoreReason] = []
    live = [c for c in candidates if c.is_live and not c.user_rejected]

    confirmed = [c for c in live if c.score.band is MatchBand.CONFIRMED]
    likely = [c for c in live if c.score.band is MatchBand.LIKELY]
    domains = {e.source_domain for e in evidence if e.source_domain}

    if anchor.is_confident:
        reasons.append(
            ScoreReason("anchor_confirmed", f"identity anchored on '{anchor.handle}' ({anchor.confirmed_by})", 30.0)
        )
    if confirmed:
        reasons.append(
            ScoreReason(
                "confirmed_accounts",
                f"{len(confirmed)} account(s) confirmed to a high standard",
                min(30.0, 15.0 * len(confirmed)),
            )
        )
    if likely:
        reasons.append(
            ScoreReason("likely_accounts", f"{len(likely)} further likely account(s)", min(15.0, 5.0 * len(likely)))
        )
    if domains:
        reasons.append(
            ScoreReason(
                "independent_sources",
                f"evidence from {len(domains)} independent site(s)",
                min(20.0, 2.5 * len(domains)),
            )
        )
    if any(e.kind is EvidenceKind.ANSWER for e in evidence):
        reasons.append(ScoreReason("user_guidance", "you confirmed details during the search", 10.0))
    if not live:
        reasons.append(ScoreReason("no_live_accounts", "no reachable account was verified", -25.0))
    if len(domains) <= 1:
        reasons.append(ScoreReason("single_source", "everything traces back to a single source", -15.0))

    return finalize(reasons)


# -- helpers -----------------------------------------------------------------


def _apply_evidence(
    candidate: ProfileCandidate,
    anchor: Anchor,
    evidence: Sequence[Evidence],
    add,  # noqa: ANN001 - local closure, typed by usage
) -> None:
    """Signals that come from stored evidence rather than the candidate itself."""
    key = candidate.key
    for ev in sorted(evidence, key=lambda e: (e.kind, e.subject, e.value)):
        if ev.subject != key and ev.platform not in (None, candidate.platform):
            continue
        if ev.kind is EvidenceKind.EMPLOYER and anchor.employer:
            if normalize_org(ev.value) == normalize_org(anchor.employer):
                add("employer_match", other=ev.value, fingerprints=(ev.fingerprint,))
        elif ev.kind is EvidenceKind.SCHOOL and anchor.school:
            if normalize_org(ev.value) == normalize_org(anchor.school):
                add("school_match", other=ev.value, fingerprints=(ev.fingerprint,))
        elif ev.kind is EvidenceKind.NEGATIVE and ev.subject == key:
            # A verified absence is recorded but must not double-penalize; the
            # verdict already carries it.
            continue


def _has_other_anchor_link(candidate: ProfileCandidate, ctx: ScoringContext, anchor: Anchor) -> bool:
    """Is this candidate tied to the anchor by something other than its name?

    A name mismatch is only damning when nothing else connects the account. People
    routinely use a nickname as their display name.
    """
    key = candidate.key
    if candidate.user_confirmed:
        return True
    if any(key in pair for pair in ctx.reciprocal_pairs | ctx.rel_me_pairs):
        return True
    if candidate.avatar_sha256 and len(ctx.avatar_sha_index.get(candidate.avatar_sha256, set())) > 1:
        return True
    anchor_handle = normalize_handle(anchor.handle)
    if anchor_handle and is_similar_handle(normalize_handle(candidate.username), anchor_handle):
        return True
    return any(
        match_profile_url(link) and match_profile_url(link).canonical_url in ctx.confirmed_urls  # type: ignore[union-attr]
        for link in candidate.outbound_links
    )


_CORROBORATING_CODES = frozenset(
    {
        "user_confirmed",
        "reciprocal_link",
        "rel_me_verified",
        "personal_site_backlink",
        "outbound_link_match",
        "exact_username_anchor",
        "avatar_sha256_identical",
        "reverse_image_hit",
        "email_local_match",
        "employer_match",
        "school_match",
    }
)


def _has_independent_corroboration(reasons: Sequence[ScoreReason]) -> bool:
    """True when something other than a name/handle coincidence supports this."""
    return any(r.code in _CORROBORATING_CODES for r in reasons)

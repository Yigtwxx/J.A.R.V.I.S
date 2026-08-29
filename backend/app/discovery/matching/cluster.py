"""Group candidates into identities and elect exactly one.

This module is the fix for the single worst behaviour of the old pipeline: it
poured every finding for a name into one bag and handed the bag to the LLM, which
dutifully wrote one biography describing three different people. A composite
answer is worse than a wrong answer, because a wrong answer can be corrected and
a composite one cannot even be evaluated.

The approach is a union-find over an **agreement graph**:

* Two candidates are merged when something ties them together that is hard to
  coincide with — a reciprocal link, a shared avatar file, the same confirmed
  handle, the same employer *and* city, or an explicit user confirmation.
* Contradictions (different cities, different employers, an explicit rejection)
  keep them apart, and a contradiction always beats a weak agreement.

Then exactly one cluster is elected. Everything the user sees — biography,
picture, accounts, work history — is built from the elected cluster alone. The
others are returned separately as `alternate_identities` so a genuine namesake is
still surfaced, but never merged into the answer.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.discovery.evidence.model import Evidence
from app.discovery.identity.anchor import Anchor
from app.discovery.identity.normalize import name_tokens, normalize_handle, normalize_org, token_overlap
from app.discovery.matching.candidate import MatchScore, ProfileCandidate, ScoreReason
from app.discovery.matching.scoring import ScoringContext, finalize, score_subject
from app.discovery.platforms.urlmatch import is_generic_handle, match_profile_url
from app.discovery.types import MatchBand


class _UnionFind:
    """Standard union-find with path compression."""

    def __init__(self, keys: Sequence[str]) -> None:
        self._parent: dict[str, str] = {k: k for k in keys}

    def find(self, key: str) -> str:
        parent = self._parent.setdefault(key, key)
        if parent != key:
            root = self.find(parent)
            self._parent[key] = root
            return root
        return key

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            # Deterministic: the lexicographically smaller key always wins, so the
            # same input always produces the same cluster ids.
            if root_a <= root_b:
                self._parent[root_b] = root_a
            else:
                self._parent[root_a] = root_b

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for key in sorted(self._parent):
            out.setdefault(self.find(key), []).append(key)
        return out


@dataclass(slots=True)
class IdentityCluster:
    """One coherent identity: a set of accounts believed to be the same person."""

    cluster_id: str
    members: list[ProfileCandidate] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    anchor: Anchor | None = None
    score: MatchScore = MatchScore(0, MatchBand.REJECTED, ())
    label: str = ""
    """Short distinguishing summary, e.g. "Istanbul · Software Engineer at Getir"."""

    @property
    def member_keys(self) -> tuple[str, ...]:
        return tuple(sorted(c.key for c in self.members))

    @property
    def live_members(self) -> list[ProfileCandidate]:
        return [c for c in self.members if c.is_live]

    @property
    def source_domains(self) -> set[str]:
        return {e.source_domain for e in self.evidence if e.source_domain}

    def top_member(self) -> ProfileCandidate | None:
        live = self.live_members
        if not live:
            return None
        return max(live, key=lambda c: (c.score.value, c.platform == "github", c.platform))


def cluster_id_for(keys: Sequence[str]) -> str:
    """Stable id derived from the member set, so re-runs reuse the same id."""
    digest = hashlib.sha1("|".join(sorted(keys)).encode("utf-8")).hexdigest()
    return digest[:16]


def build_clusters(
    candidates: Sequence[ProfileCandidate],
    anchor: Anchor,
    evidence: Sequence[Evidence] = (),
    context: ScoringContext | None = None,
) -> list[IdentityCluster]:
    """Partition candidates into identity clusters. Deterministic."""
    live = [c for c in candidates if c.is_live]
    if not live:
        return []

    ctx = context or ScoringContext()
    keys = [c.key for c in live]
    by_key = {c.key: c for c in live}
    uf = _UnionFind(keys)

    agreements = _agreement_edges(live, ctx, anchor)
    conflicts = _conflict_edges(live)

    for pair in sorted(agreements):
        if pair in conflicts:
            # A contradiction always beats a weak agreement: two accounts that
            # disagree about city AND employer are not the same person, no matter
            # how similar their handles look.
            continue
        uf.union(*pair)

    clusters: list[IdentityCluster] = []
    for member_keys in uf.groups().values():
        members = [by_key[k] for k in member_keys if k in by_key]
        if not members:
            continue
        cluster = IdentityCluster(cluster_id=cluster_id_for(member_keys), members=members)
        cluster.evidence = _evidence_for(members, evidence)
        cluster.anchor = anchor
        cluster.label = describe(cluster, anchor)
        cluster.score = score_subject(anchor, cluster.evidence, members)
        for candidate in members:
            candidate.cluster_id = cluster.cluster_id
        clusters.append(cluster)

    clusters.sort(key=lambda c: (-c.score.value, -len(c.live_members), c.cluster_id))
    return clusters


def elect(clusters: Sequence[IdentityCluster]) -> tuple[IdentityCluster | None, list[IdentityCluster]]:
    """Choose the one identity the answer describes.

    Returns ``(winner, alternates)``. A winner is chosen even when confidence is
    low — the requirement is one coherent answer, stated with an honest confidence,
    rather than a merged blur of several people. `subject_confidence` on the
    response tells the user how much to trust it.
    """
    if not clusters:
        return None, []
    ordered = sorted(
        clusters,
        key=lambda c: (
            -_cluster_rank(c),
            -len(c.source_domains),
            -sum(1 for m in c.live_members if m.score.band is MatchBand.CONFIRMED),
            c.cluster_id,
        ),
    )
    return ordered[0], list(ordered[1:])


def _cluster_rank(cluster: IdentityCluster) -> float:
    """Primary ranking: overall confidence, weighted by how much of it is solid."""
    confirmed = sum(1 for m in cluster.live_members if m.score.band is MatchBand.CONFIRMED)
    likely = sum(1 for m in cluster.live_members if m.score.band is MatchBand.LIKELY)
    user_confirmed = any(m.user_confirmed for m in cluster.members)
    return cluster.score.value + confirmed * 12 + likely * 5 + (50 if user_confirmed else 0)


def limit_per_platform(
    cluster: IdentityCluster,
    *,
    max_per_platform: int,
) -> list[ProfileCandidate]:
    """At most N accounts per platform, best first.

    These are several accounts belonging to the *same* person (main, business,
    secondary) — not several people. That invariant holds because the cluster was
    elected first and this only trims within it.
    """
    grouped: dict[str, list[ProfileCandidate]] = {}
    for candidate in cluster.live_members:
        grouped.setdefault(candidate.platform, []).append(candidate)

    out: list[ProfileCandidate] = []
    for platform in sorted(grouped):
        ranked = sorted(
            grouped[platform],
            key=lambda c: (-c.score.value, 0 if c.user_confirmed else 1, c.username.lower()),
        )
        out.extend(ranked[: max(1, max_per_platform)])
    out.sort(key=lambda c: (-c.score.value, c.platform, c.username.lower()))
    return out


def describe(cluster: IdentityCluster, anchor: Anchor) -> str:
    """A short label a human can use to tell two same-name identities apart."""
    parts: list[str] = []
    top = cluster.top_member()
    if top and top.display_name and name_tokens(top.display_name) != anchor.tokens:
        parts.append(top.display_name)
    locations = [m.location for m in cluster.live_members if m.location]
    if locations:
        parts.append(sorted(locations)[0])
    employers = [m.employer for m in cluster.live_members if m.employer]
    if employers:
        parts.append(sorted(employers)[0])
    if not parts:
        handles = sorted({normalize_handle(m.username) for m in cluster.live_members})
        parts.append("/".join(handles[:3]) or "unidentified")
    platforms = sorted({m.platform for m in cluster.live_members})
    return " · ".join(parts[:3]) + (f" ({', '.join(platforms[:4])})" if platforms else "")


def reanchor_reasons(previous: IdentityCluster | None, chosen: IdentityCluster) -> tuple[ScoreReason, ...]:
    """Explain a mid-search identity switch, for the ``anchor_changed`` event."""
    if previous is None or previous.cluster_id == chosen.cluster_id:
        return ()
    return (
        ScoreReason(
            code="identity_switched",
            text=f"switched from '{previous.label}' to '{chosen.label}' — earlier findings were discarded",
            points=0.0,
        ),
    )


def merged_score(cluster: IdentityCluster) -> MatchScore:
    """Recompute the cluster score from its members' reasons, deduplicated by code."""
    best: dict[str, ScoreReason] = {}
    for member in cluster.live_members:
        for reason in member.score.reasons:
            current = best.get(reason.code)
            if current is None or abs(reason.points) > abs(current.points):
                best[reason.code] = reason
    return finalize(tuple(best.values()))


# -- edge construction -------------------------------------------------------


def _agreement_edges(
    candidates: Sequence[ProfileCandidate],
    ctx: ScoringContext,
    anchor: Anchor,
) -> set[tuple[str, str]]:
    """Pairs that something hard-to-coincide-with ties together."""
    edges: set[tuple[str, str]] = set()
    by_key = {c.key: c for c in candidates}
    keys = set(by_key)

    def link(a: str, b: str) -> None:
        if a != b and a in keys and b in keys:
            edges.add((a, b) if a <= b else (b, a))

    # Explicit topology already computed by the caller.
    for a, b in ctx.reciprocal_pairs | ctx.rel_me_pairs:
        link(a, b)

    # Outbound links between two candidates.
    for candidate in candidates:
        for href in candidate.outbound_links:
            matched = match_profile_url(href)
            if matched is not None:
                link(candidate.key, matched.key)

    # Identical or near-identical avatar files (not faces).
    for sha, member_keys in ctx.avatar_sha_index.items():
        if sha in ctx.generic_images:
            continue
        ordered = sorted(member_keys)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                link(a, b)
    # A *perceptual* hash match is deliberately NOT a merge edge. Observed live:
    # two unrelated Erdoğans both using a platform's default avatar produced an
    # identical dhash and were fused into one identity. Near-identical pixels are
    # far too weak to fuse identities; dhash stays a scoring signal (+8) where it
    # can be outweighed, but it never joins two clusters on its own.

    # The same distinctive handle on several platforms.
    handle_groups: dict[str, list[str]] = {}
    for candidate in candidates:
        handle = normalize_handle(candidate.username)
        if handle and not is_generic_handle(handle) and len(handle) >= 4:
            handle_groups.setdefault(handle, []).append(candidate.key)
    for group in handle_groups.values():
        ordered = sorted(group)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                link(a, b)

    # Same employer AND same city — either alone is far too common.
    for i, first in enumerate(candidates):
        for second in candidates[i + 1 :]:
            if _same_org(first.employer, second.employer) and _same_place(first.location, second.location):
                link(first.key, second.key)

    # A user-confirmed account joins the anchor's cluster by definition.
    confirmed = [c.key for c in candidates if c.user_confirmed]
    for i, a in enumerate(confirmed):
        for b in confirmed[i + 1 :]:
            link(a, b)
    anchor_handle = normalize_handle(anchor.handle)
    if anchor.is_confident and anchor_handle:
        anchored = [c.key for c in candidates if normalize_handle(c.username) == anchor_handle]
        for key in anchored:
            for other in confirmed:
                link(key, other)

    return edges


def _conflict_edges(candidates: Sequence[ProfileCandidate]) -> set[tuple[str, str]]:
    """Pairs that cannot be the same person."""
    conflicts: set[tuple[str, str]] = set()
    for i, first in enumerate(candidates):
        for second in candidates[i + 1 :]:
            pair = (first.key, second.key) if first.key <= second.key else (second.key, first.key)
            if first.user_rejected != second.user_rejected and (first.user_confirmed or second.user_confirmed):
                conflicts.add(pair)
                continue
            if names_contradict(first.display_name, second.display_name):
                conflicts.add(pair)
                continue
            employer_conflict = _conflicts(first.employer, second.employer, _same_org)
            place_conflict = _conflicts(first.location, second.location, _same_place)
            if employer_conflict and place_conflict:
                conflicts.add(pair)
    return conflicts


def names_contradict(first: str | None, second: str | None) -> bool:
    """True when two display names name *different* people rather than one.

    The hard case in practice is a shared surname: "Yılmaz Erdoğan" and "Yiğit
    Erdoğan" overlap on one token, so neither a plain overlap ratio nor a
    zero-overlap mismatch check separates them — and left unseparated they merge
    into a single person who is neither.

    The test that does work: each name carries a distinctive token the other
    lacks. A subset relationship ("Yiğit Erdoğan" vs "Yiğit Erdoğan (yigitrdgn)")
    is one person written two ways; a mutual difference is two people.
    """
    if not first or not second:
        return False  # unknown never contradicts
    left, right = set(name_tokens(first)), set(name_tokens(second))
    if not left or not right or not (left & right):
        return False  # no shared token at all is a different question entirely
    return bool(left - right) and bool(right - left)


def _evidence_for(members: Sequence[ProfileCandidate], evidence: Sequence[Evidence]) -> list[Evidence]:
    """Evidence attributable to this cluster: about its members, or platform-free."""
    keys = {c.key for c in members}
    platforms = {c.platform for c in members}
    out = [
        ev
        for ev in evidence
        if ev.subject in keys or (ev.platform in platforms and ev.platform is not None) or ev.platform is None
    ]
    return sorted(out, key=lambda e: (e.kind, e.subject, e.value))


def _same_org(a: str | None, b: str | None) -> bool:
    return bool(a and b and normalize_org(a) == normalize_org(b))


def _same_place(a: str | None, b: str | None) -> bool:
    return bool(a and b and token_overlap(name_tokens(a), name_tokens(b)) > 0)


def _conflicts(a: str | None, b: str | None, same) -> bool:  # noqa: ANN001 - predicate
    """Both sides known and disagreeing. Unknown never conflicts."""
    return bool(a and b and not same(a, b))

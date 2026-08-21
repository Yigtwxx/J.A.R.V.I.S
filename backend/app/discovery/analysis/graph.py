"""Relationship graph for the elected identity.

The frontend has carried ``react-force-graph-2d`` as a dependency for a while
with nothing to feed it. :meth:`RelationshipGraph.as_dict` is that feed: plain
JSON scalars under exactly ``{"nodes": [...], "edges": [...]}``.

The same restriction that governs the biography governs this graph: **only
members of the elected cluster become nodes**. A graph that quietly draws a
namesake's account next to the subject's is the identical bug as a biography
that blends two people, except it looks more authoritative because it is drawn
rather than written.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.discovery.evidence.model import Evidence
from app.discovery.identity.normalize import fold_ascii
from app.discovery.matching.cluster import IdentityCluster
from app.discovery.platforms.urlmatch import match_profile_url
from app.discovery.types import EvidenceKind

SUBJECT_ID = "subject"

# Evidence kind -> (node type, edge kind). Kinds absent from this table produce no
# node: an unmapped kind is one we cannot label honestly, and an unlabelled node
# is noise on a graph whose whole value is that every mark means something.
_KIND_NODES: dict[EvidenceKind, tuple[str, str]] = {
    EvidenceKind.EMAIL: ("email", "owns_domain"),
    EvidenceKind.DOMAIN: ("domain", "owns_domain"),
    EvidenceKind.EMPLOYER: ("organization", "works_at"),
    EvidenceKind.SCHOOL: ("school", "studied_at"),
    EvidenceKind.LOCATION: ("location", "located_in"),
    EvidenceKind.MENTION: ("domain", "mentioned_by"),
}


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One entity on the graph."""

    id: str
    type: str
    """``profile`` | ``email`` | ``domain`` | ``organization`` | ``school`` | ``location`` | ``subject``."""

    label: str
    platform: str | None = None
    confidence: int = 0
    url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "platform": self.platform,
            "confidence": self.confidence,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """One relationship, carrying the evidence that justifies drawing it."""

    source: str
    target: str
    kind: str
    """``outbound_link`` | ``reciprocal_link`` | ``same_avatar`` | ``works_at`` |
    ``studied_at`` | ``located_in`` | ``owns_domain`` | ``mentioned_by``."""

    weight: float = 1.0
    evidence_fingerprints: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "weight": round(float(self.weight), 3),
            "evidence_fingerprints": list(self.evidence_fingerprints),
        }


@dataclass(frozen=True, slots=True)
class RelationshipGraph:
    """Nodes and edges, ready to hand to the force-directed renderer."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"nodes": [n.as_dict() for n in self.nodes], "edges": [e.as_dict() for e in self.edges]}


def _entity_id(node_type: str, value: str) -> str:
    """Stable, collision-free id for a non-profile entity."""
    return f"{node_type}:{fold_ascii(value).strip() or value.strip().lower()}"


def build_graph(cluster: IdentityCluster, evidence: Sequence[Evidence]) -> RelationshipGraph:
    """Build the relationship graph for one elected cluster.

    Every node is either the subject, one of the cluster's live members, or an
    entity asserted by evidence attached to that cluster. Nothing else can enter.
    """
    members = cluster.live_members
    nodes: dict[str, GraphNode] = {
        SUBJECT_ID: GraphNode(
            id=SUBJECT_ID,
            type="subject",
            label=cluster.label or "subject",
            confidence=cluster.score.value,
        )
    }
    edges: dict[tuple[str, str, str], GraphEdge] = {}

    def add_edge(
        source: str, target: str, kind: str, *, weight: float = 1.0, fingerprints: tuple[str, ...] = ()
    ) -> None:
        if source == target or source not in nodes or target not in nodes:
            return
        key = (source, target, kind)
        existing = edges.get(key)
        merged = tuple(dict.fromkeys((existing.evidence_fingerprints if existing else ()) + fingerprints))
        edges[key] = GraphEdge(source=source, target=target, kind=kind, weight=weight, evidence_fingerprints=merged)

    member_keys = {member.key for member in members}
    for member in members:
        nodes[member.key] = GraphNode(
            id=member.key,
            type="profile",
            label=member.display_name or member.username,
            platform=member.platform,
            confidence=member.score.value,
            url=member.url,
        )

    for member in members:
        add_edge(SUBJECT_ID, member.key, "outbound_link", weight=max(0.1, member.score.value / 100))

    # Profile-to-profile links. A link that points back is a reciprocal_link,
    # which is the strongest keyless corroborator the pipeline has.
    linked: set[tuple[str, str]] = set()
    for member in members:
        for href in member.outbound_links:
            matched = match_profile_url(href)
            if matched is not None and matched.key in member_keys:
                linked.add((member.key, matched.key))
    for source, target in sorted(linked):
        kind = "reciprocal_link" if (target, source) in linked else "outbound_link"
        add_edge(source, target, kind, weight=2.0 if kind == "reciprocal_link" else 1.0)

    # Shared avatar file: same bytes on two platforms is not a coincidence.
    by_avatar: dict[str, list[str]] = {}
    for member in members:
        if member.avatar_sha256:
            by_avatar.setdefault(member.avatar_sha256, []).append(member.key)
    for group in by_avatar.values():
        ordered = sorted(group)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                add_edge(left, right, "same_avatar", weight=2.0)

    for item in evidence:
        mapping = _KIND_NODES.get(item.kind)
        if mapping is None or not item.value.strip():
            continue
        node_type, edge_kind = mapping
        node_id = _entity_id(node_type, item.value)
        if node_id not in nodes:
            nodes[node_id] = GraphNode(
                id=node_id,
                type=node_type,
                label=item.value.strip(),
                confidence=round(100 * item.confidence),
                url=item.source_url or None,
            )
        # Attach to the member the evidence is about when it names one, otherwise
        # to the subject. Evidence about a non-member is skipped entirely.
        anchor = item.subject if item.subject in member_keys else SUBJECT_ID
        add_edge(anchor, node_id, edge_kind, weight=max(0.1, item.confidence), fingerprints=(item.fingerprint,))

    ordered_nodes = tuple(sorted(nodes.values(), key=lambda n: (n.type != "subject", n.type, n.id)))
    ordered_edges = tuple(sorted(edges.values(), key=lambda e: (e.source, e.kind, e.target)))
    return RelationshipGraph(nodes=ordered_nodes, edges=ordered_edges)

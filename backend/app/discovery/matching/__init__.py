"""Candidate scoring and single-identity election."""

from app.discovery.matching.candidate import EMPTY_SCORE, MatchScore, ProfileCandidate, ScoreReason
from app.discovery.matching.cluster import (
    IdentityCluster,
    build_clusters,
    cluster_id_for,
    describe,
    elect,
    limit_per_platform,
    merged_score,
    reanchor_reasons,
)
from app.discovery.matching.scoring import ScoringContext, finalize, score_profile, score_subject

__all__ = [
    "EMPTY_SCORE",
    "IdentityCluster",
    "MatchScore",
    "ProfileCandidate",
    "ScoreReason",
    "ScoringContext",
    "build_clusters",
    "cluster_id_for",
    "describe",
    "elect",
    "finalize",
    "limit_per_platform",
    "merged_score",
    "reanchor_reasons",
    "score_profile",
    "score_subject",
]

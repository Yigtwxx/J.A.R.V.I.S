"""Evidence-driven OSINT discovery pipeline.

Replaces the old `scraper_service` + `search_service` engine layer. The design
rests on four rules, each of which fixes a specific failure of the old pipeline:

1. **Nothing is ever silently empty.** Every fetch, every existence check and
   every platform reports a status; "blocked" is never confused with "not found",
   and neither is ever confused with "found".
2. **A URL is never regexed as a string.** Host equality plus anchored path
   patterns, so `roblox.com/users/1` can never be mistaken for an X profile.
3. **One identity per answer.** Candidates are clustered by mutual corroboration
   and exactly one cluster is elected; the narrative, the picture and the accounts
   all come from that cluster and nowhere else.
4. **Every claim traces to evidence.** Confidence is a deterministic sum of named,
   human-readable signals, and the biography is grounded in stored evidence.
"""

from app.discovery.types import (
    EntityType,
    EvidenceKind,
    ExistenceVerdict,
    FetchStatus,
    FetchTier,
    MatchBand,
    PlatformStatus,
    PlatformTier,
    SourceKind,
    band_for,
)

__all__ = [
    "EntityType",
    "EvidenceKind",
    "ExistenceVerdict",
    "FetchStatus",
    "FetchTier",
    "MatchBand",
    "PlatformStatus",
    "PlatformTier",
    "SourceKind",
    "band_for",
]

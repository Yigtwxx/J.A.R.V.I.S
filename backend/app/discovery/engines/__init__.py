"""Search-engine layer of the discovery pipeline.

A pool of independent SERP scrapers plus the dork templates that feed them. No
single engine is trusted: results are fused across engines with Reciprocal Rank
Fusion, and every engine reports *why* it produced what it produced, so "blocked"
is never quietly rendered as "nothing found".
"""

from app.discovery.engines.base import (
    EngineHealth,
    EngineResult,
    HtmlSearchEngine,
    SearchEngine,
    SearchHit,
    build_engine_result,
    clean_result_url,
    dedupe_hits,
    health_for_fetch,
    normalize_hit_url,
)
from app.discovery.engines.bing import BingEngine
from app.discovery.engines.brave import BraveEngine
from app.discovery.engines.duckduckgo import DuckDuckGoEngine
from app.discovery.engines.google import GoogleEngine
from app.discovery.engines.mojeek import MojeekEngine
from app.discovery.engines.queries import (
    QueryTerms,
    ascii_fold,
    build_query_terms,
    canonical_query,
    entity_queries,
    evidence_queries,
    normalize_query,
    platform_queries,
)
from app.discovery.engines.registry import EngineRegistry, default_engines, fuse_results
from app.discovery.engines.startpage import StartpageEngine

__all__ = [
    "BingEngine",
    "BraveEngine",
    "DuckDuckGoEngine",
    "EngineHealth",
    "EngineRegistry",
    "EngineResult",
    "GoogleEngine",
    "HtmlSearchEngine",
    "MojeekEngine",
    "QueryTerms",
    "SearchEngine",
    "SearchHit",
    "StartpageEngine",
    "ascii_fold",
    "build_engine_result",
    "build_query_terms",
    "canonical_query",
    "clean_result_url",
    "dedupe_hits",
    "default_engines",
    "entity_queries",
    "evidence_queries",
    "fuse_results",
    "health_for_fetch",
    "normalize_hit_url",
    "normalize_query",
    "platform_queries",
]

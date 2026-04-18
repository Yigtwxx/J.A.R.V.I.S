"""PipelineContext — shared mutable state carried through every pipeline step."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PipelineContext:
    """
    All data flowing through the search pipeline.
    Each step reads what it needs and writes its outputs back here.
    """
    # Input
    raw_query: str = ""
    depth_config: Optional[Any] = None
    db: Optional[Any] = None

    # Step 1 — query parser
    real_name: str = ""
    username: str = ""

    # Step 2 — data fetcher
    orch_result: Optional[Any] = None
    github_data: Optional[dict] = None
    search_results: Optional[tuple] = None   # (wiki_image, web_results, deep_context, raw_sources)

    # Step 3 — result processor
    context: Optional[dict] = None
    deep_context: Optional[str] = None
    github_url: Optional[str] = None
    raw_sources: Optional[list] = None

    # Step 5 — image collector
    images: Optional[list] = None
    face_images: Optional[list] = None      # list of (label, url) tuples

    # Step 6 — analysis runner
    ai_response: Optional[str] = None
    face_match_report: Optional[Any] = None
    sentiment_report: Optional[Any] = None

    # Step 7 — post-analysis runner
    post_analysis: Optional[dict] = None

    # Step 8 — response builder
    response: Optional[Any] = None

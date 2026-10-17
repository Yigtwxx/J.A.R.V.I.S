"""PipelineContext — shared mutable state carried through every pipeline step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PipelineContext:
    """
    All data flowing through the search pipeline.
    Each step reads what it needs and writes its outputs back here.
    """

    # Input
    raw_query: str = ""
    depth_config: Any | None = None
    db: Any | None = None

    # Step 1 — query parser
    real_name: str = ""
    username: str = ""

    # Step 2 — data fetcher
    orch_result: Any | None = None
    github_data: dict | None = None
    search_results: tuple | None = None  # (wiki_image, web_results, deep_context, raw_sources)
    discovery_result: Any | None = None
    """The `DiscoveryResult` for this search, when the discovery pipeline is enabled.

    The blocking route runs it non-interactively (no questions — an HTTP request
    cannot wait on a human), and `build_response` merges its typed fields into the
    response. Without it the legacy path returns no social profiles at all, because
    the old scraper that used to supply them was removed for manufacturing them.
    """

    # Step 3 — result processor
    context: dict | None = None
    deep_context: str | None = None
    github_url: str | None = None
    raw_sources: list | None = None

    # Step 5 — image collector
    images: list | None = None
    face_images: list | None = None  # list of (label, url) tuples

    # Step 6 — analysis runner
    ai_response: str | None = None
    face_match_report: Any | None = None
    sentiment_report: Any | None = None

    # Step 7 — post-analysis runner
    post_analysis: dict | None = None

    # Step 8 — response builder
    response: Any | None = None

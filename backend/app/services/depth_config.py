"""
DepthConfig — translates a user-selected search depth (1-10) into concrete
pipeline parameters so every downstream service can scale its effort.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DepthConfig:
    """Immutable configuration derived from a 1-10 depth integer."""

    depth: int  # raw value chosen by the user

    def __post_init__(self) -> None:
        if not 1 <= self.depth <= 10:
            object.__setattr__(self, "depth", max(1, min(10, self.depth)))

    # -- tier label ---------------------------------------------------------

    @property
    def tier(self) -> str:
        if self.depth <= 3:
            return "surface"
        if self.depth <= 6:
            return "medium"
        return "deep"

    # -- search query variations --------------------------------------------

    @property
    def num_query_variations(self) -> int:
        """How many distinct Yahoo/web queries to fire."""
        mapping = {1: 2, 2: 2, 3: 3, 4: 4, 5: 5, 6: 5, 7: 8, 8: 10, 9: 11, 10: 12}
        return mapping[self.depth]

    # -- deep-scrape budget -------------------------------------------------

    @property
    def max_deep_scrapes(self) -> int:
        """Max URLs to fully scrape for body text."""
        mapping = {1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 5, 7: 8, 8: 10, 9: 11, 10: 12}
        return mapping[self.depth]

    # -- relevance threshold ------------------------------------------------

    @property
    def relevance_threshold(self) -> float:
        """Minimum fuzzy-match ratio for `_is_relevant` checks.
        Higher ⇒ stricter ⇒ fewer false positives (important for deep mode
        where we want to discard famous-name collisions)."""
        if self.depth <= 3:
            return 0.60
        if self.depth <= 6:
            return 0.75
        return 0.85

    # -- username variation budget ------------------------------------------

    @property
    def max_username_variations(self) -> int:
        mapping = {1: 2, 2: 3, 3: 3, 4: 4, 5: 5, 6: 6, 7: 8, 8: 10, 9: 12, 10: 15}
        return mapping[self.depth]

    # -- multi-agent deep search --------------------------------------------

    @property
    def multi_agent(self) -> bool:
        """Whether to spawn the DeepSearchAgent for parallel sub-searches."""
        return self.depth >= 7

    # -- validation passes --------------------------------------------------

    @property
    def validation_passes(self) -> int:
        """Cross-reference validation rounds. >1 means a second pass checks
        that at least N sources agree on the same person."""
        if self.depth <= 6:
            return 1
        if self.depth <= 8:
            return 2
        return 3

    # -- inter-query delay --------------------------------------------------

    @property
    def query_delay_seconds(self) -> float:
        """Delay between search-engine queries to respect rate limits.
        Deep search fires many queries, so we need longer pauses."""
        if self.depth <= 3:
            return 0.8
        if self.depth <= 6:
            return 1.2
        return 2.0

    # -- search engine count ------------------------------------------------

    @property
    def search_engines_to_use(self) -> int:
        """How many search engines to query (Yahoo, Google, Bing, DuckDuckGo)."""
        if self.depth <= 3:
            return 1
        if self.depth <= 6:
            return 2
        return 4

    # -- academic / patent / registry search --------------------------------

    @property
    def include_institutional(self) -> bool:
        """Whether to run academic, patent, and registry searches."""
        return self.depth >= 4

    def __repr__(self) -> str:
        return (
            f"DepthConfig(depth={self.depth}, tier={self.tier!r}, "
            f"queries={self.num_query_variations}, scrapes={self.max_deep_scrapes}, "
            f"multi_agent={self.multi_agent})"
        )

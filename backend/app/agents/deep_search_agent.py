"""
DeepSearchAgent — activated when search depth >= 7.

Spawns parallel sub-searches with different query strategies (career,
academic, news, social, controversy) and cross-references results to
discard entries that don't actually belong to the target person.
"""

from __future__ import annotations

import asyncio
import difflib
import time
import unicodedata
import urllib.parse
from typing import Any

from .base_agent import AgentResult, BaseAgent, StatusCallback


def _normalize(text: str) -> str:
    """Strip diacritics and lower-case for fuzzy matching."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


class DeepSearchAgent(BaseAgent):
    """Multi-strategy parallel search with cross-reference validation."""

    def __init__(
        self,
        search_service: Any,
        name: str,
        depth: int,
        status_callback: StatusCallback,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        super().__init__(status_callback, loop)
        self._search = search_service
        self._name = name
        self._depth = depth

    @property
    def agent_name(self) -> str:
        return "DeepSearchAgent"

    # ------------------------------------------------------------------
    # Query strategy templates
    # ------------------------------------------------------------------

    def _build_query_strategies(self) -> list[tuple[str, list[str]]]:
        """Return (strategy_label, query_list) pairs based on depth."""
        name = self._name
        strategies: list[tuple[str, list[str]]] = [
            (
                "career",
                [
                    f'"{name}" career OR profession OR company',
                    f'"{name}" CEO OR founder OR director OR manager',
                    f'"{name}" work experience OR employment',
                ],
            ),
            (
                "academic",
                [
                    f'"{name}" university OR education OR degree',
                    f'"{name}" research OR publication OR thesis',
                    f'"{name}" PhD OR professor OR academic',
                ],
            ),
            (
                "news",
                [
                    f'"{name}" interview OR news OR article',
                    f'"{name}" award OR achievement OR recognition',
                    f'"{name}" event OR conference OR speaker',
                ],
            ),
            (
                "social",
                [
                    f'"{name}" profile OR about OR bio',
                    f'"{name}" blog OR personal site OR portfolio',
                ],
            ),
        ]

        if self._depth >= 9:
            strategies.append(
                (
                    "controversy",
                    [
                        f'"{name}" controversy OR scandal OR criticism',
                        f'"{name}" lawsuit OR court OR legal',
                    ],
                )
            )
            strategies.append(
                (
                    "deep_web",
                    [
                        f'"{name}" forum OR community OR discussion',
                        f'"{name}" review OR feedback OR testimonial',
                    ],
                )
            )

        return strategies

    # ------------------------------------------------------------------
    # Single strategy runner
    # ------------------------------------------------------------------

    def _run_strategy(self, label: str, queries: list[str]) -> list[dict[str, str]]:
        """Execute a set of queries for one strategy. Runs synchronously."""
        results: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        for query in queries:
            try:
                hits = self._search.search_yahoo(query, num_results=5)
                for h in hits:
                    url = h.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        h["_strategy"] = label
                        results.append(h)
                time.sleep(1.5)  # conservative delay for deep search
            except Exception as e:
                self._broadcast(f"[WARN] Search query failed: {e}")
                continue

        return results

    # ------------------------------------------------------------------
    # Cross-reference validation
    # ------------------------------------------------------------------

    def _cross_validate(self, strategy_results: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
        """Keep only results whose text is corroborated by ≥ 2 strategies."""
        name_norm = _normalize(self._name)
        name_parts = [p for p in name_norm.split() if len(p) > 2]

        # Collect all results and tag them
        all_items: list[dict[str, str]] = []
        for items in strategy_results.values():
            all_items.extend(items)

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for item in all_items:
            url = item.get("url", "")
            if url not in seen:
                seen.add(url)
                unique.append(item)

        # Score each result
        validated: list[dict[str, str]] = []
        for item in unique:
            text = _normalize(f"{item.get('title', '')} {item.get('snippet', '')}")

            # Check name presence
            parts_found = sum(1 for p in name_parts if p in text)
            if not name_parts or parts_found < len(name_parts):
                # Fuzzy fallback
                text_words = text.split()
                fuzzy_found = sum(
                    1
                    for p in name_parts
                    if p in text or (len(p) >= 4 and difflib.get_close_matches(p, text_words, n=1, cutoff=0.85))
                )
                if fuzzy_found < len(name_parts):
                    continue  # Not about our person

            # Count how many strategies produced this URL or a very similar URL
            strategies_with_url: set[str] = set()
            for strat_label, strat_items in strategy_results.items():
                for si in strat_items:
                    if si.get("url") == item.get("url"):
                        strategies_with_url.add(strat_label)
                        break
                    # Also check if same domain+path (different query params)
                    try:
                        a = urllib.parse.urlparse(si.get("url", ""))
                        b = urllib.parse.urlparse(item.get("url", ""))
                        if a.netloc == b.netloc and a.path == b.path:
                            strategies_with_url.add(strat_label)
                            break
                    except Exception:
                        continue

            # For deep search, we want ≥1 strategy match + name match
            # Results that appear in ≥2 strategies get higher priority
            item["_validation_score"] = len(strategies_with_url)
            validated.append(item)

        # Sort: multi-strategy hits first, then single-strategy
        validated.sort(key=lambda x: x.get("_validation_score", 0), reverse=True)

        return validated

    # ------------------------------------------------------------------
    # Deep content extraction
    # ------------------------------------------------------------------

    def _deep_scrape(self, results: list[dict[str, str]], max_scrapes: int) -> str:
        """Fetch full page content from top validated results."""
        skip_domains = {
            "instagram.com",
            "twitter.com",
            "x.com",
            "linkedin.com",
            "facebook.com",
            "youtube.com",
            "tiktok.com",
        }
        deep_context = ""
        scraped = 0

        for item in results:
            if scraped >= max_scrapes:
                break
            url = item.get("url", "")
            try:
                host = urllib.parse.urlparse(url).hostname or ""
                if any(d in host for d in skip_domains):
                    continue
            except Exception:
                continue

            content = self._search.fetch_content(url)
            if content and len(content.strip()) > 100:
                strategy = item.get("_strategy", "unknown")
                deep_context += f"--- DEEP NODE [{strategy}]: {url} ---\n{content}\n\n"
                scraped += 1

        return deep_context

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    async def run_async(self) -> AgentResult:
        self._broadcast(
            f"[SYS] DeepSearchAgent: launching multi-strategy deep search for '{self._name}' (depth={self._depth})"
        )

        strategies = self._build_query_strategies()

        # Run all strategies in parallel
        tasks = []
        for label, queries in strategies:
            tasks.append(self._run_sync(self._run_strategy, label, queries))

        strategy_outputs = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results by strategy
        strategy_results: dict[str, list[dict[str, str]]] = {}
        for (label, _), output in zip(strategies, strategy_outputs):
            if isinstance(output, Exception):
                self._broadcast(f"[WARN] DeepSearchAgent: strategy '{label}' failed: {output}")
                strategy_results[label] = []
            else:
                strategy_results[label] = output
                self._broadcast(f"[OK] DeepSearchAgent: strategy '{label}' returned {len(output)} result(s)")

        # Cross-reference validation
        validated = self._cross_validate(strategy_results)
        self._broadcast(f"[OK] DeepSearchAgent: {len(validated)} result(s) passed cross-validation")

        # Deep scrape validated results
        max_scrapes = min(self._depth, 12)
        deep_context = await self._run_sync(self._deep_scrape, validated, max_scrapes)

        self._broadcast(f"[OK] DeepSearchAgent: deep content extraction complete ({len(deep_context)} chars)")

        # Store extra deep context and validated web results in the agent result
        # These will be merged into the main pipeline by the orchestrator
        return AgentResult(
            agent_name=self.agent_name,
            # Reuse academic_context field to carry extra deep context
            academic_context=deep_context,
            # Reuse registry_context to carry validated result summaries
            registry_context=self._format_validated_results(validated[:20]),
        )

    def _format_validated_results(self, results: list[dict[str, str]]) -> str:
        """Format validated results as a readable summary."""
        if not results:
            return ""
        lines = ["\n=== DEEP SEARCH VALIDATED RESULTS ==="]
        for i, r in enumerate(results[:20], 1):
            score = r.get("_validation_score", 0)
            lines.append(
                f"  {i}. [{r.get('_strategy', '?')}] (corroboration: {score}) "
                f"{r.get('title', 'N/A')}\n     URL: {r.get('url', '')}\n     "
                f"{r.get('snippet', '')[:200]}"
            )
        return "\n".join(lines)

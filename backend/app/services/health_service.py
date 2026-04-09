"""
Health Telemetry Service — biometric and wellness tracking layer.

Built on top of UserMemoryService to store health data in the same
SQLite + ChromaDB infrastructure. Adds health-specific categories,
AI-powered suggestions, and pattern detection.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import ollama
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.user_memory_service import UserMemoryService
from app.utils.logger import logger

settings = get_settings()

HEALTH_CATEGORIES = [
    "health_sleep",
    "health_energy",
    "health_illness",
    "health_exercise",
    "health_mood",
    "health_nutrition",
    "health_vitals",
]

CATEGORY_LABELS = {
    "health_sleep": "Sleep & Rest",
    "health_energy": "Energy Levels",
    "health_illness": "Illness & Symptoms",
    "health_exercise": "Physical Activity",
    "health_mood": "Mood & Emotions",
    "health_nutrition": "Nutrition & Hydration",
    "health_vitals": "Vitals (Heart Rate, BP, etc.)",
}


class HealthService:
    """Health telemetry and wellness tracking powered by AI."""

    def __init__(self, memory_service: UserMemoryService):
        self._memory = memory_service
        self._client = ollama.AsyncClient()
        self._model = settings.ollama_model

    @staticmethod
    def _strip_thinking(text: str) -> str:
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    # -- Data Recording -------------------------------------------------------

    def record(
        self,
        db: Session,
        category: str,
        key: str,
        value: str,
        context: str | None = None,
    ) -> dict[str, Any]:
        """Record a health data point.

        Category must be one of HEALTH_CATEGORIES.
        Key is a human-readable label (e.g. 'sleep_hours', 'feeling_tired').
        Value is the data (e.g. '6 hours', 'headache since morning').
        """
        if category not in HEALTH_CATEGORIES:
            raise ValueError(f"Invalid category '{category}'. Must be one of: {HEALTH_CATEGORIES}")

        # Timestamp-prefix the key for chronological tracking
        ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        timestamped_key = f"{ts} | {key}"

        memory = self._memory.remember(
            db, category, timestamped_key, value,
            context=context, importance=7,
        )
        return {
            "id": memory.id,
            "category": memory.category,
            "key": memory.key,
            "value": memory.value,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
        }

    # -- Data Retrieval -------------------------------------------------------

    def get_history(
        self, db: Session, category: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve health records, optionally filtered by category."""
        if category and category not in HEALTH_CATEGORIES:
            raise ValueError(f"Invalid category '{category}'")

        if category:
            return self._memory.recall(db, category=category)[:limit]

        all_records: list[dict[str, Any]] = []
        for cat in HEALTH_CATEGORIES:
            all_records.extend(self._memory.recall(db, category=cat))
        # Sort by most recent first
        all_records.sort(key=lambda r: r.get("updated_at") or r.get("created_at") or "", reverse=True)
        return all_records[:limit]

    def get_categories(self) -> list[dict[str, str]]:
        """Return available health categories with labels."""
        return [
            {"id": cat, "label": CATEGORY_LABELS.get(cat, cat)}
            for cat in HEALTH_CATEGORIES
        ]

    # -- AI-Powered Suggestions -----------------------------------------------

    async def get_suggestions(self, db: Session, user_report: str) -> dict[str, Any]:
        """Given a user health report (e.g. 'I feel tired'), generate AI suggestions.

        Uses semantic memory search to find related health history, then asks
        Ollama for personalized health recommendations.
        """
        # 1. Semantic search for related health memories
        semantic_context = self._memory.semantic_recall(user_report, n_results=10)

        # 2. Get recent health history
        recent = self.get_history(db, limit=30)
        history_text = ""
        if recent:
            lines = [f"  [{r['category']}] {r['key']}: {r['value']}" for r in recent[:20]]
            history_text = "\n".join(lines)

        # 3. Build AI prompt
        prompt = f"""You are J.A.R.V.I.S., a personal health assistant for your owner.
Your owner has reported the following:

"{user_report}"

Based on their health history and current report, provide personalized health suggestions.

=== HEALTH HISTORY ===
{history_text if history_text else "No prior health data recorded."}

=== RELATED MEMORIES ===
{semantic_context if semantic_context else "No related memories found."}

RULES:
- Be caring, practical, and specific in your suggestions.
- Reference their health history when relevant.
- Do NOT provide medical diagnoses — suggest professional help when needed.
- Output ONLY a valid JSON object, no markdown formatting.

Required JSON Structure:
{{
  "assessment": "<string: 1-2 sentence assessment of their current state>",
  "suggestions": ["<string: each a specific, actionable health suggestion>"],
  "warnings": ["<string: any concerns that warrant attention>"],
  "follow_up_questions": ["<string: questions to better understand their state>"]
}}

Do NOT include ```json tags.
"""

        try:
            response = await self._client.generate(
                model=self._model,
                prompt=prompt,
                options={"temperature": 0.4, "top_p": 0.5},
            )

            response_text = self._strip_thinking(response["response"])

            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1

            if start_idx != -1 and end_idx > start_idx:
                parsed = json.loads(response_text[start_idx:end_idx])
                return {
                    "assessment": str(parsed.get("assessment", "")),
                    "suggestions": [str(s) for s in parsed.get("suggestions", [])],
                    "warnings": [str(w) for w in parsed.get("warnings", [])],
                    "follow_up_questions": [str(q) for q in parsed.get("follow_up_questions", [])],
                    "user_report": user_report,
                }

        except Exception as e:
            logger.log_error(f"Health suggestion generation failed: {e}")

        return {
            "assessment": "I couldn't fully analyze your report right now.",
            "suggestions": ["Please try again or provide more details about how you're feeling."],
            "warnings": [],
            "follow_up_questions": [],
            "user_report": user_report,
        }

    # -- Pattern Detection ----------------------------------------------------

    async def detect_patterns(self, db: Session) -> dict[str, Any]:
        """Analyze health data for recurring patterns."""
        history = self.get_history(db, limit=100)

        if len(history) < 5:
            return {
                "patterns": [],
                "summary": "Insufficient data for pattern detection. Keep logging your health data.",
                "data_points": len(history),
            }

        # Group by category
        by_cat: dict[str, list[str]] = {}
        for r in history:
            cat = r.get("category", "unknown")
            by_cat.setdefault(cat, []).append(f"{r['key']}: {r['value']}")

        evidence = "\n".join(
            f"[{cat}]\n" + "\n".join(items[:15])
            for cat, items in by_cat.items()
        )

        prompt = f"""You are J.A.R.V.I.S., analyzing your owner's health data for patterns.

=== HEALTH DATA ===
{evidence}

Analyze this data and identify recurring patterns, correlations, and trends.
Output ONLY a valid JSON object, no markdown formatting.

Required JSON Structure:
{{
  "patterns": [
    {{
      "description": "<string: what pattern you detected>",
      "category": "<string: which health area>",
      "severity": "<low|medium|high>",
      "recommendation": "<string: what to do about it>"
    }}
  ],
  "summary": "<string: 2-3 sentence overall health summary>",
  "data_points": {len(history)}
}}

Do NOT include ```json tags.
"""

        try:
            response = await self._client.generate(
                model=self._model,
                prompt=prompt,
                options={"temperature": 0.3, "top_p": 0.4},
            )

            response_text = self._strip_thinking(response["response"])
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1

            if start_idx != -1 and end_idx > start_idx:
                parsed = json.loads(response_text[start_idx:end_idx])
                return {
                    "patterns": parsed.get("patterns", []),
                    "summary": str(parsed.get("summary", "")),
                    "data_points": len(history),
                }

        except Exception as e:
            logger.log_error(f"Health pattern detection failed: {e}")

        return {
            "patterns": [],
            "summary": "Pattern analysis could not be completed.",
            "data_points": len(history),
        }

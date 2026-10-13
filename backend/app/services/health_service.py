"""
Health Telemetry Service — biometric and wellness tracking layer.

Built on top of UserMemoryService to store health data in the same
SQLite + ChromaDB infrastructure. Adds health-specific categories,
AI-powered suggestions, and pattern detection.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user_memory import UserMemory
from app.services.ollama_client import build_ollama_client
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
        self._client = build_ollama_client()
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

        # Appended, never upserted: health entries are observations on a
        # timeline, so logging "energy: Low" and then "energy: High" must leave
        # two rows. The key stays clean — the timestamp lives in created_at.
        memory = self._memory.append(
            db,
            category,
            key,
            value,
            context=context,
            importance=7,
        )
        return _record_to_dict(memory)

    def delete(self, db: Session, record_id: int) -> bool:
        """Delete one health record.

        Refuses non-health memories so the health panel can never erase the
        user's general memory rows, which share this table.
        """
        memory = db.query(UserMemory).filter(UserMemory.id == record_id).first()
        if not memory:
            return False
        if memory.category not in HEALTH_CATEGORIES:
            raise ValueError(f"Record {record_id} is not a health record")
        return self._memory.forget(db, record_id)

    # -- Data Retrieval -------------------------------------------------------

    def get_history(
        self,
        db: Session,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve health records, optionally filtered by category."""
        if category and category not in HEALTH_CATEGORIES:
            raise ValueError(f"Invalid category '{category}'")

        query = db.query(UserMemory).filter(
            UserMemory.category == category if category else UserMemory.category.in_(HEALTH_CATEGORIES)
        )
        # Newest first, and id as the tiebreaker: two entries logged in the same
        # second share a created_at, and without a stable second key their order
        # flips between reads, which reads as the list shuffling itself.
        records = query.order_by(UserMemory.created_at.desc(), UserMemory.id.desc()).limit(limit).all()
        return [_record_to_dict(m) for m in records]

    def get_categories(self) -> list[dict[str, str]]:
        """Return available health categories with labels."""
        return [{"id": cat, "label": CATEGORY_LABELS.get(cat, cat)} for cat in HEALTH_CATEGORIES]

    # -- AI-Powered Suggestions -----------------------------------------------

    async def get_suggestions(self, db: Session, user_report: str) -> dict[str, Any]:
        """Given a user health report (e.g. 'I feel tired'), generate AI suggestions.

        Uses semantic memory search to find related health history, then asks
        Ollama for personalized health recommendations.
        """
        # 1. Semantic search for related health memories
        semantic_context = self._memory.semantic_recall(db, user_report, n_results=10)

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

        evidence = "\n".join(f"[{cat}]\n" + "\n".join(items[:15]) for cat, items in by_cat.items())

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
                # Coerced per field rather than passed through: this is raw model
                # output, and a pattern missing "category" reached the panel as
                # undefined, where `category.includes(...)` threw and took the
                # console down. get_suggestions already coerces for this reason.
                raw_patterns = parsed.get("patterns", [])
                patterns = [
                    {
                        "description": str(p.get("description", "")),
                        "category": str(p.get("category", "")),
                        "severity": str(p.get("severity", "low")),
                        "recommendation": str(p.get("recommendation", "")),
                    }
                    for p in (raw_patterns if isinstance(raw_patterns, list) else [])
                    if isinstance(p, dict)
                ]
                return {
                    "patterns": patterns,
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


# Entries written before health records moved off ``remember`` carry the
# timestamp inside the key ("2026-08-23 09:26 | sleep_hours"), which the panel
# rendered raw. Strip it on read so old and new rows look the same; created_at
# is the timestamp either way.
_LEGACY_KEY_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?\s*\|\s*")


def _clean_key(key: str) -> str:
    return _LEGACY_KEY_PREFIX.sub("", key)


def _record_to_dict(memory: UserMemory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "category": memory.category,
        "key": _clean_key(memory.key),
        "value": memory.value,
        "context": memory.context,
        "importance": memory.importance,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
    }

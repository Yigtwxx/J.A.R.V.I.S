"""Tests for HealthService — recording, retrieval and AI-backed suggestions."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.health_service import HealthService
from app.services.user_memory_service import UserMemoryService


@pytest.fixture
def health_service():
    """HealthService wired to a real UserMemoryService but a stubbed LLM.

    The memory service is real on purpose: the bug this suite pins down was a
    wrong call into it, which a mocked memory service would have hidden.
    """
    service = HealthService(memory_service=UserMemoryService())
    service._client = MagicMock()
    service._client.generate = AsyncMock(
        return_value={
            "response": json.dumps(
                {
                    "assessment": "You seem run down.",
                    "suggestions": ["Sleep earlier tonight."],
                    "warnings": ["Recurring headaches deserve a doctor."],
                    "follow_up_questions": ["How much water did you drink?"],
                }
            )
        }
    )
    return service


class TestHealthRecording:
    def test_record_stores_and_history_returns_it(self, health_service, db_session):
        health_service.record(db_session, "health_sleep", "sleep_hours", "6 hours")

        history = health_service.get_history(db_session)

        assert len(history) == 1, "recorded entry should come back from history"
        assert history[0]["value"] == "6 hours"
        assert history[0]["category"] == "health_sleep"

    def test_record_rejects_unknown_category(self, health_service, db_session):
        with pytest.raises(ValueError):
            health_service.record(db_session, "health_haircut", "length", "short")

    def test_history_filters_by_category(self, health_service, db_session):
        health_service.record(db_session, "health_sleep", "sleep_hours", "6 hours")
        health_service.record(db_session, "health_mood", "mood", "Good")

        sleep_only = health_service.get_history(db_session, category="health_sleep")

        assert len(sleep_only) == 1, "category filter should exclude the mood entry"
        assert sleep_only[0]["category"] == "health_sleep"

    def test_two_entries_in_the_same_minute_are_kept_separately(self, health_service, db_session):
        """Same key twice must not collapse into one row.

        The memory layer upserts on (category, key), so a minute-resolution
        timestamp prefix silently overwrote the first entry when a user logged
        twice in quick succession — the entry appeared to vanish.
        """
        health_service.record(db_session, "health_energy", "energy_level", "Low")
        health_service.record(db_session, "health_energy", "energy_level", "High")

        history = health_service.get_history(db_session)

        assert len(history) == 2, "both entries should survive; the second must not overwrite the first"
        assert {r["value"] for r in history} == {"Low", "High"}


class TestHealthSuggestions:
    @pytest.mark.asyncio
    async def test_suggestions_returns_parsed_llm_output(self, health_service, db_session):
        """Regression: this raised TypeError and surfaced as a 500 in the panel.

        ``get_suggestions`` called ``semantic_recall(user_report, ...)`` without
        the ``db`` session the method requires, outside the try/except, so the
        whole endpoint failed before ever reaching the model.
        """
        health_service.record(db_session, "health_sleep", "sleep_hours", "5 hours")

        result = await health_service.get_suggestions(db_session, "I feel tired and have a headache")

        assert result["assessment"] == "You seem run down.", "LLM assessment should be passed through"
        assert result["suggestions"] == ["Sleep earlier tonight."]
        assert result["warnings"] == ["Recurring headaches deserve a doctor."]
        assert result["follow_up_questions"] == ["How much water did you drink?"]
        assert result["user_report"] == "I feel tired and have a headache"

    @pytest.mark.asyncio
    async def test_suggestions_degrade_gracefully_when_the_model_fails(self, health_service, db_session):
        health_service._client.generate = AsyncMock(side_effect=RuntimeError("ollama down"))

        result = await health_service.get_suggestions(db_session, "I feel tired")

        assert result["suggestions"], "fallback must still give the user something actionable"
        assert result["user_report"] == "I feel tired"


class TestHealthDeletion:
    def test_delete_removes_a_health_record(self, health_service, db_session):
        record = health_service.record(db_session, "health_mood", "mood", "Stressed")

        assert health_service.delete(db_session, record["id"]) is True
        assert health_service.get_history(db_session) == []

    def test_delete_refuses_non_health_records(self, health_service, db_session):
        """A health panel must not be able to erase the user's general memories."""
        memory = UserMemoryService().remember(db_session, "preferences", "theme", "dark")

        with pytest.raises(ValueError):
            health_service.delete(db_session, memory.id)


class TestHealthAPI:
    def test_suggestions_endpoint_returns_200(self, client, monkeypatch):
        """End-to-end guard on the route that was returning 500."""
        from app.dependencies import get_health_service

        service = get_health_service()
        monkeypatch.setattr(
            service,
            "_client",
            MagicMock(
                generate=AsyncMock(
                    return_value={
                        "response": json.dumps(
                            {
                                "assessment": "ok",
                                "suggestions": ["rest"],
                                "warnings": [],
                                "follow_up_questions": [],
                            }
                        )
                    }
                )
            ),
        )

        response = client.post("/api/health/suggestions", json={"report": "I feel tired"})

        assert response.status_code == 200, response.text
        assert response.json()["assessment"] == "ok"

    def test_categories_endpoint_lists_every_category(self, client):
        response = client.get("/api/health/categories")

        assert response.status_code == 200
        assert {c["id"] for c in response.json()} >= {"health_sleep", "health_mood"}

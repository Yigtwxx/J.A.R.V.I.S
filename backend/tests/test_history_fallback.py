"""The blocking fallback has to land in the same list as an interactive run.

`POST /api/search/` runs only when DISCOVERY_ENABLED=false. If it kept writing
`search_history` alone, that deployment would have a permanently empty Logs
panel - the bug this change exists to fix, moved to a different path.
"""

from unittest.mock import MagicMock

from app.models.discovery import SearchSession
from app.services.search_orchestration_service import SearchOrchestrationService


def test_fallback_writes_a_conversation_row(db_session):
    service = SearchOrchestrationService.__new__(SearchOrchestrationService)
    service._version = MagicMock()
    service._version.generate_change_report.return_value = None

    response = MagicMock()
    response.model_dump.return_value = {"name": "Ada Lovelace", "ai_response": "..."}

    service.save_history(db_session, "ada lovelace", response)
    db_session.commit()

    row = db_session.query(SearchSession).one()
    assert row.raw_query == "ada lovelace", "the row must carry the text the user typed"
    assert row.interactive is False
    assert row.status == "completed"
    assert row.termination_reason == "blocking_fallback"
    assert row.result_json == {"name": "Ada Lovelace", "ai_response": "..."}
    assert row.target_key == "ada-lovelace:person"


def test_a_snapshot_failure_does_not_lose_the_conversation(db_session):
    service = SearchOrchestrationService.__new__(SearchOrchestrationService)
    service._version = MagicMock()
    service._version.save_snapshot.side_effect = RuntimeError("snapshot backend down")

    response = MagicMock()
    response.model_dump.return_value = {"name": "Ada Lovelace"}

    service.save_history(db_session, "ada lovelace", response)
    db_session.commit()

    assert db_session.query(SearchSession).count() == 1

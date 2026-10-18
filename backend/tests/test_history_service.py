"""The Logs panel's data source.

The panel used to list ``search_history``, which only the blocking fallback ever
wrote, so the interactive path - the default - left it empty. These tests pin the
replacement to ``search_sessions``, and pin the one thing SQLite will not do for
us: detaching evidence when a conversation is deleted.
"""

from datetime import UTC, datetime, timedelta

from app.models.discovery import EvidenceRecord, PlatformOutcome, SearchSession, UserAnswer
from app.services.history_service import (
    clear_conversations,
    delete_conversation,
    get_conversation,
    list_conversations,
)


def make_session(session_id: str, raw_query: str, *, minutes_ago: int = 0, result=None) -> SearchSession:
    return SearchSession(
        id=session_id,
        target_key=f"{raw_query.replace(' ', '-')}:person",
        raw_query=raw_query,
        status="completed",
        started_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        result_json=result,
    )


def test_lists_newest_first(db_session):
    db_session.add(make_session("old", "ada lovelace", minutes_ago=30))
    db_session.add(make_session("new", "grace hopper", minutes_ago=1))
    db_session.commit()

    rows = list_conversations(db_session)

    assert [r.id for r in rows] == ["new", "old"], "the newest conversation must come first"


def test_keeps_repeated_queries_as_separate_conversations(db_session):
    db_session.add(make_session("first", "ada lovelace", minutes_ago=10))
    db_session.add(make_session("second", "ada lovelace", minutes_ago=1))
    db_session.commit()

    rows = list_conversations(db_session)

    assert len(rows) == 2, "two searches for the same person are two conversations, not one"


def test_honours_the_limit(db_session):
    for i in range(5):
        db_session.add(make_session(f"s{i}", f"target {i}", minutes_ago=i))
    db_session.commit()

    assert len(list_conversations(db_session, limit=2)) == 2


def test_skips_a_session_with_no_first_message(db_session):
    db_session.add(make_session("titled", "ada lovelace"))
    db_session.add(make_session("untitled", ""))
    blank = make_session("null-query", "x")
    blank.raw_query = None
    db_session.add(blank)
    db_session.commit()

    assert [r.id for r in list_conversations(db_session)] == ["titled"], (
        "a conversation with no first message cannot be titled or opened"
    )


def test_get_returns_none_for_an_unknown_id(db_session):
    assert get_conversation(db_session, "nope") is None


def test_delete_detaches_evidence_but_keeps_it(db_session):
    db_session.add(make_session("s1", "ada lovelace"))
    db_session.add(
        EvidenceRecord(
            target_key="ada-lovelace:person",
            session_id="s1",
            kind="account",
            subject="github",
            value="ada",
            fingerprint="fp-1",
        )
    )
    db_session.add(UserAnswer(session_id="s1", target_key="ada-lovelace:person", question_id="q1"))
    db_session.add(PlatformOutcome(session_id="s1", platform="github", username="ada", status="found"))
    db_session.commit()

    assert delete_conversation(db_session, "s1") is True
    db_session.commit()

    assert db_session.query(SearchSession).count() == 0
    assert db_session.query(UserAnswer).count() == 0
    assert db_session.query(PlatformOutcome).count() == 0

    evidence = db_session.query(EvidenceRecord).one()
    assert evidence.session_id is None, (
        "SQLite does not enforce the model's ondelete=SET NULL, so the detach must be explicit"
    )


def test_delete_reports_a_missing_conversation(db_session):
    assert delete_conversation(db_session, "nope") is False


def test_clear_removes_every_conversation_and_detaches_evidence(db_session):
    db_session.add(make_session("s1", "ada lovelace"))
    db_session.add(make_session("s2", "grace hopper"))
    db_session.add(
        EvidenceRecord(
            target_key="ada-lovelace:person",
            session_id="s1",
            kind="account",
            subject="github",
            value="ada",
            fingerprint="fp-1",
        )
    )
    db_session.commit()

    assert clear_conversations(db_session) == 2
    db_session.commit()

    assert db_session.query(SearchSession).count() == 0
    assert db_session.query(EvidenceRecord).one().session_id is None

"""The HTTP surface the Logs panel reads.

`has_result` is asserted against ``bool(result_json)`` rather than
``is not None``: ``_serialisable_result`` stores ``{}`` when serialisation fails
and ``/sessions/{id}/result`` answers ``ready: false`` for that empty dict, so
promising a result here would contradict the route that has to hand it over.
"""

from datetime import UTC, datetime, timedelta

from app.models.discovery import EvidenceRecord, SearchSession


def add_session(db, session_id: str, raw_query: str, *, minutes_ago: int = 0, result=None, status="completed"):
    db.add(
        SearchSession(
            id=session_id,
            target_key=f"{raw_query.replace(' ', '-')}:person",
            raw_query=raw_query,
            status=status,
            started_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
            result_json=result,
        )
    )
    db.commit()


def test_lists_conversations_newest_first(client, db_session):
    add_session(db_session, "old", "ada lovelace", minutes_ago=30)
    add_session(db_session, "new", "grace hopper", minutes_ago=1)

    body = client.get("/api/history/").json()

    assert [row["session_id"] for row in body] == ["new", "old"]
    assert body[0]["raw_query"] == "grace hopper"


def test_reports_whether_a_conversation_can_be_opened(client, db_session):
    add_session(db_session, "with", "ada lovelace", minutes_ago=2, result={"name": "Ada"})
    add_session(db_session, "empty", "grace hopper", minutes_ago=1, result={})

    by_id = {row["session_id"]: row for row in client.get("/api/history/").json()}

    assert by_id["with"]["has_result"] is True
    assert by_id["empty"]["has_result"] is False, "an empty result_json is not a result"


def test_limit_is_honoured_and_validated(client, db_session):
    for i in range(4):
        add_session(db_session, f"s{i}", f"target {i}", minutes_ago=i)

    assert len(client.get("/api/history/?limit=2").json()) == 2
    assert client.get("/api/history/?limit=0").status_code == 422


def test_single_conversation_and_its_404(client, db_session):
    add_session(db_session, "s1", "ada lovelace")

    assert client.get("/api/history/s1").json()["raw_query"] == "ada lovelace"
    assert client.get("/api/history/nope").status_code == 404


def test_delete_removes_the_conversation_and_keeps_the_evidence(client, db_session):
    add_session(db_session, "s1", "ada lovelace")
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

    assert client.delete("/api/history/s1").status_code == 204
    assert client.delete("/api/history/s1").status_code == 404

    assert db_session.query(SearchSession).count() == 0
    assert db_session.query(EvidenceRecord).one().session_id is None


def test_clear_empties_the_list(client, db_session):
    add_session(db_session, "s1", "ada lovelace")

    assert client.delete("/api/history/").status_code == 204
    assert client.get("/api/history/").json() == []

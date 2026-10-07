"""Conversation history for the Logs panel.

The panel used to read ``search_history``, a table whose only writer is the
blocking fallback, so the interactive path - the default - left it empty. Every
interactive run already records a ``search_sessions`` row holding the raw query
the user typed and, once the loop finishes, the result. That row *is* the
conversation, so this is what the panel reads.

Deletion detaches evidence explicitly. ``EvidenceRecord.session_id`` declares
``ondelete="SET NULL"``, but ``app/database/connection.py`` never issues
``PRAGMA foreign_keys=ON`` and SQLite leaves foreign keys unenforced by default,
so that clause does nothing at runtime. Without the explicit update the evidence
would keep pointing at a session id that no longer exists.
"""

from sqlalchemy.orm import Session

from app.models.discovery import EvidenceRecord, PlatformOutcome, SearchSession, UserAnswer


def list_conversations(db: Session, limit: int = 100) -> list[SearchSession]:
    """Conversations newest first.

    Deliberately not deduplicated by query text. Searching the same person twice
    produces two conversations with two different answers; collapsing them would
    hide one of the two.
    """
    return (
        db.query(SearchSession)
        .filter(SearchSession.raw_query.isnot(None))
        .filter(SearchSession.raw_query != "")
        .order_by(SearchSession.started_at.desc())
        .limit(limit)
        .all()
    )


def get_conversation(db: Session, session_id: str) -> SearchSession | None:
    return db.query(SearchSession).filter(SearchSession.id == session_id).first()


def _detach(db: Session, session_ids: list[str]) -> None:
    """Drop the rows that belong to a conversation and unlink the ones that outlive it."""
    if not session_ids:
        return
    db.query(UserAnswer).filter(UserAnswer.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.query(PlatformOutcome).filter(PlatformOutcome.session_id.in_(session_ids)).delete(synchronize_session=False)
    # Evidence outlives the conversation that observed it: it is keyed by
    # target_key too, and a later search for the same person still reads it.
    db.query(EvidenceRecord).filter(EvidenceRecord.session_id.in_(session_ids)).update(
        {EvidenceRecord.session_id: None}, synchronize_session=False
    )


def delete_conversation(db: Session, session_id: str) -> bool:
    """Delete one conversation. Returns False when there was nothing to delete."""
    row = get_conversation(db, session_id)
    if row is None:
        return False
    _detach(db, [session_id])
    db.delete(row)
    return True


def clear_conversations(db: Session) -> int:
    """Delete every conversation. Returns how many were removed."""
    session_ids = [row.id for row in db.query(SearchSession.id).all()]
    if not session_ids:
        return 0
    _detach(db, session_ids)
    db.query(SearchSession).filter(SearchSession.id.in_(session_ids)).delete(synchronize_session=False)
    return len(session_ids)

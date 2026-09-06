"""Persistence tables for the OSINT discovery pipeline.

The discovery loop runs for many minutes and outlives the HTTP request that
started it, so its state cannot live in the request scope. These four tables are
that state:

- ``search_sessions``   one run of the loop, and how it ended
- ``evidence``          every fact observed, deduplicated by fingerprint
- ``user_answers``      the disambiguation questions and what the user replied
- ``platform_outcomes`` per-platform verdicts, including ``blocked``

Style follows the rest of ``app/models``: classic Column-based declarative.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class SearchSession(Base):
    """One execution of the discovery loop.

    ``status`` is the lifecycle: running | completed | failed | cancelled |
    abandoned. ``abandoned`` exists because the loop keeps its pending-question
    futures in memory; a process restart kills them, so any row still marked
    running at startup is a zombie and gets swept. The loop stays ``running``
    while it is parked on a question — there is no ``awaiting_answer``, which was
    documented here and written by nothing; the sweep still accepts it so rows
    left by older builds are not stranded.
    """

    __tablename__ = "search_sessions"

    id = Column(String(36), primary_key=True)  # uuid4
    target_key = Column(String(255), nullable=False, index=True)
    raw_query = Column(Text)
    entity_type = Column(String(16), default="person")
    depth = Column(Integer, default=5)
    interactive = Column(Boolean, default=True)
    status = Column(String(20), default="running", index=True)

    anchor_handle = Column(String(255), nullable=True)
    """The handle this session settled on. Used to decide whether evidence from a
    previous session with the same target_key is even about the same person."""

    elected_cluster_id = Column(String(64), nullable=True)
    rounds_completed = Column(Integer, default=0)
    termination_reason = Column(String(48), nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    result_json = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<SearchSession(id='{self.id}', target='{self.target_key}', status='{self.status}')>"


class EvidenceRecord(Base):
    """A single observed fact, unique per (kind, subject, value, source domain).

    The uniqueness is enforced by the DB on ``fingerprint`` rather than by a
    read-then-write check, because rounds run concurrently and a check-then-insert
    race would let duplicates through. See ``app.discovery.evidence.model`` for
    why the fingerprint is keyed on the source *domain* and not the full URL.
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_target_kind", "target_key", "kind"),
        Index("ix_evidence_target_round", "target_key", "round_no"),
    )

    id = Column(Integer, primary_key=True, index=True)
    target_key = Column(String(255), index=True)
    session_id = Column(
        String(36),
        ForeignKey("search_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    round_no = Column(Integer, default=0)

    kind = Column(String(32), index=True)
    subject = Column(String(255))
    value = Column(Text)
    platform = Column(String(32), nullable=True, index=True)

    source_url = Column(Text)
    source_domain = Column(String(255), index=True)
    source_kind = Column(String(24))
    extractor = Column(String(64))
    confidence = Column(Float, default=0.5)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    fingerprint = Column(String(64), nullable=False, unique=True, index=True)
    cluster_id = Column(String(64), nullable=True, index=True)
    superseded_by = Column(Integer, ForeignKey("evidence.id"), nullable=True)
    """Set when a later, better observation replaces this one. Rows are never
    deleted — a retracted fact is still a fact about what a source claimed."""

    raw = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<EvidenceRecord(id={self.id}, kind='{self.kind}', subject='{self.subject}')>"


class UserAnswer(Base):
    """A disambiguation question and the user's reply.

    ``skipped``, ``timed_out`` and ``unknown`` are three different things and are
    stored separately: "I don't know" is real information about the target,
    while a timeout is only information about the user's attention.
    """

    __tablename__ = "user_answers"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("search_sessions.id"), index=True)
    target_key = Column(String(255), index=True)

    question_id = Column(String(36), index=True)
    question_kind = Column(String(32))
    question_text = Column(Text)
    options_json = Column(JSON, nullable=True)

    answer_option_ids = Column(JSON, nullable=True)
    answer_text = Column(Text, nullable=True)
    skipped = Column(Boolean, default=False)
    timed_out = Column(Boolean, default=False)
    unknown = Column(Boolean, default=False)

    asked_at = Column(DateTime(timezone=True), server_default=func.now())
    answered_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<UserAnswer(id={self.id}, question_id='{self.question_id}')>"


class PlatformOutcome(Base):
    """What happened when one platform was checked for one username.

    Stored even when nothing was found, because ``not_found`` and ``blocked`` are
    reportable results. Silently omitting a platform would let the UI imply the
    account does not exist when we were simply refused.
    """

    __tablename__ = "platform_outcomes"
    __table_args__ = (UniqueConstraint("session_id", "platform", "username", name="uq_platform_outcome"),)

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("search_sessions.id"), index=True)
    platform = Column(String(32))
    username = Column(String(255), nullable=True)
    status = Column(String(16))
    detail = Column(Text, nullable=True)
    signals = Column(JSON, nullable=True)
    tier_used = Column(String(12), nullable=True)
    checked_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<PlatformOutcome(platform='{self.platform}', username='{self.username}', status='{self.status}')>"

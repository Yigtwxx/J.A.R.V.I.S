"""add discovery tables

Revision ID: f1a2b3c4d5e6
Revises: b2c3d4e5f6a1
Create Date: 2026-08-11 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "b2c3d4e5f6a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_sessions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("target_key", sa.String(255), nullable=False),
        sa.Column("raw_query", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(16), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=True),
        sa.Column("interactive", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("anchor_handle", sa.String(255), nullable=True),
        sa.Column("elected_cluster_id", sa.String(64), nullable=True),
        sa.Column("rounds_completed", sa.Integer(), nullable=True),
        sa.Column("termination_reason", sa.String(48), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_search_sessions_target_key", "search_sessions", ["target_key"], unique=False)
    op.create_index("ix_search_sessions_status", "search_sessions", ["status"], unique=False)
    op.create_index("ix_search_sessions_started_at", "search_sessions", ["started_at"], unique=False)

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_key", sa.String(255), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("round_no", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=True),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_domain", sa.String(255), nullable=True),
        sa.Column("source_kind", sa.String(24), nullable=True),
        sa.Column("extractor", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "observed_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("cluster_id", sa.String(64), nullable=True),
        sa.Column("superseded_by", sa.Integer(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["search_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by"], ["evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_id", "evidence", ["id"], unique=False)
    op.create_index("ix_evidence_target_key", "evidence", ["target_key"], unique=False)
    op.create_index("ix_evidence_session_id", "evidence", ["session_id"], unique=False)
    op.create_index("ix_evidence_kind", "evidence", ["kind"], unique=False)
    op.create_index("ix_evidence_platform", "evidence", ["platform"], unique=False)
    op.create_index("ix_evidence_source_domain", "evidence", ["source_domain"], unique=False)
    op.create_index("ix_evidence_observed_at", "evidence", ["observed_at"], unique=False)
    op.create_index("ix_evidence_cluster_id", "evidence", ["cluster_id"], unique=False)
    # Deduplication is enforced here, not in Python: rounds insert concurrently.
    op.create_index("ix_evidence_fingerprint", "evidence", ["fingerprint"], unique=True)
    op.create_index("ix_evidence_target_kind", "evidence", ["target_key", "kind"], unique=False)
    op.create_index("ix_evidence_target_round", "evidence", ["target_key", "round_no"], unique=False)

    op.create_table(
        "user_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("target_key", sa.String(255), nullable=True),
        sa.Column("question_id", sa.String(36), nullable=True),
        sa.Column("question_kind", sa.String(32), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("answer_option_ids", sa.JSON(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("skipped", sa.Boolean(), nullable=True),
        sa.Column("timed_out", sa.Boolean(), nullable=True),
        sa.Column("unknown", sa.Boolean(), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["search_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_answers_id", "user_answers", ["id"], unique=False)
    op.create_index("ix_user_answers_session_id", "user_answers", ["session_id"], unique=False)
    op.create_index("ix_user_answers_target_key", "user_answers", ["target_key"], unique=False)
    op.create_index("ix_user_answers_question_id", "user_answers", ["question_id"], unique=False)

    op.create_table(
        "platform_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("tier_used", sa.String(12), nullable=True),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.ForeignKeyConstraint(["session_id"], ["search_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "platform", "username", name="uq_platform_outcome"),
    )
    op.create_index("ix_platform_outcomes_id", "platform_outcomes", ["id"], unique=False)
    op.create_index("ix_platform_outcomes_session_id", "platform_outcomes", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_platform_outcomes_session_id", table_name="platform_outcomes")
    op.drop_index("ix_platform_outcomes_id", table_name="platform_outcomes")
    op.drop_table("platform_outcomes")

    op.drop_index("ix_user_answers_question_id", table_name="user_answers")
    op.drop_index("ix_user_answers_target_key", table_name="user_answers")
    op.drop_index("ix_user_answers_session_id", table_name="user_answers")
    op.drop_index("ix_user_answers_id", table_name="user_answers")
    op.drop_table("user_answers")

    op.drop_index("ix_evidence_target_round", table_name="evidence")
    op.drop_index("ix_evidence_target_kind", table_name="evidence")
    op.drop_index("ix_evidence_fingerprint", table_name="evidence")
    op.drop_index("ix_evidence_cluster_id", table_name="evidence")
    op.drop_index("ix_evidence_observed_at", table_name="evidence")
    op.drop_index("ix_evidence_source_domain", table_name="evidence")
    op.drop_index("ix_evidence_platform", table_name="evidence")
    op.drop_index("ix_evidence_kind", table_name="evidence")
    op.drop_index("ix_evidence_session_id", table_name="evidence")
    op.drop_index("ix_evidence_target_key", table_name="evidence")
    op.drop_index("ix_evidence_id", table_name="evidence")
    op.drop_table("evidence")

    op.drop_index("ix_search_sessions_started_at", table_name="search_sessions")
    op.drop_index("ix_search_sessions_status", table_name="search_sessions")
    op.drop_index("ix_search_sessions_target_key", table_name="search_sessions")
    op.drop_table("search_sessions")

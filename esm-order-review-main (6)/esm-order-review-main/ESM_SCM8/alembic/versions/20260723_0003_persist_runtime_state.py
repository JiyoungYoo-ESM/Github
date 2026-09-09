"""Persist auth sessions, analysis jobs, and latest analysis snapshots."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0003"
down_revision: Union[str, Sequence[str], None] = "20260722_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_digest"),
    )
    op.create_index("ix_auth_sessions_username", "auth_sessions", ["username"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    op.create_table(
        "analysis_jobs",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("client_id", sa.String(length=160), nullable=True),
        sa.Column("security_scope", sa.String(length=160), nullable=True),
        sa.Column("is_latest", sa.Boolean(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_analysis_jobs_kind_scope_updated", "analysis_jobs", ["kind", "security_scope", "updated_at"])
    op.create_index("ix_analysis_jobs_kind_client_updated", "analysis_jobs", ["kind", "client_id", "updated_at"])

    op.create_table(
        "latest_analysis_snapshots",
        sa.Column("snapshot_key", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_key"),
    )


def downgrade() -> None:
    op.drop_table("latest_analysis_snapshots")
    op.drop_index("ix_analysis_jobs_kind_client_updated", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_kind_scope_updated", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_username", table_name="auth_sessions")
    op.drop_table("auth_sessions")

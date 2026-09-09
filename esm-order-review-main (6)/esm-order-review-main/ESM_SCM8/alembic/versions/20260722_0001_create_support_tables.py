"""Create customer-support ticket tables."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260722_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_number", sa.String(length=32), nullable=False),
        sa.Column("requester_name", sa.String(length=100), nullable=False),
        sa.Column("requester_team", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee", sa.String(length=100), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_number"),
    )
    op.create_index("ix_support_tickets_ticket_number", "support_tickets", ["ticket_number"], unique=True)
    op.create_index("ix_support_tickets_status_created_at", "support_tickets", ["status", "created_at"])
    op.create_index("ix_support_tickets_requester_created_at", "support_tickets", ["requester_name", "created_at"])

    op.create_table(
        "support_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_support_attachments_ticket_id", "support_attachments", ["ticket_id"])

    op.create_table(
        "support_status_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_status_events_ticket_id", "support_status_events", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_support_status_events_ticket_id", table_name="support_status_events")
    op.drop_table("support_status_events")
    op.drop_index("ix_support_attachments_ticket_id", table_name="support_attachments")
    op.drop_table("support_attachments")
    op.drop_index("ix_support_tickets_requester_created_at", table_name="support_tickets")
    op.drop_index("ix_support_tickets_status_created_at", table_name="support_tickets")
    op.drop_index("ix_support_tickets_ticket_number", table_name="support_tickets")
    op.drop_table("support_tickets")

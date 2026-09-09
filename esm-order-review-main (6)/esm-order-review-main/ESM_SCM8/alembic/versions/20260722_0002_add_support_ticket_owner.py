"""Add authenticated ownership to customer-support tickets.

Existing rows intentionally keep a NULL owner. A requester name is free-form
display data and cannot be safely mapped to an account, so legacy tickets are
visible only in the administrator's unfiltered view.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260722_0002"
down_revision: Union[str, Sequence[str], None] = "20260722_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "support_tickets",
        sa.Column("owner_username", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_support_tickets_owner_created_at",
        "support_tickets",
        ["owner_username", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_support_tickets_owner_created_at", table_name="support_tickets")
    op.drop_column("support_tickets", "owner_username")

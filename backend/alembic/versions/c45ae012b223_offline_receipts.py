"""Idempotent offline playlist synchronization receipts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c45ae012b223"
down_revision = "b34fd901a112"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "offline_receipts",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("mutation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "resource_id",
            sa.Uuid(),
            sa.ForeignKey("music_resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("offline_receipts")

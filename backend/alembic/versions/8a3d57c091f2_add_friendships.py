"""Friend requests and accepted friendships for profile privacy."""

import sqlalchemy as sa

from alembic import op

revision = "8a3d57c091f2"
down_revision = "7c2a49ef601b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "friendships",
        sa.Column(
            "user_low", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "user_high", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "requester_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("user_low < user_high", name="ck_friendships_ordered_pair"),
        sa.CheckConstraint(
            "requester_id IN (user_low, user_high)", name="ck_friendships_requester"
        ),
        sa.CheckConstraint("status IN ('pending', 'accepted')", name="ck_friendships_status"),
    )
    op.create_index("ix_friendships_user_high", "friendships", ["user_high"])


def downgrade():
    op.drop_index("ix_friendships_user_high", table_name="friendships")
    op.drop_table("friendships")

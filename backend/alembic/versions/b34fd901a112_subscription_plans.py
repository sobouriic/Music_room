"""Persist subscription entitlements."""

import sqlalchemy as sa

from alembic import op

revision = "b34fd901a112"
down_revision = "9c124f30d7aa"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("plan", sa.String(16), nullable=False, server_default="free"))
    op.create_check_constraint("ck_user_plan", "users", "plan IN ('free', 'premium')")


def downgrade():
    op.drop_constraint("ck_user_plan", "users", type_="check")
    op.drop_column("users", "plan")

"""Schedule independent mail retries without blocking other recipients."""

import sqlalchemy as sa

from alembic import op

revision = "7c2a49ef601b"
down_revision = "20c08bdcb574"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_jobs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "mail_jobs",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_mail_jobs_next_attempt_at", "mail_jobs", ["next_attempt_at"])


def downgrade():
    op.drop_index("ix_mail_jobs_next_attempt_at", table_name="mail_jobs")
    op.drop_column("mail_jobs", "next_attempt_at")
    op.drop_column("mail_jobs", "attempts")

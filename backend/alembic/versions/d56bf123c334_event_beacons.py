"""Bluetooth event discovery identifiers."""

import sqlalchemy as sa

from alembic import op

revision = "d56bf123c334"
down_revision = "c45ae012b223"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_beacons",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "resource_id",
            sa.Uuid(),
            sa.ForeignKey("music_resources.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table("event_beacons")

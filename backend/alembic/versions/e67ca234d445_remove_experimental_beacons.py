"""Replace experimental Bluetooth discovery with GPS nearby notifications."""

import sqlalchemy as sa

from alembic import op

revision = "e67ca234d445"
down_revision = "d56bf123c334"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("event_beacons")


def downgrade():
    op.create_table(
        "event_beacons",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "resource_id",
            sa.Uuid(),
            sa.ForeignKey("music_resources.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
    )

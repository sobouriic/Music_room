"""Playlists, events, invitations, votes and delegated playback devices."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "9c124f30d7aa"
down_revision = "8a3d57c091f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "music_resources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("license", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tracks", JSONB(), nullable=False),
        sa.Column("geo_rule", JSONB(), nullable=True),
        sa.Column("current_track", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('playlist', 'event')", name="ck_music_kind"),
        sa.CheckConstraint("visibility IN ('public', 'private')", name="ck_music_visibility"),
        sa.CheckConstraint("license IN ('open', 'invited', 'geo_time')", name="ck_music_license"),
        sa.CheckConstraint("kind = 'event' OR license != 'geo_time'", name="ck_playlist_license"),
        sa.CheckConstraint("version >= 1", name="ck_music_version"),
    )
    op.create_index("ix_music_resources_owner_id", "music_resources", ["owner_id"])
    op.create_index("ix_music_resources_kind", "music_resources", ["kind"])
    op.create_table(
        "music_invitations",
        sa.Column(
            "resource_id",
            sa.Uuid(),
            sa.ForeignKey("music_resources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'accepted')", name="ck_invitation_status"),
    )
    op.create_index("ix_music_invitations_user_id", "music_invitations", ["user_id"])
    op.create_table(
        "track_votes",
        sa.Column(
            "resource_id",
            sa.Uuid(),
            sa.ForeignKey("music_resources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("track_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
    )
    op.create_index("ix_track_votes_user_id", "track_votes", ["user_id"])
    op.create_table(
        "playback_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "delegate_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", JSONB(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_device_version"),
    )
    op.create_index("ix_playback_devices_owner_id", "playback_devices", ["owner_id"])
    op.create_index("ix_playback_devices_delegate_id", "playback_devices", ["delegate_id"])


def downgrade():
    op.drop_table("playback_devices")
    op.drop_table("track_votes")
    op.drop_table("music_invitations")
    op.drop_table("music_resources")

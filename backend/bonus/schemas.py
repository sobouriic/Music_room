from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.music import Version


class OfflineEdit(Version):
    mutation_id: UUID
    track_ids: list[UUID] = Field(max_length=500)

    @field_validator("track_ids")
    @classmethod
    def unique_tracks(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Track IDs must be unique")
        return value

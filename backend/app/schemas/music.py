from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.schemas.auth import Input

Name = Annotated[str, Field(min_length=1, max_length=160)]
Visibility = Literal["public", "private"]


class GeoRule(Input):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)
    radius_m: float = Field(gt=0, le=100000, allow_inf_nan=False)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def interval(self):
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo or self.ends_at <= self.starts_at:
            raise ValueError("Provide timezone-aware start/end times with end after start")
        return self


class PlaylistCreate(Input):
    name: Name
    visibility: Visibility = "public"
    license: Literal["open", "invited"] = "open"

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class EventCreate(PlaylistCreate):
    license: Literal["open", "invited", "geo_time"] = "open"
    geo_rule: GeoRule | None = None

    @model_validator(mode="after")
    def require_geo(self):
        if (self.license == "geo_time") != (self.geo_rule is not None):
            raise ValueError("geo_time requires geo_rule; other licenses must not include it")
        return self


class PlaylistUpdate(PlaylistCreate):
    base_version: int = Field(ge=1)


class EventUpdate(EventCreate):
    base_version: int = Field(ge=1)


class Version(Input):
    base_version: int = Field(ge=1)


class AddTrack(Input):
    deezer_id: int = Field(gt=0, le=2**63 - 1)
    base_version: int = Field(ge=1)


class Advance(Version):
    expected_current_track_id: UUID | None = None


class MoveTrack(Version):
    from_index: int = Field(ge=0)
    to_index: int = Field(ge=0)


class Invite(Version):
    user_id: UUID


class VoteInput(Input):
    lat: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    lng: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)


class CatalogTrack(BaseModel):
    deezer_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=500)
    artist: str = Field(min_length=1, max_length=300)
    duration: int = Field(ge=0, le=86400)
    preview_url: HttpUrl | None = None
    artwork_url: HttpUrl | None = None
    deezer_url: HttpUrl | None = None


class TrackView(CatalogTrack):
    id: UUID
    votes: int = 0
    voted_by_me: bool = False


class ResourceView(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    visibility: Visibility
    license: Literal["open", "invited", "geo_time"]
    version: int
    tracks: list[TrackView]
    geo_rule: GeoRule | None = None
    current_track: TrackView | None = None


class InvitationView(BaseModel):
    user_id: UUID
    status: Literal["pending", "accepted"]


class DeviceCreate(Input):
    name: Name
    _meaningful_name = field_validator("name")(PlaylistCreate.meaningful_name.__func__)


class DelegateInput(Input):
    friend_id: UUID | None
    base_version: int = Field(ge=1)


class DeviceControl(Version):
    action: Literal["play", "pause", "stop"]
    deezer_id: int | None = Field(default=None, gt=0, le=2**63 - 1)

    @model_validator(mode="after")
    def playing_track(self):
        if self.action == "play" and self.deezer_id is None:
            raise ValueError("play requires deezer_id")
        if self.action != "play" and self.deezer_id is not None:
            raise ValueError("Only play accepts deezer_id")
        return self


class DeviceView(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    friend_id: UUID | None
    version: int
    state: dict


class InboxInvitation(InvitationView):
    resource_id: UUID
    kind: Literal["playlist", "event"]
    name: str

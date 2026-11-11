from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.auth import Input


class PublicProfile(Input):
    display_name: str = Field(default="", max_length=100)
    bio: str = Field(default="", max_length=1000)


class FriendsProfile(Input):
    location: str = Field(default="", max_length=100)


class PrivateProfile(Input):
    notes: str = Field(default="", max_length=1000)


class ProfileUpdate(Input):
    public: PublicProfile | None = None
    friends_only: FriendsProfile | None = None
    private: PrivateProfile | None = None
    music_preferences: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = Field(
        default=None, max_length=50
    )


class UserView(BaseModel):
    id: UUID
    email: str
    verified: bool
    has_password: bool
    providers: list[str]
    public: PublicProfile
    friends_only: FriendsProfile
    private: PrivateProfile
    music_preferences: list[str]


class PublicUserView(BaseModel):
    id: UUID
    public: PublicProfile


class FriendsUserView(PublicUserView):
    friends_only: FriendsProfile

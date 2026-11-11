from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.auth import Input


class FriendRequest(Input):
    user_id: UUID


class FriendshipView(BaseModel):
    user_id: UUID
    requester_id: UUID
    status: Literal["pending", "accepted"]

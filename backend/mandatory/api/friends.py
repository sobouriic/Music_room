from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import current_user, sensitive
from app.db.session import get_db
from app.schemas.auth import Message
from app.schemas.friend import FriendRequest, FriendshipView
from mandatory.services import friend_service

router = APIRouter(prefix="/friends", tags=["friends"], dependencies=[Depends(sensitive)])


@router.get("", response_model=list[FriendshipView])
def friends(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return friend_service.listing(db, user, "accepted", limit, offset)


@router.get("/requests", response_model=list[FriendshipView])
def requests(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return friend_service.listing(db, user, "pending", limit, offset)


@router.post("/requests", response_model=FriendshipView, status_code=201)
def request(data: FriendRequest, user=Depends(current_user), db=Depends(get_db, scope="function")):
    return friend_service.request(db, user, data.user_id)


@router.post("/{user_id}/accept", response_model=FriendshipView)
def accept(user_id: UUID, user=Depends(current_user), db=Depends(get_db, scope="function")):
    return friend_service.accept(db, user, user_id)


@router.delete("/{user_id}", response_model=Message)
def remove(user_id: UUID, user=Depends(current_user), db=Depends(get_db, scope="function")):
    return friend_service.remove(db, user, user_id)

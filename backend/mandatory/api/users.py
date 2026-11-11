from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import current_user, music_sensitive
from app.db.session import get_db
from app.schemas.user import FriendsUserView, ProfileUpdate, PublicUserView, UserView
from mandatory.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserView)
def me(user=Depends(current_user), db=Depends(get_db, scope="function")):
    return user_service.own_profile(db, user)


@router.patch("/me", response_model=UserView)
def update_me(
    data: ProfileUpdate, user=Depends(current_user), db=Depends(get_db, scope="function")
):
    return user_service.update_profile(db, user, data)


@router.get("/{user_id}/public", response_model=PublicUserView)
def public(user_id: UUID, user=Depends(current_user), db=Depends(get_db, scope="function")):
    return user_service.public_profile(db, user_id)


@router.get("/{user_id}/friends-only", response_model=FriendsUserView)
def friends_only(user_id: UUID, user=Depends(current_user), db=Depends(get_db, scope="function")):
    return user_service.friends_profile(db, user, user_id)


@router.get("/search", response_model=list[PublicUserView], dependencies=[Depends(music_sensitive)])
def search_users(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return user_service.search_users(db, user, q.strip(), limit, offset)

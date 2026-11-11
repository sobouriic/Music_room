from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import current_user, music_sensitive
from app.db.session import get_db
from app.schemas.music import ResourceView
from bonus.offline_service import sync_offline
from bonus.schemas import OfflineEdit
from bonus.subscription_service import require_premium

router = APIRouter(tags=["offline"], dependencies=[Depends(music_sensitive)])


@router.post("/playlists/{resource_id}/offline", response_model=ResourceView)
def sync_playlist(
    resource_id: UUID,
    data: OfflineEdit,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    require_premium(db, user)
    return sync_offline(db, resource_id, user, data)

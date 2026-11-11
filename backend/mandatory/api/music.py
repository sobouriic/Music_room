from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from starlette.convertors import Convertor, register_url_convertor

from app.api.dependencies import current_user, music_sensitive
from app.db.session import get_db
from app.schemas.auth import Message
from app.schemas.music import (
    AddTrack,
    Advance,
    CatalogTrack,
    DelegateInput,
    DeviceControl,
    DeviceCreate,
    DeviceView,
    EventCreate,
    EventUpdate,
    InboxInvitation,
    InvitationView,
    Invite,
    MoveTrack,
    PlaylistCreate,
    PlaylistUpdate,
    ResourceView,
    VoteInput,
)
from mandatory.services import deezer_service as deezer
from mandatory.services import device_service as devices
from mandatory.services import music_service as service


class CollectionConvertor(Convertor):
    regex = "playlists|events"

    def convert(self, value):
        return value

    def to_string(self, value):
        return value


register_url_convertor("music_collection", CollectionConvertor())


router = APIRouter(tags=["music"], dependencies=[Depends(music_sensitive), Depends(current_user)])
Kind = Literal["playlists", "events"]


def kind(value):
    return "playlist" if value == "playlists" else "event"


@router.get("/tracks/search", response_model=list[CatalogTrack])
def search_tracks(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=10000),
):
    if len(q.strip()) < 2:
        from app.core.exceptions import fail

        fail(422, "invalid_search", "Enter at least two characters")
    return deezer.search(q.strip(), limit, offset)


@router.get("/tracks/{deezer_id}", response_model=CatalogTrack)
def get_track(deezer_id: int):
    if deezer_id <= 0 or deezer_id > 2**63 - 1:
        from app.core.exceptions import fail

        fail(422, "invalid_track", "Invalid Deezer ID")
    return deezer.track(deezer_id)


@router.post("/playlists", response_model=ResourceView, status_code=201)
def create_playlist(
    data: PlaylistCreate, user=Depends(current_user), db=Depends(get_db, scope="function")
):
    return service.create(db, "playlist", user, data)


@router.post("/events", response_model=ResourceView, status_code=201)
def create_event(
    data: EventCreate, user=Depends(current_user), db=Depends(get_db, scope="function")
):
    return service.create(db, "event", user, data)


@router.put("/playlists/{resource_id}", response_model=ResourceView)
def update_playlist(
    resource_id: UUID,
    data: PlaylistUpdate,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.update(db, service.load(db, "playlist", resource_id, user, True), user, data)


@router.put("/events/{resource_id}", response_model=ResourceView)
def update_event(
    resource_id: UUID,
    data: EventUpdate,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.update(db, service.load(db, "event", resource_id, user, True), user, data)


@router.get("/{collection:music_collection}", response_model=list[ResourceView])
def list_resources(
    collection: Kind,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, min_length=2, max_length=100),
):
    return service.listing(db, kind(collection), user, limit, offset, q)


@router.get("/{collection:music_collection}/{resource_id}", response_model=ResourceView)
def get_resource(
    collection: Kind,
    resource_id: UUID,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.view(db, service.load(db, kind(collection), resource_id, user), user)


@router.delete("/{collection:music_collection}/{resource_id}", response_model=Message)
def delete_resource(
    collection: Kind,
    resource_id: UUID,
    base_version: int = Query(ge=1),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    resource = service.load(db, kind(collection), resource_id, user, True)
    service.owner(resource, user)
    service.version(resource, base_version)
    db.delete(resource)
    return {"message": "Resource deleted"}


@router.post("/{collection:music_collection}/{resource_id}/tracks", response_model=ResourceView)
def add_track(
    collection: Kind,
    resource_id: UUID,
    data: AddTrack,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    # Check access before calling the provider; recheck with a lock after the network call.
    resource = service.load(db, kind(collection), resource_id, user)
    service.editable(db, resource, user)
    service.version(resource, data.base_version)
    metadata = deezer.track(data.deezer_id)
    return service.add(
        db, service.load(db, kind(collection), resource_id, user, True), user, data, metadata
    )


@router.post("/playlists/{resource_id}/tracks/move", response_model=ResourceView)
def move_track(
    resource_id: UUID,
    data: MoveTrack,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.move(db, service.load(db, "playlist", resource_id, user, True), user, data)


@router.delete(
    "/{collection:music_collection}/{resource_id}/tracks/{track_id}", response_model=ResourceView
)
def remove_track(
    collection: Kind,
    resource_id: UUID,
    track_id: UUID,
    base_version: int = Query(ge=1),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.remove_track(
        db,
        service.load(db, kind(collection), resource_id, user, True),
        user,
        track_id,
        base_version,
    )


@router.get(
    "/{collection:music_collection}/{resource_id}/invitations", response_model=list[InvitationView]
)
def list_invitations(
    collection: Kind,
    resource_id: UUID,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.invitation_list(db, service.load(db, kind(collection), resource_id, user), user)


@router.post(
    "/{collection:music_collection}/{resource_id}/invitations",
    response_model=InvitationView,
    status_code=201,
)
def invite(
    collection: Kind,
    resource_id: UUID,
    data: Invite,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.invite(
        db, service.load(db, kind(collection), resource_id, user, True), user, data
    )


@router.post(
    "/{collection:music_collection}/{resource_id}/invitations/accept", response_model=ResourceView
)
def accept_invitation(
    collection: Kind,
    resource_id: UUID,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.accept_invitation(
        db, service.load(db, kind(collection), resource_id, user, True), user
    )


@router.delete(
    "/{collection:music_collection}/{resource_id}/invitations/{user_id}", response_model=Message
)
def uninvite(
    collection: Kind,
    resource_id: UUID,
    user_id: UUID,
    base_version: int = Query(ge=1),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.uninvite(
        db, service.load(db, kind(collection), resource_id, user, True), user, user_id, base_version
    )


@router.post("/events/{resource_id}/tracks/{track_id}/votes", response_model=ResourceView)
def vote(
    resource_id: UUID,
    track_id: UUID,
    data: VoteInput,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.vote(
        db, service.load(db, "event", resource_id, user, True), user, track_id, data
    )


@router.delete("/events/{resource_id}/tracks/{track_id}/votes", response_model=ResourceView)
def unvote(
    resource_id: UUID,
    track_id: UUID,
    data: VoteInput,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.vote(
        db, service.load(db, "event", resource_id, user, True), user, track_id, data, True
    )


@router.post("/events/{resource_id}/advance", response_model=ResourceView)
def advance(
    resource_id: UUID,
    data: Advance,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.advance(
        db,
        service.load(db, "event", resource_id, user, True),
        user,
        data.base_version,
        data.expected_current_track_id,
    )


# Device routes are registered separately to avoid the generic resource GET routes.
device_router = APIRouter(
    prefix="/devices", tags=["devices"], dependencies=[Depends(music_sensitive)]
)


@device_router.get("", response_model=list[DeviceView])
def list_devices(
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return devices.listing(db, user, limit, offset)


@device_router.post("", response_model=DeviceView, status_code=201)
def create_device(
    data: DeviceCreate, user=Depends(current_user), db=Depends(get_db, scope="function")
):
    return devices.create(db, user, data)


@device_router.get("/{device_id}", response_model=DeviceView)
def get_device(device_id: UUID, user=Depends(current_user), db=Depends(get_db, scope="function")):
    return devices.view(db, devices.load(db, device_id, user))


@device_router.put("/{device_id}/delegation", response_model=DeviceView)
def delegate(
    device_id: UUID,
    data: DelegateInput,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return devices.delegate(db, devices.load(db, device_id, user, True), user, data)


@device_router.post("/{device_id}/control", response_model=DeviceView)
def control(
    device_id: UUID,
    data: DeviceControl,
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    device = devices.load(db, device_id, user)
    service.version(device, data.base_version)
    track = deezer.track(data.deezer_id) if data.deezer_id else None
    return devices.control(db, devices.load(db, device_id, user, True), data, track)


@device_router.delete("/{device_id}", response_model=Message)
def delete_device(
    device_id: UUID,
    base_version: int = Query(ge=1),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    device = devices.load(db, device_id, user, True)
    service.owner(device, user)
    service.version(device, base_version)
    db.delete(device)
    return {"message": "Device deleted"}


@router.get("/invitations", response_model=list[InboxInvitation])
def invitation_inbox(
    status: Literal["pending", "accepted"] = "pending",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    return service.invitation_inbox(db, user, status, limit, offset)

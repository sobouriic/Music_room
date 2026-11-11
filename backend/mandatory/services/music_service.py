import math
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select

from app.core.exceptions import fail
from app.core.security import now
from app.models.entities import MusicInvitation, MusicResource, TrackVote, User
from app.schemas.music import GeoRule


def member(db, resource, user):
    return (
        db.scalar(
            select(MusicInvitation.user_id).where(
                MusicInvitation.resource_id == resource.id,
                MusicInvitation.user_id == user.id,
            )
        )
        is not None
    )


def visible(db, resource, user):
    return (
        resource.owner_id == user.id
        or resource.visibility == "public"
        or member(db, resource, user)
    )


def load(db, kind, resource_id, user, lock=False):
    statement = (
        select(MusicResource)
        .join(User, User.id == MusicResource.owner_id)
        .where(
            MusicResource.id == resource_id,
            MusicResource.kind == kind,
            User.disabled.is_(False),
        )
    )
    if lock:
        statement = statement.with_for_update(of=MusicResource)
    resource = db.scalar(statement.execution_options(populate_existing=True))
    if not resource or not visible(db, resource, user):
        fail(404, "not_found", "Resource not found")
    return resource


def owner(resource, user):
    if resource.owner_id != user.id:
        fail(403, "forbidden", "Only the owner can manage this resource")


def version(resource, base):
    if resource.version != base:
        fail(409, "version_conflict", "Resource changed; reload before retrying")


def editable(db, resource, user):
    if (
        resource.owner_id != user.id
        and resource.license == "invited"
        and not member(db, resource, user)
    ):
        fail(403, "forbidden", "An invitation is required")


def view(db, resource, user):
    votes, mine = {}, set()
    if resource.kind == "event":
        for vote in db.scalars(select(TrackVote).where(TrackVote.resource_id == resource.id)):
            key = str(vote.track_id)
            votes[key] = votes.get(key, 0) + 1
            if vote.user_id == user.id:
                mine.add(key)
    tracks = [
        {**t, "votes": votes.get(t["id"], 0), "voted_by_me": t["id"] in mine}
        for t in resource.tracks
    ]
    if resource.kind == "event":
        # Stable insertion order breaks vote ties.
        tracks.sort(key=lambda t: -t["votes"])
    return {
        "id": resource.id,
        "owner_id": resource.owner_id,
        "name": resource.name,
        "visibility": resource.visibility,
        "license": resource.license,
        "version": resource.version,
        "geo_rule": resource.geo_rule,
        "tracks": tracks,
        "current_track": resource.current_track,
    }


def listing(db, kind, user, limit, offset, query=None):
    invited = select(MusicInvitation.resource_id).where(MusicInvitation.user_id == user.id)
    statement = (
        select(MusicResource)
        .join(User, User.id == MusicResource.owner_id)
        .where(
            MusicResource.kind == kind,
            User.disabled.is_(False),
            or_(
                MusicResource.visibility == "public",
                MusicResource.owner_id == user.id,
                MusicResource.id.in_(invited),
            ),
        )
    )
    if query:
        statement = statement.where(MusicResource.name.icontains(query, autoescape=True))
    return [
        view(db, r, user)
        for r in db.scalars(
            statement.order_by(MusicResource.created_at, MusicResource.id)
            .limit(limit)
            .offset(offset)
        )
    ]


def create(db, kind, user, data):
    resource = MusicResource(
        owner_id=user.id,
        kind=kind,
        name=data.name,
        visibility=data.visibility,
        license=data.license,
    )
    rule = getattr(data, "geo_rule", None)
    resource.geo_rule = rule.model_dump(mode="json") if rule else None
    db.add(resource)
    db.flush()
    return view(db, resource, user)


def update(db, resource, user, data):
    owner(resource, user)
    version(resource, data.base_version)
    resource.name, resource.visibility, resource.license = data.name, data.visibility, data.license
    rule = getattr(data, "geo_rule", None)
    resource.geo_rule = rule.model_dump(mode="json") if rule else None
    resource.version += 1
    db.flush()
    return view(db, resource, user)


def add(db, resource, user, data, track):
    editable(db, resource, user)
    version(resource, data.base_version)
    if len(resource.tracks) >= 500:
        fail(409, "track_limit", "Resource contains the maximum of 500 tracks")
    if any(t["deezer_id"] == data.deezer_id for t in resource.tracks):
        fail(409, "duplicate_track", "Track is already in this resource")
    resource.tracks = [*resource.tracks, {**track, "id": str(uuid4())}]
    resource.version += 1
    db.flush()
    return view(db, resource, user)


def move(db, resource, user, data):
    editable(db, resource, user)
    version(resource, data.base_version)
    tracks = list(resource.tracks)
    if max(data.from_index, data.to_index) >= len(tracks):
        fail(400, "invalid_position", "Track position is outside the playlist")
    tracks.insert(data.to_index, tracks.pop(data.from_index))
    resource.tracks = tracks
    resource.version += 1
    db.flush()
    return view(db, resource, user)


def remove_track(db, resource, user, track_id, base_version):
    if resource.kind == "event":
        owner(resource, user)
    else:
        editable(db, resource, user)
    version(resource, base_version)
    if not any(t["id"] == str(track_id) for t in resource.tracks):
        fail(404, "not_found", "Track not found")
    resource.tracks = [t for t in resource.tracks if t["id"] != str(track_id)]
    db.execute(
        delete(TrackVote).where(
            TrackVote.resource_id == resource.id, TrackVote.track_id == track_id
        )
    )
    resource.version += 1
    db.flush()
    return view(db, resource, user)


def check_geo(resource, data):
    rule = GeoRule.model_validate(resource.geo_rule)
    if not rule.starts_at <= now() < rule.ends_at or data.lat is None or data.lng is None:
        fail(
            403, "outside_voting_area", "Voting requires venue coordinates during the voting window"
        )
    lat1, lat2 = math.radians(rule.lat), math.radians(data.lat)
    dlat, dlng = lat2 - lat1, math.radians(data.lng - rule.lng)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    distance = 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))
    if distance > rule.radius_m:
        fail(403, "outside_voting_area", "Outside the voting venue")


def vote(db, resource, user, track_id, data, undo=False):
    editable(db, resource, user)
    if resource.license == "geo_time":
        check_geo(resource, data)
    if not any(t["id"] == str(track_id) for t in resource.tracks):
        fail(404, "not_found", "Track not found")
    key = (resource.id, track_id, user.id)
    existing = db.get(TrackVote, key)
    if undo:
        if not existing:
            fail(404, "not_found", "Vote not found")
        db.delete(existing)
    else:
        if existing:
            fail(409, "already_voted", "You already voted for this track")
        db.add(TrackVote(resource_id=resource.id, track_id=track_id, user_id=user.id))
    resource.version += 1
    db.flush()
    return view(db, resource, user)


def invite(db, resource, user, data):
    owner(resource, user)
    version(resource, data.base_version)
    target = db.get(User, data.user_id)
    if not target or target.disabled or not target.verified:
        fail(404, "not_found", "User not found")
    if target.id == user.id:
        fail(400, "invalid_invitation", "Owner already has access")
    if db.get(MusicInvitation, (resource.id, target.id)):
        fail(409, "already_invited", "User already invited")
    db.add(MusicInvitation(resource_id=resource.id, user_id=target.id))
    resource.version += 1
    db.flush()
    return {"user_id": target.id, "status": "pending"}


def invitation_list(db, resource, user):
    owner(resource, user)
    return [
        {"user_id": i.user_id, "status": i.status}
        for i in db.scalars(
            select(MusicInvitation)
            .where(MusicInvitation.resource_id == resource.id)
            .order_by(MusicInvitation.user_id)
        )
    ]


def uninvite(db, resource, user, target_id, base_version):
    if target_id != user.id:
        owner(resource, user)
    version(resource, base_version)
    invitation = db.get(MusicInvitation, (resource.id, target_id))
    if not invitation:
        fail(404, "not_found", "Invitation not found")
    db.delete(invitation)
    resource.version += 1
    return {"message": "Invitation removed"}


def accept_invitation(db, resource, user):
    invitation = db.get(MusicInvitation, (resource.id, user.id))
    if not invitation:
        fail(404, "not_found", "Invitation not found")
    if invitation.status == "accepted":
        return view(db, resource, user)
    invitation.status = "accepted"
    resource.version += 1
    db.flush()
    return view(db, resource, user)


def advance(db, resource, user, base_version, expected_current_track_id=None):
    owner(resource, user)
    version(resource, base_version)
    if expected_current_track_id is not None and (
        not resource.current_track or resource.current_track["id"] != str(expected_current_track_id)
    ):
        fail(409, "version_conflict", "Current track changed; reload playback")
    tracks = view(db, resource, user)["tracks"]
    if not tracks:
        fail(409, "empty_queue", "No queued tracks")
    resource.current_track = {k: v for k, v in tracks[0].items() if k != "voted_by_me"}
    selected_id = UUID(tracks[0]["id"])
    resource.tracks = [t for t in resource.tracks if t["id"] != str(selected_id)]
    db.execute(
        delete(TrackVote).where(
            TrackVote.resource_id == resource.id, TrackVote.track_id == selected_id
        )
    )
    resource.version += 1
    db.flush()
    return view(db, resource, user)


def invitation_inbox(db, user, status, limit, offset):
    rows = db.execute(
        select(MusicInvitation, MusicResource)
        .join(MusicResource, MusicResource.id == MusicInvitation.resource_id)
        .join(User, User.id == MusicResource.owner_id)
        .where(
            MusicInvitation.user_id == user.id,
            MusicInvitation.status == status,
            User.disabled.is_(False),
        )
        .order_by(MusicResource.created_at, MusicResource.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "user_id": invite.user_id,
            "status": invite.status,
            "resource_id": resource.id,
            "kind": resource.kind,
            "name": resource.name,
        }
        for invite, resource in rows
    ]

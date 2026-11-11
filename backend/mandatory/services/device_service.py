from sqlalchemy import or_, select

from app.core.exceptions import fail
from app.models.entities import Friendship, PlaybackDevice, User
from mandatory.services.friend_service import pair_ids
from mandatory.services.music_service import owner, version


def friends(db, a, b):
    if b is None:
        return False
    low, high = pair_ids(a, b)
    return (
        db.scalar(
            select(Friendship.user_low)
            .join(User, User.id == b)
            .where(
                Friendship.user_low == low,
                Friendship.user_high == high,
                Friendship.status == "accepted",
                User.disabled.is_(False),
            )
        )
        is not None
    )


def load(db, device_id, user, lock=False):
    query = (
        select(PlaybackDevice)
        .join(User, User.id == PlaybackDevice.owner_id)
        .where(PlaybackDevice.id == device_id, User.disabled.is_(False))
    )
    if lock:
        query = query.with_for_update(of=PlaybackDevice)
    device = db.scalar(query.execution_options(populate_existing=True))
    if not device or not (
        device.owner_id == user.id
        or (device.delegate_id == user.id and friends(db, device.owner_id, user.id))
    ):
        fail(404, "not_found", "Device not found")
    return device


def view(db, device):
    delegate = device.delegate_id if friends(db, device.owner_id, device.delegate_id) else None
    return {
        "id": device.id,
        "owner_id": device.owner_id,
        "name": device.name,
        "friend_id": delegate,
        "version": device.version,
        "state": device.state,
    }


def listing(db, user, limit, offset):
    result = []
    for device in db.scalars(
        select(PlaybackDevice)
        .where(
            or_(
                PlaybackDevice.owner_id == user.id,
                PlaybackDevice.delegate_id == user.id,
            )
        )
        .order_by(PlaybackDevice.id)
    ):
        target = db.get(User, device.owner_id)
        if (
            target
            and not target.disabled
            and (device.owner_id == user.id or friends(db, device.owner_id, user.id))
        ):
            result.append(view(db, device))
    return result[offset : offset + limit]


def create(db, user, data):
    device = PlaybackDevice(owner_id=user.id, name=data.name)
    db.add(device)
    db.flush()
    return view(db, device)


def delegate(db, device, user, data):
    owner(device, user)
    version(device, data.base_version)
    if data.friend_id is not None and not friends(db, user.id, data.friend_id):
        fail(403, "forbidden", "Delegate must be an accepted enabled friend")
    device.delegate_id = data.friend_id
    device.version += 1
    db.flush()
    return view(db, device)


def control(db, device, data, track=None):
    version(device, data.base_version)
    if data.action == "play":
        device.state = {"action": "play", "track": track}
    else:
        device.state = {"action": data.action, "track": device.state.get("track")}
    device.version += 1
    db.flush()
    return view(db, device)

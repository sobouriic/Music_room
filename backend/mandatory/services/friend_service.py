from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from app.core.exceptions import fail
from app.db.session import lock_user
from app.models.entities import Friendship, User


def pair_ids(a, b):
    return tuple(sorted((a, b)))


def view(relation, viewer_id):
    return {
        "user_id": relation.user_high if viewer_id == relation.user_low else relation.user_low,
        "requester_id": relation.requester_id,
        "status": relation.status,
    }


def locked_pair(db, viewer, target_id, allow_inactive=False):
    if viewer.id == target_id:
        fail(400, "invalid_friendship", "Choose another user")
    low, high = pair_ids(viewer.id, target_id)
    # Serialize pair mutations, including absent rows; consistent order avoids deadlocks.
    locked = {key: lock_user(db, key) for key in (low, high)}
    if not locked[viewer.id] or locked[viewer.id].disabled or not locked[viewer.id].verified:
        fail(403, "forbidden", "Verified account required")
    target = locked[target_id]
    if not target or (not allow_inactive and (target.disabled or not target.verified)):
        fail(404, "not_found", "User not found")
    return low, high


def request(db, viewer, target_id):
    key = locked_pair(db, viewer, target_id)
    relation = db.get(Friendship, key)
    if relation:
        fail(409, "friendship_exists", "A friendship or request already exists")
    relation = Friendship(user_low=key[0], user_high=key[1], requester_id=viewer.id)
    db.add(relation)
    db.flush()
    return view(relation, viewer.id)


def accept(db, viewer, target_id):
    key = locked_pair(db, viewer, target_id)
    relation = db.get(Friendship, key)
    if not relation:
        fail(404, "not_found", "Friend request not found")
    if relation.status != "pending":
        fail(409, "friendship_exists", "Already friends")
    if relation.requester_id == viewer.id:
        fail(403, "forbidden", "Only the recipient can accept a request")
    relation.status = "accepted"
    db.flush()
    return view(relation, viewer.id)


def remove(db, viewer, target_id):
    key = locked_pair(db, viewer, target_id, allow_inactive=True)
    relation = db.get(Friendship, key)
    if not relation:
        fail(404, "not_found", "Friendship or request not found")
    db.delete(relation)
    return {"message": "Friendship or request removed"}


def listing(db, viewer, status, limit, offset):
    low_user, high_user = aliased(User), aliased(User)
    relations = db.scalars(
        select(Friendship)
        .join(low_user, low_user.id == Friendship.user_low)
        .join(high_user, high_user.id == Friendship.user_high)
        .where(
            or_(Friendship.user_low == viewer.id, Friendship.user_high == viewer.id),
            Friendship.status == status,
            low_user.disabled.is_(False),
            high_user.disabled.is_(False),
        )
        .order_by(Friendship.created_at, Friendship.user_low, Friendship.user_high)
        .offset(offset)
        .limit(limit)
    )
    return [view(r, viewer.id) for r in relations]

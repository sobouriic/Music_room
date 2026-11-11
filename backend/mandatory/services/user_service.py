from sqlalchemy import and_, or_, select

from app.core.exceptions import fail
from app.db.session import lock_user
from app.models.entities import Friendship, OAuthIdentity, Profile, User
from app.schemas.user import ProfileUpdate


def own_profile(db, user):
    profile = db.get(Profile, user.id)
    providers = db.scalars(select(OAuthIdentity.provider).where(OAuthIdentity.user_id == user.id))
    return {
        "id": user.id,
        "email": user.email,
        "verified": user.verified,
        "has_password": user.password_hash is not None,
        "providers": list(providers),
        "public": profile.public,
        "friends_only": profile.friends_only,
        "private": profile.private,
        "music_preferences": profile.music_preferences,
    }


def update_profile(db, user, data: ProfileUpdate):
    lock_user(db, user.id)
    profile = db.get(Profile, user.id)
    for name in ("public", "friends_only", "private"):
        section = getattr(data, name)
        if section is not None:
            setattr(
                profile, name, {**getattr(profile, name), **section.model_dump(exclude_unset=True)}
            )
    if data.music_preferences is not None:
        profile.music_preferences = data.music_preferences
    db.flush()
    return own_profile(db, user)


def public_profile(db, user_id):
    user = db.get(User, user_id)
    if not user or user.disabled:
        fail(404, "not_found", "User not found")
    profile = db.get(Profile, user_id)
    return {"id": user.id, "public": profile.public}


def friends_profile(db, viewer, user_id):
    # A single statement evaluates accepted membership and profile visibility together.
    friendship = (
        select(Friendship.user_low)
        .where(
            Friendship.status == "accepted",
            or_(
                and_(Friendship.user_low == viewer.id, Friendship.user_high == user_id),
                and_(Friendship.user_high == viewer.id, Friendship.user_low == user_id),
            ),
        )
        .exists()
    )
    profile = db.scalar(
        select(Profile)
        .join(User, User.id == Profile.user_id)
        .where(
            User.id == user_id,
            User.disabled.is_(False),
            or_(User.id == viewer.id, friendship),
        )
    )
    if profile is None:
        fail(403, "forbidden", "Friends-only profile is not available")
    return {"id": user_id, "public": profile.public, "friends_only": profile.friends_only}


def search_users(db, viewer, query, limit, offset):
    if len(query) < 2:
        fail(422, "invalid_search", "Enter at least two characters")
    names = Profile.public["display_name"].astext.icontains(query, autoescape=True)
    results = db.execute(
        select(User.id, Profile.public)
        .join(Profile, Profile.user_id == User.id)
        .where(User.id != viewer.id, User.disabled.is_(False), User.verified.is_(True), names)
        .order_by(Profile.public["display_name"].astext, User.id)
        .offset(offset)
        .limit(limit)
    )
    return [{"id": row[0], "public": row[1]} for row in results]

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import fail
from app.core.security import access_token, digest, hasher, now, opaque, verify_password
from app.db.session import lock_user
from app.models.entities import ActionToken, OAuthIdentity, RefreshSession
from app.repositories import users
from mandatory.services.email_service import queue_mail

GENERIC = {"message": "If the account is eligible, an email will be sent"}


def issue_pair(db, user, family_id=None, expires_at=None):
    raw = opaque()
    session = RefreshSession(
        user_id=user.id,
        token_digest=digest(raw),
        expires_at=expires_at or now() + timedelta(days=get_settings().refresh_days),
    )
    if family_id:
        session.family_id = family_id
    db.add(session)
    db.flush()
    return {
        "access_token": access_token(user.id, session.id, user.auth_version),
        "refresh_token": raw,
        "token_type": "bearer",
        "expires_in": get_settings().access_seconds,
    }


def register(db, data):
    # Hash even for existing addresses to reduce timing differences.
    hashed = hasher.hash(data.password)
    existing = users.by_email(db, data.email)
    if existing:
        if not existing.disabled and not existing.verified:
            queue_mail(db, existing, "verify")
        return GENERIC
    try:
        with db.begin_nested():
            user = users.create(db, data.email, hashed)
            queue_mail(db, user, "verify")
    except IntegrityError:
        pass  # Unique constraint handles concurrent registrations; response is enumeration-safe.
    return GENERIC


def login(db, data):
    candidate = users.by_email(db, data.email)
    # Always verify one Argon2 hash even for nonexistent and Google-only users.
    if not verify_password(data.password, candidate.password_hash if candidate else None):
        fail(401, "invalid_credentials", "Invalid email or password")
    checked_hash = candidate.password_hash
    user = lock_user(db, candidate.id)
    # Recheck after lock to avoid issuing sessions across a concurrent password change.
    if user.disabled or not user.verified or user.password_hash != checked_hash:
        fail(401, "invalid_credentials", "Invalid email or password")
    return issue_pair(db, user)


def request_email(db, email, kind):
    user = users.by_email(db, email)
    if user and not user.disabled:
        if (kind == "verify" and not user.verified) or (
            kind == "reset" and user.password_hash is not None
        ):
            queue_mail(db, user, kind)
    return GENERIC


def consume_action(db, raw, kind):
    candidate = db.scalar(
        select(ActionToken).where(ActionToken.token_digest == digest(raw), ActionToken.kind == kind)
    )
    if candidate is None:
        fail(400, "invalid_token", "Invalid or expired token")
    user = lock_user(db, candidate.user_id)
    token = db.scalar(
        select(ActionToken)
        .where(ActionToken.id == candidate.id)
        .execution_options(populate_existing=True)
    )
    if token.used or token.expires_at <= now() or user.disabled:
        fail(400, "invalid_token", "Invalid or expired token")
    # Invalidate all tokens of the same purpose so older reset links cannot be replayed.
    db.execute(
        update(ActionToken)
        .where(ActionToken.user_id == user.id, ActionToken.kind == kind)
        .values(used=True)
    )
    return user


def verify_email(db, raw, password):
    user = consume_action(db, raw, "verify")
    if user.verified:
        fail(400, "invalid_token", "Account is already verified")
    # Never activate credentials supplied by an earlier unverified registrant.
    # A later duplicate signup cannot replace this password after verification.
    user.password_hash = hasher.hash(password)
    user.verified = True
    invalidate_all(db, user)
    return {"message": "Email verified"}


def invalidate_all(db, user):
    user.auth_version += 1
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id).values(revoked=True))


def reset_password(db, data):
    user = consume_action(db, data.token, "reset")
    user.password_hash = hasher.hash(data.password)
    invalidate_all(db, user)
    return {"message": "Password reset; sign in again"}


def change_password(db, user, data):
    user = lock_user(db, user.id)
    if user.password_hash and not verify_password(data.current_password or "", user.password_hash):
        fail(401, "invalid_credentials", "Invalid current password")
    # Google-only account may add a password after authenticated Google sign-in.
    if not user.verified:
        fail(403, "verification_required", "Verify your email first")
    user.password_hash = hasher.hash(data.password)
    db.execute(
        update(ActionToken)
        .where(ActionToken.user_id == user.id, ActionToken.kind == "reset")
        .values(used=True)
    )
    invalidate_all(db, user)
    return {"message": "Password changed; sign in again"}


def refresh(db, raw):
    candidate = db.scalar(select(RefreshSession).where(RefreshSession.token_digest == digest(raw)))
    if candidate is None:
        fail(401, "invalid_refresh", "Invalid refresh token")
    user = lock_user(db, candidate.user_id)
    session = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.id == candidate.id)
        .execution_options(populate_existing=True)
    )
    if session.used_at is not None:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == session.family_id)
            .values(revoked=True)
        )
        # Persist replay response before raising; request rollback must not undo revocation.
        db.commit()
        fail(401, "refresh_reuse", "Session revoked; sign in again")
    if session.revoked or session.expires_at <= now() or user.disabled:
        fail(401, "invalid_refresh", "Invalid refresh token")
    session.used_at = now()
    # Absolute family lifetime is preserved across rotation.
    return issue_pair(db, user, session.family_id, session.expires_at)


def logout(db, user, current_session, raw):
    user = lock_user(db, user.id)
    target = db.scalar(
        select(RefreshSession).where(
            RefreshSession.token_digest == digest(raw), RefreshSession.user_id == user.id
        )
    )
    if target is None or target.family_id != current_session.family_id:
        fail(400, "invalid_refresh", "Token does not belong to this session")
    db.execute(
        update(RefreshSession)
        .where(RefreshSession.family_id == target.family_id)
        .values(revoked=True)
    )
    return {"message": "Logged out"}


def unlink_google(db, user):
    user = lock_user(db, user.id)
    if not user.password_hash or not user.verified:
        fail(409, "last_auth_method", "Add a verified password before unlinking Google")
    identity = db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.user_id == user.id, OAuthIdentity.provider == "google"
        )
    )
    if identity:
        db.delete(identity)
        invalidate_all(db, user)
    return {"message": "Google unlinked; sign in again"}

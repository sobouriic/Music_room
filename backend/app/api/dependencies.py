from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import fail
from app.core.security import decode_access, now
from app.db.session import get_db
from app.models.entities import RefreshSession, User
from mandatory.services.rate_limit import hit

bearer = HTTPBearer(auto_error=False)


def authenticate(credentials, db):
    if not credentials:
        fail(401, "unauthorized", "Bearer access token required")
    try:
        claims = decode_access(credentials.credentials)
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        fail(401, "unauthorized", "Invalid or expired access token")
    user = db.get(User, UUID(claims["sub"]))
    session = db.get(RefreshSession, UUID(claims["sid"]))
    if (
        not user
        or user.disabled
        or claims["ver"] != user.auth_version
        or not session
        or session.user_id != user.id
        or session.revoked
        or session.expires_at <= now()
    ):
        fail(401, "unauthorized", "Session is no longer valid")
    return user, session


def current_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db=Depends(get_db, scope="function"),
):
    return authenticate(credentials, db)


def current_user(auth=Depends(current_auth)):
    return auth[0]


def sensitive(request: Request):
    # Trust the socket peer only. Deploy a trusted proxy with explicit forwarded-IP policy.
    hit("ip", request.client.host if request.client else "unknown")


def music_sensitive(request: Request):
    from app.core.config import get_settings

    hit(
        "music_ip",
        request.client.host if request.client else "unknown",
        limit=get_settings().music_rate_limit,
    )

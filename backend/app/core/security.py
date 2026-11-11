import hashlib
import secrets
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def now() -> datetime:
    return datetime.now(UTC)


def opaque() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return hasher.verify(hashed or DUMMY_HASH, password) and hashed is not None
    except (VerificationError, InvalidHashError):
        return False


def access_token(user_id: UUID, session_id: UUID, version: int) -> str:
    cfg = get_settings()
    issued = int(time.time())
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "ver": version,
            "typ": "access",
            "iss": cfg.jwt_issuer,
            "aud": cfg.jwt_audience,
            "iat": issued,
            "exp": issued + cfg.access_seconds,
            "jti": str(uuid4()),
        },
        cfg.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access(token: str) -> dict:
    cfg = get_settings()
    claims = jwt.decode(
        token,
        cfg.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=cfg.jwt_issuer,
        audience=cfg.jwt_audience,
        options={"require": ["sub", "sid", "ver", "typ", "iss", "aud", "iat", "exp", "jti"]},
    )
    if claims["typ"] != "access" or type(claims["ver"]) is not int:
        raise jwt.InvalidTokenError()
    UUID(claims["sub"])
    UUID(claims["sid"])
    return claims

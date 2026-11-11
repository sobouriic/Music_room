import base64
import hashlib
import secrets
from datetime import timedelta
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.exceptions import fail
from app.core.security import digest, now, opaque
from app.db.session import lock_user
from app.models.entities import ActionToken, OAuthAttempt, OAuthIdentity
from app.repositories import users
from mandatory.services.auth_service import invalidate_all, issue_pair


@lru_cache
def google_keys():
    # Static trusted Google endpoint, never a URL supplied by the client/token.
    return PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", timeout=10)


def require_config():
    cfg = get_settings()
    if not cfg.google_client_id or not cfg.google_client_secret.get_secret_value():
        fail(503, "google_not_configured", "Google authentication is not configured")
    return cfg


def start(db, data, user=None):
    cfg = require_config()
    if data.intent == "link" and user is None:
        fail(401, "unauthorized", "Sign in before linking Google")
    state, nonce = opaque(), opaque()
    # Bind the return platform to the one-use state, without client-supplied URLs.
    if data.platform == "native":
        state = "native." + state
    db.add(
        OAuthAttempt(
            state_digest=digest(state),
            nonce=nonce,
            challenge=data.code_challenge,
            intent=data.intent,
            user_id=user.id if data.intent == "link" else None,
            expires_at=now() + timedelta(minutes=10),
        )
    )
    params = {
        "client_id": cfg.google_client_id,
        "redirect_uri": cfg.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": data.code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params),
        "state": state,
        "expires_in": 600,
    }


def google_claims(code, verifier, nonce):
    cfg = require_config()
    try:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": cfg.google_client_id,
                "client_secret": cfg.google_client_secret.get_secret_value(),
                "redirect_uri": cfg.google_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=10,
        )
        response.raise_for_status()
        token = response.json()["id_token"]
        key = google_keys().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=cfg.google_client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={"require": ["sub", "aud", "iss", "iat", "exp", "nonce"]},
        )
        if (
            not secrets.compare_digest(claims["nonce"], nonce)
            or claims.get("email_verified") is not True
            or not isinstance(claims["sub"], str)
            or not 1 <= len(claims["sub"]) <= 255
            or ("azp" in claims and claims["azp"] != cfg.google_client_id)
            or (
                isinstance(claims["aud"], list)
                and len(claims["aud"]) > 1
                and claims.get("azp") != cfg.google_client_id
            )
        ):
            raise ValueError()
        claims["email"] = str(TypeAdapter(EmailStr).validate_python(claims["email"])).casefold()
        return claims
    except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, TypeError):
        fail(401, "invalid_google_identity", "Google identity could not be verified")


def exchange(db, data, intent, user=None):
    require_config()
    attempt = db.scalar(
        select(OAuthAttempt)
        .where(OAuthAttempt.state_digest == digest(data.state))
        .with_for_update()
    )
    if (
        not attempt
        or attempt.used
        or attempt.expires_at <= now()
        or attempt.intent != intent
        or (intent == "link" and (user is None or attempt.user_id != user.id))
    ):
        fail(400, "invalid_oauth_state", "Invalid or expired OAuth attempt")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(data.code_verifier.encode()).digest())
    if not secrets.compare_digest(challenge.decode().rstrip("="), attempt.challenge):
        fail(400, "invalid_pkce", "Invalid PKCE verifier")
    attempt.used = True
    # State is one-use even when the provider rejects the code.
    nonce = attempt.nonce
    db.commit()
    claims = google_claims(data.code, data.code_verifier, nonce)
    identity = db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == "google", OAuthIdentity.subject == claims["sub"]
        )
    )
    if intent == "link":
        user = lock_user(db, user.id)
        if user.disabled:
            fail(403, "disabled", "Account disabled")
        if identity and identity.user_id != user.id:
            fail(409, "identity_conflict", "Google account is already linked")
        existing = db.scalar(
            select(OAuthIdentity).where(
                OAuthIdentity.user_id == user.id, OAuthIdentity.provider == "google"
            )
        )
        if existing and existing.subject != claims["sub"]:
            fail(409, "identity_conflict", "A different Google account is already linked")
        if not identity:
            db.add(OAuthIdentity(user_id=user.id, provider="google", subject=claims["sub"]))
        return {"message": "Google linked"}
    if identity:
        user = lock_user(db, identity.user_id)
        # Unlink may have committed between the identity lookup and acquiring this lock.
        linked = db.scalar(
            select(OAuthIdentity.id).where(
                OAuthIdentity.user_id == user.id,
                OAuthIdentity.provider == "google",
                OAuthIdentity.subject == claims["sub"],
            )
        )
        if user.disabled or linked is None:
            fail(401, "invalid_credentials", "Unable to sign in")
    else:
        candidate = users.by_email(db, claims["email"])
        if candidate:
            user = lock_user(db, candidate.id)
            if user.disabled:
                fail(401, "invalid_credentials", "Unable to sign in")
            existing = db.scalar(
                select(OAuthIdentity).where(
                    OAuthIdentity.user_id == user.id, OAuthIdentity.provider == "google"
                )
            )
            if existing and existing.subject != claims["sub"]:
                fail(409, "identity_conflict", "A different Google account is already linked")
            if not user.verified:
                # Google proved ownership of the email. Discard credentials from an
                # unverified signup so its creator cannot later access this account.
                user.password_hash = None
                user.verified = True
                invalidate_all(db, user)
                db.execute(
                    update(ActionToken).where(ActionToken.user_id == user.id).values(used=True)
                )
        else:
            user = users.create(db, claims["email"], None, verified=True)
        if not candidate or not existing:
            db.add(OAuthIdentity(user_id=user.id, provider="google", subject=claims["sub"]))
    return issue_pair(db, user)

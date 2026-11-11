import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import get_settings
from mandatory.services import oauth_service
from tests.conftest import EMAIL, PASSWORD, account, headers

BASE = "/api/v1/auth"
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
)


def start(client, intent="login", pair=None):
    response = client.post(
        BASE + "/google/start",
        json={"code_challenge": CHALLENGE, "intent": intent},
        headers=headers(pair) if pair else {},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    params = parse_qs(urlparse(data["authorization_url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"] == [CHALLENGE]
    assert "nonce" in params
    return {"code": "provider-code", "state": data["state"], "code_verifier": VERIFIER}


@pytest.fixture
def google(monkeypatch):
    claims = {"sub": "google-subject-123", "email": "google@example.com", "email_verified": True}
    monkeypatch.setattr(oauth_service, "google_claims", lambda *args: claims.copy())
    return claims


def test_google_registration_login_replay_and_last_method(client, google):
    body = start(client)
    response = client.post(BASE + "/google/exchange", json=body)
    assert response.status_code == 200, response.text
    pair = response.json()
    profile = client.get("/api/v1/users/me", headers=headers(pair)).json()
    assert (
        profile["verified"] and not profile["has_password"] and profile["providers"] == ["google"]
    )
    assert client.post(BASE + "/google/exchange", json=body).status_code == 400
    second = client.post(BASE + "/google/exchange", json=start(client))
    assert second.status_code == 200
    assert client.delete(BASE + "/google/link", headers=headers(pair)).status_code == 409
    assert (
        client.post(
            BASE + "/change-password", headers=headers(pair), json={"password": PASSWORD}
        ).status_code
        == 200
    )
    pair = client.post(
        BASE + "/login", json={"email": google["email"], "password": PASSWORD}
    ).json()
    assert client.delete(BASE + "/google/link", headers=headers(pair)).status_code == 200
    assert client.get("/api/v1/users/me", headers=headers(pair)).status_code == 401


def test_google_signs_into_existing_email_and_requires_auth_for_explicit_link(client, google):
    pair = account(client)
    google["email"] = EMAIL
    response = client.post(BASE + "/google/exchange", json=start(client))
    assert response.status_code == 200
    before = client.get("/api/v1/users/me", headers=headers(pair)).json()
    after = client.get("/api/v1/users/me", headers=headers(response.json())).json()
    assert before["id"] == after["id"]
    assert after["has_password"] and after["providers"] == ["google"]
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    )
    assert (
        client.post(
            BASE + "/google/start", json={"intent": "link", "code_challenge": CHALLENGE}
        ).status_code
        == 401
    )
    body = start(client, "link", pair)
    assert client.post(BASE + "/google/link", json=body).status_code == 401
    assert client.post(BASE + "/google/link", json=body, headers=headers(pair)).status_code == 200
    signed_in = client.post(BASE + "/google/exchange", json=start(client)).json()
    assert client.get("/api/v1/users/me", headers=headers(signed_in)).json()["email"] == EMAIL


def test_google_state_intent_user_and_pkce_binding(client, google):
    alice = account(client)
    bob = account(client, email="bob@example.com")
    body = start(client, "link", alice)
    assert client.post(BASE + "/google/link", json=body, headers=headers(bob)).status_code == 400
    assert client.post(BASE + "/google/exchange", json=body).status_code == 400
    bad = {**body, "code_verifier": "x" * 64}
    assert client.post(BASE + "/google/link", json=bad, headers=headers(alice)).status_code == 400
    assert client.post(BASE + "/google/link", json=body, headers=headers(alice)).status_code == 200
    assert (
        client.post(
            BASE + "/google/link", json=start(client, "link", bob), headers=headers(bob)
        ).status_code
        == 409
    )


def test_google_not_configured(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    get_settings.cache_clear()
    assert (
        client.post(BASE + "/google/start", json={"code_challenge": CHALLENGE}).status_code == 503
    )


def test_google_expired_state(client, google, db):
    from datetime import timedelta

    from sqlalchemy import select

    from app.core.security import now
    from app.models.entities import OAuthAttempt

    body = start(client)
    db.scalar(select(OAuthAttempt)).expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert client.post(BASE + "/google/exchange", json=body).status_code == 400


def test_google_unlink_wins_over_inflight_login(client, google, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    pair = client.post(BASE + "/google/exchange", json=start(client)).json()
    assert (
        client.post(
            BASE + "/change-password", headers=headers(pair), json={"password": PASSWORD}
        ).status_code
        == 200
    )
    pair = client.post(
        BASE + "/login", json={"email": google["email"], "password": PASSWORD}
    ).json()
    body = start(client)
    identity_read = Event()
    unlink_complete = Event()
    original_lock = oauth_service.lock_user

    def pause_before_lock(db, user_id):
        identity_read.set()
        assert unlink_complete.wait(timeout=10)
        return original_lock(db, user_id)

    monkeypatch.setattr(oauth_service, "lock_user", pause_before_lock)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, BASE + "/google/exchange", json=body)
        try:
            assert identity_read.wait(timeout=10)
            assert client.delete(BASE + "/google/link", headers=headers(pair)).status_code == 200
        finally:
            unlink_complete.set()
        assert pending.result(timeout=10).status_code == 401


def test_google_callback_does_not_reflect_code_or_state(client):
    response = client.get(BASE + "/google/callback?code=private-code&state=private-state")
    assert response.status_code == 200
    assert "private-code" not in response.text and "private-state" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_google_callback_bridges_back_to_app(client):
    response = client.get(BASE + "/google/callback")
    assert response.headers["content-type"].startswith("text/html")
    assert "location.replace(" in response.text
    assert "#google-callback=" in response.text
    assert "http://localhost:8081/" in response.text
    assert "musicroom://oauth?" in response.text
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "startsWith('native.')" in response.text


def test_native_google_state_is_bound_to_exchange(client, google):
    response = client.post(
        BASE + "/google/start",
        json={"code_challenge": CHALLENGE, "platform": "native"},
    )
    assert response.status_code == 200
    state = response.json()["state"]
    assert state.startswith("native.")
    body = {"state": state, "code": "provider-code", "code_verifier": VERIFIER}
    assert (
        client.post(BASE + "/google/exchange", json={**body, "state": state[7:]}).status_code == 400
    )
    assert client.post(BASE + "/google/exchange", json=body).status_code == 200
    assert client.post(BASE + "/google/exchange", json=body).status_code == 400


def test_google_rejects_disabled_matching_account(client, google, db):
    from sqlalchemy import select

    from app.models.entities import User

    account(client)
    google["email"] = EMAIL
    db.scalar(select(User).where(User.email == EMAIL)).disabled = True
    db.commit()
    assert client.post(BASE + "/google/exchange", json=start(client)).status_code == 401


def test_google_claims_unverified_signup_without_preserving_untrusted_password(client, google):
    google["email"] = EMAIL
    client.post(BASE + "/register", json={"email": EMAIL, "password": PASSWORD})
    response = client.post(BASE + "/google/exchange", json=start(client))
    assert response.status_code == 200
    profile = client.get("/api/v1/users/me", headers=headers(response.json())).json()
    assert profile["verified"] and not profile["has_password"]
    assert profile["providers"] == ["google"]
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    )


def test_google_does_not_replace_a_different_linked_identity(client, google):
    google["email"] = EMAIL
    assert client.post(BASE + "/google/exchange", json=start(client)).status_code == 200
    google["sub"] = "different-google-subject"
    response = client.post(BASE + "/google/exchange", json=start(client))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "identity_conflict"


@pytest.mark.parametrize("result", [{"code": "provider-code"}, {"error": "access_denied"}])
def test_native_callback_redirects_directly_to_registered_app(client, result):
    response = client.get(
        BASE + "/google/callback",
        params={"state": "native.one-use-state", **result, "redirect_uri": "https://evil.example"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    destination = urlparse(response.headers["location"])
    assert (destination.scheme, destination.netloc) == ("musicroom", "oauth")
    assert parse_qs(destination.query) == {
        "state": ["native.one-use-state"],
        **{key: [value] for key, value in result.items()},
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"

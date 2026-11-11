from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.security import digest, now
from app.models.entities import ActionToken, MailJob, RefreshSession, User
from tests.conftest import EMAIL, PASSWORD, account, headers, mail_token

BASE = "/api/v1/auth"


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_verification_establishes_email_owners_password_not_preclaimed_password(client):
    attacker = "First-unverified-password-42!"
    owner = "Verified-owner-password-42!"
    client.post(BASE + "/register", json={"email": EMAIL, "password": attacker})
    client.post(BASE + "/register", json={"email": EMAIL, "password": owner})
    token = mail_token()
    # A competing unverified signup after delivery cannot change what the owner sets.
    client.post(BASE + "/register", json={"email": EMAIL, "password": attacker})
    response = client.post(BASE + "/verify-email", json={"token": token, "password": owner})
    assert response.status_code == 200
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": attacker}).status_code == 401
    )
    assert client.post(BASE + "/login", json={"email": EMAIL, "password": owner}).status_code == 200
    client.post(BASE + "/register", json={"email": EMAIL, "password": attacker})
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": attacker}).status_code == 401
    )


def test_registration_normalization_duplicate_and_hash(client, db):
    body = {"email": "Alice@EXAMPLE.COM", "password": PASSWORD}
    first = client.post(BASE + "/register", json=body)
    second = client.post(BASE + "/register", json=body)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert db.scalar(select(func.count()).select_from(User)) == 1
    user = db.scalar(select(User))
    assert user.email == EMAIL and not user.verified
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != PASSWORD
    assert db.scalar(select(func.count()).select_from(MailJob)) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"email": "invalid", "password": PASSWORD},
        {"email": EMAIL, "password": "short"},
        {"email": EMAIL, "password": "a" * 20},
        {"email": EMAIL, "password": "password123456"},
        {"email": EMAIL, "password": "a" * 129},
        {"email": EMAIL, "password": PASSWORD, "verified": True},
    ],
)
def test_registration_validation(client, body):
    response = client.post(BASE + "/register", json=body)
    assert response.status_code == 422
    assert "input" not in response.text
    assert 'password":"' not in response.text


def test_verification_and_single_use(client):
    client.post(BASE + "/register", json={"email": EMAIL, "password": PASSWORD})
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    )
    token = mail_token()
    assert (
        client.post(BASE + "/verify-email", json={"token": token, "password": PASSWORD}).status_code
        == 200
    )
    assert (
        client.post(BASE + "/verify-email", json={"token": token, "password": PASSWORD}).status_code
        == 400
    )
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    )


def test_expired_verification_and_resend(client, db):
    client.post(BASE + "/register", json={"email": EMAIL, "password": PASSWORD})
    raw = mail_token()
    token = db.scalar(select(ActionToken))
    token.expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(BASE + "/verify-email", json={"token": raw, "password": PASSWORD}).status_code
        == 400
    )
    assert client.post(BASE + "/resend-verification", json={"email": EMAIL}).status_code == 202
    replacement = mail_token()
    assert raw != replacement
    assert (
        client.post(
            BASE + "/verify-email", json={"token": replacement, "password": PASSWORD}
        ).status_code
        == 200
    )


def test_login_errors_and_disabled_account(client, db):
    account(client)
    wrong = client.post(BASE + "/login", json={"email": EMAIL, "password": "wrong"})
    missing = client.post(
        BASE + "/login", json={"email": "missing@example.com", "password": "wrong"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json()
    user = db.scalar(select(User))
    user.disabled = True
    db.commit()
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    )


def test_refresh_rotation_reuse_and_access_revocation(client, db):
    pair = account(client)
    next_pair = client.post(BASE + "/refresh", json={"refresh_token": pair["refresh_token"]}).json()
    assert next_pair["refresh_token"] != pair["refresh_token"]
    assert client.get("/api/v1/users/me", headers=headers(next_pair)).status_code == 200
    replay = client.post(BASE + "/refresh", json={"refresh_token": pair["refresh_token"]})
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "refresh_reuse"
    assert (
        client.post(
            BASE + "/refresh", json={"refresh_token": next_pair["refresh_token"]}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/users/me", headers=headers(next_pair)).status_code == 401
    sessions = list(db.scalars(select(RefreshSession)))
    assert all(session.revoked for session in sessions)
    assert all(
        session.token_digest not in (pair["refresh_token"], next_pair["refresh_token"])
        for session in sessions
    )


def test_logout_and_logout_all(client):
    pair = account(client)
    other = client.post(BASE + "/login", json={"email": EMAIL, "password": PASSWORD}).json()
    assert (
        client.post(
            BASE + "/logout", headers=headers(pair), json={"refresh_token": pair["refresh_token"]}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/users/me", headers=headers(pair)).status_code == 401
    assert client.get("/api/v1/users/me", headers=headers(other)).status_code == 200
    assert client.post(BASE + "/logout-all", headers=headers(other)).status_code == 200
    assert client.get("/api/v1/users/me", headers=headers(other)).status_code == 401


def test_password_reset_revokes_sessions_and_tokens(client):
    pair = account(client)
    body = {"email": EMAIL}
    existing = client.post(BASE + "/forgot-password", json=body)
    missing = client.post(BASE + "/forgot-password", json={"email": "missing@example.com"})
    assert existing.status_code == missing.status_code == 202
    assert existing.json() == missing.json()
    token = mail_token()
    new_password = "My new long password 43!"
    reset = {"token": token, "password": new_password}
    assert client.post(BASE + "/reset-password", json=reset).status_code == 200
    assert client.post(BASE + "/reset-password", json=reset).status_code == 400
    assert client.get("/api/v1/users/me", headers=headers(pair)).status_code == 401
    assert (
        client.post(BASE + "/refresh", json={"refresh_token": pair["refresh_token"]}).status_code
        == 401
    )
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    )
    assert (
        client.post(BASE + "/login", json={"email": EMAIL, "password": new_password}).status_code
        == 200
    )


def test_expired_reset(client, db):
    account(client)
    client.post(BASE + "/forgot-password", json={"email": EMAIL})
    token = mail_token()
    row = db.scalar(select(ActionToken).where(ActionToken.token_digest == digest(token)))
    row.expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(
            BASE + "/reset-password", json={"token": token, "password": PASSWORD}
        ).status_code
        == 400
    )


def test_change_password(client):
    pair = account(client)
    body = {"current_password": "wrong", "password": "A replacement password 45!"}
    assert (
        client.post(BASE + "/change-password", headers=headers(pair), json=body).status_code == 401
    )
    body["current_password"] = PASSWORD
    assert (
        client.post(BASE + "/change-password", headers=headers(pair), json=body).status_code == 200
    )
    assert client.get("/api/v1/users/me", headers=headers(pair)).status_code == 401
    assert (
        client.post(
            BASE + "/login", json={"email": EMAIL, "password": body["password"]}
        ).status_code
        == 200
    )


def test_concurrent_refresh_fails_closed(client):
    pair = account(client)

    def refresh(_):
        return client.post(BASE + "/refresh", json={"refresh_token": pair["refresh_token"]})

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(refresh, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(response.json() for response in responses if response.status_code == 200)
    assert client.get("/api/v1/users/me", headers=headers(winner)).status_code == 401


def test_concurrent_registration(client, db):
    def register(_):
        return client.post(BASE + "/register", json={"email": EMAIL, "password": PASSWORD})

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(register, range(2)))
    assert [r.status_code for r in responses] == [202, 202]
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_expired_refresh(client, db):
    pair = account(client)
    row = db.scalar(select(RefreshSession))
    row.expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(BASE + "/refresh", json={"refresh_token": pair["refresh_token"]}).status_code
        == 401
    )
    assert client.get("/api/v1/users/me", headers=headers(pair)).status_code == 401


def test_concurrent_verification_is_single_use(client):
    client.post(BASE + "/register", json={"email": EMAIL, "password": PASSWORD})
    raw = mail_token()

    def verify(_):
        return client.post(BASE + "/verify-email", json={"token": raw, "password": PASSWORD})

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(verify, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 400]


def test_concurrent_reset_is_single_use(client):
    pair = account(client)
    client.post(BASE + "/forgot-password", json={"email": EMAIL})
    raw = mail_token()

    def reset(_):
        return client.post(
            BASE + "/reset-password",
            json={"token": raw, "password": "A replacement long password 55!"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(reset, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 400]
    assert client.get("/api/v1/users/me", headers=headers(pair)).status_code == 401


def test_register_again_resends_verification(client, db):
    from sqlalchemy import func, select

    from app.models.entities import MailJob
    from tests.conftest import EMAIL, PASSWORD

    body = {"email": EMAIL, "password": PASSWORD}
    assert client.post("/api/v1/auth/register", json=body).status_code == 202
    assert client.post("/api/v1/auth/register", json=body).status_code == 202
    assert db.scalar(select(func.count()).select_from(MailJob)) == 2

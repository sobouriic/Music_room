import json
import logging
import time

import jwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.entities import RateBucket
from tests.conftest import EMAIL, PASSWORD, account, headers


@pytest.mark.parametrize(
    "change",
    [
        {"exp": 1},
        {"iss": "wrong"},
        {"aud": "wrong"},
        {"typ": "refresh"},
        {"sub": "not-a-uuid"},
        {"ver": "0"},
        {"iat": int(time.time()) + 3600},
    ],
)
def test_jwt_claim_validation(client, change):
    pair = account(client)
    cfg = get_settings()
    claims = jwt.decode(
        pair["access_token"],
        cfg.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=cfg.jwt_audience,
    )
    claims.update(change)
    forged = jwt.encode(claims, cfg.jwt_secret.get_secret_value(), algorithm="HS256")
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + forged}).status_code
        == 401
    )


def test_wrong_signature_missing_claims_and_unauthorized(client):
    pair = account(client)
    claims = jwt.decode(pair["access_token"], options={"verify_signature": False})
    wrong = jwt.encode(claims, "wrong-signing-key-with-thirty-two-bytes", algorithm="HS256")
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + wrong}).status_code
        == 401
    )
    del claims["exp"]
    missing = jwt.encode(claims, get_settings().jwt_secret.get_secret_value(), algorithm="HS256")
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + missing}).status_code
        == 401
    )
    for token in (None, "junk"):
        assert (
            client.get(
                "/api/v1/users/me",
                headers={} if token is None else {"Authorization": "Bearer " + token},
            ).status_code
            == 401
        )


def test_rate_limit_persists_failed_requests(client, monkeypatch, db):
    monkeypatch.setenv("RATE_LIMIT", "2")
    get_settings.cache_clear()
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": EMAIL, "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "wrong"}).status_code
        == 429
    )
    assert len(list(db.scalars(select(RateBucket)))) == 2


def test_logs_redact_and_sanitize(client, caplog):
    pair = account(client)
    with caplog.at_level(logging.INFO, logger="music_room.audit"):
        response = client.get(
            "/api/v1/users/me?secret=do-not-log",
            headers={
                **headers(pair),
                "X-App-Platform": "Android",
                "X-App-Device": "test<script>",
                "X-App-Version": "1.0",
            },
        )
    assert response.status_code == 200
    logs = "\n".join(
        record.message for record in caplog.records if record.name == "music_room.audit"
    )
    for value in (pair["access_token"], pair["refresh_token"], PASSWORD, EMAIL, "do-not-log"):
        assert value not in logs
    entry = json.loads(logs.splitlines()[-1])
    assert entry["platform"] == "Android" and "<" not in entry["device"]
    assert entry["route"].endswith("/users/me")
    assert response.headers["cache-control"] == "no-store"


def test_logout_cannot_revoke_another_user(client):
    alice = account(client)
    bob = account(client, email="bob@example.com")
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers=headers(alice),
            json={"refresh_token": bob["refresh_token"]},
        ).status_code
        == 400
    )
    assert client.get("/api/v1/users/me", headers=headers(bob)).status_code == 200


def test_rate_limit_is_atomic_and_has_retry_after(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("RATE_LIMIT", "3")
    get_settings.cache_clear()

    def login(_):
        return client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "wrong"})

    with ThreadPoolExecutor(max_workers=5) as executor:
        responses = list(executor.map(login, range(5)))
    assert sorted(response.status_code for response in responses) == [401, 401, 401, 429, 429]
    assert all(
        int(response.headers["Retry-After"]) > 0
        for response in responses
        if response.status_code == 429
    )


def test_unknown_route_error_contract(client):
    response = client.get("/api/v1/users/not-a-route")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "http_error", "message": "Not Found"}}


@pytest.mark.parametrize("algorithm", ["none", "HS384"])
def test_jwt_algorithm_allowlist(client, algorithm):
    pair = account(client)
    claims = jwt.decode(pair["access_token"], options={"verify_signature": False})
    key = None if algorithm == "none" else get_settings().jwt_secret.get_secret_value()
    token = jwt.encode(claims, key, algorithm=algorithm)
    response = client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401


def test_unexpected_errors_do_not_leak_secrets(client, monkeypatch, caplog):
    pair = account(client)
    secret = "a-private-database-or-validation-value"

    def broken(*args):
        raise RuntimeError(secret)

    monkeypatch.setattr("mandatory.services.user_service.own_profile", broken)
    with caplog.at_level(logging.INFO):
        response = client.get("/api/v1/users/me", headers=headers(pair))
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Unexpected server error"}
    }
    assert secret not in response.text and secret not in caplog.text
    assert response.headers["cache-control"] == "no-store"

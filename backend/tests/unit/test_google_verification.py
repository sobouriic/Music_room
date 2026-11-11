import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.core.config import get_settings
from mandatory.services import oauth_service


@pytest.fixture
def provider(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {
        "sub": "subject",
        "email": "verified@example.com",
        "email_verified": True,
        "iss": "https://accounts.google.com",
        "aud": get_settings().google_client_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": "expected",
    }
    captured = {}

    def post(url, data, timeout):
        captured.update(data)
        assert url == "https://oauth2.googleapis.com/token"
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"id_token": token})

    monkeypatch.setattr(oauth_service.httpx, "post", post)
    monkeypatch.setattr(
        oauth_service,
        "google_keys",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())
        ),
    )
    return claims, captured


def test_google_real_signed_id_token_verification(provider):
    claims, captured = provider
    result = oauth_service.google_claims("code", "verifier", "expected")
    assert result["sub"] == "subject"
    assert captured["code_verifier"] == "verifier"
    assert captured["redirect_uri"] == get_settings().google_redirect_uri


@pytest.mark.parametrize(
    "change",
    [
        {"nonce": "wrong"},
        {"aud": "attacker-client"},
        {"iss": "https://attacker.com"},
        {"email_verified": False},
        {"email_verified": "true"},
        {"exp": 1},
        {"email": "invalid"},
        {"azp": "attacker"},
        {"sub": ""},
    ],
)
def test_google_rejects_untrusted_claims(provider, change):
    claims, _ = provider
    claims.update(change)
    with pytest.raises(HTTPException) as error:
        oauth_service.google_claims("code", "verifier", "expected")
    assert error.value.status_code == 401


def test_google_wrong_signature_is_rejected(provider, monkeypatch):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        oauth_service,
        "google_keys",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=other.public_key())
        ),
    )
    with pytest.raises(HTTPException) as error:
        oauth_service.google_claims("code", "verifier", "expected")
    assert error.value.status_code == 401


def test_google_provider_failure_is_sanitized(monkeypatch):
    import httpx

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("sensitive provider error")

    monkeypatch.setattr(oauth_service.httpx, "post", unavailable)
    with pytest.raises(HTTPException) as error:
        oauth_service.google_claims("private-code", "private-verifier", "nonce")
    assert error.value.status_code == 401
    assert "sensitive" not in str(error.value.detail)


def test_google_multi_audience_requires_authorized_party(provider):
    claims, _ = provider
    claims["aud"] = [get_settings().google_client_id, "another-client"]
    with pytest.raises(HTTPException):
        oauth_service.google_claims("code", "verifier", "expected")
    claims["azp"] = get_settings().google_client_id
    assert oauth_service.google_claims("code", "verifier", "expected")["sub"] == "subject"

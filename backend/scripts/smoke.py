"""Exercise a running local server using the development file email transport."""

import os
import secrets
from email import policy
from email.parser import Parser
from pathlib import Path

import httpx

from app.core.config import get_settings
from mandatory.services.email_service import process_one


def main():
    cfg = get_settings()
    if cfg.app_env != "development":
        raise SystemExit("Smoke test requires development environment and file email transport")
    email = f"smoke-{secrets.token_hex(6)}@example.com"
    password = secrets.token_urlsafe(24)
    base = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")
    with httpx.Client(
        base_url=base,
        timeout=20,
        headers={"X-App-Platform": "Android", "X-App-Device": "smoke-test", "X-App-Version": "1.0"},
    ) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert (
            client.post(
                "/api/v1/auth/register", json={"email": email, "password": password}
            ).status_code
            == 202
        )
        while process_one():
            pass
        messages = [
            Parser(policy=policy.default).parsestr(path.read_text())
            for path in Path(cfg.mail_directory).glob("*.eml")
        ]
        message = next(item for item in messages if item["To"] == email)
        token = message.get_content().split("Token: ")[1].split()[0]
        assert (
            client.post(
                "/api/v1/auth/verify-email", json={"token": token, "password": password}
            ).status_code
            == 200
        )
        result = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert result.status_code == 200
        pair = result.json()
        auth = {"Authorization": "Bearer " + pair["access_token"]}
        assert client.get("/api/v1/users/me", headers=auth).status_code == 200
        result = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert result.status_code == 200
        pair = result.json()
        auth = {"Authorization": "Bearer " + pair["access_token"]}
        assert (
            client.post(
                "/api/v1/auth/logout", headers=auth, json={"refresh_token": pair["refresh_token"]}
            ).status_code
            == 200
        )
        assert client.get("/api/v1/users/me", headers=auth).status_code == 401
    print(
        "Live smoke passed: health → register → email verification → login → profile "
        "→ refresh → logout"
    )


if __name__ == "__main__":
    main()

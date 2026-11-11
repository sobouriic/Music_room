import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

ORIGIN = "http://localhost:5173"


def configured_client(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173"]')
    get_settings.cache_clear()
    return TestClient(create_app())


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_allowed_preflight_headers(monkeypatch, method):
    with configured_client(monkeypatch) as client:
        response = client.options(
            "/api/v1/users/me",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": (
                    "authorization,content-type,x-app-platform,x-app-device,x-app-version"
                ),
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "origin" in response.headers["vary"].lower()
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_untrusted_origin_is_not_granted_access(monkeypatch):
    with configured_client(monkeypatch) as client:
        response = client.options(
            "/api/v1/users/me",
            headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_disallowed_method_or_header(monkeypatch):
    with configured_client(monkeypatch) as client:
        for method, header in [("TRACE", "authorization"), ("GET", "x-unapproved-header")]:
            response = client.options(
                "/api/v1/users/me",
                headers={
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": header,
                },
            )
            assert response.status_code == 400


def test_errors_and_json_responses_keep_cors_headers(monkeypatch):
    with configured_client(monkeypatch) as client:
        for method, path, body, status in [
            ("GET", "/api/v1/health", None, 200),
            ("GET", "/api/v1/users/me", None, 401),
            ("POST", "/api/v1/auth/register", {"email": "bad", "password": "short"}, 422),
        ]:
            response = client.request(method, path, json=body, headers={"Origin": ORIGIN})
            assert response.status_code == status
            assert response.headers["access-control-allow-origin"] == ORIGIN
            assert response.headers["cache-control"] == "no-store"


def test_default_cors_does_not_allow_browser_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "[]")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_development_loopback_ports_are_shared_by_http_and_websockets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "[]")
    get_settings.cache_clear()
    cfg = get_settings()
    assert "http://localhost:8082" in cfg.browser_origins
    assert "http://127.0.0.1:8083" in cfg.browser_origins
    assert "http://localhost.evil.example:8082" not in cfg.browser_origins
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/v1/users/me",
            headers={"Origin": "http://localhost:8082", "Access-Control-Request-Method": "GET"},
        )
        assert response.status_code == 200
        # A successful handshake gets to token authentication, rather than HTTP 403.
        with client.websocket_connect(
            "/api/v1/ws/event/00000000-0000-0000-0000-000000000001",
            headers={"Origin": "http://localhost:8082"},
        ) as ws:
            ws.send_json({"access_token": "invalid"})
            from starlette.websockets import WebSocketDisconnect

            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


def test_non_development_origins_remain_explicit(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "[]")
    get_settings.cache_clear()
    assert "http://localhost:8082" not in get_settings().browser_origins

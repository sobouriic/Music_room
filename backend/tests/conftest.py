import os
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from alembic import command

# Always use a separate database. Never fall back to DATABASE_URL or the developer database.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://music:music_test_only@localhost:5433/music_room_test",
)
os.environ["JWT_SECRET"] = "unit-test-secret-with-more-than-thirty-two-characters"
os.environ["APP_ENV"] = "test"
os.environ["GOOGLE_CLIENT_ID"] = "test-google-client"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-google-secret"
os.environ["RATE_LIMIT"] = "1000"

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import session_factory  # noqa: E402
from app.main import create_app  # noqa: E402
from mandatory.services.email_service import process_one  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    url = make_url(os.environ["DATABASE_URL"])
    if not url.database or not url.database.endswith("_test"):
        raise RuntimeError("Refusing destructive tests: database name must end in _test")
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def clean_database(database, tmp_path, monkeypatch):
    with session_factory()() as db:
        tables = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
        db.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
        db.commit()
    monkeypatch.setenv("MAIL_DIRECTORY", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(api_operations):
    required, tested = api_operations

    def record(request):
        # Store route templates only: no user IDs, bodies, credentials or query strings.
        for operation in required:
            method, template = operation.split(" ", 1)
            actual = request.url.path.split("/")
            parts = template.split("/")
            if (
                method == request.method
                and len(actual) == len(parts)
                and all(
                    a == p or (p.startswith("{") and p.endswith("}")) for a, p in zip(actual, parts)
                )
            ):
                tested.add(operation)

    with TestClient(create_app()) as client:
        client.event_hooks["request"].append(record)
        yield client


@pytest.fixture
def db():
    with session_factory()() as db:
        yield db


def mail_token():
    while process_one():
        pass
    paths = list(Path(get_settings().mail_directory).glob("*.eml"))
    assert paths, "Expected a development email"
    latest = max(paths, key=lambda path: path.stat().st_mtime_ns)
    return latest.read_text().split("Token: ")[1].split()[0]


PASSWORD = "A good long password 42!"
EMAIL = "alice@example.com"


def account(client, email=EMAIL, password=PASSWORD):
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        ).status_code
        == 202
    )
    token = mail_token()
    assert (
        client.post(
            "/api/v1/auth/verify-email", json={"token": token, "password": password}
        ).status_code
        == 200
    )
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def headers(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


def pytest_addoption(parser):
    parser.addoption("--check-api-coverage", action="store_true", default=False)
    parser.addoption("--api-coverage-report", default=None)


@pytest.fixture(scope="session")
def api_operations(request):
    import json

    required = {
        f"{method.upper()} {path}"
        for path, methods in create_app().openapi()["paths"].items()
        for method in methods
        if method in {"get", "post", "patch", "delete", "put"}
    }
    tested = set()
    yield required, tested
    destination = request.config.getoption("--api-coverage-report")
    if destination:
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_text(
            json.dumps(
                {
                    "required": sorted(required),
                    "tested": sorted(tested),
                    "missing": sorted(required - tested),
                },
                indent=2,
            )
            + "\n"
        )
    if request.config.getoption("--check-api-coverage") and required - tested:
        pytest.fail("API operations not exercised: " + ", ".join(sorted(required - tested)))

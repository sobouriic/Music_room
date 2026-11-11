# Music Room backend — Phase 1

A working FastAPI/PostgreSQL backend for email/password authentication, Google OIDC sign-in and
account linking, rotating refresh sessions, email verification/recovery, and privacy-aware profiles.
F Friendship requests and friends-only profile permissions are implemented. Music-service backend APIs are described below; audio playback executes on the client.

## One-command startup (recommended)

On Linux, install **Python 3.12+**, Python's **venv** support, and **Docker Engine with Compose
2.20+**. Start Docker and ensure your user can run `docker info` without sudo. Then run:

```sh
./start.sh
# Also works without executable permission:
sh start.sh
```

The script resolves all project paths relative to its own location. It works from another directory
and with spaces in the project path, for example:

```sh
sh "/home/yourname/My Projects/music room/start.sh"
```

No virtual-environment activation or manual `.env` copying is needed. The script creates `.venv`,
installs the tested dependencies, creates `.env` with a random JWT secret if missing, waits for
PostgreSQL, applies migrations, and starts the API with auto-reload plus the email worker.
Existing `.env` credentials are preserved; only a missing, empty or example JWT secret is generated.
Swagger is at **http://localhost:8000/docs**. Verification/reset emails are written to `.dev-mail/`
with the default development configuration. Press **Ctrl+C** to stop the API and worker; the
PostgreSQL container and its data remain available.

```sh
./start.sh --skip-install          # Faster subsequent startup
./start.sh --setup-only            # Install/configure/migrate without starting the API
./start.sh --host 0.0.0.0          # Allow mobile devices on your local network
./start.sh --port 8001             # Choose a different API port
./start.sh --help                  # All options
```

This launcher targets Linux and does not depend on your username or a fixed installation path.
Clone/copy source files, not another machine's `.venv`; each machine creates its own environment.
It does not install system packages or configure real Google credentials. On Debian/Ubuntu,
Python's venv support may need the `python3-venv` package (or the package matching your Python version).
Other distributions use their own package managers. Internet access is required for dependency/image
downloads; the API port and PostgreSQL port 5432 must be available. Restart the script after changing
`.env` or email-worker code. API source changes are reloaded automatically.
Changing `--port` does not rewrite email/OAuth callback settings in `.env`.

If the Docker application is already using port 8000, stop its API and worker before switching
startup methods (this keeps PostgreSQL and its data):

```sh
docker compose --profile app stop api mail-worker
./start.sh
```

To stop the development database later: `docker compose stop db`.

## Manual setup (local Python + Docker PostgreSQL)

Requires Python 3.12 or newer and Docker with Compose. Run from the repository root.

```sh
git clone <your-repository-url> music-room-backend
cd music-room-backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
python -c 'import secrets; from pathlib import Path; p=Path(".env"); p.write_text(p.read_text().replace("replace-with-at-least-32-random-characters", secrets.token_urlsafe(48))); p.chmod(0o600)'
docker compose up -d db --wait
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --no-access-log
```

The current working copy already has a generated, ignored local `.env`; do not overwrite it unless
you intend to rotate its JWT secret. PostgreSQL is bound to localhost with development-only credentials.
Changing `.env` requires restarting API and worker processes.

In a second terminal, start the email outbox worker with the same environment:

```sh
source .venv/bin/activate
python -m mandatory.services.email_service
```

Open **http://localhost:8000/docs**. Readiness: **http://localhost:8000/api/v1/health**.
OpenAPI: **http://localhost:8000/openapi.json**. ReDoc: **http://localhost:8000/redoc**.

1. `POST /api/v1/auth/register` with `{"email":"alice@example.com","password":"A good long password 42!"}`.
2. Open the latest `.dev-mail/*.eml` locally and copy its `Token:` value. This directory is secret,
   development-only and ignored by Git. It is not an HTTP endpoint. No paid email provider is needed.
3. `POST /api/v1/auth/verify-email` with `{"token":"<copied token>","password":"<your new password>"}`.
4. `POST /api/v1/auth/login` with the registration credentials. Copy `access_token` into Swagger's
   **Authorize** dialog (without a `Bearer ` prefix), then call `GET /api/v1/users/me`.
5. Refresh using the opaque `refresh_token`; always replace both saved tokens from the response.
6. Logout sends a bearer access token and refresh token from the same session family.
7. Try forgot/reset password using the worker's next email. Recovery expires after one hour.

The integrated React Native verification screen accepts tokens from local `.eml` files.
This backend does not serve a verification webpage; Swagger also accepts the raw token. Missing Google credentials affect
only Google routes: they return a truthful 503 until configured.

## Docker application option

```sh
mkdir -m 700 -p .dev-mail
docker compose --profile app build
# Apply migrations before starting API and worker:
docker compose --profile app run --rm api alembic upgrade head
docker compose --profile app up -d api mail-worker
```

Compose starts the database dependency automatically. Host port 8000 is bound to localhost for this
option; expose it deliberately for physical-device testing. Read emails from `.dev-mail/` on the host.
The API/worker run as an unprivileged user. Production requires separate deployment configuration,
real credentials, TLS, backups and the controls in [SECURITY.md](docs/SECURITY.md).
`docker compose stop` preserves the development DB volume. Do not use `down -v` unless deleting
all local data is intended.

## Configuration

`.env.example` lists local configuration. Settings are validated by Pydantic. JWT/Google secret fields have redacted reprs;
never log the settings object because DATABASE_URL can also contain credentials. A JWT secret is mandatory; generate it rather than keeping the placeholder.

| Variable | Purpose |
|---|---|
| APP_ENV | development, test or production |
| DATABASE_URL | PostgreSQL SQLAlchemy URL (`postgresql+psycopg://...`) |
| JWT_SECRET / JWT_ISSUER / JWT_AUDIENCE | Random HMAC key, issuer and mobile audience |
| ACCESS_SECONDS / REFRESH_DAYS | Defaults: 900 seconds / absolute 30-day family lifetime |
| CORS_ORIGINS | JSON array of allowed browser origins; default [] |
| RATE_LIMIT / RATE_WINDOW_SECONDS | Defaults: 20 requests per 300-second fixed window |
| MAIL_DIRECTORY | Private folder for local verification/reset email files |
| EMAIL_LINK_BASE | Mobile app-link domain/base for verify-email and reset-password paths |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | Google **Web application** OAuth client for this backend exchange flow |
| GOOGLE_REDIRECT_URI | Exact registered HTTPS app link; local callback supplied for manual testing |

Emails are written locally as private `.eml` files; no external email provider is used.
Never commit `.env`, mail files or provider keys. Set production `EMAIL_LINK_BASE` to a domain the
React Native app is configured to handle, with paths `/verify-email` and `/reset-password`.

Google: follow the exact setup and end-to-end flow in [REACT_NATIVE_INTEGRATION.md](docs/REACT_NATIVE_INTEGRATION.md#google-configuration-and-flow).
No credentials are invented or committed. The backend receives codes plus PKCE verifiers, not
unverified client-decoded Google claims or a bare email address.

## Database migrations

```sh
alembic upgrade head
alembic current
alembic check
# After intentional model changes, create and review a migration:
alembic revision --autogenerate -m 'describe the change'
```

Migrations create relational users, profiles, provider identities, refresh sessions, single-use action
tokens, OAuth attempts, rate counters and mail jobs. Tables are never automatically created at API
startup. UTC timestamps, indexes, foreign keys and database uniqueness protect the state.

## Test every API operation with one command

```sh
sh test-api.sh
```

No running API or manual token copying is required. The script installs dependencies, starts the
isolated PostgreSQL test database, applies its migrations, and runs the authentication, profile,
security, concurrency and CORS tests. Existing development accounts and `.env` are not changed.
The test database is deliberately emptied by the tests; do not run simultaneous test sessions.

For subsequent runs: `sh test-api.sh --skip-install`. Like the startup script, this works from any
working directory using the script's path. It needs Python 3.12+, Docker/Compose access and port 5433.
It always targets Compose's `music_room_test` database, regardless of TEST_DATABASE_URL in your shell.

The terminal lists each test's pass/fail result and the API operations exercised. A nonzero exit code
means setup failed, a test failed, or an API operation was not exercised. Reports are written to
`.test-results/api-tests.xml` and `.test-results/api-coverage.json` (ignored by Git).
Operation coverage means requests were issued for every documented method/path; behavioral
assertions are in the tests. It is not a claim that all possible inputs or deployment configurations
have been checked. Latest local execution: **73 tests passed**, **19/19 operations exercised**, plus
**six startup checks passed**; one non-failing Starlette/httpx deprecation warning remains.

Google calls are mocked; emails are written to local files. Live Google consent, mobile integration
still require their own credentials and testing. These tests exercise the current application in-process
through HTTP using real PostgreSQL, rather than your already-running server or deployment proxy.

### CORS and frontend headers

CORS is enforced by browsers, including Expo web; native React Native and Postman do not enforce it.
The suite checks allowed/rejected origins, GET/POST/PATCH/DELETE preflights, authorization/JSON/client
metadata headers, and CORS headers on successful and error responses. The default empty origin list
is intentional. If your teammate uses a browser frontend, configure its exact origin in `.env`, e.g.:

```dotenv
CORS_ORIGINS=["http://localhost:5173"]
```

Restart the API after changing this value. Use the actual frontend origin, including scheme and port.
Postman working does not establish that a browser's origin is allowed. A configured-origin test is
not evidence that a different `.env` or reverse proxy has the same configuration.

## Tests and checks

Tests use actual PostgreSQL, not SQLite. They automatically apply migrations to an **isolated** DB.
The test fixture refuses to truncate a database whose name does not end in `_test`. Never point
`TEST_DATABASE_URL` at valuable data. Tests deliberately empty every application table there.

```sh
docker compose --profile test up -d test-db --wait
# Default: PostgreSQL on localhost:5433/music_room_test
pytest -q
ruff check app mandatory bonus tests scripts alembic
ruff format --check app mandatory bonus tests scripts alembic
python -m pip check
python -m unittest scripts.test_startup
python -m scripts.export_api
# With the local development server running:
python -m scripts.smoke
```

Set `TEST_DATABASE_URL` to override the dedicated test connection. Google calls are mocked and emails are written to local files
in automated tests; signed JWT/Google ID token checks, database transactions, uniqueness, locks,
rate limits, privacy and HTTP behavior are exercised. The live smoke test creates one development
account and delivery file; it never prints credentials/tokens. It must use the same local DB and file
mail configuration as the running server; avoid running it simultaneously with the mail worker.

`requirements.lock` records the resolved local test environment. For a repeatable dependency set:
`python -m pip install -r requirements.lock`, then `python -m pip install --no-deps -e .`.
The Docker build uses Python 3.12 and project dependency ranges. Run backend tests locally with `sh test-api.sh`; GitHub Actions is not configured.

## API endpoints

All paths use `/api/v1`. Full JSON examples, validation, success/error responses and status codes:
[API_CONTRACT.md](docs/API_CONTRACT.md). Import [postman_collection.json](docs/postman_collection.json)
into Postman; successful login/refresh/exchange automatically save tokens as collection variables.

| Method | Path |
|---|---|
| GET | /health |
| POST | /auth/register |
| POST | /auth/verify-email |
| POST | /auth/resend-verification |
| POST | /auth/login |
| POST | /auth/refresh |
| POST | /auth/logout |
| POST | /auth/logout-all |
| POST | /auth/forgot-password |
| POST | /auth/reset-password |
| POST | /auth/change-password |
| POST | /auth/google/start |
| GET | /auth/google/callback |
| POST | /auth/google/exchange |
| POST, DELETE | /auth/google/link |
| GET, PATCH | /users/me |
| GET | /users/{user_id}/public |

## Frontend handoff and project reference

Send your teammate [REACT_NATIVE_INTEGRATION.md](docs/REACT_NATIVE_INTEGRATION.md),
[API_CONTRACT.md](docs/API_CONTRACT.md), [openapi.json](docs/openapi.json),
[postman_collection.json](docs/postman_collection.json), and the reachable backend base URL.
Agree on production app-link domains and Google consent/test-user configuration together. Do not
send backend secrets or database credentials to the React Native app.

Architecture: [ARCHITECTURE.md](docs/ARCHITECTURE.md). Current service behavior, permissions and
limitations: [MUSIC_INTEGRATION.md](docs/MUSIC_INTEGRATION.md). AI-assisted implementation
requires maintainer review and understanding for the 42 defense.

### Google return to Music Room

The Google callback returns to `GOOGLE_WEB_RETURN_URL` (default
`http://localhost:8081/`) in the same browser tab. The frontend restores its pending
PKCE attempt and finishes login automatically. Native mobile sign-in still uses
the manual callback field. Add the exact web app origin to `CORS_ORIGINS` (for example
`["http://localhost:8081"]`). Restart the backend after changing `.env`.
On physical phones, `GOOGLE_REDIRECT_URI` must be a
reachable HTTPS backend callback registered in Google Cloud, rather than localhost.
The manual callback field remains available for local testing.

Run `make backend` to start both the API and mail worker. Repeating signup for an
unverified account queues a fresh verification email without changing its password.

### Mail retry scheduling

Run migrations (`python -m alembic upgrade head`) before restarting the mail worker
after updating. `make backend` does both automatically. Failed local file writes retain their
job and roll back the undelivered token. Each job retries after 30 seconds, then
60 seconds, doubling up to one hour between attempts. Other due jobs continue
immediately. Logs include job ID, attempt, error class; recipient addresses, credentials, and raw exception text are omitted.
`python -m mandatory.services.email_service --once` processes currently due jobs only;
future retries stay queued. Messages stay local and are not sent to inboxes.

### Friendships and profile privacy (subject V.1)

All routes require bearer authentication. Send `POST /api/v1/friends/requests` with
`{"user_id":"<other user UUID>"}`. Only the recipient can accept with
`POST /api/v1/friends/<sender UUID>/accept`. Duplicate and opposite-direction requests
return 409; a pending request never grants profile access.

`GET /api/v1/friends` lists accepted friends. `GET /api/v1/friends/requests` lists
incoming/outgoing pending requests (`requester_id` identifies the sender). Both use
`limit` (default 50, maximum 100) and `offset`. `DELETE /api/v1/friends/<other UUID>`
cancels, declines or removes the relationship; access is revoked after commit.

`GET /api/v1/users/<UUID>/friends-only` returns only id, public and friends_only
for an accepted friend or the owner. Strangers and pending requests receive 403.
Private information and music preferences remain owner-only; the existing public
endpoint continues to return public fields only.

Run migrations before starting the updated backend (`make backend` applies them). The new
friendship endpoints are ready for React Native integration; this backend change does
not replace the existing frontend friendship mocks.

## Music backend implementation

User search, Deezer metadata/previews, collaborative playlists, event voting/queue advancement,
resource invitations, delegated device control state, and authenticated WebSockets are implemented.
See [MUSIC_INTEGRATION.md](docs/MUSIC_INTEGRATION.md) for all routes, permission semantics,
React Native mock mappings, version-conflict handling, geo/time rules and playback limitations.
`make backend` applies migration `9c124f30d7aa` without deleting existing accounts or friendships.
The mobile folder was not changed by this work. Full audio playback, device execution and final
end-to-end integration must be verified in the client.

The mixed HTTP/WebSocket capacity test is available as
`python -m scripts.capacity_test`. It uses only an isolated `_test` database.
See [CAPACITY_RESULTS.json](docs/CAPACITY_RESULTS.json) for the measured local
workload and hardware, and [SUBJECT_SECURITY_AUDIT.md](docs/SUBJECT_SECURITY_AUDIT.md)
for limitations and remaining acceptance checks. Repeat on the deployment server
before claiming sustained capacity.

Step-by-step standalone benchmark instructions: [LOAD_TESTING.md](docs/LOAD_TESTING.md).

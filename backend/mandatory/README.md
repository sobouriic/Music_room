# Mandatory features

`api/` contains authentication, users, friendships, music services, device control,
and WebSocket routes. `services/` contains their application logic, provider
adapter, rate limiting, and local email worker.

Shared configuration, cryptography, database sessions, common models/schemas and
router composition stay in `backend/app/`. Migrations and the shared test harness
remain in `backend/alembic/` and `backend/tests/`. These are shared infrastructure,
not a second implementation of the mandatory features.

Run from the repository root: `make install`, then `make`.
API paths and the `app.main:app` entry point are unchanged. The mail worker is now
`python -m mandatory.services.email_service`.

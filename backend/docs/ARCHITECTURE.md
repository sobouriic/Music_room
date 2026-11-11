# Architecture

Music Room is a modular monolith with mandatory and bonus feature modules.
FastAPI exposes JSON REST APIs under `/api/v1`. PostgreSQL is authoritative. The integrated React Native/Expo client lives in `mobile/` and uses the JSON API.
PostgreSQL stores authentication, profiles, friendships, music resources, device control,
subscription plans, offline synchronization receipts and nearby-event notifications.

## Structure and responsibilities

- `mandatory/api`: HTTP handlers, explicit request/response schemas, authentication dependencies.
- `bonus`: subscriptions, idempotent offline playlist edits, and nearby-event notifications registry.
- `app/schemas`: Pydantic v2 validation and safe serialization; extra input fields are forbidden.
- `mandatory/services`: authentication, OAuth, profiles, shared rate limiting and email outbox worker.
- `app/repositories`: reusable user lookup/creation queries. Session/token queries stay near their
  transaction logic in services to keep the lock ordering visible and avoid trivial wrappers.
- `app/models/entities.py`: mandatory/shared SQLAlchemy entities; bonus tables are in `bonus/models.py`.
- `app/db`: declarative base, pooled synchronous sessions and user row locking.
- `app/core`: configuration, cryptographic primitives, errors and metadata audit logging.
- `alembic`: explicit versioned migrations, with no runtime table creation.
- `tests`: API integration, security regression and isolated provider behavior tests.
- `docs`: API contract, OpenAPI snapshot, frontend handoff, security and requirements mapping.
- `scripts`: executable smoke test and generated documentation helpers.

Synchronous SQLAlchemy/psycopg runs in FastAPI's worker thread pool. This avoids mixing async
and blocking database calls and makes transaction ownership straightforward. PostgreSQL JSONB
stores bounded, explicitly typed profile sections; authentication constraints use relational columns.
No generic repository framework, microservices or placeholder music features are introduced.

## Request lifecycle

Validation → IP/account rate limits where applicable → authenticated user/session dependency →
service transaction → safe response model → commit → metadata audit event. A database failure
rolls back the unit of work. Rate limits deliberately commit independently so failures still count.
Integrity constraint conflicts produce a generic 409. Duplicate email registration returns the same
202 as a new registration, including when two requests race.

Each access token includes only opaque user/session identifiers, token version and standard
JWT claims. Every authenticated request checks the user and session in PostgreSQL. This costs
one or two indexed lookups but enables immediate logout, password-reset and disable enforcement.
A rotated ancestor access token remains usable until its short expiration unless its family is revoked.

## Tables

| Table | Responsibility / constraints |
|---|---|
| users | UUID identity, unique normalized email, nullable Argon2id hash, verified/disabled flags, auth version |
| friendships | Canonical unordered user pair; pending/accepted status, sender, consent and cascade deletion |
| profiles | One-to-one FK; public, friends-only, private sections and music preferences |
| oauth_identities | Provider/subject globally unique; one identity per provider per user |
| refresh_sessions | Unique SHA-256 token digest, family index, expiry, used/revoked state |
| action_tokens | Verification/reset purpose, unique digest, expiration, consumed flag |
| oauth_attempts | One-use hashed state, nonce, PKCE challenge, login/link intent, optional linking user |
| rate_buckets | Atomic PostgreSQL upsert counters keyed by hashed IP/account scope |
| mail_jobs | Transactional delivery intent; no raw token stored in the database |

Timestamps are timezone-aware UTC. UUID primary keys avoid exposing sequential identifiers.
Nullable passwords represent social-only users; nullable OAuth attempt users represent login attempts.
Nullable `used_at` means a refresh token has not yet been consumed.

## Concurrency and email delivery

User-row locks serialize refresh, verification, password changes and session invalidation for a user.
Refresh tokens rotate once, preserving a 30-day absolute family lifetime. Reuse revokes the entire
family and commits that revocation before returning 401. Two simultaneous refresh requests yield
one success and one replay rejection; the successful token is then revoked. React Native must serialize
refreshes. Unique database constraints arbitrate racing registrations and OAuth identity links.

Mail delivery jobs commit with account creation/recovery requests. A separate worker selects jobs
using `FOR UPDATE SKIP LOCKED`, locks the user, creates a digest-only action token and delivers the
raw token. Recovery jobs are bound to the account credential version; outdated jobs are discarded
after password/session invalidation. Delivery failure rolls back token creation and retains the job for retry. A crash after writing a local message but before commit can leave an unusable or duplicate
file: local delivery is at least once, not exactly once. Never promise an email was delivered merely because a request returned 202.

## Future extension points

Add feature routers/services/models for rooms, voting and playlists in later phases. Reuse `get_db`,
`current_user`, user-row locking patterns, metadata logging and the shared error contract. The current
friendship policy exposes a separate authorized friends-only projection to the owner or accepted
friends. Pending requests grant no access and removals revoke access. Music preferences are owner-visible until a future privacy policy is chosen.
Future websockets must authenticate and authorize room operations server-side and emit the same
metadata audit events. Load testing, event synchronization and music permissions belong to later phases.

## Technology references

- [FastAPI JWT authentication guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [Google OIDC protocol and claim validation](https://developers.google.com/identity/openid-connect/openid-connect)
- [Google native app OAuth and PKCE](https://developers.google.com/identity/protocols/oauth2/native-app)

JWT access tokens plus opaque refresh tokens are engineering choices, rather than PDF mandates.
Dependency ranges live in `pyproject.toml`; `requirements.lock` records the tested environment.

## Subsequent music-service architecture

`music_resources` stores bounded (500-entry) playlist/event queue snapshots, settings and committed
versions. `music_invitations`, `track_votes` and `playback_devices` store access grants, unique votes
and per-device desired state. Ordered track JSONB snapshots are replaced under a resource row lock;
base_version prevents lost updates. Vote totals come from relational votes, not client counters.

Deezer is a fixed external catalog/preview provider; application data stays in PostgreSQL. Network
lookups occur before mutation locks and access/version are rechecked after lookup. WebSockets poll
committed version and current access in independent short-lived sessions, avoiding process-local
pubsub and supporting multiple API workers. This simple design trades database polling cost for
reliable state discovery. Capacity and a notification-broker upgrade require measurement.

The original Phase 1 sections above are historical boundaries; current routes and limits are
documented in MUSIC_INTEGRATION.md and generated OpenAPI.

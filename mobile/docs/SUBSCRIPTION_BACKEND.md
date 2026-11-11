# Subscription and offline backend integration

The backend now implements `GET /api/v1/subscription` and
`PUT /api/v1/subscription` with `{ "plan": "free" | "premium" }`.
Plans are persisted in PostgreSQL. Online playlist creation/editing is Free;
only offline saving, editing cached drafts and synchronization require Premium.
Private/invited-only access rules apply independently of the plan.
The switch is a development/test demo: no payment is taken. Production disables
self-service changes until an external billing provider is integrated.

The frontend uses server-confirmed plans and does not grant Premium when the
subscription endpoint is missing. Previously verified offline access is limited
to seven days and scoped to the current account and server.
Connection failures preserve the last verified plan and saved playlist tracks.
Offline drafts appear immediately and remain saved if synchronization fails.
Device control requires a connection; it is unavailable in offline mode.

See [backend bonus guide](../../backend/bonus/README.md) for request/response
examples, offline conflicts and replay, nearby notifications and speaker testing, and validation status.

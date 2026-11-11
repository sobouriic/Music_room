"""Generate the OpenAPI snapshot, endpoint reference and Postman collection."""

import json
import re
from pathlib import Path

from app.main import app

BASE = "/api/v1"
SAMPLE_USER = "11111111-1111-4111-8111-111111111111"
EMAIL = {"email": "alice@example.com"}
REGISTER = {**EMAIL, "password": "A good long password 42!"}
MESSAGE = {"message": "If the account is eligible, an email will be sent"}
PAIR = {
    "access_token": "<JWT access token>",
    "refresh_token": "<opaque refresh token>",
    "token_type": "bearer",
    "expires_in": 900,
}
ME = {
    "id": SAMPLE_USER,
    "email": "alice@example.com",
    "verified": True,
    "has_password": True,
    "providers": [],
    "public": {"display_name": "Alice", "bio": ""},
    "friends_only": {"location": ""},
    "private": {"notes": ""},
    "music_preferences": [],
}
# method, path, bearer required, input example, success status, response example, errors, notes
ENDPOINTS = [
    ("GET", "/health", False, None, 200, {"status": "ok"}, "503", "Checks database connectivity."),
    (
        "POST",
        "/auth/register",
        False,
        REGISTER,
        202,
        MESSAGE,
        "422, 429",
        "Creates an unverified password account and queues email. Existing addresses receive the same response.",
    ),
    (
        "POST",
        "/auth/verify-email",
        False,
        {"token": "{{verification_token}}", "password": REGISTER["password"]},
        200,
        {"message": "Email verified"},
        "400, 422, 429",
        "24-hour single-use verification token. Establish the email owner's password here; any unverified signup password is replaced.",
    ),
    (
        "POST",
        "/auth/resend-verification",
        False,
        EMAIL,
        202,
        MESSAGE,
        "422, 429",
        "Queues another verification for an eligible unverified account.",
    ),
    (
        "POST",
        "/auth/login",
        False,
        REGISTER,
        200,
        PAIR,
        "401, 422, 429",
        "JSON email/password login; no OAuth password-grant form. Unverified/disabled accounts receive generic 401.",
    ),
    (
        "POST",
        "/auth/refresh",
        False,
        {"refresh_token": "{{refresh_token}}"},
        200,
        PAIR,
        "401, 422, 429",
        "Replaces the refresh token. Reuse revokes the family. Serialize refreshes on the client.",
    ),
    (
        "POST",
        "/auth/logout",
        True,
        {"refresh_token": "{{refresh_token}}"},
        200,
        {"message": "Logged out"},
        "400, 401, 422, 429",
        "Requires access token and refresh token from the same session family.",
    ),
    (
        "POST",
        "/auth/logout-all",
        True,
        None,
        200,
        {"message": "All sessions revoked"},
        "401, 429",
        "Revokes all access and refresh sessions immediately.",
    ),
    (
        "POST",
        "/auth/forgot-password",
        False,
        EMAIL,
        202,
        MESSAGE,
        "422, 429",
        "Generic response; only eligible password accounts receive mail.",
    ),
    (
        "POST",
        "/auth/reset-password",
        False,
        {"token": "{{reset_token}}", "password": "A replacement password 43!"},
        200,
        {"message": "Password reset; sign in again"},
        "400, 422, 429",
        "One-hour single-use token; invalidates other reset tokens, queued resets and all sessions.",
    ),
    (
        "POST",
        "/auth/change-password",
        True,
        {"current_password": REGISTER["password"], "password": "A replacement password 43!"},
        200,
        {"message": "Password changed; sign in again"},
        "401, 403, 422, 429",
        "Current password is required for password accounts. Google-only verified users may omit it to add a password. All sessions revoked.",
    ),
    (
        "POST",
        "/auth/google/start",
        False,
        {"code_challenge": "{{code_challenge}}", "intent": "login"},
        200,
        {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
            "state": "<random state>",
            "expires_in": 600,
        },
        "401, 422, 429, 503",
        "intent is login or link. Linking requires a bearer token. Use PKCE S256; keep verifier/state on device.",
    ),
    (
        "GET",
        "/auth/google/callback",
        False,
        None,
        200,
        "<!doctype html>...Google callback return bridge...</html>",
        "429",
        "Native attempts receive HTTP 302 to musicroom://oauth. Web attempts receive HTML redirecting to GOOGLE_WEB_RETURN_URL with a #google-callback= fragment. The integrated React Native/Expo browser client validates the saved attempt and exchanges the code. This GET does not issue login tokens.",
    ),
    (
        "POST",
        "/auth/google/exchange",
        False,
        {
            "state": "{{oauth_state}}",
            "code": "{{google_code}}",
            "code_verifier": "{{code_verifier}}",
        },
        200,
        PAIR,
        "400, 401, 409, 422, 429, 503",
        "Exchanges a one-time code and validates the Google ID token. Automatically signs into the matching email account or creates one. Disabled accounts and conflicting identities are rejected. Unverified signup credentials are invalidated before Google verifies the account.",
    ),
    (
        "POST",
        "/auth/google/link",
        True,
        {
            "state": "{{oauth_state}}",
            "code": "{{google_code}}",
            "code_verifier": "{{code_verifier}}",
        },
        200,
        {"message": "Google linked"},
        "400, 401, 403, 409, 422, 429, 503",
        "Requires an unconsumed intent=link attempt bound to this authenticated user. Does not change account email or password-email verification.",
    ),
    (
        "DELETE",
        "/auth/google/link",
        True,
        None,
        200,
        {"message": "Google unlinked; sign in again"},
        "401, 409, 429",
        "Refuses removal of the last authentication method. Actual unlink revokes all sessions.",
    ),
    (
        "GET",
        "/users/me",
        True,
        None,
        200,
        ME,
        "401",
        "Owner view includes all four profile categories.",
    ),
    (
        "PATCH",
        "/users/me",
        True,
        {
            "public": {"display_name": "Alice"},
            "friends_only": {"location": "Casablanca"},
            "private": {"notes": "Only me"},
            "music_preferences": ["jazz"],
        },
        200,
        ME,
        "401, 422",
        "Partial typed section merge. Lists replace. Omitted/null sections remain unchanged; empty strings/lists clear fields. No email/password/role/owner updates.",
    ),
    (
        "GET",
        "/users/{user_id}/public",
        True,
        None,
        200,
        {"id": SAMPLE_USER, "public": ME["public"]},
        "401, 404, 422",
        "Any authenticated user can view only explicitly public fields. Friends-only data is available separately to accepted friends or the owner.",
    ),
]


ENDPOINTS.extend(
    [
        (
            "GET",
            "/friends",
            True,
            None,
            200,
            [{"user_id": SAMPLE_USER, "requester_id": SAMPLE_USER, "status": "accepted"}],
            "401, 422, 429",
            "Lists accepted friendships for the caller. Query limit (1–100, default 50) and offset (default 0). Disabled users are excluded.",
        ),
        (
            "GET",
            "/friends/requests",
            True,
            None,
            200,
            [{"user_id": SAMPLE_USER, "requester_id": SAMPLE_USER, "status": "pending"}],
            "401, 422, 429",
            "Lists incoming and outgoing pending requests, paginated with limit/offset. requester_id identifies the sender; user_id is the other participant.",
        ),
        (
            "POST",
            "/friends/requests",
            True,
            {"user_id": SAMPLE_USER},
            201,
            {"user_id": SAMPLE_USER, "requester_id": "<caller UUID>", "status": "pending"},
            "400, 401, 403, 404, 409, 422, 429",
            "Request friendship with another verified enabled user by UUID. Self requests are 400; existing friendship or either-direction request is 409. Pending requests grant no profile access.",
        ),
        (
            "POST",
            "/friends/{user_id}/accept",
            True,
            None,
            200,
            {"user_id": SAMPLE_USER, "requester_id": SAMPLE_USER, "status": "accepted"},
            "400, 401, 403, 404, 409, 422, 429",
            "Only the recipient can accept. user_id is the original sender. Unknown requests return 404; sender self-acceptance is forbidden.",
        ),
        (
            "DELETE",
            "/friends/{user_id}",
            True,
            None,
            200,
            {"message": "Friendship or request removed"},
            "400, 401, 403, 404, 422, 429",
            "Either participant may cancel/decline a pending request or remove an accepted friendship. user_id is the other participant. Friends-only access is revoked after commit.",
        ),
        (
            "GET",
            "/users/{user_id}/friends-only",
            True,
            None,
            200,
            {"id": SAMPLE_USER, "public": ME["public"], "friends_only": ME["friends_only"]},
            "401, 403, 422",
            "Only the owner or an accepted friend can read. Pending requests and strangers receive 403; unavailable/disabled targets also receive 403. Never returns email, private fields or music preferences. Public endpoint stays public-only.",
        ),
    ]
)


MUSIC_EXAMPLES = {
    ("POST", "/activity"): {
        "events": [
            {
                "event_id": "22222222-2222-4222-8222-222222222222",
                "action": "playback_start",
                "occurred_at": "2026-11-05T16:00:00Z",
            }
        ]
    },
    ("PUT", "/subscription"): {"plan": "premium"},
    ("POST", "/playlists/{resource_id}/offline"): {
        "mutation_id": "22222222-2222-4222-8222-222222222222",
        "base_version": 1,
        "track_ids": [],
    },
    ("POST", "/playlists"): {"name": "Road trip", "visibility": "public", "license": "open"},
    ("POST", "/events"): {"name": "Friday party", "visibility": "public", "license": "open"},
    ("PUT", "/playlists/{resource_id}"): {
        "name": "Road trip",
        "visibility": "private",
        "license": "invited",
        "base_version": 1,
    },
    ("PUT", "/events/{resource_id}"): {
        "name": "Friday party",
        "visibility": "public",
        "license": "open",
        "base_version": 1,
    },
    ("POST", "/{collection}/{resource_id}/tracks"): {"deezer_id": 67238732, "base_version": 1},
    ("POST", "/playlists/{resource_id}/tracks/move"): {
        "from_index": 0,
        "to_index": 1,
        "base_version": 1,
    },
    ("POST", "/{collection}/{resource_id}/invitations"): {
        "user_id": "{{user_id}}",
        "base_version": 1,
    },
    ("POST", "/events/{resource_id}/tracks/{track_id}/votes"): {},
    ("DELETE", "/events/{resource_id}/tracks/{track_id}/votes"): {},
    ("POST", "/events/{resource_id}/advance"): {"base_version": 1},
    ("POST", "/devices"): {"name": "Living room speaker"},
    ("PUT", "/devices/{device_id}/delegation"): {"friend_id": "{{user_id}}", "base_version": 1},
    ("POST", "/devices/{device_id}/control"): {
        "action": "play",
        "deezer_id": 67238732,
        "base_version": 1,
    },
}


def include_new_operations():
    """Keep every live operation in the handoff artifacts, including music routes."""
    known = {(method, BASE + path) for method, path, *_ in ENDPOINTS}
    for full, operations in app.openapi()["paths"].items():
        path = full.removeprefix(BASE)
        for method, operation in operations.items():
            method = method.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"} or (method, full) in known:
                continue
            status = next(int(code) for code in operation["responses"] if code.startswith("2"))
            query = [p["name"] for p in operation.get("parameters", []) if p["in"] == "query"]
            notes = (
                operation.get("summary", "")
                + ". See OpenAPI response schemas and MUSIC_INTEGRATION.md."
            )
            if query:
                notes += " Query parameters: " + ", ".join(query) + "."
            if "{collection}" in path:
                notes += " collection is playlists or events."
            ENDPOINTS.append(
                (
                    method,
                    path,
                    True,
                    MUSIC_EXAMPLES.get((method, path)),
                    status,
                    {"schema": "See live OpenAPI response schema"},
                    "400, 401, 403, 404, 409, 422, 429, 503",
                    notes,
                )
            )


def main():
    include_new_operations()
    docs = Path("docs")
    docs.mkdir(exist_ok=True)
    (docs / "openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")
    lines = [
        "# API contract",
        "",
        "Generated by `python -m scripts.export_api`; regenerate after API changes.",
        "",
        "Base URL: `http://localhost:8001` (combined local development). All routes below include `/api/v1`.",
        "Swagger: `/docs`; machine-readable source: `/openapi.json` (snapshot: `docs/openapi.json`).",
        "Request/response bodies are JSON except the HTML Google callback. Bearer authorization uses `Authorization: Bearer <access_token>`.",
        "Swagger uses the Authorize button: paste the access token only. Login uses a JSON body.",
        "",
        "## Shared validation and errors",
        "",
        "Email: valid address, casefolded. Password registration/reset/change: 12–128 characters, at least five distinct characters, rejects a small trivial-password denylist. Login accepts 1–128 characters.",
        "Tokens: 20–2048 characters. Google codes: 1–4096 characters; verifier: 43–128 RFC 7636 characters; challenge: 43 base64url characters. Unknown input fields are rejected.",
        "Profile: display_name ≤100, bio ≤1000, location ≤100, notes ≤1000; music_preferences ≤50 strings, each 1–100 characters. See OpenAPI schemas for every field.",
        "",
        "All endpoints can also return 503 for database unavailability and 500 for unexpected server failure. All auth routes can return 429, including callback. Rate limits default to 20 requests per 300 seconds per socket peer and separately per normalized email for registration/login/resend/recovery. 429 includes Retry-After in seconds.",
        "",
        '```json\n{"error":{"code":"invalid_credentials","message":"Invalid email or password"}}\n```',
        "",
        '```json\n{"error":{"code":"validation_error","message":"Invalid request","fields":[{"field":"body.email","type":"value_error"}]}}\n```',
        "",
        "Error codes: unauthorized / invalid_credentials / invalid_google_identity (401); invalid_token / invalid_refresh / invalid_oauth_state / invalid_pkce (400 or 401 as listed); refresh_reuse (401); last_auth_method / identity_conflict / conflict (409); verification_required / disabled (403); not_found (404); rate_limited (429); google_not_configured / database_unavailable (503). 401 includes WWW-Authenticate: Bearer.",
        "",
        "Provide optional untrusted metadata headers: `X-App-Platform`, `X-App-Device`, `X-App-Version`. Do not put secrets in them. Responses use Cache-Control: no-store.",
        "",
        "Examples use Postman variables; replace them with actual values before sending.",
        "",
    ]
    items = []
    for method, path, required, body, status, response, errors, notes in ENDPOINTS:
        full = BASE + path
        lines += [
            f"## {method} {full}",
            "",
            f"Authentication: {'bearer access token' if required else 'none (bearer required for Google link intent)' if path == '/auth/google/start' else 'none'}.",
            "",
            notes,
            "",
            f"Success: **{status}**. Errors: **{errors}**.",
            "",
        ]
        if body is not None:
            lines += ["Request:", "", "```json", json.dumps(body, indent=2), "```", ""]
        else:
            lines += ["Request body: none.", ""]
        lines += ["Response:", "", "```json", json.dumps(response, indent=2), "```", ""]
        request = {
            "method": method,
            "header": [
                {"key": "X-App-Platform", "value": "Android"},
                {"key": "X-App-Device", "value": "Postman"},
                {"key": "X-App-Version", "value": "1.0.0"},
            ],
            "url": "{{base_url}}" + re.sub(r"\{(\w+)\}", r"{{\1}}", full),
            "description": notes,
        }
        operation = app.openapi()["paths"][full][method.lower()]
        query_parts = []
        for parameter in operation.get("parameters", []):
            if parameter["in"] == "query" and parameter.get("required"):
                value = "1" if parameter["name"] == "base_version" else "rock"
                query_parts.append(parameter["name"] + "=" + value)
        if query_parts:
            request["url"] += "?" + "&".join(query_parts)
        if not required and path != "/auth/google/start":
            request["auth"] = {"type": "noauth"}
        if body is not None:
            request["header"].append({"key": "Content-Type", "value": "application/json"})
            request["body"] = {
                "mode": "raw",
                "raw": json.dumps(body, indent=2),
                "options": {"raw": {"language": "json"}},
            }
        item = {"name": f"{method} {full}", "request": request}
        if response is PAIR:
            item["event"] = [
                {
                    "listen": "test",
                    "script": {
                        "type": "text/javascript",
                        "exec": [
                            "if (pm.response.code === 200) {",
                            "  const data = pm.response.json();",
                            "  pm.collectionVariables.set('access_token', data.access_token);",
                            "  pm.collectionVariables.set('refresh_token', data.refresh_token);",
                            "}",
                        ],
                    },
                }
            ]
        if path == "/auth/google/start":
            item["event"] = [
                {
                    "listen": "test",
                    "script": {
                        "type": "text/javascript",
                        "exec": [
                            "if (pm.response.code === 200) pm.collectionVariables.set('oauth_state', pm.response.json().state);"
                        ],
                    },
                }
            ]
        items.append(item)
    (docs / "API_CONTRACT.md").write_text("\n".join(lines))
    collection = {
        "info": {
            "name": "Music Room — Phase 1",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}],
        },
        "variable": [
            {"key": name, "value": value}
            for name, value in {
                "base_url": "http://localhost:8001",
                "collection": "playlists",
                "deezer_id": "67238732",
                "resource_id": "",
                "track_id": "",
                "device_id": "",
                "access_token": "",
                "refresh_token": "",
                "verification_token": "",
                "reset_token": "",
                "oauth_state": "",
                "google_code": "",
                "code_verifier": "",
                "code_challenge": "",
                "user_id": SAMPLE_USER,
            }.items()
        ],
        "item": items,
    }
    (docs / "postman_collection.json").write_text(json.dumps(collection, indent=2) + "\n")


if __name__ == "__main__":
    main()

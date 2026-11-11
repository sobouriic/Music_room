import json
import logging
from uuid import uuid4

from app.core.security import now
from tests.conftest import account, headers


def test_local_actions_are_authenticated_bounded_and_redacted(client, caplog):
    body = {
        "events": [
            {"event_id": str(uuid4()), "action": "playback_start", "occurred_at": now().isoformat()}
        ]
    }
    assert client.post("/api/v1/activity", json=body).status_code == 401
    auth = headers(account(client))
    with caplog.at_level(logging.INFO, logger="music_room.audit"):
        response = client.post(
            "/api/v1/activity",
            json=body,
            headers={
                **auth,
                "X-App-Platform": "android",
                "X-App-Device": "Pixel\tbad",
                "X-App-Version": "0.1.0",
            },
        )
    assert response.status_code == 204
    row = next(json.loads(r.message) for r in caplog.records if "CLIENT_ACTION" in r.message)
    assert row["platform"] == "android"
    assert row["device"] == "Pixel?bad"
    assert row["app_version"] == "0.1.0"
    assert "password" not in row and "access_token" not in row
    assert (
        client.post(
            "/api/v1/activity", json={"events": body["events"] * 51}, headers=auth
        ).status_code
        == 422
    )
    body["events"][0]["action"] = "arbitrary private data"
    assert client.post("/api/v1/activity", json=body, headers=auth).status_code == 422

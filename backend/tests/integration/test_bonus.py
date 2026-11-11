from uuid import uuid4

import pytest

from tests.conftest import account, headers
from tests.integration import test_music as music_tests
from tests.integration.test_music import add, create

BASE = "/api/v1"


@pytest.fixture
def people(client):
    result = music_tests.people.__wrapped__(client)
    for _, auth, _ in result:
        assert (
            client.put(BASE + "/subscription", headers=auth, json={"plan": "premium"}).status_code
            == 200
        )
    return result


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    return music_tests.catalog.__wrapped__(monkeypatch)


def test_subscription_defaults_switches_and_isolation(client):
    alice = headers(account(client))
    bob = headers(account(client, email="bob@example.com"))
    assert client.get(BASE + "/subscription").status_code == 401
    assert client.get(BASE + "/subscription", headers=alice).json() == {
        "plan": "free",
        "billing_mode": "demo",
    }
    playlist = create(client, alice)
    assert playlist["visibility"] == "public" and playlist["license"] == "open"
    playlist = add(client, alice, playlist).json()
    # A second Free user can collaborate on the default public/open playlist.
    playlist = add(client, bob, playlist, track=2).json()
    pid = playlist["id"]
    moved = client.post(
        BASE + f"/playlists/{pid}/tracks/move",
        headers=bob,
        json={
            "from_index": 0,
            "to_index": 1,
            "base_version": playlist["version"],
        },
    )
    assert moved.status_code == 200, moved.text
    playlist = moved.json()
    assert (
        client.put(BASE + "/subscription", headers=alice, json={"plan": "premium"}).status_code
        == 200
    )
    assert client.get(BASE + "/subscription", headers=bob).json()["plan"] == "free"
    assert (
        client.put(BASE + "/subscription", headers=alice, json={"plan": "gold"}).status_code == 422
    )
    assert (
        client.put(BASE + "/subscription", headers=alice, json={"plan": "free"}).status_code == 200
    )
    # Downgrading only removes offline entitlement, not ordinary editing.
    updated = add(client, alice, playlist, track=3)
    assert updated.status_code == 200, updated.text
    playlist = updated.json()
    response = client.post(
        BASE + f"/playlists/{pid}/offline",
        headers=alice,
        json={
            "mutation_id": str(uuid4()),
            "base_version": playlist["version"],
            "track_ids": [],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "premium_required"


def test_offline_sync_atomic_replay_and_conflict(client, people):
    (_, alice, _), (_, bob, _), _ = people
    playlist = create(client, alice)
    playlist = add(client, alice, playlist).json()
    playlist = add(client, alice, playlist, track=2).json()
    path = BASE + f"/playlists/{playlist['id']}/offline"
    body = {
        "mutation_id": str(uuid4()),
        "base_version": playlist["version"],
        "track_ids": [t["id"] for t in reversed(playlist["tracks"])],
    }
    first = client.post(path, headers=alice, json=body)
    assert first.status_code == 200, first.text
    assert [t["id"] for t in first.json()["tracks"]] == body["track_ids"]
    assert client.post(path, headers=alice, json=body).json() == first.json()
    assert client.post(path, headers=alice, json={**body, "track_ids": []}).status_code == 409
    assert client.post(path, headers=bob, json=body).status_code == 409
    assert (
        client.post(path, headers=alice, json={**body, "mutation_id": str(uuid4())}).status_code
        == 409
    )
    invalid = {
        **body,
        "mutation_id": str(uuid4()),
        "base_version": first.json()["version"],
        "track_ids": [str(uuid4())],
    }
    assert client.post(path, headers=alice, json=invalid).status_code == 422
    assert (
        client.post(
            path, headers=alice, json={**invalid, "track_ids": [body["track_ids"][0]] * 2}
        ).status_code
        == 422
    )
    assert client.get(BASE + f"/playlists/{playlist['id']}", headers=alice).json() == first.json()
    assert (
        client.put(BASE + "/subscription", headers=alice, json={"plan": "free"}).status_code == 200
    )
    assert client.post(path, headers=alice, json=body).status_code == 403


def test_offline_sync_rechecks_private_access(client, people):
    (_, alice, _), (_, bob, bid), _ = people
    playlist = create(client, alice, visibility="private")
    path = BASE + f"/playlists/{playlist['id']}/offline"
    body = {"mutation_id": str(uuid4()), "base_version": playlist["version"], "track_ids": []}
    assert client.post(path, headers=bob, json=body).status_code == 404
    assert (
        client.post(
            BASE + f"/playlists/{playlist['id']}/invitations",
            headers=alice,
            json={"user_id": bid, "base_version": playlist["version"]},
        ).status_code
        == 201
    )
    playlist = client.get(BASE + f"/playlists/{playlist['id']}", headers=alice).json()
    body["base_version"] = playlist["version"]
    synced = client.post(path, headers=bob, json=body)
    assert synced.status_code == 200
    assert (
        client.delete(
            BASE + f"/playlists/{playlist['id']}/invitations/{bid}",
            headers=alice,
            params={"base_version": synced.json()["version"]},
        ).status_code
        == 200
    )
    assert client.post(path, headers=bob, json=body).status_code == 404


def test_nearby_public_active_events_only(client, people):
    from datetime import timedelta

    from app.core.security import now

    (_, alice, _), (_, bob, _), _ = people
    rule = {
        "lat": 33.57,
        "lng": -7.59,
        "radius_m": 200,
        "starts_at": (now() - timedelta(minutes=5)).isoformat(),
        "ends_at": (now() + timedelta(minutes=5)).isoformat(),
    }
    event = create(client, alice, "events", license="geo_time", geo_rule=rule)
    create(client, alice, "events", visibility="private", license="geo_time", geo_rule=rule)
    create(client, alice, "events", license="geo_time", geo_rule={**rule, "lng": 0})
    create(
        client,
        alice,
        "events",
        license="geo_time",
        geo_rule={
            **rule,
            "starts_at": (now() - timedelta(hours=2)).isoformat(),
            "ends_at": (now() - timedelta(hours=1)).isoformat(),
        },
    )
    client.put(BASE + "/subscription", headers=bob, json={"plan": "free"})
    path = BASE + "/events/nearby"
    params = {"lat": 33.57, "lng": -7.59}
    assert client.get(path, params=params).status_code == 401
    response = client.get(path, headers=bob, params=params)
    assert response.status_code == 200, response.text
    assert [value["id"] for value in response.json()] == [event["id"]]
    assert len(client.get(path, headers=alice, params=params).json()) == 1
    assert client.get(path, headers=bob, params={"lat": 0, "lng": 0}).json() == []
    assert client.get(path, headers=bob, params={"lat": "nan", "lng": 0}).status_code == 422
    assert client.get(path, headers=bob, params={"lat": 91, "lng": 0}).status_code == 422
    assert client.get(path, headers=bob, params={**params, "radius_m": 100001}).status_code == 422

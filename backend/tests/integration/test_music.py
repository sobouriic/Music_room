from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import now
from app.db.session import session_factory
from app.models.entities import User
from tests.conftest import account, headers

BASE = "/api/v1"


@pytest.fixture
def people(client):
    result = []
    for name in ("alice", "bob", "charlie"):
        pair = account(client, email=f"{name}@example.com")
        auth = headers(pair)
        uid = client.get(BASE + "/users/me", headers=auth).json()["id"]
        client.patch(
            BASE + "/users/me",
            headers=auth,
            json={
                "public": {"display_name": name.title()},
                "private": {"notes": "secret"},
                "friends_only": {"location": "private-location"},
            },
        )
        result.append((pair, auth, uid))
    return result


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    def track(deezer_id):
        return {
            "deezer_id": deezer_id,
            "title": f"Track {deezer_id}",
            "artist": "Artist",
            "duration": 120,
            "preview_url": "https://cdn.example.com/preview.mp3",
            "artwork_url": None,
            "deezer_url": f"https://www.deezer.com/track/{deezer_id}",
        }

    monkeypatch.setattr("mandatory.services.deezer_service.track", track)
    monkeypatch.setattr(
        "mandatory.services.deezer_service.search", lambda q, limit, offset: [track(1)]
    )


def create(client, auth, collection="playlists", **extra):
    response = client.post(BASE + "/" + collection, headers=auth, json={"name": "Party", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def add(client, auth, resource, collection="playlists", track=1):
    return client.post(
        BASE + f"/{collection}/{resource['id']}/tracks",
        headers=auth,
        json={"deezer_id": track, "base_version": resource["version"]},
    )


def invite(client, auth, resource, uid, collection="playlists"):
    return client.post(
        BASE + f"/{collection}/{resource['id']}/invitations",
        headers=auth,
        json={"user_id": uid, "base_version": resource["version"]},
    )


def test_public_user_search_never_leaks_email_or_private_sections(client, people, db):
    (_, alice, aid), (_, bob, _), (_, _, cid) = people
    result = client.get(BASE + "/users/search?q=ali", headers=bob)
    assert result.status_code == 200
    assert result.json() == [{"id": aid, "public": {"display_name": "Alice", "bio": ""}}]
    for secret in ("@example.com", "private-location", "secret", "music_preferences"):
        assert secret not in result.text
    assert client.get(BASE + "/users/search?q=ali", headers=alice).json() == []
    assert client.get(BASE + "/users/search?q=%25", headers=bob).status_code == 422
    assert client.get(BASE + "/users/search?q=zz", headers=bob).json() == []
    assert client.get(BASE + "/users/search?q=  ", headers=bob).status_code == 422
    charlie = db.get(User, UUID(cid))
    charlie.disabled = True
    db.commit()
    assert client.get(BASE + "/users/search?q=charlie", headers=bob).json() == []


def test_catalog_routes_and_authentication(client, people):
    _, auth, _ = people[0]
    assert client.get(BASE + "/tracks/search?q=rock", headers=auth).json()[0]["deezer_id"] == 1
    assert client.get(BASE + "/tracks/42", headers=auth).json()["deezer_id"] == 42
    assert client.get(BASE + "/tracks/0", headers=auth).status_code == 422
    assert client.get(BASE + "/tracks/search?q= ", headers=auth).status_code == 422
    for path in (
        "/tracks/search?q=rock",
        "/playlists",
        "/events",
        "/devices",
        "/users/search?q=alice",
    ):
        assert client.get(BASE + path).status_code == 401


def test_private_visibility_invitations_and_licenses(client, people):
    (_, alice, _), (_, bob, bid), (_, charlie, _) = people
    playlist = create(client, alice, visibility="private", license="invited")
    path = BASE + "/playlists/" + playlist["id"]
    assert client.get(path, headers=bob).status_code == 404
    assert client.get(BASE + "/playlists", headers=bob).json() == []
    assert invite(client, bob, playlist, bid).status_code == 404
    assert invite(client, alice, playlist, bid).status_code == 201
    playlist = client.get(path, headers=bob).json()
    assert len(client.get(BASE + "/playlists", headers=bob).json()) == 1
    assert len(client.get(path + "/invitations", headers=alice).json()) == 1
    assert client.get(path + "/invitations", headers=bob).status_code == 403
    assert client.post(path + "/invitations/accept", headers=bob).status_code == 200
    playlist = client.get(path, headers=bob).json()
    playlist = add(client, bob, playlist).json()
    assert (
        client.put(
            path,
            headers=bob,
            json={
                "name": "Hijack",
                "base_version": playlist["version"],
            },
        ).status_code
        == 403
    )
    assert client.get(path, headers=charlie).status_code == 404
    assert (
        client.delete(
            path + "/invitations/" + bid,
            headers=alice,
            params={"base_version": playlist["version"]},
        ).status_code
        == 200
    )
    assert client.get(path, headers=bob).status_code == 404
    assert client.get(path, headers=alice).status_code == 200


def test_playlist_edits_conflicts_remove_and_delete(client, people):
    (_, alice, _), (_, bob, _), _ = people
    p = create(client, alice)
    path = BASE + "/playlists/" + p["id"]
    p = add(client, bob, p).json()
    p = add(client, alice, p, track=2).json()
    original = [t["id"] for t in p["tracks"]]
    stale_version = p["version"]
    response = client.post(
        path + "/tracks/move",
        headers=bob,
        json={
            "from_index": 0,
            "to_index": 1,
            "base_version": stale_version,
        },
    )
    assert response.status_code == 200
    p = response.json()
    assert [t["id"] for t in p["tracks"]] == original[::-1]
    assert (
        client.post(
            path + "/tracks/move",
            headers=alice,
            json={
                "from_index": 0,
                "to_index": 1,
                "base_version": stale_version,
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/tracks/move",
            headers=bob,
            json={
                "from_index": 0,
                "to_index": 99,
                "base_version": p["version"],
            },
        ).status_code
        == 400
    )
    assert add(client, alice, p, track=1).status_code == 409
    response = client.delete(
        path + "/tracks/" + original[0], headers=bob, params={"base_version": p["version"]}
    )
    assert response.status_code == 200
    p = response.json()
    assert len(p["tracks"]) == 1
    response = client.put(
        path,
        headers=alice,
        json={
            "name": "Renamed",
            "license": "invited",
            "base_version": p["version"],
        },
    )
    assert response.status_code == 200
    p = response.json()
    assert add(client, bob, p, track=3).status_code == 403
    assert (
        client.delete(path, headers=bob, params={"base_version": p["version"]}).status_code == 403
    )
    assert (
        client.delete(path, headers=alice, params={"base_version": p["version"]}).status_code == 200
    )
    assert client.get(path, headers=alice).status_code == 404


def test_simultaneous_playlist_edits_reject_one_stale_writer(client, people):
    (_, alice, _), (_, bob, _), _ = people
    p = create(client, alice)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(add, client, alice, p, track=1)
        b = pool.submit(add, client, bob, p, track=2)
        assert sorted([a.result().status_code, b.result().status_code]) == [200, 409]
    saved = client.get(BASE + "/playlists/" + p["id"], headers=alice).json()
    assert len(saved["tracks"]) == 1 and saved["version"] == 2


def test_event_votes_are_unique_ranked_and_advance_is_owner_only(client, people):
    (_, alice, _), (_, bob, _), (_, charlie, _) = people
    event = create(client, alice, "events")
    path = BASE + "/events/" + event["id"]
    event = add(client, alice, event, "events", 1).json()
    event = add(client, bob, event, "events", 2).json()
    first, second = [t["id"] for t in event["tracks"]]
    vote_path = path + "/tracks/" + second + "/votes"
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(client.post, vote_path, headers=bob, json={})
        b = pool.submit(client.post, vote_path, headers=bob, json={})
        assert sorted([a.result().status_code, b.result().status_code]) == [200, 409]
    event = client.post(vote_path, headers=charlie, json={}).json()
    assert event["tracks"][0]["id"] == second and event["tracks"][0]["votes"] == 2
    assert event["tracks"][0]["voted_by_me"] is True
    event = client.request("DELETE", vote_path, headers=bob, json={}).json()
    assert event["tracks"][0]["votes"] == 1 and not event["tracks"][0]["voted_by_me"]
    assert (
        client.post(
            path + "/advance", headers=bob, json={"base_version": event["version"]}
        ).status_code
        == 403
    )
    response = client.post(
        path + "/advance", headers=alice, json={"base_version": event["version"]}
    )
    assert response.status_code == 200
    event = response.json()
    assert event["current_track"]["id"] == second
    assert [t["id"] for t in event["tracks"]] == [first]
    assert client.post(vote_path, headers=bob, json={}).status_code == 404
    response = client.put(
        path,
        headers=alice,
        json={
            "name": "Invited voting",
            "license": "invited",
            "base_version": event["version"],
        },
    )
    assert response.status_code == 200
    assert (
        client.post(path + "/tracks/" + first + "/votes", headers=bob, json={}).status_code == 403
    )


def test_geo_time_rule_enforced_by_server(client, people):
    (_, alice, _), (_, bob, _), _ = people
    rule = {
        "lat": 33.57,
        "lng": -7.59,
        "radius_m": 100,
        "starts_at": (now() - timedelta(minutes=1)).isoformat(),
        "ends_at": (now() + timedelta(minutes=1)).isoformat(),
    }
    assert (
        client.post(
            BASE + "/events",
            headers=alice,
            json={
                "name": "Missing rule",
                "license": "geo_time",
            },
        ).status_code
        == 422
    )
    e = create(client, alice, "events", license="geo_time", geo_rule=rule)
    e = add(client, alice, e, "events").json()
    path = BASE + f"/events/{e['id']}/tracks/{e['tracks'][0]['id']}/votes"
    assert client.post(path, headers=bob, json={}).status_code == 403
    assert client.post(path, headers=bob, json={"lat": 0, "lng": 0}).status_code == 403
    assert client.post(path, headers=bob, json={"lat": 33.57, "lng": -7.59}).status_code == 200
    rule["starts_at"] = (now() - timedelta(hours=2)).isoformat()
    rule["ends_at"] = (now() - timedelta(hours=1)).isoformat()
    e = client.get(BASE + "/events/" + e["id"], headers=alice).json()
    assert (
        client.put(
            BASE + "/events/" + e["id"],
            headers=alice,
            json={
                "name": "Closed",
                "license": "geo_time",
                "geo_rule": rule,
                "base_version": e["version"],
            },
        ).status_code
        == 200
    )
    assert client.post(path, headers=alice, json={"lat": 33.57, "lng": -7.59}).status_code == 403


def test_per_device_delegation_and_friend_removal(client, people):
    (_, alice, aid), (_, bob, bid), (_, charlie, _) = people
    d = client.post(BASE + "/devices", headers=alice, json={"name": "Speaker"}).json()
    path = BASE + "/devices/" + d["id"]
    assert (
        client.put(
            path + "/delegation",
            headers=alice,
            json={
                "friend_id": bid,
                "base_version": d["version"],
            },
        ).status_code
        == 403
    )
    client.post(BASE + "/friends/requests", headers=alice, json={"user_id": bid})
    client.post(BASE + f"/friends/{aid}/accept", headers=bob)
    d = client.put(
        path + "/delegation",
        headers=alice,
        json={
            "friend_id": bid,
            "base_version": d["version"],
        },
    ).json()
    assert len(client.get(BASE + "/devices", headers=bob).json()) == 1
    assert client.get(path, headers=charlie).status_code == 404
    d = client.post(
        path + "/control",
        headers=bob,
        json={
            "action": "play",
            "deezer_id": 1,
            "base_version": d["version"],
        },
    ).json()
    assert d["state"]["action"] == "play"
    assert (
        client.put(
            path + "/delegation",
            headers=bob,
            json={
                "friend_id": None,
                "base_version": d["version"],
            },
        ).status_code
        == 403
    )
    d = client.put(
        path + "/delegation",
        headers=alice,
        json={"friend_id": None, "base_version": d["version"]},
    ).json()
    assert client.get(path, headers=bob).status_code == 404
    assert client.get(BASE + "/devices", headers=bob).json() == []
    assert (
        client.post(
            path + "/control",
            headers=bob,
            json={"action": "pause", "base_version": d["version"]},
        ).status_code
        == 404
    )
    d = client.put(
        path + "/delegation",
        headers=alice,
        json={"friend_id": bid, "base_version": d["version"]},
    ).json()
    client.delete(BASE + f"/friends/{aid}", headers=bob)
    assert client.get(path, headers=bob).status_code == 404
    assert client.get(path, headers=alice).json()["friend_id"] is None
    d = client.put(
        path + "/delegation",
        headers=alice,
        json={
            "friend_id": None,
            "base_version": d["version"],
        },
    ).json()
    assert (
        client.delete(path, headers=alice, params={"base_version": d["version"]}).status_code == 200
    )


def test_websocket_invalidation_logout_and_private_access(client, people):
    (pair, alice, _), (bob_pair, bob, _), _ = people
    p = create(client, alice)
    path = BASE + "/ws/playlist/" + p["id"]
    with client.websocket_connect(path) as ws:
        ws.send_json({"access_token": pair["access_token"]})
        assert ws.receive_json()["type"] == "ready"
        assert add(client, bob, p).status_code == 200
        assert ws.receive_json()["type"] == "playlist_changed"
        assert client.post(BASE + "/auth/logout-all", headers=alice).status_code == 200
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    private = create(client, bob, visibility="private")
    with client.websocket_connect(BASE + "/ws/playlist/" + private["id"]) as ws:
        ws.send_json({"access_token": pair["access_token"]})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    with client.websocket_connect(BASE + "/ws/playlist/" + private["id"]) as ws:
        ws.send_json({"access_token": bob_pair["access_token"]})
        assert ws.receive_json()["type"] == "ready"
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "pong"


def test_event_privacy_inbox_and_invited_voting(client, people):
    (_, alice, _), (_, bob, bid), (_, charlie, _) = people
    event = create(client, alice, "events", visibility="private", license="invited")
    path = BASE + "/events/" + event["id"]
    assert client.get(path, headers=bob).status_code == 404
    assert invite(client, alice, event, bid, "events").status_code == 201
    inbox = client.get(BASE + "/invitations", headers=bob).json()
    assert len(inbox) == 1 and inbox[0]["resource_id"] == event["id"]
    assert client.get(BASE + "/invitations", headers=charlie).json() == []
    event = client.post(path + "/invitations/accept", headers=bob).json()
    assert client.get(BASE + "/invitations", headers=bob).json() == []
    assert len(client.get(BASE + "/invitations?status=accepted", headers=bob).json()) == 1
    event = add(client, bob, event, "events").json()
    assert event["tracks"]
    vote_path = path + "/tracks/" + event["tracks"][0]["id"] + "/votes"
    assert client.post(vote_path, headers=charlie, json={}).status_code == 404
    event = client.post(vote_path, headers=bob, json={}).json()
    assert event["tracks"][0]["votes"] == 1
    assert client.get(BASE + "/events?q=Party", headers=charlie).json() == []
    assert len(client.get(BASE + "/events?q=Party", headers=bob).json()) == 1


def test_websocket_private_revocation_and_database_updates(client, people):
    (pair, alice, _), (bob_pair, bob, bid), _ = people
    p = create(client, alice, visibility="private")
    invite(client, alice, p, bid)
    path = BASE + "/ws/playlist/" + p["id"]
    with client.websocket_connect(path) as ws:
        ws.send_json({"access_token": bob_pair["access_token"]})
        assert ws.receive_json()["type"] == "ready"
        p = client.get(BASE + "/playlists/" + p["id"], headers=alice).json()
        response = client.delete(
            BASE + "/playlists/" + p["id"] + "/invitations/" + bid,
            headers=alice,
            params={"base_version": p["version"]},
        )
        assert response.status_code == 200
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    with client.websocket_connect(path) as ws:
        ws.send_json({"access_token": pair["access_token"]})
        assert ws.receive_json()["type"] == "ready"
        from app.models.entities import MusicResource

        with session_factory()() as db:
            resource = db.get(MusicResource, UUID(p["id"]))
            resource.version += 1
            db.commit()
        assert ws.receive_json()["type"] == "playlist_changed"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers={"origin": "https://untrusted.example"}) as ws:
            ws.send_json({"access_token": pair["access_token"]})
    with client.websocket_connect(path) as ws:
        ws.send_json({"access_token": "invalid"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_simultaneous_distinct_users_votes_are_not_lost(client, people):
    (_, alice, _), (_, bob, _), (_, charlie, _) = people
    event = add(client, alice, create(client, alice, "events"), "events").json()
    path = BASE + f"/events/{event['id']}/tracks/{event['tracks'][0]['id']}/votes"
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(client.post, path, headers=bob, json={})
        b = pool.submit(client.post, path, headers=charlie, json={})
        assert a.result().status_code == b.result().status_code == 200
    event = client.get(BASE + "/events/" + event["id"], headers=alice).json()
    assert event["tracks"][0]["votes"] == 2
    assert event["version"] == 4


def test_music_quota_is_separate_and_provider_failure_keeps_state(client, people, monkeypatch):
    from app.core.config import get_settings
    from app.core.exceptions import fail

    (_, alice, _), _, _ = people
    p = create(client, alice)
    monkeypatch.setattr(
        "mandatory.services.deezer_service.track",
        lambda *a: fail(503, "music_provider_unavailable", "Unavailable"),
    )
    assert add(client, alice, p).status_code == 503
    current = client.get(BASE + "/playlists/" + p["id"], headers=alice).json()
    assert current["tracks"] == [] and current["version"] == 1
    monkeypatch.setenv("MUSIC_RATE_LIMIT", "1")
    get_settings.cache_clear()
    assert client.get(BASE + "/tracks/search?q=rock", headers=alice).status_code == 429
    assert client.get(BASE + "/users/me", headers=alice).status_code == 200


def test_event_and_device_websocket_messages(client, people):
    (pair, alice, _), _, _ = people
    event = create(client, alice, "events")
    with client.websocket_connect(BASE + "/ws/event/" + event["id"]) as ws:
        ws.send_json({"access_token": pair["access_token"]})
        assert ws.receive_json()["type"] == "ready"
        assert add(client, alice, event, "events").status_code == 200
        assert ws.receive_json()["type"] == "tracks_changed"
    device = client.post(BASE + "/devices", headers=alice, json={"name": "Speaker"}).json()
    path = BASE + "/devices/" + device["id"]
    with client.websocket_connect(BASE + "/ws/device/" + device["id"]) as ws:
        ws.send_json({"access_token": pair["access_token"]})
        assert ws.receive_json()["type"] == "ready"
        changed = client.post(
            path + "/control",
            headers=alice,
            json={"action": "play", "deezer_id": 1, "base_version": 1},
        )
        assert changed.status_code == 200
        assert ws.receive_json()["type"] == "device_changed"


def test_event_advance_expected_track_prevents_two_players_skipping(client, people, caplog):
    import json
    import logging

    (pair, alice, _), _, _ = people
    event = create(client, alice, "events")
    for number in (1, 2, 3):
        event = add(client, alice, event, "events", track=number).json()
    path = BASE + f"/events/{event['id']}/advance"
    first = client.post(path, headers=alice, json={"base_version": event["version"]}).json()
    original = first["current_track"]["id"]
    second = client.post(
        path,
        headers=alice,
        json={"base_version": first["version"], "expected_current_track_id": original},
    )
    assert second.status_code == 200
    second = second.json()
    # Even after refetching the new version, a second player must not advance the old song again.
    duplicate = client.post(
        path,
        headers=alice,
        json={"base_version": second["version"], "expected_current_track_id": original},
    )
    assert duplicate.status_code == 409
    with caplog.at_level(logging.INFO, logger="music_room.audit"):
        with client.websocket_connect(BASE + "/ws/event/" + event["id"]) as ws:
            ws.send_json(
                {
                    "access_token": pair["access_token"],
                    "metadata": {"platform": "ios", "device": "iPhone", "app_version": "0.1.0"},
                }
            )
            assert ws.receive_json()["type"] == "ready"
    entry = next(json.loads(r.message) for r in caplog.records if "WEBSOCKET" in r.message)
    assert (entry["platform"], entry["device"], entry["app_version"]) == ("ios", "iPhone", "0.1.0")
    assert pair["access_token"] not in caplog.text

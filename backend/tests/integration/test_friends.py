from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.models.entities import Friendship, User
from tests.conftest import account, headers

BASE = "/api/v1"


def people(client):
    result = []
    for name in ("alice", "bob", "charlie"):
        auth = headers(account(client, email=f"{name}@example.com"))
        user_id = client.get(BASE + "/users/me", headers=auth).json()["id"]
        result.append((auth, user_id))
    return result


def send(client, auth, target):
    return client.post(BASE + "/friends/requests", headers=auth, json={"user_id": target})


def accept(client, auth, target):
    return client.post(BASE + f"/friends/{target}/accept", headers=auth)


def test_friend_lifecycle_and_profile_privacy(client):
    (alice, aid), (bob, bid), (charlie, cid) = people(client)
    client.patch(
        BASE + "/users/me",
        headers=alice,
        json={
            "public": {"display_name": "Alice"},
            "friends_only": {"location": "Casablanca"},
            "private": {"notes": "private secret"},
            "music_preferences": ["jazz"],
        },
    )
    path = BASE + f"/users/{aid}/friends-only"
    assert client.get(path, headers=bob).status_code == 403
    assert send(client, alice, bid).status_code == 201
    pending = client.get(BASE + "/friends/requests", headers=bob).json()
    assert pending == [{"user_id": aid, "requester_id": aid, "status": "pending"}]
    assert client.get(BASE + "/friends/requests", headers=charlie).json() == []
    assert client.get(BASE + "/friends", headers=alice).json() == []
    assert client.get(path, headers=bob).status_code == 403
    assert accept(client, alice, bid).status_code == 403
    assert accept(client, charlie, aid).status_code == 404
    assert accept(client, bob, aid).status_code == 200
    assert len(client.get(BASE + "/friends", headers=alice).json()) == 1
    assert len(client.get(BASE + "/friends", headers=bob).json()) == 1
    assert client.get(BASE + "/friends/requests", headers=bob).json() == []
    response = client.get(path, headers=bob)
    assert response.status_code == 200
    assert set(response.json()) == {"id", "public", "friends_only"}
    assert response.json()["friends_only"] == {"location": "Casablanca"}
    assert "private secret" not in response.text and "jazz" not in response.text
    client.patch(BASE + "/users/me", headers=bob, json={"friends_only": {"location": "Rabat"}})
    reciprocal = client.get(BASE + f"/users/{bid}/friends-only", headers=alice)
    assert reciprocal.status_code == 200
    assert reciprocal.json()["friends_only"]["location"] == "Rabat"
    assert client.get(path, headers=charlie).status_code == 403
    assert client.get(path, headers=alice).status_code == 200
    public = client.get(BASE + f"/users/{aid}/public", headers=bob).json()
    assert set(public) == {"id", "public"}
    assert "friends_only" not in public
    assert client.delete(BASE + f"/friends/{aid}", headers=charlie).status_code == 404
    assert client.delete(BASE + f"/friends/{aid}", headers=bob).status_code == 200
    assert client.get(path, headers=bob).status_code == 403
    assert client.get(BASE + "/friends", headers=alice).json() == []


def test_request_validation_duplicates_decline_and_cancel(client):
    (alice, aid), (bob, bid), _ = people(client)
    assert send(client, alice, aid).status_code == 400
    assert send(client, alice, str(uuid4())).status_code == 404
    assert send(client, alice, "invalid-id").status_code == 422
    assert (
        client.post(
            BASE + "/friends/requests",
            headers=alice,
            json={
                "user_id": bid,
                "status": "accepted",
            },
        ).status_code
        == 422
    )
    assert send(client, alice, bid).status_code == 201
    assert send(client, alice, bid).status_code == 409
    assert send(client, bob, aid).status_code == 409
    assert client.delete(BASE + f"/friends/{aid}", headers=bob).status_code == 200
    assert send(client, alice, bid).status_code == 201
    assert client.delete(BASE + f"/friends/{bid}", headers=alice).status_code == 200
    assert accept(client, bob, aid).status_code == 404
    assert client.get(BASE + "/friends?limit=101", headers=alice).status_code == 422
    assert client.get(BASE + "/friends/requests?offset=-1", headers=bob).status_code == 422


def test_all_friend_routes_require_authentication(client):
    uid = str(uuid4())
    for method, path, body in (
        ("GET", "/friends", None),
        ("GET", "/friends/requests", None),
        ("POST", "/friends/requests", {"user_id": uid}),
        ("POST", f"/friends/{uid}/accept", None),
        ("DELETE", f"/friends/{uid}", None),
        ("GET", f"/users/{uid}/friends-only", None),
    ):
        assert client.request(method, BASE + path, json=body).status_code == 401


def test_disabled_friends_lose_visibility_and_can_be_removed(client, db):
    (alice, aid), (bob, bid), _ = people(client)
    assert send(client, alice, bid).status_code == 201
    assert accept(client, bob, aid).status_code == 200
    db.get(User, UUID(aid)).disabled = True
    db.commit()
    assert client.get(BASE + f"/users/{aid}/friends-only", headers=bob).status_code == 403
    assert client.get(BASE + "/friends", headers=bob).json() == []
    assert send(client, bob, aid).status_code == 404
    assert client.delete(BASE + f"/friends/{aid}", headers=bob).status_code == 200


def test_concurrent_opposite_requests_create_one_pending_relationship(client, db):
    (alice, aid), (bob, bid), _ = people(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(send, client, alice, bid)
        b = pool.submit(send, client, bob, aid)
        assert sorted([a.result().status_code, b.result().status_code]) == [201, 409]
    assert db.scalar(select(func.count()).select_from(Friendship)) == 1
    assert db.scalar(select(Friendship.status)) == "pending"

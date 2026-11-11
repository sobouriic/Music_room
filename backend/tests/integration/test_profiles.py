from tests.conftest import account, headers


def test_private_profile_and_public_projection(client):
    alice = account(client)
    alice_headers = headers(alice)
    update = {
        "public": {"display_name": "Alice", "bio": "Music fan"},
        "friends_only": {"location": "Casablanca"},
        "private": {"notes": "a secret"},
        "music_preferences": ["jazz", "rock"],
    }
    response = client.patch("/api/v1/users/me", json=update, headers=alice_headers)
    assert response.status_code == 200
    user = response.json()
    for field, value in update.items():
        assert user[field] == value
    assert not any(key in user for key in ("password_hash", "auth_version", "disabled"))
    bob = account(client, email="bob@example.com")
    public = client.get(f"/api/v1/users/{user['id']}/public", headers=headers(bob))
    assert public.json() == {"id": user["id"], "public": update["public"]}
    assert "a secret" not in public.text and "Casablanca" not in public.text
    assert (
        client.patch(f"/api/v1/users/{user['id']}", json=update, headers=headers(bob)).status_code
        == 404
    )
    assert client.get(f"/api/v1/users/{user['id']}", headers=headers(bob)).status_code == 404


def test_mass_assignment_and_patch_semantics(client):
    pair = account(client)
    auth = headers(pair)
    assert (
        client.patch(
            "/api/v1/users/me", headers=auth, json={"email": "attack@example.com"}
        ).status_code
        == 422
    )
    assert (
        client.patch("/api/v1/users/me", headers=auth, json={"verified": True}).status_code == 422
    )
    assert (
        client.patch(
            "/api/v1/users/me", headers=auth, json={"public": {"password_hash": "bad"}}
        ).status_code
        == 422
    )
    client.patch(
        "/api/v1/users/me",
        headers=auth,
        json={"public": {"display_name": "Alice", "bio": "Original"}},
    )
    result = client.patch("/api/v1/users/me", headers=auth, json={"public": {"bio": "New"}})
    assert result.json()["public"] == {"display_name": "Alice", "bio": "New"}
    assert (
        client.patch(
            "/api/v1/users/me", headers=auth, json={"music_preferences": ["x" * 101]}
        ).status_code
        == 422
    )

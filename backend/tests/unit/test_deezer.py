from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException

from mandatory.services import deezer_service as deezer


def test_live_response_shape_is_normalized_and_request_is_bounded(monkeypatch):
    response = Mock()
    response.json.return_value = {
        "data": [
            {
                "id": 42,
                "title": "Track",
                "artist": {"name": "Artist"},
                "duration": 120,
                "preview": "https://cdn.example.com/audio.mp3",
                "album": {"cover_medium": "https://cdn.example.com/cover.jpg"},
                "link": "https://www.deezer.com/track/42",
            }
        ]
    }
    get = Mock(return_value=response)
    monkeypatch.setattr(deezer.httpx, "get", get)
    result = deezer.search("rock", 10, 20)
    assert result[0]["deezer_id"] == 42
    assert result[0]["preview_url"].endswith("audio.mp3")
    get.assert_called_once_with(
        "https://api.deezer.com/search",
        params={"q": "rock", "limit": 10, "index": 20},
        timeout=8,
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    "body,status",
    [
        ({"error": {"code": 800, "message": "sensitive provider body"}}, 404),
        ({"error": {"code": 4, "message": "sensitive provider body"}}, 503),
        ([], 503),
        ({"data": "invalid"}, 503),
        ({"data": [None]}, 503),
    ],
)
def test_bad_provider_responses_are_sanitized(monkeypatch, body, status):
    response = Mock()
    response.json.return_value = body
    monkeypatch.setattr(deezer.httpx, "get", Mock(return_value=response))
    with pytest.raises(HTTPException) as caught:
        deezer.search("rock", 10, 0)
    assert caught.value.status_code == status
    assert "sensitive" not in str(caught.value.detail)


def test_network_timeout_and_track_identity_mismatch(monkeypatch):
    monkeypatch.setattr(deezer.httpx, "get", Mock(side_effect=httpx.ConnectTimeout("private URL")))
    with pytest.raises(HTTPException) as caught:
        deezer.track(1)
    assert caught.value.status_code == 503
    assert "private" not in str(caught.value.detail)
    monkeypatch.setattr(
        deezer,
        "fetch",
        lambda *a: {
            "id": 2,
            "title": "Wrong",
            "artist": {"name": "Artist"},
            "duration": 1,
        },
    )
    with pytest.raises(HTTPException) as caught:
        deezer.track(1)
    assert caught.value.status_code == 503

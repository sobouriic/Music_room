"""Catalog metadata and previews only. No full-track playback or account OAuth."""

import httpx

from app.core.exceptions import fail
from app.schemas.music import CatalogTrack

BASE = "https://api.deezer.com"


def fetch(path, params=None):
    try:
        response = httpx.get(BASE + path, params=params, timeout=8, follow_redirects=False)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
        if "error" in data:
            code = data["error"].get("code") if isinstance(data["error"], dict) else None
            if code == 800:
                fail(404, "track_not_found", "Deezer track not found")
            fail(503, "music_provider_unavailable", "Deezer could not serve this request")
        return data
    except (httpx.HTTPError, ValueError, TypeError):
        fail(503, "music_provider_unavailable", "Deezer is unavailable; try again later")


def normalize(data):
    try:
        return CatalogTrack(
            deezer_id=int(data["id"]),
            title=data["title"],
            artist=data["artist"]["name"],
            duration=data["duration"],
            preview_url=data.get("preview") or None,
            artwork_url=data.get("album", {}).get("cover_medium") or None,
            deezer_url=data.get("link") or None,
        ).model_dump(mode="json")
    except (KeyError, ValueError, TypeError):
        fail(503, "music_provider_unavailable", "Deezer returned an invalid track")


def search(query, limit, offset):
    data = fetch("/search", {"q": query, "limit": limit, "index": offset})
    if not isinstance(data.get("data"), list):
        fail(503, "music_provider_unavailable", "Deezer returned invalid search results")
    return [normalize(item) for item in data["data"][:limit]]


def track(deezer_id):
    result = normalize(fetch(f"/track/{deezer_id}"))
    if result["deezer_id"] != deezer_id:
        fail(503, "music_provider_unavailable", "Deezer returned an unexpected track")
    return result

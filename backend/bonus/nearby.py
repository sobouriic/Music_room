import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.dependencies import current_user, music_sensitive
from app.core.security import now
from app.db.session import get_db
from app.models.entities import MusicResource, User
from app.schemas.music import GeoRule, ResourceView
from mandatory.services.music_service import view

router = APIRouter(tags=["nearby events"], dependencies=[Depends(music_sensitive)])


def distance(lat, lng, venue_lat, venue_lng):
    a, b = math.radians(lat), math.radians(venue_lat)
    dlat, dlng = b - a, math.radians(venue_lng - lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


@router.get("/events/nearby", response_model=list[ResourceView])
def nearby_events(
    lat: float = Query(ge=-90, le=90, allow_inf_nan=False),
    lng: float = Query(ge=-180, le=180, allow_inf_nan=False),
    radius_m: float = Query(1000, ge=50, le=100000, allow_inf_nan=False),
    user=Depends(current_user),
    db=Depends(get_db, scope="function"),
):
    # Public venues only. Private events are never disclosed by a nearby query,
    # even to invitees. GPS coordinates are not saved by this operation.
    delta = radius_m / 110000  # conservative latitude bounding band before exact distance
    query = (
        select(MusicResource)
        .join(User, User.id == MusicResource.owner_id)
        .where(
            MusicResource.kind == "event",
            MusicResource.visibility == "public",
            MusicResource.license == "geo_time",
            User.disabled.is_(False),
            MusicResource.geo_rule["lat"].as_float().between(lat - delta, lat + delta),
        )
        .order_by(MusicResource.id)
        .limit(500)
    )
    results = []
    current = now()
    for event in db.scalars(query):
        rule = GeoRule.model_validate(event.geo_rule)
        meters = distance(lat, lng, rule.lat, rule.lng)
        if rule.starts_at <= current < rule.ends_at and meters <= radius_m:
            results.append((meters, event))
    return [view(db, event, user) for _, event in sorted(results, key=lambda value: value[0])[:30]]

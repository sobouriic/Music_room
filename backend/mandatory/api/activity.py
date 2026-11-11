"""Bounded, authenticated telemetry for actions that do not mutate server data."""

import json
import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.dependencies import current_user, music_sensitive
from app.core.logging import clean

router = APIRouter(tags=["activity"])


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    action: Literal[
        "screen_view",
        "playback_start",
        "playback_pause",
        "playback_stop",
        "queue_next",
        "offline_saved",
        "offline_edit",
        "offline_sync",
        "nearby_alerts_enabled",
        "nearby_alerts_disabled",
    ]
    occurred_at: AwareDatetime


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[Activity] = Field(min_length=1, max_length=50)


@router.post("/activity", status_code=204, dependencies=[Depends(music_sensitive)])
def activity(data: Batch, request: Request, user=Depends(current_user)):
    for event in data.events:
        logging.getLogger("music_room.audit").info(
            json.dumps(
                {
                    "method": "CLIENT_ACTION",
                    "user_id": str(user.id),
                    "event_id": str(event.event_id),
                    "action": event.action,
                    "occurred_at": event.occurred_at.isoformat(),
                    "received_at": datetime.now().astimezone().isoformat(),
                    "platform": clean(request.headers.get("x-app-platform", "unknown")),
                    "device": clean(request.headers.get("x-app-device", "unknown")),
                    "app_version": clean(request.headers.get("x-app-version", "unknown")),
                }
            )
        )

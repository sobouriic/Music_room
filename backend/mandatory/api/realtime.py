"""Version invalidations from PostgreSQL: works across API workers without in-memory pubsub."""

import asyncio
import json
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import authenticate
from app.core.config import get_settings
from app.core.logging import clean
from app.db.session import session_factory
from mandatory.services import device_service, music_service
from mandatory.services.rate_limit import hit

router = APIRouter()


def state(token, channel, resource_id):
    with session_factory()() as db:
        user, _ = authenticate(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db)
        if channel == "device":
            resource = device_service.load(db, resource_id, user)
            # Delegation changes may follow friendship changes without a device version bump.
            effective = device_service.view(db, resource)["friend_id"]
            return resource.version, str(effective)
        resource = music_service.load(db, channel, resource_id, user)
        return resource.version, None


@router.websocket("/ws/{channel}/{resource_id}")
async def updates(
    websocket: WebSocket, channel: Literal["playlist", "event", "device"], resource_id: UUID
):
    cfg = get_settings()
    origin = websocket.headers.get("origin")
    if origin and origin not in cfg.browser_origins:
        logging.getLogger(__name__).warning(
            "WebSocket origin rejected: %s; configure CORS_ORIGINS for this frontend",
            clean(origin),
        )
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        await run_in_threadpool(hit, "ws", websocket.client.host if websocket.client else "unknown")
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        if len(raw) > 4096:
            await websocket.close(code=1008)
            return
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
            await websocket.close(code=1008)
            return
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict) or any(not isinstance(v, str) for v in metadata.values()):
            await websocket.close(code=1008)
            return
        token = payload["access_token"]
        previous = await run_in_threadpool(state, token, channel, resource_id)
        logging.getLogger("music_room.audit").info(
            json.dumps(
                {
                    "method": "WEBSOCKET",
                    "route": "/api/v1/ws/{channel}/{resource_id}",
                    "status": 101,
                    "platform": clean(
                        metadata.get("platform", websocket.headers.get("x-app-platform", "unknown"))
                    ),
                    "device": clean(
                        metadata.get("device", websocket.headers.get("x-app-device", "unknown"))
                    ),
                    "app_version": clean(
                        metadata.get(
                            "app_version", websocket.headers.get("x-app-version", "unknown")
                        )
                    ),
                }
            )
        )
        await websocket.send_json({"type": "ready", "version": previous[0]})
        ticks = 0
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                if message != "ping":
                    await websocket.close(code=1008)
                    return
                await websocket.send_json({"type": "pong"})
            except TimeoutError:
                pass
            current = await run_in_threadpool(state, token, channel, resource_id)
            if current != previous:
                event = {
                    "playlist": "playlist_changed",
                    "event": "tracks_changed",
                    "device": "device_changed",
                }[channel]
                await websocket.send_json(
                    {"type": event, "version": current[0], "id": str(resource_id)}
                )
                previous = current
            ticks += 1
            if ticks % 20 == 0:
                await websocket.send_json({"type": "heartbeat"})
    except (HTTPException, ValueError, TypeError, TimeoutError):
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass

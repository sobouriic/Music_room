import json
import logging
import re

logger = logging.getLogger("music_room.audit")


def clean(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9 ._()/-]", "?", value[:100])


def audit(request, status: int):
    # Do not log URL query strings, bodies, authorization, email addresses, or tokens.
    route = request.scope.get("route")
    logger.info(
        json.dumps(
            {
                "method": request.method,
                "route": getattr(route, "path", "unmatched"),
                "status": status,
                "platform": clean(request.headers.get("X-App-Platform", "unknown")),
                "device": clean(request.headers.get("X-App-Device", "unknown")),
                "app_version": clean(request.headers.get("X-App-Version", "unknown")),
            }
        )
    )

import time

from fastapi import HTTPException
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.security import digest
from app.db.session import session_factory
from app.models.entities import RateBucket


def hit(scope: str, key: str, limit: int | None = None):
    cfg = get_settings()
    window = int(time.time()) // cfg.rate_window_seconds
    statement = insert(RateBucket).values(key=digest(scope + ":" + key), window=window, count=1)
    statement = statement.on_conflict_do_update(
        index_elements=[RateBucket.key],
        set_={
            "window": window,
            "count": case((RateBucket.window == window, RateBucket.count + 1), else_=1),
        },
    ).returning(RateBucket.count)
    # Separate transaction: failed login attempts must also count across all workers.
    with session_factory()() as db:
        count = db.scalar(statement)
        db.commit()
    if count > (cfg.rate_limit if limit is None else limit):
        raise HTTPException(
            429,
            {"code": "rate_limited", "message": "Too many requests; try again later"},
            headers={
                "Retry-After": str(
                    cfg.rate_window_seconds - int(time.time()) % cfg.rate_window_seconds
                )
            },
        )

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.logging import audit
from app.db.session import session_factory
from app.schemas.errors import ErrorResponse, HealthResponse


def create_app():
    cfg = get_settings()
    application = FastAPI(
        title="Music Room API",
        version="1.0.0",
        description="Authentication, profiles, friendships, music services, subscriptions, "
        "offline playlist sync and nearby-event discovery. "
        "See docs/API_CONTRACT.md for request examples and client flows.",
        responses={
            status: {"model": ErrorResponse, "description": description}
            for status, description in {
                400: "Invalid or expired token / OAuth state",
                401: "Invalid credentials, token or revoked session",
                403: "Operation forbidden",
                404: "Resource not found",
                409: "Account or identity conflict",
                422: "Invalid input (raw input is never echoed)",
                429: "Too many requests",
                503: "Required service unavailable",
            }.items()
        },
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.browser_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-App-Platform",
            "X-App-Device",
            "X-App-Version",
        ],
    )

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "http_error", "message": str(exc.detail)}
        )
        return JSONResponse({"error": detail}, status_code=exc.status_code, headers=exc.headers)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic errors normally include raw input, which may contain passwords/tokens.
        fields = [{"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in exc.errors()]
        return JSONResponse(
            {"error": {"code": "validation_error", "message": "Invalid request", "fields": fields}},
            422,
        )

    @application.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "conflict",
                    "message": "Operation conflicts with an existing account or identity",
                }
            },
            409,
        )

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "database_unavailable",
                    "message": "Service temporarily unavailable",
                }
            },
            503,
        )

    @application.middleware("http")
    async def log_request(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            # Suppress raw exception traces: validation/driver exceptions may include secrets.
            response = JSONResponse(
                {"error": {"code": "internal_error", "message": "Unexpected server error"}}, 500
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        audit(request, response.status_code)
        return response

    @application.get("/api/v1/health", tags=["operations"], response_model=HealthResponse)
    def health():
        try:
            with session_factory()() as db:
                db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise HTTPException(503, {"code": "database_unavailable", "message": "Not ready"})
        return {"status": "ok"}

    from app.api.v1.router import router

    application.include_router(router)
    return application


logging.basicConfig(level=logging.INFO, format="%(message)s")
app = create_app()

"""FastAPI application factory."""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import admin, chat, ingest, search
from app.core.config import get_settings
from app.core.exceptions import KnowledgeForgeError
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Enterprise knowledge platform: ingestion, hybrid retrieval, "
        "RAG chat with document-level RBAC.",
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "ctx": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            },
        )
        return response

    @app.exception_handler(KnowledgeForgeError)
    async def domain_error_handler(request: Request, exc: KnowledgeForgeError):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}
        )

    for router in (ingest.router, search.router, chat.router, admin.router):
        app.include_router(router, prefix="/api")

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"status": "ok", "mode": settings.mode, "version": __version__}

    logger.info("app configured", extra={"ctx": {"mode": settings.mode}})
    return app


app = create_app()

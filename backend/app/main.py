from __future__ import annotations

from fastapi import FastAPI

from app.api import (
    admin_ai,
    admin_content,
    admin_questions,
    admin_releases,
    admin_users,
    admin_waves,
    attempts,
    auth,
    certificates,
    integration,
    learner,
    reference,
    reports,
    system,
)
from app.auth.csrf import CsrfHeaderMiddleware
from app.config import settings
from app.errors import register_error_handlers
from app.security import PrivateResponseMiddleware

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Yagona oyna Akademiyasi",
        version="0.1.0",
        # Swagger UI pulls its assets from a CDN, so it only exists in dev; production
        # must not reference external resources.
        docs_url="/api/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.add_middleware(CsrfHeaderMiddleware)
    app.add_middleware(PrivateResponseMiddleware)
    register_error_handlers(app)
    routers = (
        system.router,
        auth.router,
        learner.router,
        attempts.router,
        certificates.router,
        integration.router,
        reports.router,
        admin_users.router,
        reference.router,
        admin_content.router,
        admin_releases.router,
        admin_questions.router,
        admin_waves.router,
        admin_ai.router,
    )
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()

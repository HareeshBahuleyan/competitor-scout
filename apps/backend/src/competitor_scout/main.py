from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from competitor_scout.api.auth import router as auth_router
from competitor_scout.api.briefs import router as briefs_router
from competitor_scout.api.competitors import router as competitors_router
from competitor_scout.api.deps import current_user
from competitor_scout.api.errors import register_exception_handlers
from competitor_scout.api.findings import router as findings_router
from competitor_scout.api.health import ReadinessProbe
from competitor_scout.api.health import router as health_router
from competitor_scout.api.runs import router as runs_router
from competitor_scout.api.settings import router as settings_router
from competitor_scout.api.test_auth import router as test_auth_router
from competitor_scout.config import Settings, get_settings
from competitor_scout.db import (
    SessionFactory,
    check_database_readiness,
    create_engine,
    create_session_factory,
)
from competitor_scout.logging import configure_logging
from competitor_scout.models.auth import User
from competitor_scout.security.urls import validate_public_https_url
from competitor_scout.services.auth import AuthlibGoogleOAuthProvider, GoogleOAuthProvider


def create_app(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    readiness_probe: ReadinessProbe | None = None,
    oauth_provider: GoogleOAuthProvider | None = None,
    testing: bool = False,
    current_user_override: Callable[..., User] | None = None,
    source_url_validator: Callable[[str], Awaitable[str]] | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging()

    if current_user_override is not None and not testing:
        raise ValueError("current-user overrides require testing=True")

    engine: AsyncEngine | None = None
    if session_factory is None and readiness_probe is None:
        engine = create_engine(resolved_settings)
        session_factory = create_session_factory(engine)

    if readiness_probe is None:
        if session_factory is None:
            raise RuntimeError("readiness requires a database session factory")

        async def database_readiness_probe() -> None:
            await check_database_readiness(session_factory)

        readiness_probe = database_readiness_probe

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(
        title="Competitor Scout API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.state.readiness_probe = readiness_probe
    app.state.oauth_provider = oauth_provider or AuthlibGoogleOAuthProvider(resolved_settings)
    app.state.source_url_validator = source_url_validator or validate_public_https_url
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(competitors_router)
    app.include_router(findings_router)
    app.include_router(briefs_router)
    app.include_router(runs_router)
    app.include_router(settings_router)
    if (
        resolved_settings.environment == "test"
        and resolved_settings.e2e_auth_secret is not None
    ):
        app.include_router(test_auth_router)
    if current_user_override is not None:
        app.dependency_overrides[current_user] = current_user_override
    return app


app = create_app()


def run() -> None:
    uvicorn.run("competitor_scout.main:app", host="0.0.0.0", port=8000)

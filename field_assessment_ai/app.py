from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import AppSettings, load_settings
from .database import bootstrap_database
from .routes import router
from .services.analysis import MockVisionAnalysisService
import sell_before_check_ai.models  # noqa: F401


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine, session_factory = bootstrap_database(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="不用品回収・遺品整理・片付け向けの現場査定バックエンド",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.analysis_service = MockVisionAnalysisService()

    allow_origins = list(settings.cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_origins == ["*"] else allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")
    app.include_router(router, prefix=settings.api_prefix)
    return app

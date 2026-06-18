from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import field_assessment_ai.models  # noqa: F401

from field_assessment_ai.database import bootstrap_database

from .config import AppSettings, load_settings
from . import models as _consumer_models  # noqa: F401
from .routes import router
from .mobile_preview import render_mobile_preview_html
from .mobile_preview import render_mobile_preview_frame_html
from .pages import (
    render_consumer_flyer_html,
    render_consumer_home_html,
    render_consumer_item_html,
    render_consumer_quote_html,
    render_consumer_result_html,
)
from .ui import render_dashboard_html
from .services.official_info_service import ensure_official_info_seeded
from .services.refusal_phrase_service import ensure_refusal_phrases_seeded


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
        description="一般ユーザー向けの売る前チェックAPI",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    with session_factory() as session:
        ensure_official_info_seeded(session)
        ensure_refusal_phrases_seeded(session)

    allow_origins = list(settings.cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_origins == ["*"] else allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/home", response_class=HTMLResponse, include_in_schema=False)
    def home() -> HTMLResponse:
        return HTMLResponse(render_consumer_home_html(settings))

    @app.get("/flyer-check", response_class=HTMLResponse, include_in_schema=False)
    def flyer_check() -> HTMLResponse:
        return HTMLResponse(render_consumer_flyer_html(settings))

    @app.get("/item-check", response_class=HTMLResponse, include_in_schema=False)
    def item_check() -> HTMLResponse:
        return HTMLResponse(render_consumer_item_html(settings))

    @app.get("/quote-check", response_class=HTMLResponse, include_in_schema=False)
    def quote_check() -> HTMLResponse:
        return HTMLResponse(render_consumer_quote_html(settings))

    @app.get("/result", response_class=HTMLResponse, include_in_schema=False)
    def result(check_type: str | None = None, check_id: int | None = None) -> HTMLResponse:
        return HTMLResponse(render_consumer_result_html(settings, check_type=check_type, check_id=check_id))

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    def dashboard() -> HTMLResponse:
        return HTMLResponse(render_dashboard_html(settings))

    @app.get("/mobile-preview", response_class=HTMLResponse, include_in_schema=False)
    def mobile_preview(
        selected: str | None = None,
        target: str | None = None,
        scenario: str | None = None,
        view: str | None = None,
    ) -> HTMLResponse:
        view_targets = {
            "live": ("/", "Home"),
            "home": ("/", "Home"),
            "flyer": ("/flyer-check", "チラシチェック"),
            "item": ("/item-check", "商品チェック"),
            "quote": ("/quote-check", "見積もりチェック"),
            "result": ("/result", "診断結果"),
        }
        if view in view_targets:
            target_url, scenario_label = view_targets[view]
            return HTMLResponse(
                render_mobile_preview_frame_html(
                    target_url,
                    device_label="iPhone縦",
                    scenario_label=scenario_label,
                )
            )

        allowed_types = {"flyer", "item", "quote"}
        allowed_scenarios = {
            "kimono": "flyer",
            "mishin": "item",
            "kikinzoku": "item",
            "recovery_quote": "quote",
        }
        initial_scenario = scenario if scenario in allowed_scenarios else None
        initial_type = (
            allowed_scenarios[initial_scenario]
            if initial_scenario
            else selected if selected in allowed_types else target if target in allowed_types else None
        )
        return HTMLResponse(
            render_mobile_preview_html(
                settings,
                selected_type=initial_type,
                scenario_key=initial_scenario,
            )
        )

    app.include_router(router, prefix=settings.api_prefix)
    return app

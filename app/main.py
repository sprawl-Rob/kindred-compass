"""Application factory.

Run:  .venv/bin/python -m app   (see README)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, demo, seeding
from .ai.credentials import KeyringStore
from .ai.providers import AIError
from .ai.service import AIService, DuplicateRun
from .db import connect, migrate
from .directory import NotFound, ValidationError
from .evidence import DuplicateSource
from .integrations import IntegrationError
from .research.ai_agent import AIResearch
from .research.engine import ResearchService

STATIC = config.PROJECT_ROOT / "static"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}


def create_app(data_dir: str | Path | None = None, creds=None, ai_factories: dict | None = None, load_demo: bool = True,
               archive_http=None) -> FastAPI:
    settings = config.load_settings(data_dir)
    conn = connect(settings.db_path)
    try:
        migrate(conn, settings.db_path)
        status = seeding.seed_status(conn)
        seed = seeding.load_seed()
        if not status or status["version"] < int(seed["version"]):
            seeding.apply_directory_seed(conn, seed)
        if load_demo:
            demo.ensure_demo(conn)
        creds = creds or KeyringStore()
        ai = AIService(settings, creds, ai_factories)
        ai.mark_orphans(conn)
        research = ResearchService(settings, creds, archive_http)
        research.mark_orphans(conn)
        from .research.engine import rescore_pending
        rescore_pending(conn)
    finally:
        conn.close()

    app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, docs_url="/api/docs", redoc_url=None)
    app.state.settings = settings
    app.state.ai = ai
    app.state.creds = creds
    app.state.research = research
    app.state.ai_research = AIResearch(settings, creds, ai, research)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0] if not (request.headers.get("host") or "").startswith("[") \
            else (request.headers.get("host") or "").split("]")[0] + "]"
        if host not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "This app only accepts requests addressed to localhost."}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/"):
            # Custom header blocks cross-site form posts from other web pages (CSRF).
            if request.headers.get("x-kindred") != "1":
                return JSONResponse({"detail": "Missing X-Kindred header"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"   # always revalidate (ETag) so app updates load
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.exception_handler(NotFound)
    async def _nf(request, exc):
        return JSONResponse({"detail": f"Not found: {exc}"}, status_code=404)

    @app.exception_handler(ValidationError)
    async def _ve(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(DuplicateSource)
    async def _dup(request, exc):
        return JSONResponse({"detail": "A source with the same URL or the same title, repository and page already exists.",
                             "code": "possible_duplicate", "matches": exc.matches}, status_code=409)

    @app.exception_handler(DuplicateRun)
    async def _duprun(request, exc):
        return JSONResponse({"detail": "This exact AI request is already running.", "code": "duplicate_run", "run_id": exc.run_id}, status_code=409)

    @app.exception_handler(AIError)
    async def _ai(request, exc):
        return JSONResponse({"detail": exc.message, "code": exc.code, "retryable": exc.retryable},
                            status_code=400 if exc.code in ("no_key", "unknown_provider") else 502)

    @app.exception_handler(IntegrationError)
    async def _ie(request, exc):
        return JSONResponse({"detail": exc.message, "retryable": exc.retryable}, status_code=502)

    from .routes import router
    from .routes_ai import router as ai_router
    from .routes_import import router as import_router
    from .routes_research import router as research_router
    from .routes_family import router as family_router
    app.include_router(router, prefix="/api")
    app.include_router(ai_router, prefix="/api/ai")
    app.include_router(import_router, prefix="/api/imports")
    app.include_router(research_router, prefix="/api")
    app.include_router(family_router, prefix="/api")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    return app

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

_OPEN_PREFIXES = ("/auth/", "/app", "/docs", "/openapi.json", "/redoc", "/health")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from config.settings import get_settings
    from db.session import init_db
    from observability.events import configure_logging
    from sources import scheduler

    configure_logging(get_settings().log_level)
    init_db()
    scheduler.start()   # nightly sync + scheduled summaries (AGENT_SCHEDULER=0 disables)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="UP Police Data Analyst", version="0.1.0", lifespan=_lifespan)

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        from auth import core
        from api.auth import users_exist_cached

        request.state.user = core.user_for_token(request.cookies.get("session"))
        path = request.url.path
        open_path = path == "/" or any(path == p or path.startswith(p) for p in _OPEN_PREFIXES)
        if users_exist_cached() and not open_path and request.state.user is None:
            return JSONResponse(
                status_code=401,
                content={"detail": {"code": "AUTH_REQUIRED", "message": "Login required."}},
            )
        return await call_next(request)

    from api import admin, auth, conversations, datasets, health, questions, runs, schedules, sources
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(datasets.router)
    app.include_router(questions.router)
    app.include_router(conversations.router)
    app.include_router(runs.router)
    app.include_router(sources.router)
    app.include_router(schedules.router)
    app.include_router(admin.router)

    # Serve the built Next.js static export at /app
    # Run `cd frontend && pnpm build` to generate frontend/out/ before starting.
    # Server starts fine without it (API-only mode when out/ doesn't exist).
    # __file__ = src/api/__init__.py → 3 parents up = repo root
    frontend_out = Path(__file__).resolve().parent.parent.parent / "frontend" / "out"
    if frontend_out.exists():
        app.mount("/app", StaticFiles(directory=str(frontend_out), html=True), name="frontend")

    return app


app = create_app()

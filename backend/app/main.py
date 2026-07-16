import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.db_migrate import run_migrations
from app.local_auth import LocalAuthMiddleware
from app.routers import clients, metrics, insights, tasks, summaries, actions, onboarding, google_auth, cloudflare_auth, auth, settings, rankings, levers, recommendations, pulse, experiments, portal
from app.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_docs = None if os.getenv("KINEAXIS_DISABLE_DOCS", "").strip().lower() in ("1", "true", "yes") else "/docs"
_redoc = None if _docs is None else "/redoc"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Release pooled SQLite connections before Alembic — sharing the same
    # engine without dispose can deadlock on Windows (startup hangs forever).
    engine.dispose()
    run_migrations()
    try:
        from app.database import SessionLocal
        from app.insight_service import backfill_insight_kinds
        from app.routers.settings import sync_ai_settings_from_db

        db = SessionLocal()
        try:
            sync_ai_settings_from_db(db)
            n = backfill_insight_kinds(db)
            if n:
                logger.info("Backfilled kind on %s insights", n)
        finally:
            db.close()
    except Exception as e:
        logger.exception("Could not sync AI settings from DB on startup: %s", e)
    start_scheduler()
    yield
    try:
        from app.scheduler import scheduler as bg_scheduler
        bg_scheduler.shutdown(wait=False)
    except Exception:
        pass


app = FastAPI(
    title="Kinexis API",
    description="Backend for the Kinexis Digital Dashboard",
    version="0.0.1-beta",
    docs_url=_docs,
    redoc_url=_redoc,
    openapi_url="/openapi.json" if _docs else None,
    lifespan=lifespan,
)

app.add_middleware(LocalAuthMiddleware)

_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_pub = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
if _pub.startswith(("http://", "https://")) and _pub not in _cors_origins:
    _cors_origins.append(_pub)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients.router)
app.include_router(metrics.router)
app.include_router(insights.router)
app.include_router(tasks.router)
app.include_router(summaries.router)
app.include_router(actions.router)
app.include_router(onboarding.router)
app.include_router(google_auth.router)
app.include_router(cloudflare_auth.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(rankings.router)
app.include_router(levers.router)
app.include_router(recommendations.router)
app.include_router(pulse.router)
app.include_router(experiments.router)
app.include_router(portal.router)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        payload: dict = {"status": "ok"}
        try:
            from app.models import JobRun

            last = (
                db.query(JobRun)
                .filter(JobRun.finished_at.isnot(None))
                .order_by(JobRun.finished_at.desc())
                .first()
            )
            if last:
                payload["scheduler"] = {
                    "last_finished_at": last.finished_at.isoformat() if last.finished_at else None,
                    "job_type": last.job_type,
                    "ok": last.ok,
                }
            else:
                payload["scheduler"] = {"last_finished_at": None, "job_type": None, "ok": None}
        except Exception as e:
            logger.warning("Health scheduler heartbeat unavailable: %s", e)
            payload["scheduler"] = {"last_finished_at": None, "job_type": None, "ok": None}
        return payload
    except Exception:
        return JSONResponse(status_code=503, content={"status": "db_unavailable"})


def _resolve_frontend_dir() -> str:
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            os.path.normpath(os.path.join(exe_dir, "..", "frontend")),
            os.path.normpath(os.path.join(exe_dir, "..", "..", "frontend")),
            os.path.normpath(os.path.join(exe_dir, "..", "..", "..", "frontend", "out")),
            os.path.normpath(os.path.join(exe_dir, "..", "frontend", "out")),
        ]
        for path in candidates:
            if os.path.isfile(os.path.join(path, "index.html")):
                return path
        logger.warning("Frontend directory not found in any candidate path")
        return ""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "out")


FRONTEND_DIR = _resolve_frontend_dir()

logger.info(f"FRONTEND_DIR={FRONTEND_DIR} exists={os.path.isdir(FRONTEND_DIR)}")

_API_ROOTS = frozenset({
    "clients",
    "metrics",
    "insights",
    "tasks",
    "summaries",
    "actions",
    "onboarding",
    "auth",
    "settings",
    "rankings",
    "levers",
    "health",
    "pulse",
    "recommendations",
    "experiments",
    "portal",
    "docs",
    "redoc",
    "openapi.json",
})


def _safe_frontend_path(filename: str) -> Optional[str]:
    """Resolve filename under FRONTEND_DIR or return None if traversal / missing."""
    if not filename or ".." in filename.replace("\\", "/").split("/"):
        # Still allow nested dirs; block explicit .. segments
        parts = filename.replace("\\", "/").split("/")
        if any(p == ".." for p in parts):
            return None
    root = os.path.realpath(FRONTEND_DIR)
    candidate = os.path.realpath(os.path.join(FRONTEND_DIR, filename))
    if candidate != root and not candidate.startswith(root + os.sep):
        return None
    return candidate


if os.path.isdir(FRONTEND_DIR):
    _next_dir = os.path.join(FRONTEND_DIR, "_next")
    static_dir = os.path.join(FRONTEND_DIR, "static")
    if os.path.isdir(_next_dir):
        app.mount("/_next", StaticFiles(directory=_next_dir), name="_next")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    index_path = os.path.join(FRONTEND_DIR, "index.html")

    _NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    def _html_response(path: str):
        return FileResponse(path, headers=_NO_CACHE_HEADERS)

    @app.get("/")
    async def serve_root():
        return _html_response(index_path)

    @app.get("/{filename:path}")
    async def serve_frontend(request: Request, filename: str):
        root = (filename or "").split("/", 1)[0]
        if root in _API_ROOTS:
            raise HTTPException(status_code=404, detail="Not found")

        if filename:
            file_path = _safe_frontend_path(filename)
            if file_path and os.path.isfile(file_path):
                return FileResponse(file_path)

            html_path = _safe_frontend_path(f"{filename}.html")
            if html_path and os.path.isfile(html_path):
                return _html_response(html_path)

        return _html_response(index_path)
else:
    logger.warning("Frontend directory not found, running API-only mode")


if __name__ == "__main__":
    import uvicorn

    def _ensure_stdio():
        """PyInstaller windowed builds have no console; uvicorn logging needs streams."""
        for name, fd in (("stdout", 1), ("stderr", 2)):
            if getattr(sys, name) is not None:
                continue
            try:
                stream = os.fdopen(fd, "w", encoding="utf-8", closefd=False)
            except OSError:
                stream = open(os.devnull, "w", encoding="utf-8")
            setattr(sys, name, stream)

    if getattr(sys, "frozen", False):
        _ensure_stdio()

    from app.config import BACKEND_HOST, BACKEND_PORT
    host = BACKEND_HOST
    port = BACKEND_PORT
    uvicorn.run(app, host=host, port=port, log_level="info", log_config=None)

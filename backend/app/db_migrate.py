"""Run Alembic migrations at process start (dev + Electron/PyInstaller)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)


def _backend_root() -> Path:
    """Resolve backend/ (or frozen bundle root that contains alembic/)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass)
            if (candidate / "alembic").is_dir():
                return candidate
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "alembic").is_dir():
            return exe_dir
        if (exe_dir / "_internal" / "alembic").is_dir():
            return exe_dir / "_internal"
    return Path(__file__).resolve().parent.parent


def run_migrations() -> None:
    root = _backend_root()
    script_location = root / "alembic"
    if not script_location.is_dir():
        logger.warning("Alembic script_location missing at %s — skipping", script_location)
        return

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    ini = root / "alembic.ini"
    cfg = Config(str(ini)) if ini.is_file() else Config()
    cfg.set_main_option("script_location", str(script_location))
    logger.info("Running Alembic upgrade head (script_location=%s)", script_location)
    try:
        command.upgrade(cfg, "head")
    except Exception as e:
        logger.error("Alembic migration failed: %s — refusing to start in degraded mode", e)
        raise RuntimeError(
            f"Database migration failed — fix schema before starting Kinexis: {e}"
        ) from e

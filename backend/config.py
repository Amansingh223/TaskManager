from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = os.environ.get("DB_PATH", "/tmp/project_tracker.db")
DATABASE_URL = os.environ.get("DATABASE_URL")
SECRET_PATH = Path(os.environ.get("SECRET_PATH", "/tmp/.app_secret"))

PBKDF2_ITERATIONS = 120_000
TOKEN_TTL_HOURS = 24
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

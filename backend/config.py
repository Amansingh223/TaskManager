from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "project_tracker.db"
SECRET_PATH = BASE_DIR / ".app_secret"

PBKDF2_ITERATIONS = 120_000
TOKEN_TTL_HOURS = 24
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

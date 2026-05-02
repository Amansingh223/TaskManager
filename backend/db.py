from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .config import DATABASE_URL, DB_PATH

try:
    import psycopg
    from psycopg.rows import dict_row as pg_dict_row
except ImportError:  # Local SQLite mode does not need psycopg installed.
    psycopg = None
    pg_dict_row = None


USING_POSTGRES = bool(DATABASE_URL)


class Database:
    def __init__(self):
        if USING_POSTGRES:
            if psycopg is None:
                raise RuntimeError("psycopg is required when DATABASE_URL is set")
            self.conn = psycopg.connect(DATABASE_URL, row_factory=pg_dict_row)
        else:
            if DB_PATH != ":memory:":
                Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        return self.conn.execute(self.prepare_sql(sql), params)

    def executescript(self, sql: str) -> None:
        if not USING_POSTGRES:
            self.conn.executescript(sql)
            return

        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                self.conn.execute(statement)

    def prepare_sql(self, sql: str) -> str:
        if not USING_POSTGRES:
            return sql

        sql = sql.replace("?", "%s")
        sql = sql.replace("date('now')", "CURRENT_DATE::text")
        sql = sql.replace(
            "INSERT OR IGNORE INTO project_members (project_id, user_id, created_at) VALUES (%s, %s, %s)",
            """
            INSERT INTO project_members (project_id, user_id, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (project_id, user_id) DO NOTHING
            """,
        )
        return sql


def connect() -> Database:
    return Database()


def dict_row(row) -> dict | None:
    return dict(row) if row else None


def is_integrity_error(error: Exception) -> bool:
    if isinstance(error, sqlite3.IntegrityError):
        return True
    return psycopg is not None and isinstance(error, psycopg.IntegrityError)


def init_db() -> None:
    if USING_POSTGRES:
        schema = """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Member',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                due_date TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_members (
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY(project_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'Todo',
                due_date TEXT,
                created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """
    else:
        schema = """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Member',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                owner_id INTEGER NOT NULL,
                due_date TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_members (
                project_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(project_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                assignee_id INTEGER,
                status TEXT NOT NULL DEFAULT 'Todo',
                due_date TEXT,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """

    with connect() as db:
        db.executescript(schema)

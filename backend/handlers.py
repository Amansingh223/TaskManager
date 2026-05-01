from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import PBKDF2_ITERATIONS, STATIC_DIR
from .db import connect, dict_row


TOKENS: dict[str, int] = {}
VALID_ROLES = {"Admin", "Member"}
VALID_STATUSES = {"Todo", "In Progress", "Done"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"{PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        iterations, salt, expected = password_hash.split("$", 2)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (TypeError, ValueError):
        return False


class AppHandler(BaseHTTPRequestHandler):
    server_version = "TaskManager/1.0"

    def log_message(self, format, *args):
        return

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json(status, {"error": message})

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON")

    def current_user(self) -> dict | None:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        user_id = TOKENS.get(header.removeprefix("Bearer ").strip())
        if not user_id:
            return None
        with connect() as db:
            row = db.execute(
                "SELECT id, name, email, role, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict_row(row)

    def require_user(self) -> dict | None:
        user = self.current_user()
        if not user:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Authentication required")
            return None
        return user

    def serve_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"

        target = (STATIC_DIR / path.lstrip("/")).resolve()
        static_root = STATIC_DIR.resolve()
        if static_root not in (target, *target.parents) or not target.exists() or target.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_types.get(Path(target).suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def route_api(self, method: str, path: str, query: dict) -> None:
        if path == "/api/health" and method == "GET":
            return self.send_json(HTTPStatus.OK, {"message": "Server Running"})
        if path == "/api/signup" and method == "POST":
            return self.signup()
        if path == "/api/login" and method == "POST":
            return self.login()
        if path == "/api/users" and method == "GET":
            return self.users()
        if path == "/api/dashboard" and method == "GET":
            return self.dashboard()
        if path == "/api/projects" and method == "GET":
            return self.projects()
        if path == "/api/projects" and method == "POST":
            return self.create_project()

        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "projects":
            project_id = self.parse_id(parts[2])
            if project_id is None:
                return self.send_error_json(HTTPStatus.NOT_FOUND, "Project not found")
            if len(parts) == 3 and method == "GET":
                return self.project_detail(project_id)
            if len(parts) == 4 and parts[3] == "members" and method == "POST":
                return self.add_member(project_id)

        if len(parts) == 2 and parts[0] == "api" and parts[1] == "tasks" and method == "POST":
            return self.create_task()
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "tasks":
            task_id = self.parse_id(parts[2])
            if task_id is None:
                return self.send_error_json(HTTPStatus.NOT_FOUND, "Task not found")
            if method == "PATCH":
                return self.update_task(task_id)
            if method == "DELETE":
                return self.delete_task(task_id)

        self.send_error_json(HTTPStatus.NOT_FOUND, "API endpoint not found")

    def parse_id(self, value: str) -> int | None:
        try:
            return int(value)
        except ValueError:
            return None

    def signup(self) -> None:
        data = self.read_json()
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        role = str(data.get("role", "Member")).strip()
        if len(name) < 2:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, "Name must be at least 2 characters")
        if "@" not in email:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, "Valid email is required")
        if len(password) < 8:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, "Password must be at least 8 characters")
        if role not in VALID_ROLES:
            role = "Member"

        try:
            with connect() as db:
                cursor = db.execute(
                    """
                    INSERT INTO users (name, email, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, email, hash_password(password), role, now_iso()),
                )
                user_id = cursor.lastrowid
                user = db.execute(
                    "SELECT id, name, email, role, created_at FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
        except sqlite3.IntegrityError:
            return self.send_error_json(HTTPStatus.CONFLICT, "Email already exists")

        token = secrets.token_urlsafe(32)
        TOKENS[token] = int(user_id)
        self.send_json(HTTPStatus.CREATED, {"token": token, "user": dict(user)})

    def login(self) -> None:
        data = self.read_json()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        with connect() as db:
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return self.send_error_json(HTTPStatus.UNAUTHORIZED, "Invalid email or password")

        token = secrets.token_urlsafe(32)
        TOKENS[token] = int(user["id"])
        self.send_json(
            HTTPStatus.OK,
            {
                "token": token,
                "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
            },
        )

    def users(self) -> None:
        if not self.require_user():
            return
        with connect() as db:
            rows = db.execute("SELECT id, name, email, role, created_at FROM users ORDER BY name").fetchall()
        self.send_json(HTTPStatus.OK, {"users": [dict(row) for row in rows]})

    def dashboard(self) -> None:
        user = self.require_user()
        if not user:
            return
        with connect() as db:
            counts = db.execute("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status").fetchall()
            overdue = db.execute(
                "SELECT COUNT(*) AS count FROM tasks WHERE due_date < date('now') AND status != 'Done'"
            ).fetchone()["count"]
            assigned = db.execute(
                """
                SELECT tasks.*, projects.name AS project_name, users.name AS assignee_name
                FROM tasks
                JOIN projects ON projects.id = tasks.project_id
                LEFT JOIN users ON users.id = tasks.assignee_id
                WHERE tasks.assignee_id = ?
                ORDER BY COALESCE(tasks.due_date, '9999-12-31'), tasks.updated_at DESC
                """,
                (user["id"],),
            ).fetchall()
        self.send_json(
            HTTPStatus.OK,
            {
                "statusCounts": {row["status"]: row["count"] for row in counts},
                "overdue": overdue,
                "assignedTasks": [dict(row) for row in assigned],
            },
        )

    def projects(self) -> None:
        if not self.require_user():
            return
        with connect() as db:
            rows = db.execute(
                """
                SELECT
                    projects.*,
                    COUNT(DISTINCT project_members.user_id) AS member_count,
                    COUNT(DISTINCT tasks.id) AS task_count,
                    SUM(CASE WHEN tasks.status = 'Done' THEN 1 ELSE 0 END) AS done_count
                FROM projects
                LEFT JOIN project_members ON project_members.project_id = projects.id
                LEFT JOIN tasks ON tasks.project_id = projects.id
                GROUP BY projects.id
                ORDER BY projects.created_at DESC
                """
            ).fetchall()
        self.send_json(HTTPStatus.OK, {"projects": [dict(row) for row in rows]})

    def create_project(self) -> None:
        user = self.require_user()
        if not user:
            return
        if user["role"] != "Admin":
            return self.send_error_json(HTTPStatus.FORBIDDEN, "Only admins can create projects")

        data = self.read_json()
        name = str(data.get("name", "")).strip()
        if len(name) < 2:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, "Project name must be at least 2 characters")

        created_at = now_iso()
        with connect() as db:
            cursor = db.execute(
                """
                INSERT INTO projects (name, description, owner_id, due_date, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, str(data.get("description", "")).strip(), user["id"], data.get("dueDate") or None, created_at),
            )
            db.execute(
                "INSERT OR IGNORE INTO project_members (project_id, user_id, created_at) VALUES (?, ?, ?)",
                (cursor.lastrowid, user["id"], created_at),
            )
        self.send_json(HTTPStatus.CREATED, {"message": "Project created"})

    def project_detail(self, project_id: int) -> None:
        if not self.require_user():
            return
        with connect() as db:
            project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not project:
                return self.send_error_json(HTTPStatus.NOT_FOUND, "Project not found")
            members = db.execute(
                """
                SELECT users.id, users.name, users.email, users.role
                FROM project_members
                JOIN users ON users.id = project_members.user_id
                WHERE project_members.project_id = ?
                ORDER BY users.name
                """,
                (project_id,),
            ).fetchall()
            tasks = db.execute(
                """
                SELECT tasks.*, users.name AS assignee_name
                FROM tasks
                LEFT JOIN users ON users.id = tasks.assignee_id
                WHERE tasks.project_id = ?
                ORDER BY COALESCE(tasks.due_date, '9999-12-31'), tasks.updated_at DESC
                """,
                (project_id,),
            ).fetchall()
        self.send_json(
            HTTPStatus.OK,
            {"project": dict(project), "members": [dict(row) for row in members], "tasks": [dict(row) for row in tasks]},
        )

    def add_member(self, project_id: int) -> None:
        user = self.require_user()
        if not user:
            return
        if not self.can_manage_project(project_id, user):
            return self.send_error_json(HTTPStatus.FORBIDDEN, "You cannot manage this project")
        data = self.read_json()
        with connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO project_members (project_id, user_id, created_at) VALUES (?, ?, ?)",
                (project_id, data.get("userId"), now_iso()),
            )
        self.send_json(HTTPStatus.OK, {"message": "Member added"})

    def create_task(self) -> None:
        user = self.require_user()
        if not user:
            return
        data = self.read_json()
        project_id = data.get("projectId")
        if not self.can_manage_project(project_id, user):
            return self.send_error_json(HTTPStatus.FORBIDDEN, "You cannot manage this project")
        title = str(data.get("title", "")).strip()
        status = data.get("status") if data.get("status") in VALID_STATUSES else "Todo"
        if len(title) < 2:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, "Task title must be at least 2 characters")

        timestamp = now_iso()
        with connect() as db:
            db.execute(
                """
                INSERT INTO tasks (project_id, title, description, assignee_id, status, due_date, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    title,
                    str(data.get("description", "")).strip(),
                    data.get("assigneeId") or None,
                    status,
                    data.get("dueDate") or None,
                    user["id"],
                    timestamp,
                    timestamp,
                ),
            )
        self.send_json(HTTPStatus.CREATED, {"message": "Task created"})

    def update_task(self, task_id: int) -> None:
        user = self.require_user()
        if not user:
            return
        data = self.read_json()
        with connect() as db:
            task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task:
                return self.send_error_json(HTTPStatus.NOT_FOUND, "Task not found")
            if not self.can_manage_project(task["project_id"], user) and task["assignee_id"] != user["id"]:
                return self.send_error_json(HTTPStatus.FORBIDDEN, "You cannot update this task")

            status = data.get("status", task["status"])
            if status not in VALID_STATUSES:
                return self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid task status")
            db.execute(
                """
                UPDATE tasks
                SET title = ?, description = ?, assignee_id = ?, status = ?, due_date = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(data.get("title", task["title"])).strip(),
                    data.get("description", task["description"]),
                    data.get("assigneeId", task["assignee_id"]),
                    status,
                    data.get("dueDate", task["due_date"]),
                    now_iso(),
                    task_id,
                ),
            )
        self.send_json(HTTPStatus.OK, {"message": "Task updated"})

    def delete_task(self, task_id: int) -> None:
        user = self.require_user()
        if not user:
            return
        with connect() as db:
            task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task:
                return self.send_error_json(HTTPStatus.NOT_FOUND, "Task not found")
            if not self.can_manage_project(task["project_id"], user):
                return self.send_error_json(HTTPStatus.FORBIDDEN, "You cannot delete this task")
            db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.send_json(HTTPStatus.OK, {"message": "Task deleted"})

    def can_manage_project(self, project_id: int | str | None, user: dict) -> bool:
        try:
            normalized_project_id = int(project_id)
        except (TypeError, ValueError):
            return False
        with connect() as db:
            project = db.execute("SELECT owner_id FROM projects WHERE id = ?", (normalized_project_id,)).fetchone()
        return bool(project and (user["role"] == "Admin" or project["owner_id"] == user["id"]))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/"):
                return self.route_api("GET", parsed.path, parse_qs(parsed.query))
            return self.serve_static(parsed.path)
        except ValueError as error:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
        except Exception as error:
            print("ERROR:", error)
            return self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error")

    def do_POST(self) -> None:
        self.handle_write("POST")

    def do_PATCH(self) -> None:
        self.handle_write("PATCH")

    def do_DELETE(self) -> None:
        self.handle_write("DELETE")

    def handle_write(self, method: str) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/"):
                return self.route_api(method, parsed.path, parse_qs(parsed.query))
            return self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
        except ValueError as error:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
        except Exception as error:
            print("ERROR:", error)
            return self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error")

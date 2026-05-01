from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

DB_NAME = "tasks.db"


# -------------------- DATABASE --------------------
def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            owner_id INTEGER
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            status TEXT,
            project_id INTEGER,
            assigned_to INTEGER
        )
        """)


# -------------------- HANDLER --------------------
class AppHandler(BaseHTTPRequestHandler):

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        return json.loads(data) if data else {}

    # -------------------- ROUTES --------------------

    def do_GET(self):
        if self.path == "/":
            return self.send_json(200, {"message": "Server Running"})

        if self.path == "/users":
            with connect() as db:
                users = db.execute("SELECT * FROM users").fetchall()
                return self.send_json(200, [dict(u) for u in users])

        if self.path == "/projects":
            with connect() as db:
                projects = db.execute("SELECT * FROM projects").fetchall()
                return self.send_json(200, [dict(p) for p in projects])

        if self.path == "/tasks":
            with connect() as db:
                tasks = db.execute("SELECT * FROM tasks").fetchall()
                return self.send_json(200, [dict(t) for t in tasks])

        return self.send_json(404, {"error": "Not found"})

    # -------------------- CREATE --------------------

    def do_POST(self):
        data = self.read_json()

        if self.path == "/signup":
            with connect() as db:
                db.execute(
                    "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                    (data["name"], data["email"], data["password"], data.get("role", "member"))
                )
                return self.send_json(201, {"msg": "User created"})

        if self.path == "/project":
            with connect() as db:
                db.execute(
                    "INSERT INTO projects (name, owner_id) VALUES (?, ?)",
                    (data["name"], data["owner_id"])
                )
                return self.send_json(201, {"msg": "Project created"})

        if self.path == "/task":
            with connect() as db:
                db.execute(
                    "INSERT INTO tasks (title, status, project_id, assigned_to) VALUES (?, ?, ?, ?)",
                    (data["title"], data.get("status", "Todo"), data["project_id"], data["assigned_to"])
                )
                return self.send_json(201, {"msg": "Task created"})

        return self.send_json(404, {"error": "Invalid route"})

    # -------------------- UPDATE --------------------

    def do_PUT(self):
        data = self.read_json()

        if self.path.startswith("/task/"):
            task_id = int(self.path.split("/")[-1])

            with connect() as db:
                db.execute(
                    "UPDATE tasks SET status=? WHERE id=?",
                    (data["status"], task_id)
                )
                return self.send_json(200, {"msg": "Task updated"})

        return self.send_json(404, {"error": "Not found"})

    # -------------------- DELETE --------------------

    def do_DELETE(self):
        if self.path.startswith("/task/"):
            task_id = int(self.path.split("/")[-1])

            with connect() as db:
                db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
                return self.send_json(200, {"msg": "Task deleted"})

        return self.send_json(404, {"error": "Not found"})


# -------------------- MAIN --------------------
def main():
    init_db()
    server = HTTPServer(("127.0.0.1", 8000), AppHandler)
    print("Server running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from .config import STATIC_DIR
from .db import connect, dict_row


class AppHandler(BaseHTTPRequestHandler):
    server_version = "ProjectTracker/1.0"

    def log_message(self, format, *args):
        return

    # ---------- RESPONSE HELPERS ----------

    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        self.send_json(status, {"error": message})

    # ---------- STATIC FILE SERVING ----------

    def serve_static(self, path: str):
        # 🔥 FORCE ROOT → index.html
        if path == "/":
            path = "/index.html"

        target = (STATIC_DIR / path.lstrip("/")).resolve()

        # सुरक्षा check
        if (
            not str(target).startswith(str(STATIC_DIR.resolve()))
            or not target.exists()
            or target.is_dir()
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_types = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
        }

        body = target.read_bytes()

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_types.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- API ROUTING ----------

    def route_api(self, method, path, query):
        # 👉 test route (important for checking)
        if path == "/api/health":
            return self.send_json(200, {"message": "Server Running"})

        # 👉 example API
        if path == "/api/test":
            return self.send_json(200, {"status": "ok"})

        return self.send_error_json(404, "API endpoint not found")

    # ---------- HTTP METHODS ----------

    def do_GET(self):
        parsed = urlparse(self.path)

        try:
            # 🔥 IMPORTANT FIX: ROOT ALWAYS UI
            if parsed.path == "/":
                return self.serve_static("/index.html")

            # API
            if parsed.path.startswith("/api/"):
                return self.route_api("GET", parsed.path, parse_qs(parsed.query))

            # Static files
            return self.serve_static(parsed.path)

        except Exception as e:
            print("ERROR:", e)
            self.send_error_json(500, "Internal server error")

    def do_POST(self):
        parsed = urlparse(self.path)

        try:
            if parsed.path.startswith("/api/"):
                return self.route_api("POST", parsed.path, parse_qs(parsed.query))

            self.send_error_json(404, "Not found")

        except Exception:
            self.send_error_json(500, "Internal server error")
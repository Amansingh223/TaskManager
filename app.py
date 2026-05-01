from __future__ import annotations

from http.server import ThreadingHTTPServer

from backend.config import PORT
from backend.db import init_db
from backend.handlers import AppHandler


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), AppHandler)
    print(f"Server running at http://0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()

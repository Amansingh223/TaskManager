from __future__ import annotations

from http.server import ThreadingHTTPServer
from threading import Thread

from backend.config import PORT
from backend.db import init_db
from backend.handlers import AppHandler


def run_server(port: int, required: bool = True) -> None:
    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), AppHandler)
    except OSError as error:
        print(f"Could not bind to port {port}: {error}", flush=True)
        if required:
            raise
        return

    print(f"Server running at http://0.0.0.0:{port}", flush=True)
    server.serve_forever()


def main() -> None:
    init_db()
    ports = [PORT]
    if PORT != 8000:
        ports.append(8000)

    for port in ports[1:]:
        Thread(target=run_server, args=(port, False), daemon=True).start()
    run_server(PORT)


if __name__ == "__main__":
    main()

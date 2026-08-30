"""Local HTTP API and static client server for GundHere."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from hybrid_search import hybrid_search_database
from search_index import DEFAULT_DATABASE, database_metadata
from vector_search import TfidfVectorIndex


CLIENT_DIRECTORY = Path(__file__).parent / "client"
STATIC_ROUTES = {
    "/": CLIENT_DIRECTORY / "index.html",
    "/app.js": CLIENT_DIRECTORY / "app.js",
    "/styles.css": CLIENT_DIRECTORY / "styles.css",
    "/fonts/BarlowCondensed-SemiBold.ttf": (
        CLIENT_DIRECTORY / "fonts" / "BarlowCondensed-SemiBold.ttf"
    ),
}


class GundHereServer(ThreadingHTTPServer):
    database_path: Path
    vector_index: TfidfVectorIndex
    metadata: dict[str, str]


class GundHereHandler(BaseHTTPRequestHandler):
    server: GundHereServer

    def _send_headers(self, status: HTTPStatus, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data: https:; connect-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_headers(status, "application/json; charset=utf-8")
        self.wfile.write(body)

    def _serve_static(self, path: Path) -> None:
        if not path.is_file():
            self._send_json({"error": "Client asset not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send_headers(HTTPStatus.OK, f"{content_type}; charset=utf-8")
        self.wfile.write(path.read_bytes())

    def _search(self, parameters: dict[str, list[str]]) -> None:
        query = parameters.get("q", [""])[0].strip()
        if not query:
            self._send_json(
                {"error": "Enter a kit name or remembered search terms."},
                HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            limit = int(parameters.get("limit", ["20"])[0])
            if not 1 <= limit <= 50:
                raise ValueError("limit must be between 1 and 50")
            report = hybrid_search_database(
                self.server.database_path,
                query,
                grade=parameters.get("grade", [None])[0],
                scale=parameters.get("scale", [None])[0],
                availability=parameters.get("availability", [None])[0],
                result_limit=limit,
                vector_index=self.server.vector_index,
            )
        except ValueError as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        self._send_json(report)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path in STATIC_ROUTES:
            self._serve_static(STATIC_ROUTES[parsed.path])
            return
        if parsed.path == "/api/health":
            self._send_json(
                {
                    "status": "ok",
                    "entities": int(self.server.metadata.get("count_entities", "0")),
                    "vector_features": self.server.vector_index.vocabulary_size,
                }
            )
            return
        if parsed.path == "/api/search":
            self._search(parse_qs(parsed.query))
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def create_server(
    database_path: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> GundHereServer:
    if not database_path.is_file():
        raise FileNotFoundError(
            f"Search database does not exist: {database_path}. Build it first."
        )
    server = GundHereServer((host, port), GundHereHandler)
    server.database_path = database_path
    server.vector_index = TfidfVectorIndex.from_database(database_path)
    server.metadata = database_metadata(database_path)
    return server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the GundHere web client.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = create_server(args.database, args.host, args.port)
    host, port = server.server_address
    print(f"GundHere client: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping GundHere.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

"""Production HTTP API and static client server for GundHere."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

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
LOGGER = logging.getLogger("gundhere")

Grade = Literal["HG", "RG", "MG", "PG", "SD"]
Scale = Literal["1/144", "1/100", "1/60", "Non-scale"]
Availability = Literal["IN STOCK", "OUT OF STOCK"]


class JsonFormatter(logging.Formatter):
    """Emit one structured JSON object per log line."""

    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "request_id",
            "method",
            "path",
            "status",
            "duration_ms",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)
    LOGGER.setLevel(level.upper())
    LOGGER.propagate = False


@dataclass
class Bucket:
    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Small, thread-safe per-client limiter for a single application instance."""

    def __init__(
        self,
        *,
        capacity: int,
        refill_per_second: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("rate-limit capacity must be positive")
        if refill_per_second <= 0:
            raise ValueError("rate-limit refill rate must be positive")
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.clock = clock
        self.buckets: dict[str, Bucket] = {}
        self.lock = threading.Lock()
        self.request_count = 0

    def consume(self, key: str) -> tuple[bool, int]:
        """Consume one token and return (allowed, retry_after_seconds)."""
        now = self.clock()
        with self.lock:
            bucket = self.buckets.get(key, Bucket(float(self.capacity), now))
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(
                float(self.capacity),
                bucket.tokens + elapsed * self.refill_per_second,
            )
            bucket.updated_at = now
            self.request_count += 1

            if bucket.tokens < 1:
                retry_after = max(
                    1,
                    math.ceil((1 - bucket.tokens) / self.refill_per_second),
                )
                self.buckets[key] = bucket
                return False, retry_after

            bucket.tokens -= 1
            self.buckets[key] = bucket
            if self.request_count % 500 == 0:
                self._prune(now)
            return True, 0

    def _prune(self, now: float) -> None:
        idle_limit = self.capacity / self.refill_per_second * 2
        self.buckets = {
            key: bucket
            for key, bucket in self.buckets.items()
            if now - bucket.updated_at <= idle_limit
        }


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    rate_limit_capacity: int = 20
    rate_limit_refill_per_second: float = 0.5
    maximum_request_target_bytes: int = 2048
    maximum_concurrent_searches: int = 8
    search_timeout_seconds: float = 5.0
    log_level: str = "INFO"
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")

    @classmethod
    def from_environment(cls) -> "Settings":
        hosts = {
            host.strip()
            for host in os.getenv(
                "ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"
            ).split(",")
            if host.strip()
        }
        render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
        if render_host:
            hosts.add(render_host)
        return cls(
            environment=os.getenv("ENVIRONMENT", "development").casefold(),
            rate_limit_capacity=int(os.getenv("RATE_LIMIT_CAPACITY", "20")),
            rate_limit_refill_per_second=float(
                os.getenv("RATE_LIMIT_REFILL_PER_SECOND", "0.5")
            ),
            maximum_request_target_bytes=int(
                os.getenv("MAXIMUM_REQUEST_TARGET_BYTES", "2048")
            ),
            maximum_concurrent_searches=int(
                os.getenv("MAXIMUM_CONCURRENT_SEARCHES", "8")
            ),
            search_timeout_seconds=float(
                os.getenv("SEARCH_TIMEOUT_SECONDS", "5")
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            allowed_hosts=tuple(sorted(hosts)),
        )


def _security_headers(response, *, production: bool) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: https:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )
    if production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _database_is_ready(database_path: Path) -> bool:
    try:
        connection = sqlite3.connect(
            f"file:{database_path.resolve()}?mode=ro",
            uri=True,
            timeout=1,
        )
        try:
            connection.execute("PRAGMA query_only = ON")
            return connection.execute(
                "SELECT 1 FROM metadata LIMIT 1"
            ).fetchone() is not None
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def create_app(
    database_path: Path = DEFAULT_DATABASE,
    *,
    settings: Settings | None = None,
    rate_limiter: TokenBucketRateLimiter | None = None,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    configure_logging(settings.log_level)
    limiter = rate_limiter or TokenBucketRateLimiter(
        capacity=settings.rate_limit_capacity,
        refill_per_second=settings.rate_limit_refill_per_second,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if not database_path.is_file():
            raise RuntimeError(
                f"Search database does not exist: {database_path}. Build it first."
            )
        application.state.vector_index = TfidfVectorIndex.from_database(database_path)
        application.state.metadata = database_metadata(database_path)
        application.state.search_slots = asyncio.Semaphore(
            settings.maximum_concurrent_searches
        )
        LOGGER.info("Search runtime initialized")
        yield
        LOGGER.info("Search runtime stopped")

    application = FastAPI(
        title="GundHere",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )

    @application.middleware("http")
    async def protect_and_log(request: Request, call_next):
        started_at = time.perf_counter()
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        raw_target_size = len(request.scope.get("raw_path", b"")) + len(
            request.scope.get("query_string", b"")
        )

        if raw_target_size > settings.maximum_request_target_bytes:
            response = JSONResponse(
                {"error": "Request URL is too long.", "request_id": request_id},
                status_code=414,
            )
        elif request.url.path == "/api/search":
            allowed, retry_after = limiter.consume(_client_key(request))
            if not allowed:
                response = JSONResponse(
                    {
                        "error": "Too many searches. Please wait and try again.",
                        "request_id": request_id,
                    },
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        _security_headers(
            response,
            production=settings.environment == "production",
        )
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        LOGGER.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del request, error
        return JSONResponse(
            {"error": "Invalid search parameters."},
            status_code=400,
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        LOGGER.exception(
            "Unhandled request failure",
            exc_info=error,
            extra={"request_id": request_id, "path": request.url.path},
        )
        return JSONResponse(
            {"error": "Search service temporarily unavailable.", "request_id": request_id},
            status_code=500,
        )

    @application.get("/api/health")
    def health(request: Request):
        if not _database_is_ready(database_path):
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {
            "status": "ok",
            "entities": int(request.app.state.metadata.get("count_entities", "0")),
            "vector_features": request.app.state.vector_index.vocabulary_size,
        }

    @application.get("/api/search")
    async def search(
        request: Request,
        q: Annotated[str, Query(min_length=1, max_length=160)],
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        grade: Grade | None = None,
        scale: Scale | None = None,
        availability: Availability | None = None,
    ):
        query = q.strip()
        if not query:
            return JSONResponse(
                {"error": "Enter a kit name or remembered search terms."},
                status_code=400,
            )

        try:
            await asyncio.wait_for(
                request.app.state.search_slots.acquire(),
                timeout=0.1,
            )
        except TimeoutError:
            return JSONResponse(
                {"error": "Search service is busy. Please try again."},
                status_code=503,
                headers={"Retry-After": "1"},
            )

        try:
            return await asyncio.wait_for(
                run_in_threadpool(
                    hybrid_search_database,
                    database_path,
                    query,
                    grade=grade,
                    scale=scale,
                    availability=availability,
                    result_limit=limit,
                    vector_index=request.app.state.vector_index,
                ),
                timeout=settings.search_timeout_seconds,
            )
        except ValueError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        except TimeoutError:
            LOGGER.warning("Search timed out")
            return JSONResponse(
                {"error": "Search took too long. Please simplify the query."},
                status_code=504,
            )
        finally:
            request.app.state.search_slots.release()

    def static_handler(file_path: Path):
        async def static_file():
            if not file_path.is_file():
                return JSONResponse({"error": "Client asset not found"}, status_code=404)
            return FileResponse(file_path)

        return static_file

    for route, path in STATIC_ROUTES.items():
        application.add_api_route(
            route,
            static_handler(path),
            methods=["GET"],
            include_in_schema=False,
        )

    return application


app = create_app()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the GundHere web client.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    production_app = create_app(args.database)
    trust_proxy = os.getenv("TRUST_PROXY_HEADERS", "false").casefold() == "true"
    uvicorn.run(
        production_app,
        host=args.host,
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="*" if trust_proxy else "127.0.0.1",
        server_header=False,
        access_log=False,
        timeout_keep_alive=5,
        limit_concurrency=16,
    )


if __name__ == "__main__":
    main()

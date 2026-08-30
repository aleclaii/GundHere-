import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from search_index import build_database
from server import JsonFormatter, Settings, TokenBucketRateLimiter, create_app


GROUND_TRUTH = Path("data/processed/gunpla_ground_truth.csv")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temporary_directory.name) / "test.sqlite3"
        build_database(GROUND_TRUTH, cls.database)
        cls.settings = Settings(environment="production")
        cls.client_context = TestClient(
            create_app(cls.database, settings=cls.settings),
            raise_server_exceptions=False,
        )
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        cls.temporary_directory.cleanup()

    def test_health_reports_index(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entities"], 1146)

    def test_search_returns_hybrid_candidates(self) -> None:
        response = self.client.get("/api/search?q=RG+Nu+Gundma&limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["candidates"]), 5)
        self.assertIn("retrieval", payload)
        self.assertIn("retrieved_by", payload["candidates"][0])

    def test_empty_query_returns_bad_request(self) -> None:
        response = self.client.get("/api/search")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid search parameters.")

    def test_query_and_filter_validation(self) -> None:
        too_long = self.client.get("/api/search", params={"q": "x" * 161})
        invalid_filter = self.client.get(
            "/api/search",
            params={"q": "gundam", "grade": "NOT-A-GRADE"},
        )
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(invalid_filter.status_code, 400)

    def test_request_target_limit(self) -> None:
        settings = Settings(maximum_request_target_bytes=32)
        with TestClient(create_app(self.database, settings=settings)) as client:
            response = client.get("/api/search", params={"q": "x" * 50})
        self.assertEqual(response.status_code, 414)

    def test_rate_limit_returns_retry_after(self) -> None:
        limiter = TokenBucketRateLimiter(capacity=1, refill_per_second=0.01)
        with TestClient(
            create_app(self.database, settings=self.settings, rate_limiter=limiter)
        ) as client:
            first = client.get("/api/search?q=gundam&limit=1")
            second = client.get("/api/search?q=gundam&limit=1")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)

    def test_security_headers(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("object-src 'none'", response.headers["content-security-policy"])
        self.assertIn("max-age=31536000", response.headers["strict-transport-security"])
        self.assertIn("x-request-id", response.headers)

    def test_untrusted_host_is_rejected(self) -> None:
        response = self.client.get("/", headers={"Host": "attacker.example"})
        self.assertEqual(response.status_code, 400)

    def test_generic_error_response_does_not_leak_exception(self) -> None:
        with patch("server.hybrid_search_database", side_effect=RuntimeError("secret")):
            response = self.client.get("/api/search?q=gundam")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.text)
        self.assertIn("request_id", response.json())

    def test_serves_client(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("GUNDHERE", response.text)
        self.assertIn("search-form", response.text)

    def test_serves_display_font(self) -> None:
        response = self.client.get("/fonts/BarlowCondensed-SemiBold.ttf")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.content), 100_000)


class RateLimiterTests(unittest.TestCase):
    def test_bucket_refills_over_time(self) -> None:
        now = [0.0]
        limiter = TokenBucketRateLimiter(
            capacity=1,
            refill_per_second=1,
            clock=lambda: now[0],
        )
        self.assertEqual(limiter.consume("client"), (True, 0))
        self.assertEqual(limiter.consume("client"), (False, 1))
        now[0] = 1.0
        self.assertEqual(limiter.consume("client"), (True, 0))


class LoggingTests(unittest.TestCase):
    def test_json_formatter_outputs_structured_fields(self) -> None:
        record = logging.LogRecord(
            "gundhere",
            logging.INFO,
            __file__,
            1,
            "request",
            (),
            None,
        )
        record.request_id = "abc"
        record.status = 200
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["request_id"], "abc")
        self.assertEqual(payload["status"], 200)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from search_index import build_database
from server import create_server


GROUND_TRUTH = Path("data/processed/gunpla_ground_truth.csv")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temporary_directory.name) / "test.sqlite3"
        build_database(GROUND_TRUTH, cls.database)
        cls.server = create_server(cls.database, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temporary_directory.cleanup()

    def get_json(self, path: str):
        with urlopen(f"{self.base_url}{path}") as response:
            return response.status, json.load(response)

    def test_health_reports_index(self) -> None:
        status, payload = self.get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["entities"], 1146)

    def test_search_returns_hybrid_candidates(self) -> None:
        status, payload = self.get_json("/api/search?q=RG+Nu+Gundma&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["candidates"]), 5)
        self.assertIn("retrieval", payload)
        self.assertIn("retrieved_by", payload["candidates"][0])

    def test_empty_query_returns_bad_request(self) -> None:
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/api/search")
        self.assertEqual(context.exception.code, 400)

    def test_serves_client(self) -> None:
        with urlopen(f"{self.base_url}/") as response:
            html = response.read().decode("utf-8")
        self.assertIn("GUNDHERE", html)
        self.assertIn("search-form", html)

    def test_serves_display_font(self) -> None:
        with urlopen(
            f"{self.base_url}/fonts/BarlowCondensed-SemiBold.ttf"
        ) as response:
            font = response.read()
        self.assertGreater(len(font), 100_000)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from hybrid_search import hybrid_search_database
from search_index import build_database
from vector_search import TfidfVectorIndex


GROUND_TRUTH = Path("data/processed/gunpla_ground_truth.csv")


class HybridSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temporary_directory.name) / "test.sqlite3"
        build_database(GROUND_TRUTH, cls.database)
        cls.vector_index = TfidfVectorIndex.from_database(cls.database)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def search(self, query: str, **kwargs):
        return hybrid_search_database(
            self.database,
            query,
            vector_index=self.vector_index,
            **kwargs,
        )

    def test_unions_and_deduplicates_retrievers(self) -> None:
        report = self.search("RG 1/144 Nu Gundam")
        ids = [candidate["entity_id"] for candidate in report["candidates"]]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(
            any(
                candidate["retrieved_by"] == ["fts5", "vector"]
                for candidate in report["candidates"]
            )
        )

    def test_vector_recovers_query_with_no_fts_hit(self) -> None:
        report = self.search("Gundma")

        self.assertEqual(report["retrieval"]["fts_count"], 0)
        self.assertGreater(report["retrieval"]["vector_count"], 0)
        self.assertTrue(report["candidates"])
        self.assertTrue(
            all("vector" in candidate["retrieved_by"] for candidate in report["candidates"])
        )

    def test_results_are_sorted_and_top_two_are_compared(self) -> None:
        report = self.search("RG 1/144 Nu Gundma")
        candidates = report["candidates"]
        scores = [candidate["final_score"] for candidate in candidates]

        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(
            report["comparison"]["best_entity_id"],
            candidates[0]["entity_id"],
        )
        self.assertAlmostEqual(
            report["comparison"]["score_margin"],
            candidates[0]["final_score"] - candidates[1]["final_score"],
        )

    def test_filters_apply_to_both_retrievers(self) -> None:
        report = self.search("Gundam", grade="RG", scale="144")
        self.assertTrue(report["candidates"])
        self.assertTrue(
            all(
                candidate["grade"] == "RG" and candidate["scale"] == "1/144"
                for candidate in report["candidates"]
            )
        )

    def test_conflicting_filter_is_reported(self) -> None:
        with self.assertRaisesRegex(ValueError, "Grade filter MG conflicts with RG"):
            self.search("RG Nu Gundam", grade="MG")


if __name__ == "__main__":
    unittest.main()

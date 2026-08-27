"""Integration tests for the reproducible SQLite search layer."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from search_index import (
    build_database,
    database_metadata,
    fuzzy_search_database,
    search_database,
)


GROUND_TRUTH = Path("data/processed/gunpla_ground_truth.csv")


class SearchIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temporary_directory.name) / "test.sqlite3"
        cls.counts = build_database(GROUND_TRUTH, cls.database)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_expected_counts_and_integrity(self) -> None:
        self.assertEqual(self.counts["source_records"], 1697)
        self.assertEqual(self.counts["entities"], 1146)
        self.assertEqual(self.counts["fts_documents"], 1146)
        self.assertEqual(self.counts["listings"], 59)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_exact_match_attaches_listing(self) -> None:
        results = search_database(self.database, "Gundam AGE-2 Normal")
        match = next(row for row in results if row["entity_id"] == "DALONG-MG-M158")
        self.assertTrue(any(row["source_product_id"] == "F2156349001" for row in match["listings"]))

    def test_variant_remains_distinct(self) -> None:
        results = search_database(self.database, "strike freedom titanium")
        self.assertEqual(results[0]["entity_id"], "PB-F2520561008")
        self.assertEqual(results[0]["parent_entity_ids"], ["DALONG-RG-RG14"])

    def test_accessory_is_not_searchable(self) -> None:
        results = search_database(self.database, "expansion parts barbatos lupus")
        self.assertEqual(results, [])

    def test_filters(self) -> None:
        results = search_database(
            self.database,
            "strike freedom",
            grade="RG",
            scale="144",
            availability="IN STOCK",
        )
        self.assertTrue(results)
        self.assertTrue(all(row["grade"] == "RG" and row["scale"] == "1/144" for row in results))
        self.assertTrue(all(row["listings"] for row in results))

    def test_punctuation_is_not_fts_syntax(self) -> None:
        results = search_database(self.database, 'rx-78 " OR *')
        self.assertIsInstance(results, list)

    def test_metadata_records_source_hash(self) -> None:
        metadata = database_metadata(self.database)
        self.assertEqual(metadata["schema_version"], "1")
        self.assertEqual(int(metadata["count_entities"]), 1146)
        self.assertEqual(len(metadata["source_sha256"]), 64)

    def test_fuzzy_search_reranks_twenty_fts_candidates(self) -> None:
        report = fuzzy_search_database(
            self.database,
            "RG 1/144 RX-93 Nu Gndam",
        )
        candidates = report["candidates"]

        self.assertEqual(report["candidate_limit"], 20)
        self.assertEqual(report["candidate_count"], 20)
        self.assertEqual(
            [row["final_score"] for row in candidates],
            sorted(
                (row["final_score"] for row in candidates),
                reverse=True,
            ),
        )
        self.assertTrue(all("score_components" in row for row in candidates))

    def test_fuzzy_search_compares_top_two_scores(self) -> None:
        report = fuzzy_search_database(
            self.database,
            "RG 1/144 RX-93 Nu Gndam",
        )
        best, runner_up = report["candidates"][:2]
        comparison = report["comparison"]

        self.assertEqual(comparison["best_entity_id"], best["entity_id"])
        self.assertEqual(
            comparison["runner_up_entity_id"],
            runner_up["entity_id"],
        )
        self.assertAlmostEqual(
            comparison["score_margin"],
            best["final_score"] - runner_up["final_score"],
        )


if __name__ == "__main__":
    unittest.main()

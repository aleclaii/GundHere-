import math
import tempfile
import unittest
from pathlib import Path

from search_index import build_database
from vector_search import TfidfVectorIndex, feature_counts


GROUND_TRUTH = Path("data/processed/gunpla_ground_truth.csv")


class VectorFeatureTests(unittest.TestCase):
    def test_word_and_character_features_are_separate(self) -> None:
        counts = feature_counts("RG Nu Gundam")
        self.assertEqual(counts["word:rg"], 1)
        self.assertEqual(counts["word:nu"], 1)
        self.assertGreater(counts["char:^gu"], 0)


class VectorSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temporary_directory.name) / "test.sqlite3"
        build_database(GROUND_TRUTH, cls.database)
        cls.index = TfidfVectorIndex.from_database(cls.database)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_index_contains_every_entity(self) -> None:
        self.assertEqual(len(self.index.documents), 1146)
        self.assertGreater(self.index.vocabulary_size, 100)

    def test_vectors_are_l2_normalized(self) -> None:
        vector = self.index.vectors[0]
        magnitude = math.sqrt(sum(weight * weight for weight in vector.values()))
        self.assertAlmostEqual(magnitude, 1.0)

    def test_results_are_sorted_by_cosine_similarity(self) -> None:
        results = self.index.search("RG 1/144 RX-93 Nu Gndam", limit=20)
        scores = [result["vector_score"] for result in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(len(results), 20)

    def test_transposed_word_still_retrieves_gundam_results(self) -> None:
        results = self.index.search("RG Nu Gundma", limit=20)
        self.assertTrue(
            any("Nu Gundam" in result["canonical_name"] for result in results[:5])
        )


if __name__ == "__main__":
    unittest.main()

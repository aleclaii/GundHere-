import unittest

from fuzzy import (
    classify_product_type,
    extract_grades,
    extract_model_codes,
    extract_scales,
    extract_variants,
    gunpla_match_score,
    normalize_gunpla_name,
)


class GunplaFeatureTests(unittest.TestCase):
    def test_gunpla_aliases(self) -> None:
        self.assertEqual(normalize_gunpla_name("Real Grade ν Gundam"), "rg nu gundam")

    def test_extract_grade_and_scale(self) -> None:
        name = "HGUC 1/144 RX-78-2 Gundam"
        self.assertEqual(extract_grades(name), frozenset({"HG"}))
        self.assertEqual(extract_scales(name), frozenset({"1/144"}))

    def test_extract_model_code(self) -> None:
        self.assertEqual(
            extract_model_codes("MG 1/100 ZGMF-X10A Freedom Gundam"),
            frozenset({"ZGMFX10A"}),
        )

    def test_extract_variant(self) -> None:
        self.assertEqual(
            extract_variants("RG Sazabi [Titanium Finish]"),
            frozenset({"titanium_finish"}),
        )

    def test_accessory_classification(self) -> None:
        self.assertEqual(classify_product_type("Fin Funnel Effect Unit"), "accessory")
        self.assertEqual(classify_product_type("RG 1/144 Nu Gundam"), "kit")


class GunplaScoreTests(unittest.TestCase):
    def test_matching_fields_raise_score(self) -> None:
        result = gunpla_match_score(
            "RG 1/144 RX-93 Nu Gundam",
            "Bandai RG 1/144 RX-93 Nu Gndam Model Kit",
        )
        self.assertFalse(result["rejected"])
        self.assertGreater(result["domain_adjustment"], 0)
        self.assertGreater(result["final_score"], result["lexical"]["total"])

    def test_grade_conflict_rejects_match(self) -> None:
        result = gunpla_match_score(
            "RG 1/144 RX-93 Nu Gundam",
            "MG 1/100 RX-93 Nu Gundam",
        )
        self.assertTrue(result["rejected"])
        self.assertEqual(result["final_score"], 0.0)

    def test_variant_conflict_penalizes_match(self) -> None:
        result = gunpla_match_score(
            "RG Sazabi [Titanium Finish]",
            "RG Sazabi [Clear Color]",
        )
        self.assertFalse(result["rejected"])
        self.assertLess(result["domain_adjustment"], 0)

    def test_accessory_does_not_match_base_kit(self) -> None:
        result = gunpla_match_score(
            "RG 1/144 Nu Gundam",
            "RG 1/144 Nu Gundam Fin Funnel Expansion Set",
        )
        self.assertTrue(result["rejected"])


if __name__ == "__main__":
    unittest.main()

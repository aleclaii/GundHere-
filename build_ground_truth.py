"""Build one variant-safe Gunpla entity-resolution ground-truth CSV.

Inputs:
* The Dalong canonical catalog.
* Every extracted P-Bandai listing.
* The manually adjudicated 100-listing P-Bandai sample.

The output is long-form: each row is one source record, while ``entity_id``
connects records that describe the same real kit. Unreviewed fuzzy predictions
are retained for future work but never promoted to ground truth.
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path


DEFAULT_CANONICAL = Path("gunpla_catalog_with_pbandai-Canonical Kits.csv")
DEFAULT_LISTINGS = Path("gunpla_catalog_with_pbandai-P-Bandai Listings.csv")
DEFAULT_ADJUDICATIONS = Path("data/reference/pbandai_ground_truth_100.csv")
DEFAULT_OUTPUT = Path("data/processed/gunpla_ground_truth.csv")

REVIEWED_LABELS = {
    "EXACT_MATCH",
    "VARIANT_OF",
    "NEW_PRODUCT",
    "BUNDLE",
    "ACCESSORY",
    "NON_KIT",
}
SEARCHABLE_LABELS = {"EXACT_MATCH", "VARIANT_OF", "NEW_PRODUCT"}

OUTPUT_FIELDS = [
    "record_id",
    "record_role",
    "source",
    "source_product_id",
    "source_name",
    "normalized_source_name",
    "entity_id",
    "canonical_name",
    "normalized_canonical_name",
    "relationship",
    "parent_entity_ids",
    "include_in_kit_index",
    "review_state",
    "adjudication_confidence",
    "grade",
    "scale",
    "price_usd",
    "availability",
    "source_url",
    "catalog_url",
    "image_reference",
    "matcher_status",
    "matcher_exact_entity_id",
    "matcher_suggested_entity_id",
    "matcher_suggested_name",
    "match_score",
    "score_margin",
    "matcher_evaluation",
    "adjudication_note",
    "catalog_section",
    "source_entry_id",
    "source_file",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        return list(csv.DictReader(input_file))


def require_unique(
    rows: list[dict[str, str]],
    field: str,
    source_name: str,
) -> None:
    values = [row[field].strip() for row in rows]
    duplicates = sorted(
        value for value, count in Counter(values).items() if count > 1
    )
    if duplicates:
        preview = ", ".join(duplicates[:5])
        raise ValueError(f"Duplicate {field} values in {source_name}: {preview}")
    if any(not value for value in values):
        raise ValueError(f"Blank {field} value in {source_name}")


def normalize_search_name(value: str) -> str:
    """Create a comparison/search form without erasing variant terminology."""
    replacements = {
        "∀": " turn a ",
        "ν": " nu ",
        "β": " beta ",
        "Ⅱ": " ii ",
        "Ⅲ": " iii ",
    }
    for original, replacement in replacements.items():
        value = value.replace(original, replacement)

    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = re.sub(r"\b1\s*/\s*(?:60|100|144)\b", " ", value)
    value = re.sub(
        r"\b(?:hg(?:uc|ce|ac|fc|aw|bd|ibo|cc)?|mg(?:ex|sd)?|rg|pg|sd)\b",
        " ",
        value,
    )
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def numeric_value(value: str) -> str:
    """Convert '$37.00' or '93.0%' into a machine-readable decimal string."""
    value = value.strip().replace("$", "").replace(",", "")
    if not value:
        return ""
    if value.endswith("%"):
        return f"{float(value[:-1]) / 100:g}"
    return f"{float(value):g}"


def split_targets(value: str) -> list[str]:
    return [target.strip() for target in value.split(";") if target.strip()]


def validate_inputs(
    canonical_rows: list[dict[str, str]],
    listing_rows: list[dict[str, str]],
    adjudication_rows: list[dict[str, str]],
) -> None:
    require_unique(canonical_rows, "Canonical ID", "canonical catalog")
    require_unique(listing_rows, "P-Bandai Product ID", "P-Bandai listings")
    require_unique(
        adjudication_rows,
        "pbandai_product_id",
        "manual adjudications",
    )

    canonical_ids = {row["Canonical ID"].strip() for row in canonical_rows}
    listing_ids = {
        row["P-Bandai Product ID"].strip() for row in listing_rows
    }

    for adjudication in adjudication_rows:
        product_id = adjudication["pbandai_product_id"].strip()
        label = adjudication["ground_truth_label"].strip()
        targets = split_targets(adjudication["target_canonical_ids"])

        if product_id not in listing_ids:
            raise ValueError(
                f"Reviewed product {product_id} is absent from listing input"
            )
        if label not in REVIEWED_LABELS:
            raise ValueError(f"Unknown ground-truth label {label!r}")
        missing_targets = [target for target in targets if target not in canonical_ids]
        if missing_targets:
            raise ValueError(
                f"{product_id} references missing canonical IDs: {missing_targets}"
            )
        if label == "EXACT_MATCH" and len(targets) != 1:
            raise ValueError(f"{product_id} EXACT_MATCH must have one target")
        if label == "VARIANT_OF" and not targets:
            raise ValueError(f"{product_id} VARIANT_OF requires a parent")
        if label == "NEW_PRODUCT" and not adjudication["expected_entity"].strip():
            raise ValueError(f"{product_id} NEW_PRODUCT requires expected_entity")


def canonical_output_row(row: dict[str, str]) -> dict[str, str]:
    canonical_id = row["Canonical ID"].strip()
    canonical_name = row["Canonical Name"].strip()
    return {
        "record_id": f"DALONG::{canonical_id}",
        "record_role": "CANONICAL_SOURCE",
        "source": "DALONG",
        "source_product_id": canonical_id,
        "source_name": canonical_name,
        "normalized_source_name": row["Normalized Search Name"].strip(),
        "entity_id": canonical_id,
        "canonical_name": canonical_name,
        "normalized_canonical_name": row["Normalized Search Name"].strip(),
        "relationship": "CANONICAL",
        "parent_entity_ids": "",
        "include_in_kit_index": "true",
        "review_state": "CATALOG_REFERENCE",
        "adjudication_confidence": "High",
        "grade": row["Grade"].strip(),
        "scale": row["Scale"].strip(),
        "price_usd": numeric_value(row["Lowest Linked Price USD"]),
        "availability": "",
        "source_url": row["Dalong Review URL"].strip(),
        "catalog_url": row["Dalong Catalog URL"].strip(),
        "image_reference": "",
        "matcher_status": "",
        "matcher_exact_entity_id": "",
        "matcher_suggested_entity_id": "",
        "matcher_suggested_name": "",
        "match_score": "",
        "score_margin": "",
        "matcher_evaluation": "",
        "adjudication_note": "Canonical kit from the reviewed Dalong catalog.",
        "catalog_section": row["Catalog Section"].strip(),
        "source_entry_id": row["Source Entry ID"].strip(),
        "source_file": row["Source File"].strip(),
    }


def pbandai_output_row(
    listing: dict[str, str],
    adjudication: dict[str, str] | None,
    canonical_by_id: dict[str, dict[str, str]],
) -> dict[str, str]:
    product_id = listing["P-Bandai Product ID"].strip()
    source_name = listing["P-Bandai Product Name"].strip()

    relationship = "UNREVIEWED"
    review_state = "UNREVIEWED"
    confidence = ""
    entity_id = ""
    canonical_name = ""
    parent_ids: list[str] = []
    include = False
    note = "Fuzzy matcher output is retained only as diagnostic metadata."

    if adjudication is not None:
        relationship = adjudication["ground_truth_label"].strip()
        review_state = "MANUALLY_REVIEWED"
        confidence = adjudication["adjudication_confidence"].strip()
        parent_ids = split_targets(adjudication["target_canonical_ids"])
        note = adjudication["adjudication_note"].strip()
        include = relationship in SEARCHABLE_LABELS

        if relationship == "EXACT_MATCH":
            entity_id = parent_ids[0]
            canonical_name = canonical_by_id[entity_id]["Canonical Name"].strip()
            parent_ids = []
        elif relationship in {"VARIANT_OF", "NEW_PRODUCT"}:
            entity_id = f"PB-{product_id}"
            canonical_name = (
                adjudication["expected_entity"].strip() or source_name
            )

    return {
        "record_id": f"PBANDAI::{product_id}",
        "record_role": "RETAILER_LISTING",
        "source": "P-BANDAI-US",
        "source_product_id": product_id,
        "source_name": source_name,
        "normalized_source_name": normalize_search_name(source_name),
        "entity_id": entity_id,
        "canonical_name": canonical_name,
        "normalized_canonical_name": normalize_search_name(canonical_name),
        "relationship": relationship,
        "parent_entity_ids": ";".join(parent_ids),
        "include_in_kit_index": str(include).lower(),
        "review_state": review_state,
        "adjudication_confidence": confidence,
        "grade": listing["Grade"].strip(),
        "scale": listing["Scale"].strip(),
        "price_usd": numeric_value(listing["Price USD"]),
        "availability": listing["Availability"].strip(),
        "source_url": listing["P-Bandai Product URL"].strip(),
        "catalog_url": "",
        "image_reference": listing["Saved Image Reference"].strip(),
        "matcher_status": listing["Match Status"].strip(),
        "matcher_exact_entity_id": listing["Matched Canonical ID"].strip(),
        "matcher_suggested_entity_id": listing["Suggested Canonical ID"].strip(),
        "matcher_suggested_name": listing["Suggested Canonical Name"].strip(),
        "match_score": numeric_value(listing["Match Score"]),
        "score_margin": numeric_value(listing["Score Margin"]),
        "matcher_evaluation": (
            adjudication["matcher_evaluation"].strip()
            if adjudication is not None
            else ""
        ),
        "adjudication_note": note,
        "catalog_section": "",
        "source_entry_id": "",
        "source_file": listing["Source File"].strip(),
    }


def build_rows(
    canonical_rows: list[dict[str, str]],
    listing_rows: list[dict[str, str]],
    adjudication_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    canonical_by_id = {
        row["Canonical ID"].strip(): row for row in canonical_rows
    }
    adjudication_by_product = {
        row["pbandai_product_id"].strip(): row for row in adjudication_rows
    }

    output = [canonical_output_row(row) for row in canonical_rows]
    output.extend(
        pbandai_output_row(
            listing,
            adjudication_by_product.get(listing["P-Bandai Product ID"].strip()),
            canonical_by_id,
        )
        for listing in listing_rows
    )
    return output


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one variant-safe Gunpla ground-truth CSV."
    )
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--listings", type=Path, default=DEFAULT_LISTINGS)
    parser.add_argument(
        "--adjudications",
        type=Path,
        default=DEFAULT_ADJUDICATIONS,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    canonical_rows = read_csv(args.canonical)
    listing_rows = read_csv(args.listings)
    adjudication_rows = read_csv(args.adjudications)

    validate_inputs(canonical_rows, listing_rows, adjudication_rows)
    rows = build_rows(canonical_rows, listing_rows, adjudication_rows)
    write_csv(rows, args.output)

    relationship_counts = Counter(row["relationship"] for row in rows)
    indexed_entities = {
        row["entity_id"]
        for row in rows
        if row["include_in_kit_index"] == "true" and row["entity_id"]
    }
    print(f"Wrote {len(rows)} source records to {args.output}")
    print(f"Searchable kit entities: {len(indexed_entities)}")
    print("Relationships:")
    for label, count in sorted(relationship_counts.items()):
        print(f"  {label}: {count}")


if __name__ == "__main__":
    main()

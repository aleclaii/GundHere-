"""Parse downloaded HobbyLink Japan product HTML into a listings CSV.

This program is offline-only: it does not import requests and makes no network
connections. Product pages are identified by their Schema.org Product JSON-LD.
If the same SKU was downloaded more than once, the newest snapshot wins.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from bs4 import BeautifulSoup


DEFAULT_INPUT_DIR = Path("data/raw/hlj")
DEFAULT_OUTPUT_FILE = Path("data/processed/hlj_products.csv")

CSV_FIELDS = [
    "retailer",
    "product_name",
    "grade",
    "grade_variant",
    "scale",
    "sku",
    "gtin13",
    "manufacturer",
    "series",
    "item_type",
    "category",
    "price_jpy",
    "currency",
    "stock_status",
    "schema_availability",
    "product_url",
    "image_url",
    "source_file",
    "fetched_at",
]

GRADE_PATTERN = re.compile(
    r"(?<![A-Z0-9])"
    r"(PG\s+UNLEASHED|MGEX|MGSD|HG(?:UC|CE|AC|FC|AW|BD|IBO)?|MG|RG|PG|"
    r"HIGH GRADE|MASTER GRADE|REAL GRADE|PERFECT GRADE)"
    r"(?![A-Z0-9])",
    re.IGNORECASE,
)
SCALE_PATTERN = re.compile(r"(?<!\d)1\s*/\s*(\d{2,4})(?!\d)")
TIMESTAMP_PATTERN = re.compile(r"(\d{8}T\d{6}Z)(?=\.html?$)", re.IGNORECASE)


def iter_json_objects(value: Any) -> Iterator[dict[str, Any]]:
    """Yield dictionaries from JSON-LD objects, arrays, and @graph containers."""
    if isinstance(value, list):
        for item in value:
            yield from iter_json_objects(item)
        return

    if not isinstance(value, dict):
        return

    yield value
    graph = value.get("@graph")
    if graph is not None:
        yield from iter_json_objects(graph)


def find_product_json(soup: BeautifulSoup) -> dict[str, Any] | None:
    """Return the first Schema.org Product object in the page."""
    for script in soup.find_all("script", type="application/ld+json"):
        raw_json = script.string or script.get_text()
        if not raw_json.strip():
            continue

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        for item in iter_json_objects(parsed):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(value).lower() == "product" for value in types):
                return item

    return None


def attribute(soup: BeautifulSoup, selector: str, name: str) -> str:
    element = soup.select_one(selector)
    if element is None:
        return ""
    value = element.get(name)
    return str(value).strip() if value is not None else ""


def text(soup: BeautifulSoup, selector: str) -> str:
    element = soup.select_one(selector)
    return element.get_text(" ", strip=True) if element is not None else ""


def first_offer(product: dict[str, Any]) -> dict[str, Any]:
    offers = product.get("offers", {})
    if isinstance(offers, list):
        return offers[0] if offers and isinstance(offers[0], dict) else {}
    return offers if isinstance(offers, dict) else {}


def brand_name(product: dict[str, Any]) -> str:
    brand = product.get("brand", "")
    if isinstance(brand, dict):
        return str(brand.get("name", "")).strip()
    return str(brand).strip()


def image_url(product: dict[str, Any]) -> str:
    image = product.get("image", "")
    if isinstance(image, list):
        return str(image[0]).strip() if image else ""
    if isinstance(image, dict):
        return str(image.get("url", "")).strip()
    return str(image).strip()


def identify_grade(name: str, item_type: str) -> tuple[str, str]:
    """Return a broad grade and its more specific variant."""
    match = GRADE_PATTERN.search(f"{name} {item_type}")
    if not match:
        return "", ""

    variant = re.sub(r"\s+", " ", match.group(1).upper()).strip()
    aliases = {
        "HIGH GRADE": "HG",
        "MASTER GRADE": "MG",
        "REAL GRADE": "RG",
        "PERFECT GRADE": "PG",
    }
    variant = aliases.get(variant, variant)

    if variant.startswith("HG"):
        return "HG", variant
    if variant.startswith("MG"):
        return "MG", variant
    if variant == "RG":
        return "RG", variant
    if variant.startswith("PG"):
        return "PG", variant
    return "", variant


def identify_scale(soup: BeautifulSoup, product_name: str) -> str:
    scale_number = attribute(soup, "#breadcrumbs_scale", "data-scale")
    if scale_number.isdigit():
        return f"1/{scale_number}"

    match = SCALE_PATTERN.search(product_name)
    return f"1/{match.group(1)}" if match else ""


def normalize_stock_status(raw_status: str, schema_availability: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", raw_status.lower())
    known_statuses = {
        "instock": "in_stock",
        "lowstock": "in_stock",
        "backorder": "backordered",
        "backordered": "backordered",
        "preorder": "preorder",
        "futurerelease": "future_release",
        "outofstock": "out_of_stock",
        "orderstop": "order_stop",
        "discontinued": "discontinued",
    }
    if normalized in known_statuses:
        return known_statuses[normalized]

    schema = schema_availability.lower()
    if schema == "instock":
        return "in_stock"
    if schema == "outofstock":
        return "out_of_stock"
    if schema == "preorder":
        return "preorder"
    return raw_status.strip().lower().replace(" ", "_")


def timestamp_from_filename(path: Path) -> str:
    match = TIMESTAMP_PATTERN.search(path.name)
    if not match:
        return ""
    parsed = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    return f"{parsed.isoformat()}Z"


def parse_product_file(path: Path) -> dict[str, str] | None:
    """Parse one saved HTML file, or return None when it is not a product page."""
    soup = BeautifulSoup(
        path.read_text(encoding="utf-8", errors="replace"),
        "html.parser",
    )
    product = find_product_json(soup)
    if product is None:
        return None

    offer = first_offer(product)
    product_name = str(product.get("name", "")).strip() or text(
        soup, "h2.page-title"
    )
    sku = str(product.get("sku") or product.get("productID") or "").strip()
    item_type = attribute(
        soup,
        "#details_macrotypedescr",
        "data-macrotypedescr",
    ) or text(soup, "#details_macrotypedescr")
    grade, grade_variant = identify_grade(product_name, item_type)

    schema_availability = str(offer.get("availability", "")).rstrip("/")
    if "/" in schema_availability:
        schema_availability = schema_availability.rsplit("/", 1)[-1]
    raw_status = attribute(soup, "#item_status", "value")

    canonical_url = attribute(soup, 'link[rel="canonical"]', "href")
    if not canonical_url:
        canonical_url = str(offer.get("url", "")).strip()

    manufacturer = brand_name(product) or attribute(
        soup,
        "#details_makername",
        "data-makername",
    )
    series = attribute(soup, "#details_seriesName", "data-seriesname")
    category = attribute(soup, "#details_catetory", "data-enGenreName")

    return {
        "retailer": "HobbyLink Japan",
        "product_name": product_name,
        "grade": grade,
        "grade_variant": grade_variant,
        "scale": identify_scale(soup, product_name),
        "sku": sku,
        "gtin13": str(product.get("gtin13", "")).strip(),
        "manufacturer": manufacturer,
        "series": series,
        "item_type": item_type,
        "category": category,
        "price_jpy": str(offer.get("price", "")).strip(),
        "currency": str(offer.get("priceCurrency", "")).strip(),
        "stock_status": normalize_stock_status(
            raw_status,
            schema_availability,
        ),
        "schema_availability": schema_availability,
        "product_url": canonical_url,
        "image_url": image_url(product),
        "source_file": str(path),
        "fetched_at": timestamp_from_filename(path),
    }


def find_html_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(
            path
            for path in input_path.rglob("*")
            if path.is_file() and path.suffix.lower() in {".html", ".htm"}
        )
    raise FileNotFoundError(f"Input path does not exist: {input_path}")


def newest_record_key(row: dict[str, str]) -> tuple[str, str]:
    """Use SKU for deduplication, falling back to the canonical product URL."""
    return (row["sku"] or row["product_url"], row["fetched_at"])


def parse_all(files: list[Path]) -> tuple[list[dict[str, str]], int, int]:
    records_by_product: dict[str, dict[str, str]] = {}
    skipped = 0
    duplicates = 0

    for path in files:
        row = parse_product_file(path)
        if row is None:
            skipped += 1
            print(f"Skipped non-product page: {path.name}")
            continue

        identity, fetched_at = newest_record_key(row)
        if not identity:
            skipped += 1
            print(f"Skipped product without SKU or URL: {path.name}")
            continue

        existing = records_by_product.get(identity)
        if existing is not None:
            duplicates += 1
            if fetched_at <= existing["fetched_at"]:
                continue

        records_by_product[identity] = row
        print(f"Parsed {row['sku']}: {row['product_name']}")

    rows = sorted(
        records_by_product.values(),
        key=lambda row: (row["grade"], row["product_name"].casefold()),
    )
    return rows, skipped, duplicates


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse saved HLJ product HTML into a listings CSV."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="HTML file or directory (default: data/raw/hlj).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="CSV destination (default: data/processed/hlj_products.csv).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        files = find_html_files(args.input)
    except FileNotFoundError as error:
        raise SystemExit(error) from error

    if not files:
        raise SystemExit(f"No HTML files found in {args.input}")

    rows, skipped, duplicates = parse_all(files)
    write_csv(rows, args.output)
    print(
        f"Wrote {len(rows)} unique listings to {args.output}; "
        f"skipped {skipped} non-product/invalid pages and "
        f"collapsed {duplicates} duplicate snapshots."
    )


if __name__ == "__main__":
    main()

"""Search the local GundHere SQLite index from the command line."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from search_index import DEFAULT_DATABASE, search_database


def bounded_limit(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search the GundHere index.")
    parser.add_argument("query", nargs="*", help="Words to search for.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--grade", help="Filter to a grade such as HG, MG, RG, or PG.")
    parser.add_argument("--scale", help="Filter to 1/144, 1/100, 1/60, etc.")
    parser.add_argument("--availability", help="Require a retailer availability value.")
    parser.add_argument("--limit", type=bounded_limit, default=10)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def price(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "price unavailable"


def print_human(results: list[dict[str, Any]]) -> None:
    if not results:
        print("No matching kits found.")
        return

    for position, result in enumerate(results, start=1):
        identity = " ".join(
            value for value in [result["grade"], result["scale"]] if value
        )
        suffix = f" [{identity}]" if identity else ""
        print(f"{position}. {result['canonical_name']}{suffix}")
        print(f"   entity: {result['entity_id']} ({result['relationship']})")
        if result["parent_entity_ids"]:
            print(f"   variant of: {', '.join(result['parent_entity_ids'])}")
        if not result["listings"]:
            print("   no indexed retailer listing")
        for listing in result["listings"]:
            availability = listing["availability"] or "availability unknown"
            print(
                f"   {listing['retailer']}: {price(listing['price_usd'])}; "
                f"{availability}"
            )
            if listing["product_url"]:
                print(f"   {listing['product_url']}")


def main() -> None:
    args = parse_args()
    results = search_database(
        args.database,
        " ".join(args.query),
        grade=args.grade,
        scale=args.scale,
        availability=args.availability,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print_human(results)


if __name__ == "__main__":
    main()


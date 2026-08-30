"""Search the local GundHere SQLite index from the command line."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hybrid_search import hybrid_search_database
from search_index import DEFAULT_DATABASE


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
    parser.add_argument(
        "--limit",
        type=bounded_limit,
        default=20,
        help="Maximum number of hybrid results to display (default: 20).",
    )
    parser.add_argument("--fts-limit", type=bounded_limit, default=20)
    parser.add_argument("--vector-limit", type=bounded_limit, default=20)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def price(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "price unavailable"


def print_human(report: dict[str, Any]) -> None:
    results = report["candidates"]
    if not results:
        print("No matching kits found.")
        return

    comparison = report["comparison"]
    retrieval = report["retrieval"]
    print(
        "Candidates: "
        f"{retrieval['fts_count']} FTS5 + {retrieval['vector_count']} vector "
        f"= {retrieval['union_count']} unique"
    )
    print(
        "Best: "
        f"{comparison['best_name']} ({comparison['best_score']:.3f})"
    )
    if comparison["runner_up_name"] is not None:
        print(
            "Runner-up: "
            f"{comparison['runner_up_name']} "
            f"({comparison['runner_up_score']:.3f})"
        )
        print(f"Score margin: {comparison['score_margin']:.3f}")
    print()

    for position, result in enumerate(results, start=1):
        identity = " ".join(
            value for value in [result["grade"], result["scale"]] if value
        )
        suffix = f" [{identity}]" if identity else ""
        print(f"{position}. {result['canonical_name']}{suffix}")
        print(f"   entity: {result['entity_id']} ({result['relationship']})")
        print(
            f"   final: {result['final_score']:.3f}; "
            f"lexical: {result['lexical_score']:.3f}; "
            f"domain: {result['domain_adjustment']:+.3f}; "
            f"via: {' + '.join(result['retrieved_by'])}"
        )
        retrieval_details = []
        if result["fts_rank_position"] is not None:
            retrieval_details.append(
                f"FTS #{result['fts_rank_position']} / "
                f"BM25 {result['fts_bm25']:.3f}"
            )
        if result["vector_rank_position"] is not None:
            retrieval_details.append(
                f"vector #{result['vector_rank_position']} / "
                f"cosine {result['vector_score']:.3f}"
            )
        print(f"   retrieval: {'; '.join(retrieval_details)}")
        if result["match_reasons"]:
            print(f"   reasons: {'; '.join(result['match_reasons'])}")
        if result["rejected"]:
            print("   rejected by Gunpla constraints")
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
    report = hybrid_search_database(
        args.database,
        " ".join(args.query),
        grade=args.grade,
        scale=args.scale,
        availability=args.availability,
        fts_limit=args.fts_limit,
        vector_limit=args.vector_limit,
        result_limit=args.limit,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_human(report)


if __name__ == "__main__":
    main()

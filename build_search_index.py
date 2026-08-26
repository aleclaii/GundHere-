"""Command-line entry point for rebuilding the GundHere SQLite index."""

from __future__ import annotations

import argparse
from pathlib import Path

from search_index import DEFAULT_DATABASE, DEFAULT_GROUND_TRUTH, build_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the GundHere SQLite/FTS5 search index."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--output", type=Path, default=DEFAULT_DATABASE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counts = build_database(args.input, args.output)
    print(f"Built search index: {args.output}")
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()


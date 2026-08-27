"""SQLite/FTS5 storage and search primitives for GundHere.

The ground-truth CSV remains the authoritative identity input. This module
creates a disposable, reproducible search index from it and provides read-only
query functions. It never changes matching decisions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fuzzy import gunpla_match_score


SCHEMA_VERSION = "1"
DEFAULT_GROUND_TRUTH = Path("data/processed/gunpla_ground_truth.csv")
DEFAULT_DATABASE = Path("data/index/gundhere.sqlite3")

REQUIRED_COLUMNS = {
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
    "grade",
    "scale",
    "price_usd",
    "availability",
    "source_url",
    "catalog_url",
    "image_reference",
    "matcher_suggested_entity_id",
    "match_score",
    "score_margin",
    "adjudication_note",
    "catalog_section",
}

QUERY_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE source_records (
    record_id TEXT PRIMARY KEY,
    record_role TEXT NOT NULL,
    source TEXT NOT NULL,
    source_product_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    normalized_source_name TEXT NOT NULL,
    entity_id TEXT,
    relationship TEXT NOT NULL,
    parent_entity_ids TEXT NOT NULL,
    include_in_kit_index INTEGER NOT NULL CHECK (include_in_kit_index IN (0, 1)),
    review_state TEXT NOT NULL,
    grade TEXT,
    scale TEXT,
    price_usd REAL,
    availability TEXT,
    source_url TEXT,
    matcher_suggested_entity_id TEXT,
    match_score REAL,
    score_margin REAL,
    adjudication_note TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    grade TEXT,
    scale TEXT,
    relationship TEXT NOT NULL,
    catalog_section TEXT,
    canonical_source TEXT NOT NULL,
    canonical_url TEXT,
    canonical_record_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (canonical_record_id) REFERENCES source_records(record_id)
);

CREATE TABLE entity_relations (
    child_entity_id TEXT NOT NULL,
    parent_entity_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    PRIMARY KEY (child_entity_id, parent_entity_id, relationship),
    FOREIGN KEY (child_entity_id) REFERENCES entities(entity_id),
    FOREIGN KEY (parent_entity_id) REFERENCES entities(entity_id)
);

CREATE TABLE aliases (
    alias_id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source TEXT NOT NULL,
    UNIQUE (entity_id, alias, source),
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
);

CREATE TABLE listings (
    record_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    retailer TEXT NOT NULL,
    source_product_id TEXT NOT NULL,
    listing_name TEXT NOT NULL,
    normalized_listing_name TEXT NOT NULL,
    price_usd REAL,
    availability TEXT,
    product_url TEXT,
    image_reference TEXT,
    FOREIGN KEY (record_id) REFERENCES source_records(record_id),
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
);

CREATE INDEX idx_source_records_entity ON source_records(entity_id);
CREATE INDEX idx_source_records_review ON source_records(review_state, relationship);
CREATE INDEX idx_entities_grade_scale ON entities(grade, scale);
CREATE INDEX idx_aliases_entity ON aliases(entity_id);
CREATE INDEX idx_listings_entity ON listings(entity_id);
CREATE INDEX idx_listings_availability ON listings(availability);

CREATE VIRTUAL TABLE entity_search USING fts5(
    entity_id UNINDEXED,
    canonical_name,
    aliases,
    normalized_names,
    grade,
    scale,
    catalog_section,
    tokenize = 'unicode61 remove_diacritics 2',
    prefix = '2 3 4'
);
"""


def _read_ground_truth(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"Ground-truth CSV is missing columns: {missing}")
        rows = list(reader)

    if not rows:
        raise ValueError("Ground-truth CSV contains no records")
    record_ids = [row["record_id"].strip() for row in rows]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("Ground-truth CSV contains duplicate record_id values")
    return rows


def _optional_float(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def _true(value: str) -> bool:
    return value.strip().casefold() == "true"


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for block in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _insert_source_records(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
) -> None:
    values = []
    for row in rows:
        values.append(
            (
                row["record_id"].strip(),
                row["record_role"].strip(),
                row["source"].strip(),
                row["source_product_id"].strip(),
                row["source_name"].strip(),
                row["normalized_source_name"].strip(),
                row["entity_id"].strip() or None,
                row["relationship"].strip(),
                row["parent_entity_ids"].strip(),
                int(_true(row["include_in_kit_index"])),
                row["review_state"].strip(),
                row["grade"].strip() or None,
                row["scale"].strip() or None,
                _optional_float(row["price_usd"]),
                row["availability"].strip() or None,
                row["source_url"].strip() or None,
                row["matcher_suggested_entity_id"].strip() or None,
                _optional_float(row["match_score"]),
                _optional_float(row["score_margin"]),
                row["adjudication_note"].strip(),
                json.dumps(row, ensure_ascii=False, sort_keys=True),
            )
        )

    connection.executemany(
        """
        INSERT INTO source_records (
            record_id, record_role, source, source_product_id, source_name,
            normalized_source_name, entity_id, relationship, parent_entity_ids,
            include_in_kit_index, review_state, grade, scale, price_usd,
            availability, source_url, matcher_suggested_entity_id, match_score,
            score_margin, adjudication_note, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )


def _choose_primary(rows: list[dict[str, str]]) -> dict[str, str]:
    canonical = [row for row in rows if row["relationship"] == "CANONICAL"]
    if len(canonical) == 1:
        return canonical[0]
    if len(canonical) > 1:
        raise ValueError(f"Entity {rows[0]['entity_id']} has multiple canonical rows")

    created = [
        row
        for row in rows
        if row["relationship"] in {"VARIANT_OF", "NEW_PRODUCT"}
    ]
    if len(created) != 1:
        raise ValueError(
            f"Entity {rows[0]['entity_id']} requires exactly one identity-defining row"
        )
    return created[0]


def _insert_entities(
    connection: sqlite3.Connection,
    rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        entity_id = row["entity_id"].strip()
        if _true(row["include_in_kit_index"]) and entity_id:
            grouped[entity_id].append(row)

    primaries: dict[str, dict[str, str]] = {}
    for entity_id, entity_rows in grouped.items():
        primary = _choose_primary(entity_rows)
        primaries[entity_id] = primary
        connection.execute(
            """
            INSERT INTO entities (
                entity_id, canonical_name, normalized_name, grade, scale,
                relationship, catalog_section, canonical_source, canonical_url,
                canonical_record_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                primary["canonical_name"].strip(),
                primary["normalized_canonical_name"].strip(),
                primary["grade"].strip() or None,
                primary["scale"].strip() or None,
                primary["relationship"].strip(),
                primary["catalog_section"].strip() or None,
                primary["source"].strip(),
                primary["source_url"].strip() or None,
                primary["record_id"].strip(),
            ),
        )

    for entity_id, primary in primaries.items():
        for parent_id in filter(
            None,
            (value.strip() for value in primary["parent_entity_ids"].split(";")),
        ):
            if parent_id not in grouped:
                raise ValueError(f"Entity {entity_id} has missing parent {parent_id}")
            connection.execute(
                """
                INSERT INTO entity_relations (
                    child_entity_id, parent_entity_id, relationship
                ) VALUES (?, ?, ?)
                """,
                (entity_id, parent_id, primary["relationship"].strip()),
            )

    return dict(grouped)


def _insert_aliases_and_listings(
    connection: sqlite3.Connection,
    grouped: dict[str, list[dict[str, str]]],
) -> None:
    for entity_id, rows in grouped.items():
        seen_aliases: set[tuple[str, str]] = set()
        for row in rows:
            alias = row["source_name"].strip()
            source = row["source"].strip()
            key = (alias, source)
            if alias and key not in seen_aliases:
                connection.execute(
                    """
                    INSERT INTO aliases (entity_id, alias, normalized_alias, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entity_id,
                        alias,
                        row["normalized_source_name"].strip(),
                        source,
                    ),
                )
                seen_aliases.add(key)

            if row["record_role"].strip() == "RETAILER_LISTING":
                connection.execute(
                    """
                    INSERT INTO listings (
                        record_id, entity_id, retailer, source_product_id,
                        listing_name, normalized_listing_name, price_usd,
                        availability, product_url, image_reference
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["record_id"].strip(),
                        entity_id,
                        source,
                        row["source_product_id"].strip(),
                        alias,
                        row["normalized_source_name"].strip(),
                        _optional_float(row["price_usd"]),
                        row["availability"].strip() or None,
                        row["source_url"].strip() or None,
                        row["image_reference"].strip() or None,
                    ),
                )


def _populate_fts(connection: sqlite3.Connection) -> None:
    entity_rows = connection.execute(
        """
        SELECT entity_id, canonical_name, normalized_name, grade, scale,
               COALESCE(catalog_section, '') AS catalog_section
        FROM entities
        ORDER BY entity_id
        """
    ).fetchall()

    for entity in entity_rows:
        aliases = connection.execute(
            """
            SELECT alias, normalized_alias
            FROM aliases
            WHERE entity_id = ?
            ORDER BY alias
            """,
            (entity["entity_id"],),
        ).fetchall()
        alias_text = " ".join(sorted({row["alias"] for row in aliases}))
        normalized_text = " ".join(
            sorted(
                {entity["normalized_name"]}
                | {row["normalized_alias"] for row in aliases}
            )
        )
        connection.execute(
            """
            INSERT INTO entity_search (
                entity_id, canonical_name, aliases, normalized_names,
                grade, scale, catalog_section
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity["entity_id"],
                entity["canonical_name"],
                alias_text,
                normalized_text,
                entity["grade"] or "",
                entity["scale"] or "",
                entity["catalog_section"],
            ),
        )


def _write_metadata(
    connection: sqlite3.Connection,
    source_path: Path,
) -> dict[str, int]:
    counts = {
        "source_records": connection.execute(
            "SELECT COUNT(*) FROM source_records"
        ).fetchone()[0],
        "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
        "aliases": connection.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
        "listings": connection.execute("SELECT COUNT(*) FROM listings").fetchone()[0],
        "relations": connection.execute(
            "SELECT COUNT(*) FROM entity_relations"
        ).fetchone()[0],
        "fts_documents": connection.execute(
            "SELECT COUNT(*) FROM entity_search"
        ).fetchone()[0],
        "unreviewed": connection.execute(
            "SELECT COUNT(*) FROM source_records WHERE review_state = 'UNREVIEWED'"
        ).fetchone()[0],
    }
    if counts["entities"] != counts["fts_documents"]:
        raise ValueError("FTS document count does not equal entity count")

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path.resolve()),
        "source_sha256": _source_sha256(source_path),
        **{f"count_{key}": str(value) for key, value in counts.items()},
    }
    connection.executemany(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        sorted(metadata.items()),
    )
    return counts


def build_database(source_path: Path, output_path: Path) -> dict[str, int]:
    """Atomically rebuild the SQLite search index from ground truth."""
    rows = _read_ground_truth(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)

    try:
        connection = sqlite3.connect(temporary_path)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript(SCHEMA_SQL)
            with connection:
                _insert_source_records(connection, rows)
                grouped = _insert_entities(connection, rows)
                _insert_aliases_and_listings(connection, grouped)
                _populate_fts(connection)
                counts = _write_metadata(connection, source_path)

            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"SQLite integrity check failed: {integrity}")
            connection.execute("PRAGMA optimize")
        finally:
            connection.close()

        os.replace(temporary_path, output_path)
        return counts
    finally:
        temporary_path.unlink(missing_ok=True)


def _fts_query(user_query: str, *, match_any: bool = False) -> str | None:
    tokens = QUERY_TOKEN_PATTERN.findall(user_query.casefold())
    if not tokens:
        return None
    # Quoted prefix terms avoid exposing SQLite FTS syntax to user input.
    operator = " OR " if match_any else " AND "
    return operator.join(f'"{token}"*' for token in tokens)


def _normalize_scale(scale: str | None) -> str | None:
    if scale is None:
        return None
    scale = scale.strip()
    if not scale:
        return None
    if scale.isdigit():
        return f"1/{scale}"
    return scale


def search_database(
    database_path: Path,
    query: str,
    *,
    grade: str | None = None,
    scale: str | None = None,
    availability: str | None = None,
    limit: int = 10,
    match_any: bool = False,
) -> list[dict[str, Any]]:
    """Search entities and attach every indexed retailer listing."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if not database_path.is_file():
        raise FileNotFoundError(
            f"Search database does not exist: {database_path}. Build it first."
        )

    grade = grade.strip().upper() if grade and grade.strip() else None
    scale = _normalize_scale(scale)
    availability = availability.strip() if availability and availability.strip() else None
    fts_query = _fts_query(query, match_any=match_any)

    connection = sqlite3.connect(
        f"file:{database_path.resolve()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        filters = """
            (? IS NULL OR e.grade = ?)
            AND (? IS NULL OR e.scale = ?)
            AND (
                ? IS NULL OR EXISTS (
                    SELECT 1 FROM listings filtered_listing
                    WHERE filtered_listing.entity_id = e.entity_id
                      AND UPPER(filtered_listing.availability) = UPPER(?)
                )
            )
        """
        filter_parameters: list[Any] = [
            grade,
            grade,
            scale,
            scale,
            availability,
            availability,
        ]

        if fts_query:
            hits = connection.execute(
                f"""
                SELECT e.entity_id,
                       bm25(entity_search, 0.0, 10.0, 5.0, 4.0, 2.0, 2.0, 1.0)
                           AS rank,
                       highlight(entity_search, 1, '[', ']') AS matched_name
                FROM entity_search
                JOIN entities e ON e.entity_id = entity_search.entity_id
                WHERE entity_search MATCH ? AND {filters}
                ORDER BY rank, e.canonical_name
                LIMIT ?
                """,
                [fts_query, *filter_parameters, limit],
            ).fetchall()
        else:
            hits = connection.execute(
                f"""
                SELECT e.entity_id, 0.0 AS rank, e.canonical_name AS matched_name
                FROM entities e
                WHERE {filters}
                ORDER BY e.canonical_name
                LIMIT ?
                """,
                [*filter_parameters, limit],
            ).fetchall()

        if not hits:
            return []

        entity_ids = [row["entity_id"] for row in hits]
        placeholders = ",".join("?" for _ in entity_ids)
        entities = {
            row["entity_id"]: dict(row)
            for row in connection.execute(
                f"SELECT * FROM entities WHERE entity_id IN ({placeholders})",
                entity_ids,
            )
        }
        listings_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in connection.execute(
            f"""
            SELECT * FROM listings
            WHERE entity_id IN ({placeholders})
            ORDER BY entity_id, price_usd IS NULL, price_usd, retailer
            """,
            entity_ids,
        ):
            listings_by_entity[row["entity_id"]].append(dict(row))

        parents_by_entity: dict[str, list[str]] = defaultdict(list)
        for row in connection.execute(
            f"""
            SELECT child_entity_id, parent_entity_id
            FROM entity_relations
            WHERE child_entity_id IN ({placeholders})
            ORDER BY parent_entity_id
            """,
            entity_ids,
        ):
            parents_by_entity[row["child_entity_id"]].append(row["parent_entity_id"])

        results = []
        for hit in hits:
            entity_id = hit["entity_id"]
            result = entities[entity_id]
            result["rank"] = hit["rank"]
            result["matched_name"] = hit["matched_name"]
            result["parent_entity_ids"] = parents_by_entity[entity_id]
            result["listings"] = listings_by_entity[entity_id]
            results.append(result)
        return results
    finally:
        connection.close()


def fuzzy_search_database(
    database_path: Path,
    query: str,
    *,
    grade: str | None = None,
    scale: str | None = None,
    availability: str | None = None,
    candidate_limit: int = 20,
) -> dict[str, Any]:
    """Retrieve FTS5 candidates, rerank them, and compare the top two."""
    if not query.strip():
        raise ValueError("query must not be empty for fuzzy search")
    if not 2 <= candidate_limit <= 100:
        raise ValueError("candidate_limit must be between 2 and 100")

    # OR retrieval is deliberately broad: a misspelled word should not prevent
    # correctly spelled grade, scale, model-code, or model-name terms from
    # producing candidates. FTS5 remains candidate generation, not final rank.
    fts_candidates = search_database(
        database_path,
        query,
        grade=grade,
        scale=scale,
        availability=availability,
        limit=candidate_limit,
        match_any=True,
    )

    reranked = []
    for candidate in fts_candidates:
        match = gunpla_match_score(candidate["canonical_name"], query)
        candidate = dict(candidate)
        candidate["fts_rank"] = candidate.pop("rank")
        candidate["final_score"] = match["final_score"]
        candidate["lexical_score"] = match["lexical"]["total"]
        candidate["score_components"] = match["lexical"]
        candidate["domain_adjustment"] = match["domain_adjustment"]
        candidate["rejected"] = match["rejected"]
        candidate["match_reasons"] = match["reasons"]
        candidate["query_features"] = match["listing_features"]
        candidate["candidate_features"] = match["canonical_features"]
        reranked.append(candidate)

    reranked.sort(
        key=lambda candidate: (
            -candidate["final_score"],
            candidate["fts_rank"],
            candidate["canonical_name"],
        )
    )

    best = reranked[0] if reranked else None
    runner_up = reranked[1] if len(reranked) > 1 else None
    margin = (
        best["final_score"] - runner_up["final_score"]
        if best is not None and runner_up is not None
        else None
    )

    comparison = {
        "best_entity_id": best["entity_id"] if best else None,
        "best_name": best["canonical_name"] if best else None,
        "best_score": best["final_score"] if best else None,
        "runner_up_entity_id": runner_up["entity_id"] if runner_up else None,
        "runner_up_name": runner_up["canonical_name"] if runner_up else None,
        "runner_up_score": runner_up["final_score"] if runner_up else None,
        "score_margin": margin,
    }

    return {
        "query": query,
        "candidate_limit": candidate_limit,
        "candidate_count": len(reranked),
        "comparison": comparison,
        "candidates": reranked,
    }


def database_metadata(database_path: Path) -> dict[str, str]:
    connection = sqlite3.connect(
        f"file:{database_path.resolve()}?mode=ro",
        uri=True,
    )
    try:
        return dict(connection.execute("SELECT key, value FROM metadata"))
    finally:
        connection.close()

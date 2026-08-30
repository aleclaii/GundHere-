"""Hybrid retrieval and Gunpla-specific reranking.

FTS5 and TF-IDF vectors are independent candidate generators. Their union is
deduplicated by canonical entity ID, hydrated from SQLite, and reranked by the
explainable Gunpla matcher. Raw BM25 and cosine scores are intentionally not
added together because they have incompatible scales.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from fuzzy import extract_gunpla_features, gunpla_match_score
from search_index import search_database
from vector_search import TfidfVectorIndex


RRF_K = 60


def _normalize_scale(scale: str | None) -> str | None:
    if scale is None or not scale.strip():
        return None
    scale = scale.strip()
    return f"1/{scale}" if scale.isdigit() else scale


def _eligible_entity_ids(
    database_path: Path,
    *,
    grade: str | None,
    scale: str | None,
    availability: str | None,
) -> set[str]:
    grade = grade.strip().upper() if grade and grade.strip() else None
    scale = _normalize_scale(scale)
    availability = availability.strip() if availability and availability.strip() else None

    connection = sqlite3.connect(
        f"file:{database_path.resolve()}?mode=ro",
        uri=True,
    )
    try:
        rows = connection.execute(
            """
            SELECT e.entity_id
            FROM entities e
            WHERE (? IS NULL OR e.grade = ?)
              AND (? IS NULL OR e.scale = ?)
              AND (
                    ? IS NULL OR EXISTS (
                        SELECT 1
                        FROM listings listing
                        WHERE listing.entity_id = e.entity_id
                          AND UPPER(listing.availability) = UPPER(?)
                    )
              )
            """,
            (grade, grade, scale, scale, availability, availability),
        )
        return {row[0] for row in rows}
    finally:
        connection.close()


def _load_entities(
    database_path: Path,
    entity_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if not entity_ids:
        return {}

    ordered_ids = sorted(entity_ids)
    placeholders = ",".join("?" for _ in ordered_ids)
    connection = sqlite3.connect(
        f"file:{database_path.resolve()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        entities = {
            row["entity_id"]: dict(row)
            for row in connection.execute(
                f"SELECT * FROM entities WHERE entity_id IN ({placeholders})",
                ordered_ids,
            )
        }

        listings: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in connection.execute(
            f"""
            SELECT * FROM listings
            WHERE entity_id IN ({placeholders})
            ORDER BY entity_id, price_usd IS NULL, price_usd, retailer
            """,
            ordered_ids,
        ):
            listings[row["entity_id"]].append(dict(row))

        parents: dict[str, list[str]] = defaultdict(list)
        for row in connection.execute(
            f"""
            SELECT child_entity_id, parent_entity_id
            FROM entity_relations
            WHERE child_entity_id IN ({placeholders})
            ORDER BY child_entity_id, parent_entity_id
            """,
            ordered_ids,
        ):
            parents[row["child_entity_id"]].append(row["parent_entity_id"])

        for entity_id, entity in entities.items():
            entity["listings"] = listings[entity_id]
            entity["parent_entity_ids"] = parents[entity_id]
        return entities
    finally:
        connection.close()


def hybrid_search_database(
    database_path: Path,
    query: str,
    *,
    grade: str | None = None,
    scale: str | None = None,
    availability: str | None = None,
    fts_limit: int = 20,
    vector_limit: int = 20,
    result_limit: int = 20,
    vector_index: TfidfVectorIndex | None = None,
) -> dict[str, Any]:
    """Union FTS5/vector candidates and rerank them with domain rules."""
    if not query.strip():
        raise ValueError("query must not be empty for hybrid search")
    for name, value in (
        ("fts_limit", fts_limit),
        ("vector_limit", vector_limit),
        ("result_limit", result_limit),
    ):
        if not 1 <= value <= 100:
            raise ValueError(f"{name} must be between 1 and 100")

    query_features = extract_gunpla_features(query)
    normalized_grade = grade.strip().upper() if grade and grade.strip() else None
    normalized_scale = _normalize_scale(scale)
    if (
        normalized_grade
        and query_features.grades
        and normalized_grade not in query_features.grades
    ):
        query_grades = ", ".join(sorted(query_features.grades))
        raise ValueError(
            f"Grade filter {normalized_grade} conflicts with {query_grades} in the query."
        )
    if (
        normalized_scale
        and query_features.scales
        and normalized_scale not in query_features.scales
    ):
        query_scales = ", ".join(sorted(query_features.scales))
        raise ValueError(
            f"Scale filter {normalized_scale} conflicts with {query_scales} in the query."
        )

    eligible_ids = _eligible_entity_ids(
        database_path,
        grade=grade,
        scale=scale,
        availability=availability,
    )

    fts_results = search_database(
        database_path,
        query,
        grade=grade,
        scale=scale,
        availability=availability,
        limit=fts_limit,
        match_any=True,
    )

    if vector_index is None:
        vector_index = TfidfVectorIndex.from_database(database_path)
    vector_results = vector_index.search(
        query,
        limit=vector_limit,
        allowed_entity_ids=eligible_ids,
    )

    fts_by_id = {
        candidate["entity_id"]: (position, candidate)
        for position, candidate in enumerate(fts_results, start=1)
    }
    vector_by_id = {
        candidate["entity_id"]: (position, candidate)
        for position, candidate in enumerate(vector_results, start=1)
    }
    candidate_ids = set(fts_by_id) | set(vector_by_id)
    entities = _load_entities(database_path, candidate_ids)

    candidates = []
    for entity_id in candidate_ids:
        entity = entities[entity_id]
        fts_hit = fts_by_id.get(entity_id)
        vector_hit = vector_by_id.get(entity_id)
        match = gunpla_match_score(entity["canonical_name"], query)

        retrieved_by = []
        rrf_score = 0.0
        if fts_hit:
            retrieved_by.append("fts5")
            rrf_score += 1 / (RRF_K + fts_hit[0])
        if vector_hit:
            retrieved_by.append("vector")
            rrf_score += 1 / (RRF_K + vector_hit[0])

        candidate = dict(entity)
        candidate.update(
            {
                "retrieved_by": retrieved_by,
                "fts_rank_position": fts_hit[0] if fts_hit else None,
                "fts_bm25": fts_hit[1]["rank"] if fts_hit else None,
                "vector_rank_position": vector_hit[0] if vector_hit else None,
                "vector_score": vector_hit[1]["vector_score"] if vector_hit else None,
                "rrf_score": rrf_score,
                "lexical_score": match["lexical"]["total"],
                "score_components": match["lexical"],
                "domain_adjustment": match["domain_adjustment"],
                "rejected": match["rejected"],
                "match_reasons": match["reasons"],
                "query_features": match["listing_features"],
                "candidate_features": match["canonical_features"],
                "final_score": match["final_score"],
            }
        )
        candidates.append(candidate)

    candidates.sort(
        key=lambda candidate: (
            -candidate["final_score"],
            -candidate["rrf_score"],
            candidate["canonical_name"],
        )
    )
    candidates = candidates[:result_limit]

    best = candidates[0] if candidates else None
    runner_up = candidates[1] if len(candidates) > 1 else None
    score_margin = (
        best["final_score"] - runner_up["final_score"]
        if best is not None and runner_up is not None
        else None
    )

    return {
        "query": query,
        "retrieval": {
            "fts_count": len(fts_results),
            "vector_count": len(vector_results),
            "union_count": len(candidate_ids),
            "returned_count": len(candidates),
        },
        "comparison": {
            "best_entity_id": best["entity_id"] if best else None,
            "best_name": best["canonical_name"] if best else None,
            "best_score": best["final_score"] if best else None,
            "runner_up_entity_id": runner_up["entity_id"] if runner_up else None,
            "runner_up_name": runner_up["canonical_name"] if runner_up else None,
            "runner_up_score": runner_up["final_score"] if runner_up else None,
            "score_margin": score_margin,
        },
        "candidates": candidates,
    }

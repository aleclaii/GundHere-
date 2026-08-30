"""Dependency-free TF-IDF vector retrieval for Gunpla entities.

This is the retrieval baseline, not yet a persisted vector index. It loads
canonical entities and aliases from SQLite, builds normalized sparse vectors in
memory, and ranks them with cosine similarity.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from fuzzy import normalize_gunpla_name
from search_index import DEFAULT_DATABASE


SparseVector = dict[str, float]


@dataclass(frozen=True)
class VectorDocument:
    entity_id: str
    canonical_name: str
    grade: str | None
    scale: str | None
    aliases: tuple[str, ...]

    @property
    def searchable_text(self) -> str:
        fields = [
            self.canonical_name,
            *self.aliases,
            self.grade or "",
            self.scale or "",
        ]
        return " ".join(dict.fromkeys(field for field in fields if field))


def _character_trigrams(token: str) -> Iterable[str]:
    padded = f"^{token}$"
    if len(padded) <= 3:
        yield padded
        return

    for index in range(len(padded) - 2):
        yield padded[index:index + 3]


def feature_counts(text: str) -> Counter[str]:
    """Create word and character-trigram features in separate namespaces."""
    normalized = normalize_gunpla_name(text)
    counts: Counter[str] = Counter()

    for token in normalized.split():
        counts[f"word:{token}"] += 1
        for trigram in _character_trigrams(token):
            counts[f"char:{trigram}"] += 1

    return counts


def load_vector_documents(database_path: Path) -> list[VectorDocument]:
    if not database_path.is_file():
        raise FileNotFoundError(
            f"Search database does not exist: {database_path}. Build it first."
        )

    connection = sqlite3.connect(
        f"file:{database_path.resolve()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        aliases_by_entity: dict[str, list[str]] = defaultdict(list)
        for row in connection.execute(
            "SELECT entity_id, alias FROM aliases ORDER BY entity_id, alias"
        ):
            aliases_by_entity[row["entity_id"]].append(row["alias"])

        documents = []
        for row in connection.execute(
            """
            SELECT entity_id, canonical_name, grade, scale
            FROM entities
            ORDER BY entity_id
            """
        ):
            documents.append(
                VectorDocument(
                    entity_id=row["entity_id"],
                    canonical_name=row["canonical_name"],
                    grade=row["grade"],
                    scale=row["scale"],
                    aliases=tuple(aliases_by_entity[row["entity_id"]]),
                )
            )
        return documents
    finally:
        connection.close()


class TfidfVectorIndex:
    """An educational in-memory sparse vector index."""

    def __init__(self, documents: list[VectorDocument]) -> None:
        if not documents:
            raise ValueError("at least one vector document is required")

        self.documents = documents
        self.document_frequency: Counter[str] = Counter()
        document_counts = []

        for document in documents:
            counts = feature_counts(document.searchable_text)
            document_counts.append(counts)
            self.document_frequency.update(counts.keys())

        document_total = len(documents)
        self.inverse_document_frequency = {
            feature: math.log(
                (1 + document_total) / (1 + frequency)
            ) + 1
            for feature, frequency in self.document_frequency.items()
        }
        self.vectors = [
            self._encode_counts(counts)
            for counts in document_counts
        ]

    @classmethod
    def from_database(cls, database_path: Path) -> "TfidfVectorIndex":
        return cls(load_vector_documents(database_path))

    @property
    def vocabulary_size(self) -> int:
        return len(self.inverse_document_frequency)

    def _encode_counts(self, counts: Counter[str]) -> SparseVector:
        weights = {}
        for feature, count in counts.items():
            inverse_frequency = self.inverse_document_frequency.get(feature)
            if inverse_frequency is None:
                continue

            term_frequency = 1 + math.log(count)
            weights[feature] = term_frequency * inverse_frequency

        magnitude = math.sqrt(sum(weight * weight for weight in weights.values()))
        if magnitude == 0:
            return {}
        return {
            feature: weight / magnitude
            for feature, weight in weights.items()
        }

    def encode_query(self, query: str) -> SparseVector:
        return self._encode_counts(feature_counts(query))

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        allowed_entity_ids: set[str] | None = None,
    ) -> list[dict[str, object]]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        query_vector = self.encode_query(query)
        if not query_vector:
            return []

        scored = []
        for document, document_vector in zip(self.documents, self.vectors):
            if (
                allowed_entity_ids is not None
                and document.entity_id not in allowed_entity_ids
            ):
                continue

            # Both vectors have L2 norm 1, so their dot product is cosine
            # similarity; iterating query features keeps the scan inexpensive.
            cosine = sum(
                query_weight * document_vector.get(feature, 0.0)
                for feature, query_weight in query_vector.items()
            )
            if cosine <= 0:
                continue

            scored.append(
                {
                    "entity_id": document.entity_id,
                    "canonical_name": document.canonical_name,
                    "grade": document.grade,
                    "scale": document.scale,
                    "vector_score": cosine,
                }
            )

        scored.sort(
            key=lambda result: (
                -result["vector_score"],
                result["canonical_name"],
            )
        )
        return scored[:limit]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search the TF-IDF Gunpla vectors.")
    parser.add_argument("query", nargs="+", help="Words to search for.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index = TfidfVectorIndex.from_database(args.database)
    query = " ".join(args.query)
    results = index.search(query, limit=args.limit)

    if args.json:
        print(
            json.dumps(
                {
                    "query": query,
                    "document_count": len(index.documents),
                    "vocabulary_size": index.vocabulary_size,
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    print(
        f"TF-IDF index: {len(index.documents)} entities, "
        f"{index.vocabulary_size} features"
    )
    for position, result in enumerate(results, start=1):
        print(
            f"{position}. {result['canonical_name']} "
            f"({result['vector_score']:.3f})"
        )


if __name__ == "__main__":
    main()

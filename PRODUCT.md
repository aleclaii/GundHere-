# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated from the existing project: a plain HTML/CSS/JavaScript client served
by Python's standard-library HTTP server. The search engine remains Python,
SQLite FTS5, and the dependency-free TF-IDF vector implementation. Docker is
the reproducible runtime and deployment boundary.

## Users

The primary user is a Gunpla hobbyist trying to find a specific physical kit,
including out-of-stock, Premium Bandai, variant, and unusually named releases.
They may remember only part of a name, mistype it, or confuse neighboring kits.

## Product Purpose

GundHere searches retailer and catalog names against canonical Gunpla entities.
Success means retrieving the intended kit, keeping materially different grades,
scales, variants, and accessories distinct, and making ambiguous matches clear.

## Positioning

The product combines catalog identity, FTS5 retrieval, typo-tolerant vector
retrieval, and Gunpla-specific rules instead of treating product titles as
generic web documents.

## Operating Context

Users enter a kit name or remembered fragments, optionally filter by grade,
scale, and availability, inspect ranked canonical results, compare confidence,
and follow available retailer listings. Maintainers rebuild the SQLite index
from reviewed CSV ground truth and use score explanations to diagnose errors.

## Capabilities and Constraints

- The authoritative catalog and reviewed relationships live in CSV data.
- SQLite FTS5 provides lexical candidate retrieval.
- TF-IDF word and character-trigram vectors provide typo-tolerant retrieval.
- The Gunpla scorer evaluates text, grade, scale, model code, variant, and
  product type, with hard rejection for impossible matches.
- SQLite is local and should not be concurrently rebuilt by multiple services.
- Crawling remains a separate, bounded job and is never triggered by a search.
- Prices and availability are displayed only when present in indexed listings.

## Evidence on Hand

The project contains 1,146 indexed canonical entities, reviewed ground-truth
records, retailer listings, reproducible SQLite builders, and automated search,
fuzzy, and vector tests. No testimonials, usage analytics, or performance claims
are available and none should be fabricated.

## Product Principles

- Identity correctness outranks superficial textual similarity.
- Retrieval should tolerate imperfect memory and spelling.
- Every ranking decision should remain inspectable.
- Missing data is shown as unknown, never invented.
- Generated indexes are reproducible from authoritative inputs.

## Accessibility & Inclusion

The web client must support keyboard operation, visible focus, semantic status
messages, responsive layouts, sufficient contrast, and reduced-motion settings.

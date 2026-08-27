# GundHere

GundHere is a small, domain-specific Gunpla search engine. It acquires public
retailer pages, parses listings offline, resolves retailer names to canonical
kit entities, and builds a local SQLite FTS5 search index.

## Pipeline

```text
HLJ public pages
  -> fetch.py
  -> data/raw/hlj/*.html
  -> parse_hlj.py
  -> data/processed/hlj_products.csv

Dalong catalog + P-Bandai listings + manual adjudications
  -> build_ground_truth.py
  -> data/processed/gunpla_ground_truth.csv
  -> build_search_index.py / search_index.py
  -> data/index/gundhere.sqlite3
  -> search.py
```

The raw HTML, parsed retailer listings, identity ground truth, and search index
are intentionally separate. Rebuilding an index never changes a matching
decision.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install requests beautifulsoup4
```

The SQLite search layer uses only Python's standard library. The bundled Python
must have SQLite FTS5 enabled; this can be checked with the test suite.

## Acquire and parse HLJ pages

Run a small, robots-aware crawl:

```bash
python3 fetch.py --max-products 5
```

Parse every saved HLJ product page without making network requests:

```bash
python3 parse_hlj.py
```

`fetch.py` is intentionally bounded and blocks account, cart, checkout, and
recommendation paths. Keep request volume low and re-check site rules before
expanding its scope.

## Build identity ground truth

```bash
python3 build_ground_truth.py
```

The long-form ground truth distinguishes:

- `EXACT_MATCH`: a retailer listing for an existing entity;
- `VARIANT_OF`: a distinct finish/color/configuration with a parent entity;
- `NEW_PRODUCT`: a kit absent from the current canonical catalog;
- `ACCESSORY`, `BUNDLE`, and `NON_KIT`: reviewed negative examples;
- `UNREVIEWED`: retained matcher output that cannot enter the index.

Only authoritative catalog rows and manually reviewed searchable relationships
receive an indexable `entity_id`.

## Build and query the SQLite index

```bash
python3 build_search_index.py
python3 search.py strike freedom titanium
python3 search.py gundam --grade RG --scale 144
python3 search.py strike freedom --availability "IN STOCK" --json
```

The CLI retrieves 20 broad FTS5 candidates by default, calculates the lexical
and Gunpla-specific score for every candidate, sorts them by final score, and
reports the best candidate, runner-up, and score margin. Use `--limit` to change
the candidate-pool size.

## Vector retrieval baseline

`vector_search.py` builds an in-memory sparse TF-IDF index over canonical names,
aliases, grades, and scales. It combines word features with character trigrams
and ranks all 1,146 entities using cosine similarity:

```bash
python3 vector_search.py RG 1/144 RX-93 Nu Gundma
python3 vector_search.py strike freedom titanium --json
```

This dependency-free baseline is intentionally brute-force. At the current
corpus size it is simple and fast, and it gives us retrieval measurements before
we persist vectors or adopt an approximate-nearest-neighbor dependency.

The builder writes `data/index/gundhere.sqlite3` atomically. Its normalized
schema contains:

- `source_records`: all input records and matching diagnostics;
- `entities`: one row per searchable kit identity;
- `entity_relations`: variant-to-parent relationships;
- `aliases`: retailer and catalog names for each entity;
- `listings`: retailer-specific price, availability, image, and URL;
- `entity_search`: FTS5 documents ranked with weighted BM25.

User input is tokenized into quoted prefix terms before reaching FTS5, so FTS
operators in a query cannot alter the SQL search expression.

## Tests

```bash
python3 -m unittest -v test_search_index.py
```

The tests verify expected row counts, SQLite integrity, exact-match listing
attachment, variant separation, negative-product exclusion, filters, metadata,
and punctuation handling.

## Fuzzy reranking and planned semantic search

FTS5 performs broad candidate generation while the fuzzy layer reranks those
candidates using edit, token, trigram, grade, scale, model-code, variant, and
product-type evidence. The authoritative index builder remains separate and
never changes a matching decision. Only high-precision decisions should be
accepted automatically; small best-versus-runner-up margins belong in a review
queue.

Vector search can later add semantic candidates using one embedding per entity.
Hybrid ranking should combine FTS5/BM25, fuzzy similarity, and vector distance,
while exact model codes, grade, scale, and variant constraints remain hard
signals. FTS5 remains the default until semantic retrieval demonstrates a
measurable improvement on the reviewed ground-truth set.

## Older experiments

`crawler.py`, `test.html`, and `candidate-links.csv` are early offline link
extraction experiments. `Shelve/` contains paused API experiments. They are not
part of the current production pipeline.

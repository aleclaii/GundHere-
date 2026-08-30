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

Normal searches are hybrid by default: the engine unions FTS5 and TF-IDF vector
candidates, deduplicates canonical entity IDs, and applies the explainable
Gunpla scorer. Retrieval scores remain diagnostic signals rather than being
added directly because BM25 and cosine use incompatible scales.

## Browser client

Build the index, start the local server, and open `http://127.0.0.1:8000`:

```bash
python3 build_search_index.py
python3 server.py
```

The FastAPI application caches the TF-IDF vectors at startup, exposes
`/api/search` and `/api/health`, and serves the dependency-free
HTML/CSS/JavaScript client through Uvicorn. With Docker Compose:

```bash
docker compose run --rm index
docker compose up web
```

The production image builds an immutable SQLite index, runs as an unprivileged
user, and contains only the search runtime and client. Crawling and parsing stay
in the separate development image and are never invoked by a public request.

## Production security

The API enforces strict grade, scale, availability, result-count, query-length,
and request-target limits. A per-client token bucket limits search bursts, while
a semaphore and timeout bound concurrent search work. JSON request logs include
a generated request ID, route, status, and duration without recording the search
query. Unexpected exceptions are logged server-side and return a generic error.

SQLite connections use read-only mode plus `PRAGMA query_only`. The browser
response includes a restrictive Content Security Policy, clickjacking, MIME,
referrer, permissions, opener, and production HSTS headers. FastAPI's interactive
documentation is disabled on the public application.

Important environment variables:

- `RATE_LIMIT_CAPACITY` (default `20`)
- `RATE_LIMIT_REFILL_PER_SECOND` (default `0.5`)
- `MAXIMUM_CONCURRENT_SEARCHES` (default `8`)
- `SEARCH_TIMEOUT_SECONDS` (default `5`)
- `MAXIMUM_REQUEST_TARGET_BYTES` (default `2048`)
- `ALLOWED_HOSTS` (comma-separated custom domains)
- `TRUST_PROXY_HEADERS` (set only behind a trusted hosting proxy)

## Deploy to Render

The checked-in `render.yaml` defines a free Docker web service, an HTTP health
check, and the production limits. After pushing the repository, choose
**New → Blueprint** in Render, connect the repository, and deploy the Blueprint.
Render supplies `PORT` and `RENDER_EXTERNAL_HOSTNAME`; the application uses both.
Add every custom domain to `ALLOWED_HOSTS` before directing traffic to it.

Raw retailer responses under `data/raw/` remain local and are ignored by Git.
The reviewed ground-truth CSV is the only catalog input copied into the public
container.

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
python3 -m unittest -v
```

The tests verify expected row counts, SQLite integrity, exact-match listing
attachment, variant separation, negative-product exclusion, filters, metadata,
punctuation handling, API validation, rate limiting, security headers, generic
error responses, and structured logging.

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

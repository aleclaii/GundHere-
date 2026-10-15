# GundHere

GundHere is a domain-specific search engine for Gunpla (Gundam plastic model)
kits. It is designed to help hobbyists find the intended kit when product
names differ across catalogs and retailer listings, or when a query contains
only part of a name, a typo, or kit-specific details such as grade and scale.

The search pipeline stores canonical kit identities and aliases in SQLite. It
uses SQLite FTS5 for lexical retrieval, a lightweight TF-IDF model with word
and character features for typo-tolerant candidates, and Gunpla-specific
ranking rules to consider model codes, grade, scale, and variants. A Python
API serves the results to a small HTML, CSS, and JavaScript client.

## Technology

- Python, FastAPI, and Uvicorn for the search API
- SQLite with FTS5 for the catalog and full-text index
- A dependency-light TF-IDF vector search and explainable ranking layer
- Plain HTML, CSS, and JavaScript for the browser client
- Docker for a reproducible runtime

This is an independent hobby project and is not affiliated with Bandai or any
retailer.

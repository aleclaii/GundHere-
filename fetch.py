"""A small, robots-aware crawler for public HobbyLink Japan pages.

It downloads one search/category page, discovers likely Gunpla product links,
and downloads a small bounded number of those pages. It never logs in, uses a
cart, follows pagination, or accesses account and recommendation endpoints.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


SEED_URL = (
    "https://www.hlj.com/search/"
    "?Word=gundam&GenreCode2=Gundam&Page=2&MacroType2=Gundam+Kits&Sort=rss+desc&MacroType2=High+Grade+Kits&MacroType2=Master+Grade+Kits&MacroType2=Perfect+Grade+Kits&MacroType2=Real+Grade+Kits&StockLevel=In%C2%A0Stock"
)
OUTPUT_DIR = Path("data/raw/hlj")
USER_AGENT = (
    "GundHereBot/0.1 "
    "(noncommercial student Gunpla search engine project)"
)
ALLOWED_HOSTS = {"hlj.com", "www.hlj.com"}
NEVER_CRAWL_PATHS = (
    "/account",
    "/cart",
    "/checkout",
    "/relatedproducts",
    "/recommendproducts",
)
GRADE_PATTERN = re.compile(
    r"(?<![A-Z0-9])"
    r"(HG(?:UC|CE|AC|FC|AW|BD|IBO)?|MG(?:EX|SD)?|RG|PG|"
    r"HIGH GRADE|MASTER GRADE|REAL GRADE|PERFECT GRADE)"
    r"(?![A-Z0-9])",
    re.IGNORECASE,
)
MIN_DELAY_SECONDS = 5.0


def canonicalize_url(base_url: str, href: str) -> str | None:
    """Resolve a link and keep only URLs belonging to HLJ."""
    parts = urlsplit(urljoin(base_url, href))
    if parts.scheme not in {"http", "https"}:
        return None
    if (parts.hostname or "").lower() not in ALLOWED_HOSTS:
        return None
    return urlunsplit(("https", "www.hlj.com", parts.path, parts.query, ""))


def is_never_crawl_path(url: str) -> bool:
    """Apply stricter local rules even where robots.txt has an exception."""
    path = urlsplit(url).path.lower()
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in NEVER_CRAWL_PATHS
    )


def identify_grade(text: str) -> str | None:
    match = GRADE_PATTERN.search(text)
    if not match:
        return None

    value = match.group(1).upper()
    if value.startswith("HG") or value == "HIGH GRADE":
        return "HG"
    if value.startswith("MG") or value == "MASTER GRADE":
        return "MG"
    if value in {"RG", "REAL GRADE"}:
        return "RG"
    if value in {"PG", "PERFECT GRADE"}:
        return "PG"
    return None


def fetch_robots(session: requests.Session) -> tuple[RobotFileParser, float]:
    """Fetch robots.txt; stop the crawl if it cannot be checked."""
    robots_url = "https://www.hlj.com/robots.txt"
    print(f"Checking crawler rules: {robots_url}")
    response = session.get(robots_url, timeout=20)
    response.raise_for_status()

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())

    crawl_delay = parser.crawl_delay(USER_AGENT)
    if crawl_delay is None:
        crawl_delay = parser.crawl_delay("*")
    return parser, float(crawl_delay or 0)


def assert_allowed(robots: RobotFileParser, url: str) -> None:
    if is_never_crawl_path(url):
        raise PermissionError(f"Blocked by our crawler policy: {url}")
    if not robots.can_fetch(USER_AGENT, url):
        raise PermissionError(f"Blocked by robots.txt: {url}")


def fetch_html(session: requests.Session, url: str) -> requests.Response:
    """Fetch one HTML document without automatic retries."""
    print(f"Requesting: {url}")
    response = session.get(
        url,
        headers={"Accept": "text/html,application/xhtml+xml"},
        timeout=30,
        allow_redirects=True,
    )
    print(f"Status: {response.status_code}")
    print(f"Final URL: {response.url}")
    print(f"Downloaded: {len(response.content)} bytes")
    response.raise_for_status()

    final_host = (urlsplit(response.url).hostname or "").lower()
    if final_host not in ALLOWED_HOSTS:
        raise ValueError(f"Redirected outside HLJ: {response.url}")

    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        raise ValueError(f"Expected HTML but received {content_type!r}")
    return response


def discover_product_links(
    html: str,
    page_url: str,
    robots: RobotFileParser,
) -> list[dict[str, str]]:
    """Extract same-site links that look like graded Gunpla products."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[str, dict[str, str]] = {}

    for anchor in soup.find_all("a", href=True):
        link_text = anchor.get_text(" ", strip=True)
        url = canonicalize_url(page_url, anchor.get("href", "").strip())
        if not url or is_never_crawl_path(url):
            continue
        if urlsplit(url).path in {"", "/", "/search", "/search/"}:
            continue

        grade = identify_grade(f"{link_text} {urlsplit(url).path}")
        if not grade or not robots.can_fetch(USER_AGENT, url):
            continue

        # Product-page query strings are normally tracking parameters.
        parts = urlsplit(url)
        clean_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path.rstrip("/"), "", "")
        )
        candidates[clean_url] = {
            "url": clean_url,
            "link_text": link_text,
            "matched_grade": grade,
        }

    return sorted(candidates.values(), key=lambda row: row["url"])


def safe_filename(url: str, timestamp: str) -> str:
    slug = urlsplit(url).path.strip("/") or "page"
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-")
    return f"{slug[:120]}-{timestamp}.html"


def save_response(
    response: requests.Response,
    destination: Path,
) -> dict[str, object]:
    destination.write_bytes(response.content)
    return {
        "requested_url": response.request.url,
        "final_url": response.url,
        "status": response.status_code,
        "content_type": response.headers.get("Content-Type"),
        "bytes": len(response.content),
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "file": str(destination),
    }


def write_candidates(rows: list[dict[str, str]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["url", "link_text", "matched_grade"],
        )
        writer.writeheader()
        writer.writerows(rows)


def bounded_product_count(value: str) -> int:
    count = int(value)
    if not 0 <= count <= 20:
        raise argparse.ArgumentTypeError("must be between 0 and 20")
    return count


def polite_delay(value: str) -> float:
    delay = float(value)
    if delay < MIN_DELAY_SECONDS:
        raise argparse.ArgumentTypeError("must be at least 5 seconds")
    return delay


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a bounded set of public HLJ Gunpla pages."
    )
    parser.add_argument("--seed", default=SEED_URL)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--max-products",
        type=bounded_product_count,
        default=5,
        help="Number of product pages to fetch, between 0 and 20 (default: 5).",
    )
    parser.add_argument(
        "--delay",
        type=polite_delay,
        default=MIN_DELAY_SECONDS,
        help="Seconds between page requests; minimum and default are 5.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_url = canonicalize_url("https://www.hlj.com", args.seed)
    if not seed_url:
        raise SystemExit("The seed URL must belong to hlj.com.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest: dict[str, object] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "seed_url": seed_url,
        "user_agent": USER_AGENT,
        "pages": [],
        "errors": [],
    }
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    try:
        robots, robots_delay = fetch_robots(session)
        delay = max(args.delay, robots_delay)
        manifest["delay_seconds"] = delay
        assert_allowed(robots, seed_url)

        seed_response = fetch_html(session, seed_url)
        seed_path = args.output_dir / f"seed-{timestamp}.html"
        manifest["pages"].append(save_response(seed_response, seed_path))

        candidates = discover_product_links(
            seed_response.text,
            seed_response.url,
            robots,
        )
        candidates_path = args.output_dir / f"candidates-{timestamp}.csv"
        write_candidates(candidates, candidates_path)
        print(f"Discovered {len(candidates)} candidate product links")

        for candidate in candidates[: args.max_products]:
            time.sleep(delay)
            product_url = candidate["url"]
            assert_allowed(robots, product_url)

            try:
                response = fetch_html(session, product_url)
                page_path = args.output_dir / safe_filename(product_url, timestamp)
                manifest["pages"].append(save_response(response, page_path))
            except requests.HTTPError as error:
                status = error.response.status_code if error.response else None
                manifest["errors"].append(
                    {"url": product_url, "status": status, "error": str(error)}
                )
                if status in {403, 429}:
                    print(f"Stopping after server response {status}.")
                    break
            except (requests.RequestException, ValueError) as error:
                manifest["errors"].append(
                    {"url": product_url, "error": str(error)}
                )

    except (requests.RequestException, PermissionError, ValueError) as error:
        manifest["errors"].append({"url": seed_url, "error": str(error)})
        print(f"Crawl stopped: {error}")
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path = args.output_dir / f"manifest-{timestamp}.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        session.close()
        print(f"Saved crawl manifest to {manifest_path}")


if __name__ == "__main__":
    main()

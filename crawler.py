import csv
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup


GRADE_PATTERN = re.compile(
    r"(?<![A-Z0-9])"
    r"(HG(?:UC|CE|AC|FC)?|MG(?:EX)?|RG|PG|"
    r"HIGH GRADE|MASTER GRADE|REAL GRADE|PERFECT GRADE)"
    r"(?![A-Z0-9])",
    re.IGNORECASE,
)


def normalize_url(base_url: str, href: str) -> str:
    absolute_url = urljoin(base_url, href)
    parts = urlsplit(absolute_url)

    # Fragments such as #reviews do not identify a different product.
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc.lower(),
            parts.path,
            parts.query,
            "",
        )
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
    if value == "RG" or value == "REAL GRADE":
        return "RG"
    if value == "PG" or value == "PERFECT GRADE":
        return "PG"

    return None


def extract_candidate_links(
    html: str,
    base_url: str,
) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results_by_url = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        link_text = anchor.get_text(" ", strip=True)

        if not href:
            continue

        url = normalize_url(base_url, href)
        evidence = f"{link_text} {url}"
        grade = identify_grade(evidence)

        if not grade:
            continue

        results_by_url[url] = {
            "url": url,
            "link_text": link_text,
            "matched_grade": grade,
        }

    return sorted(
        results_by_url.values(),
        key=lambda row: row["url"],
    )


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["url", "link_text", "matched_grade"],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    input_path = Path("test.html")
    output_path = Path("candidate-links.csv")

    html = input_path.read_text(encoding="utf-8")

    rows = extract_candidate_links(
        html=html,
        base_url="https://p-bandai.com",
    )

    write_csv(rows, output_path)
    print(f"Wrote {len(rows)} candidate links to {output_path}")


if __name__ == "__main__":
    main()
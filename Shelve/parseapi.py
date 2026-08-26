import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


BASE_URL = (
    "https://api.parse.bot/scraper/"
    "ea02a033-95e2-40f9-89c9-4c13960430ec"
)


def search_products(query: str, page: int = 1) -> dict:
    api_key = os.environ.get("PARSE_API_KEY")

    if not api_key:
        raise RuntimeError("PARSE_API_KEY is not set")

    response = requests.get(
        f"{BASE_URL}/search_products",
        headers={"X-API-Key": api_key},
        params={
            "query": query,
            "page": page,
        },
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def save_snapshot(response_data: dict) -> Path:
    output_directory = Path("data/raw/pbandai_jp")
    output_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_directory / f"gundam-page-1-{timestamp}.json"

    output_path.write_text(
        json.dumps(response_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_path

def search_new_products(page: int = 1) -> dict:
    api_key = os.environ.get("PARSE_API_KEY")

    response = requests.get(
        f"{BASE_URL}/search_new_products",
        headers={"X-API-Key": api_key},
        params={"page": page},
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def main() -> None:
    result = search_new_products(page=1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
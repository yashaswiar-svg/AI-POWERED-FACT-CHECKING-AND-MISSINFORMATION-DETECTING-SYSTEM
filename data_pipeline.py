"""
Unified data ingestion pipeline for offline evidence retrieval.

Sources:
- Wikipedia via HuggingFace datasets (1% split from 20220301.en)
- arXiv via arxiv Python library (query: artificial intelligence)
- Kaggle via kaggle API (dataset name optional input)

Output:
- data/documents.json with standardized records:
  {
    "title": str,
    "content": str,
    "source": str,
    "link": str
  }

Python: 3.10+
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any


MAX_CONTENT_CHARS = 1000
MIN_CONTENT_CHARS = 50
MAX_KAGGLE_DOCS = 500
DEFAULT_OUTPUT_PATH = Path("data/documents.json")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _wiki_link_from_title(title: str) -> str:
    slug = title.strip().replace(" ", "_")
    return f"https://en.wikipedia.org/wiki/{slug}" if slug else ""


def _normalize_for_dedupe(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _truncate(text: str, max_len: int = MAX_CONTENT_CHARS) -> str:
    return text[:max_len].strip()


def load_wikipedia(percent: int = 1) -> list[dict[str, str]]:
    """Load 1% of English Wikipedia from HuggingFace datasets."""
    if percent <= 0 or percent > 100:
        raise ValueError("Wikipedia percent must be between 1 and 100.")

    try:
        datasets_module = importlib.import_module("datasets")
        load_dataset = datasets_module.load_dataset
        load_dataset_builder = datasets_module.load_dataset_builder
    except Exception as exc:
        raise RuntimeError(
            "Missing dependency 'datasets'. Install with: pip install datasets"
        ) from exc

    try:
        builder = load_dataset_builder(
            "wikipedia",
            "20220301.en",
            trust_remote_code=True,
        )
        total_train = int(builder.info.splits["train"].num_examples)
        target_count = max(1, (total_train * percent) // 100)

        dataset = load_dataset(
            "wikipedia",
            "20220301.en",
            split="train",
            streaming=True,
            trust_remote_code=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to download/load Wikipedia dataset: {exc}") from exc

    records: list[dict[str, str]] = []
    for row in dataset:
        title = _safe_text(row.get("title"))
        content = _safe_text(row.get("text")) or _safe_text(row.get("content"))
        link = (
            _safe_text(row.get("url"))
            or _safe_text(row.get("source"))
            or _wiki_link_from_title(title)
        )

        if not title or not content:
            continue

        records.append(
            {
                "title": title,
                "content": content,
                "source": "wikipedia",
                "link": link,
            }
        )
        if len(records) >= target_count:
            break

    print(
        f"[pipeline] Wikipedia target count: {target_count} "
        f"({percent}% of {total_train})"
    )
    return records


def load_arxiv(query: str = "artificial intelligence", max_results: int = 200) -> list[dict[str, str]]:
    """Load arXiv papers for the given query."""
    try:
        arxiv = importlib.import_module("arxiv")
    except Exception as exc:
        raise RuntimeError("Missing dependency 'arxiv'. Install with: pip install arxiv") from exc

    try:
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)
        results = client.results(search)

        records: list[dict[str, str]] = []
        for paper in results:
            records.append(
                {
                    "title": _safe_text(getattr(paper, "title", "")),
                    "content": _safe_text(getattr(paper, "summary", "")),
                    "source": "arxiv",
                    "link": _safe_text(getattr(paper, "entry_id", ""))
                    or _safe_text(getattr(paper, "pdf_url", "")),
                }
            )
        return records
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch arXiv data: {exc}") from exc


def _kaggle_credentials_available() -> bool:
    """Check if Kaggle auth is available via env vars or kaggle.json."""
    if os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"):
        return True

    candidate_paths = [
        Path.home() / ".kaggle" / "kaggle.json",
        Path.cwd() / "kaggle.json",
        Path.cwd() / ".kaggle" / "kaggle.json",
    ]
    return any(path.exists() for path in candidate_paths)


def _extract_text_from_row(row: dict[str, Any]) -> tuple[str, str]:
    """Pick likely title/content fields from a CSV row."""
    title_keys = ["title", "headline", "name", "question", "subject"]
    content_keys = [
        "content",
        "text",
        "body",
        "description",
        "abstract",
        "summary",
        "answer",
    ]

    title = ""
    content = ""

    lowered = {str(k).lower(): v for k, v in row.items()}

    for key in title_keys:
        if key in lowered and _safe_text(lowered[key]):
            title = _safe_text(lowered[key])
            break

    for key in content_keys:
        if key in lowered and _safe_text(lowered[key]):
            content = _safe_text(lowered[key])
            break

    # Fallback: synthesize from row when explicit content key is missing.
    if not content:
        pieces = []
        for key, value in row.items():
            v = _safe_text(value)
            if v:
                pieces.append(f"{key}: {v}")
        content = " | ".join(pieces)

    if not title:
        title = _safe_text(row.get("id")) or "Kaggle Record"

    return title, content


def load_kaggle(dataset_name: str | None = None) -> list[dict[str, str]]:
    """Download and parse a Kaggle dataset into standardized records."""
    if not dataset_name:
        return []

    if not _kaggle_credentials_available():
        raise RuntimeError(
            "Kaggle credentials not found. Configure ~/.kaggle/kaggle.json "
            "or set KAGGLE_USERNAME and KAGGLE_KEY environment variables."
        )

    try:
        kaggle_api_module = importlib.import_module("kaggle.api.kaggle_api_extended")
        KaggleApi = kaggle_api_module.KaggleApi
    except Exception as exc:
        raise RuntimeError("Missing dependency 'kaggle'. Install with: pip install kaggle") from exc

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        try:
            api = KaggleApi()
            api.authenticate()
            api.dataset_download_files(dataset_name, path=str(tmp_path), unzip=True, quiet=True)
        except Exception as exc:
            raise RuntimeError(f"Failed to download Kaggle dataset '{dataset_name}': {exc}") from exc

        records: list[dict[str, str]] = []

        # Parse CSV and JSON files from extracted dataset.
        for file_path in tmp_path.rglob("*"):
            if not file_path.is_file():
                continue

            suffix = file_path.suffix.lower()
            if suffix == ".csv":
                try:
                    with file_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
                        reader = csv.DictReader(handle)
                        for row in reader:
                            if len(records) >= MAX_KAGGLE_DOCS:
                                break
                            title, content = _extract_text_from_row(row)
                            records.append(
                                {
                                    "title": title,
                                    "content": content,
                                    "source": f"kaggle:{dataset_name}",
                                    "link": "",
                                }
                            )
                except Exception:
                    continue

            elif suffix == ".json":
                try:
                    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                        raw = json.load(handle)

                    if isinstance(raw, list):
                        for item in raw:
                            if len(records) >= MAX_KAGGLE_DOCS:
                                break
                            if isinstance(item, dict):
                                title, content = _extract_text_from_row(item)
                                records.append(
                                    {
                                        "title": title,
                                        "content": content,
                                        "source": f"kaggle:{dataset_name}",
                                        "link": "",
                                    }
                                )
                except Exception:
                    continue

            if len(records) >= MAX_KAGGLE_DOCS:
                break

        return records


def clean_data(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Clean and normalize merged records:
    - remove short/empty content
    - truncate content to 1000 chars
    - remove duplicates by title OR content
    """
    cleaned: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    seen_contents: set[str] = set()

    for item in records:
        title = _safe_text(item.get("title"))
        content = _safe_text(item.get("content"))
        source = _safe_text(item.get("source"))
        link = _safe_text(item.get("link"))

        if not content or len(content) < MIN_CONTENT_CHARS:
            continue

        content = _truncate(content)

        title_key = _normalize_for_dedupe(title)
        content_key = _normalize_for_dedupe(content)

        if title_key and title_key in seen_titles:
            continue
        if content_key in seen_contents:
            continue

        if title_key:
            seen_titles.add(title_key)
        seen_contents.add(content_key)

        cleaned.append(
            {
                "title": title or "Untitled",
                "content": content,
                "source": source or "unknown",
                "link": link,
            }
        )

    return cleaned


def save_data(records: list[dict[str, str]], output_path: Path = DEFAULT_OUTPUT_PATH) -> None:
    """Persist cleaned records for downstream FAISS indexing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)


def run_ingestion_once(kaggle_dataset: str | None, output_path: Path) -> None:
    """Run one full ingestion cycle and persist output."""
    print("[pipeline] Starting dataset ingestion...")

    all_records: list[dict[str, str]] = []
    source_counts = {"wikipedia": 0, "arxiv": 0, "kaggle": 0}

    # Wikipedia
    try:
        wiki_records = load_wikipedia(percent=1)
        source_counts["wikipedia"] = len(wiki_records)
        all_records.extend(wiki_records)
        print(f"[pipeline] Wikipedia collected: {len(wiki_records)}")
    except Exception as exc:
        print(f"[pipeline][warn] Wikipedia ingestion failed: {exc}")

    # arXiv
    try:
        arxiv_records = load_arxiv(query="artificial intelligence", max_results=200)
        source_counts["arxiv"] = len(arxiv_records)
        all_records.extend(arxiv_records)
        print(f"[pipeline] arXiv collected: {len(arxiv_records)}")
    except Exception as exc:
        print(f"[pipeline][warn] arXiv ingestion failed: {exc}")

    # Kaggle (optional)
    try:
        kaggle_records = load_kaggle(dataset_name=kaggle_dataset)
        source_counts["kaggle"] = len(kaggle_records)
        all_records.extend(kaggle_records)
        if kaggle_dataset:
            print(f"[pipeline] Kaggle collected: {len(kaggle_records)} from {kaggle_dataset}")
    except Exception as exc:
        print(f"[pipeline][warn] Kaggle ingestion failed: {exc}")

    cleaned = clean_data(all_records)
    save_data(cleaned, output_path)

    print("[pipeline] ---- Summary ----")
    print(f"[pipeline] Source counts: {source_counts}")
    print(f"[pipeline] Total raw records: {len(all_records)}")
    print(f"[pipeline] Total cleaned records: {len(cleaned)}")
    print(f"[pipeline] Saved output to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unified offline evidence dataset")
    parser.add_argument(
        "--kaggle-dataset",
        type=str,
        default=None,
        help="Optional Kaggle dataset in owner/name format",
    )
    parser.add_argument(
        "--refresh-interval-hours",
        type=float,
        default=0.0,
        help="Optional refresh interval in hours (0 = run once and exit)",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Optional max number of refresh cycles (0 = unlimited when refresh enabled)",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=str(DEFAULT_OUTPUT_PATH),
        help="Output JSON path (default: data/documents.json)",
    )
    args = parser.parse_args()

    output_path = Path(args.output_path)
    interval_hours = max(0.0, float(args.refresh_interval_hours))

    if interval_hours == 0.0:
        run_ingestion_once(args.kaggle_dataset, output_path)
        return

    sleep_seconds = int(interval_hours * 3600)
    cycle = 0
    print(
        "[pipeline] Refresh mode enabled: "
        f"interval={interval_hours}h, max_cycles={args.max_cycles or 'unlimited'}"
    )

    try:
        while True:
            cycle += 1
            print(f"[pipeline] ===== Cycle {cycle} =====")
            run_ingestion_once(args.kaggle_dataset, output_path)

            if args.max_cycles > 0 and cycle >= args.max_cycles:
                print("[pipeline] Reached max cycles. Exiting.")
                break

            print(f"[pipeline] Sleeping for {sleep_seconds} seconds before next refresh...")
            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        print("\n[pipeline] Stopped by user.")


if __name__ == "__main__":
    main()

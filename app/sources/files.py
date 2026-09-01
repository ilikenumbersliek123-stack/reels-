"""CSV / JSON / JSONL ingestion.

This is the source that always works. Whatever tool you end up using to collect
reel data — a scraping service, a spreadsheet you fill in by hand, an export
from a social analytics product — get it to CSV and this reads it. Column names
do not need to match; see sources/base.py ALIASES.
"""

from __future__ import annotations

import csv
import json
from typing import Any

from .base import normalize_many


def read_csv(path: str, source: str | None = None) -> list[dict[str, Any]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return normalize_many(rows, source=source or f"csv:{path}")


def read_json(path: str, source: str | None = None) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        text = fh.read().strip()

    records: list[dict[str, Any]]
    if text.startswith("["):
        records = json.loads(text)
    elif text.startswith("{"):
        blob = json.loads(text)
        # Accept {"data": [...]}, {"items": [...]}, {"results": [...]} or a lone record.
        for key in ("data", "items", "results", "reels", "media"):
            if isinstance(blob.get(key), list):
                records = blob[key]
                break
        else:
            records = [blob]
    else:  # JSONL
        records = [json.loads(line) for line in text.splitlines() if line.strip()]

    return normalize_many(records, source=source or f"json:{path}")


def read_any(path: str) -> list[dict[str, Any]]:
    return read_csv(path) if path.lower().endswith(".csv") else read_json(path)

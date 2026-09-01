"""Turn free text into tags so patterns become countable.

A leaderboard on its own tells you which reels won. Tags are what let you ask
the useful question — "do gear reveals out-perform DJ cams for accounts under
5k?" — and get a number back instead of a vibe.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Iterable

TAXONOMY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "taxonomy.json")


@lru_cache(maxsize=1)
def load_taxonomy(path: str = TAXONOMY_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[str, str, re.Pattern[str]]]:
    out = []
    for tag, spec in load_taxonomy()["tags"].items():
        alternatives = sorted(spec["keywords"], key=len, reverse=True)
        pattern = "|".join(re.escape(k) for k in alternatives)
        # \b fails against keywords ending in punctuation (e.g. "nobody:"), so
        # only anchor the edges that are word characters.
        out.append((tag, spec["kind"], re.compile(rf"(?<!\w)(?:{pattern})", re.IGNORECASE)))
    return out


def duration_tag(duration_s: float | None) -> str | None:
    if duration_s is None:
        return None
    for low, high, label in load_taxonomy()["duration_buckets"]:
        if low <= duration_s < high:
            return label
    return None


def tags_for(reel: dict[str, Any]) -> list[tuple[str, str]]:
    """Return [(tag, kind), ...] for one reel."""
    haystack = " ".join(
        str(reel.get(field) or "") for field in ("caption", "audio_name", "author_name")
    )
    found = [(tag, kind) for tag, kind, rx in _compiled() if rx.search(haystack)]

    bucket = duration_tag(reel.get("duration_s"))
    if bucket:
        found.append((bucket, "length"))

    hashtags = re.findall(r"#(\w{2,30})", haystack)
    for tag in hashtags[:12]:
        found.append((f"tag:{tag.lower()}", "hashtag"))

    return found


def retag_all(conn, reels: Iterable[dict[str, Any]] | None = None) -> int:
    from . import db

    rows = reels if reels is not None else [dict(r) for r in db.all_reels(conn)]
    count = 0
    for reel in rows:
        db.replace_tags(conn, reel["id"], tags_for(reel))
        count += 1
    return count

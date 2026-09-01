"""Normalisation shared by every ingestion source.

Every provider names things differently — `videoPlayCount`, `play_count`,
`plays`, `video_view_count` — so all of them funnel through `normalize()` and
the rest of the app only ever sees one shape.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable

ALIASES: dict[str, tuple[str, ...]] = {
    "id": ("id", "shortcode", "short_code", "code", "pk", "media_id", "post_id"),
    "url": ("url", "permalink", "link", "post_url", "permalink_url"),
    "handle": ("handle", "username", "owner_username", "ownerUsername", "account", "user"),
    "author_name": ("author_name", "full_name", "ownerFullName", "name", "display_name"),
    "followers": ("followers", "follower_count", "followers_count", "ownerFollowers", "followersCount"),
    "posted_at": ("posted_at", "timestamp", "taken_at", "takenAt", "created_at", "date", "publish_date"),
    "duration_s": ("duration_s", "duration", "video_duration", "videoDuration", "length"),
    "views": ("views", "play_count", "plays", "video_view_count", "videoPlayCount", "video_play_count", "view_count", "reach"),
    "likes": ("likes", "like_count", "likesCount", "likes_count", "edge_liked_by"),
    "comments": ("comments", "comment_count", "commentsCount", "comments_count"),
    "shares": ("shares", "share_count", "reshare_count", "sharesCount", "sends"),
    "saves": ("saves", "save_count", "saved", "savesCount", "bookmarks"),
    "caption": ("caption", "text", "edge_media_to_caption", "title", "description"),
    "audio_name": ("audio_name", "music_title", "audio", "song", "musicInfo", "original_sound"),
    "audio_id": ("audio_id", "music_id", "audio_cluster_id"),
}

REQUIRED_NUMERIC = ("followers", "views", "likes", "comments", "shares", "saves")


def _pick(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
        # tolerate snake/camel drift and nesting like {"owner": {"username": ...}}
        for actual, value in record.items():
            if actual.lower().replace("_", "") == key.lower().replace("_", "") and value not in (None, ""):
                return value
    return None


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(",", "").replace(" ", "")
    multiplier = 1
    if text.endswith("k"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000, text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"(\d+(?:\.\d+)?)", str(value))
        return float(match.group(1)) if match else None


def _to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        seconds = float(value)
        if seconds > 1e11:  # milliseconds
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    text = str(value).strip().replace("Z", "+00:00")
    for parse in (
        lambda t: datetime.fromisoformat(t),
        lambda t: datetime.strptime(t, "%Y-%m-%d %H:%M:%S"),
        lambda t: datetime.strptime(t, "%Y-%m-%d"),
        lambda t: datetime.strptime(t, "%d/%m/%Y"),
    ):
        try:
            dt = parse(text)
        except (ValueError, TypeError):
            continue
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()
    return None


def _flatten_caption(value: Any) -> str:
    """Instagram's GraphQL shape buries the caption a few levels down."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        edges = value.get("edges")
        if isinstance(edges, list) and edges:
            node = edges[0].get("node", {})
            return str(node.get("text", ""))
        return str(value.get("text", ""))
    if isinstance(value, list) and value:
        return _flatten_caption(value[0])
    return ""


def normalize(record: dict[str, Any], source: str = "manual", is_sample: bool = False) -> dict[str, Any] | None:
    """Map one provider record onto the reels schema. Returns None if unusable."""
    out: dict[str, Any] = {}
    for field, keys in ALIASES.items():
        out[field] = _pick(record, keys)

    out["caption"] = _flatten_caption(out.get("caption")) or ""
    out["audio_name"] = str(out.get("audio_name") or "")
    out["audio_id"] = str(out.get("audio_id") or "")
    out["handle"] = str(out.get("handle") or "").lstrip("@").lower() or None
    out["author_name"] = str(out.get("author_name") or "")
    out["posted_at"] = _to_iso(out.get("posted_at"))
    out["duration_s"] = _to_float(out.get("duration_s"))
    for field in REQUIRED_NUMERIC:
        out[field] = _to_int(out.get(field))

    if not out.get("url") and out.get("id"):
        out["url"] = f"https://www.instagram.com/reel/{out['id']}/"

    if not out.get("id"):
        seed = f"{out.get('url') or ''}{out.get('handle') or ''}{out.get('posted_at') or ''}{out['caption'][:80]}"
        if not seed.strip():
            return None
        out["id"] = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    out["id"] = str(out["id"])

    if out["views"] <= 0 and out["likes"] <= 0:
        return None  # nothing measurable

    out["collected_at"] = _to_iso(record.get("collected_at")) or datetime.now(timezone.utc).isoformat()
    out["source"] = source
    out["is_sample"] = 1 if is_sample else 0
    return out


def normalize_many(records: Iterable[dict[str, Any]], source: str = "manual", is_sample: bool = False) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for record in records:
        row = normalize(record, source=source, is_sample=is_sample)
        if row and row["id"] not in seen:
            seen.add(row["id"])
            out.append(row)
    return out

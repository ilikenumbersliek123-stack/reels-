"""Pattern mining over the leaderboard.

Everything here answers one question: given the reels that won, what did they
have in common that the reels that lost did not? Each function returns plain
dicts ready to be JSON-encoded for the dashboard.

Medians are used throughout rather than means — a single 8M-view outlier should
not make its whole tag look like a strategy.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Sequence

# Below this a tag's "lift" is a coincidence, not a finding.
MIN_SAMPLE = 5


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def tag_lift(rows: Sequence[dict[str, Any]], min_sample: int = MIN_SAMPLE) -> list[dict[str, Any]]:
    """Median score of reels carrying each tag, versus the corpus median.

    lift > 1 means reels with that tag out-perform the field. `share_of_top` is
    the tag's prevalence in the top decile, which catches tags that are rare but
    dominate the very top.
    """
    if not rows:
        return []
    overall = _median([r["score"] for r in rows])
    if overall <= 0:
        return []

    top_cut = max(1, len(rows) // 10)
    top_ids = {r["reel_id"] for r in sorted(rows, key=lambda r: r["score"], reverse=True)[:top_cut]}

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    kinds: dict[str, str] = {}
    for row in rows:
        for tag, kind in row.get("tags", []):
            buckets[tag].append(row)
            kinds[tag] = kind

    out = []
    for tag, members in buckets.items():
        if len(members) < min_sample:
            continue
        scores = [m["score"] for m in members]
        out.append(
            {
                "tag": tag,
                "kind": kinds[tag],
                "count": len(members),
                "median_score": round(_median(scores), 2),
                "lift": round(_median(scores) / overall, 3),
                "median_views": int(_median([m.get("views", 0) for m in members])),
                "median_reach_multiple": round(_median([m.get("reach_multiple", 0) for m in members]), 2),
                "median_intent_rate": round(_median([m.get("intent_rate", 0) for m in members]), 5),
                "in_top_decile": sum(1 for m in members if m["reel_id"] in top_ids),
                "share_of_top": round(
                    sum(1 for m in members if m["reel_id"] in top_ids) / max(len(top_ids), 1), 4
                ),
            }
        )
    out.sort(key=lambda r: r["lift"], reverse=True)
    return out


def duration_curve(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for tag, kind in row.get("tags", []):
            if kind == "length":
                buckets[tag].append(row)
    order = ["len:0-7s", "len:7-15s", "len:15-30s", "len:30-60s", "len:60-90s", "len:90s+"]
    return [
        {
            "bucket": label,
            "count": len(buckets[label]),
            "median_score": round(_median([r["score"] for r in buckets[label]]), 2),
            "median_views": int(_median([r.get("views", 0) for r in buckets[label]])),
            "median_engagement": round(_median([r.get("engagement_rate", 0) for r in buckets[label]]), 5),
        }
        for label in order
        if buckets[label]
    ]


def posting_time(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Median score by UTC hour and weekday of posting.

    Read this as a weak signal. Posting time matters far less than the first
    two seconds of the video, and this view exists mostly to prove that to you.
    """
    by_hour: dict[int, list[float]] = defaultdict(list)
    by_dow: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        raw = row.get("posted_at")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        by_hour[dt.hour].append(row["score"])
        by_dow[dt.weekday()].append(row["score"])

    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return {
        "by_hour": [
            {"hour": h, "count": len(v), "median_score": round(_median(v), 2)}
            for h, v in sorted(by_hour.items())
        ],
        "by_weekday": [
            {"day": names[d], "count": len(v), "median_score": round(_median(v), 2)}
            for d, v in sorted(by_dow.items())
        ],
    }


def breakout_accounts(rows: Sequence[dict[str, Any]], max_followers: int = 25000) -> list[dict[str, Any]]:
    """Small accounts punching above their weight.

    This is the most directly copyable list in the whole app: these are people
    who, recently, got reach without an existing audience. Study these before
    you study anyone with a blue tick.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if (row.get("followers") or 0) <= max_followers and row.get("handle"):
            grouped[row["handle"]].append(row)

    out = []
    for handle, members in grouped.items():
        out.append(
            {
                "handle": handle,
                "followers": members[0].get("followers", 0),
                "reels": len(members),
                "median_score": round(_median([m["score"] for m in members]), 2),
                "best_reach_multiple": round(max(m.get("reach_multiple", 0) for m in members), 2),
                "best_views": max(m.get("views", 0) for m in members),
                "top_tags": _top_tags(members),
            }
        )
    out.sort(key=lambda r: r["best_reach_multiple"], reverse=True)
    return out[:50]


def _top_tags(members: Sequence[dict[str, Any]], limit: int = 4) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for m in members:
        for tag, kind in m.get("tags", []):
            if kind in ("format", "hook", "subject"):
                counts[tag] += 1
    return [t for t, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]]


def audio_leaderboard(rows: Sequence[dict[str, Any]], min_uses: int = 3) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        name = (row.get("audio_name") or "").strip()
        if name:
            grouped[name].append(row)
    out = [
        {
            "audio": name,
            "uses": len(members),
            "median_score": round(_median([m["score"] for m in members]), 2),
            "median_views": int(_median([m.get("views", 0) for m in members])),
        }
        for name, members in grouped.items()
        if len(members) >= min_uses
    ]
    out.sort(key=lambda r: r["median_score"], reverse=True)
    return out[:40]


def corpus_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"reels": 0}
    views = [r.get("views", 0) for r in rows]
    return {
        "reels": len(rows),
        "accounts": len({r.get("handle") for r in rows if r.get("handle")}),
        "median_views": int(_median(views)),
        "p90_views": int(sorted(views)[int(len(views) * 0.9)]) if views else 0,
        "max_views": max(views) if views else 0,
        "median_engagement_rate": round(_median([r.get("engagement_rate", 0) for r in rows]), 5),
        "median_intent_rate": round(_median([r.get("intent_rate", 0) for r in rows]), 5),
        "median_reach_multiple": round(_median([r.get("reach_multiple", 0) for r in rows]), 2),
        "sample_rows": sum(1 for r in rows if r.get("is_sample")),
        "newest_post": max((str(r.get("posted_at") or "") for r in rows), default=""),
    }

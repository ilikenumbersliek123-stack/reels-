"""Week-over-week comparison between two stored signal snapshots.

A single week's leaderboard tells you what is working. Two weeks tell you what
is *changing*, which is the more actionable of the two — a format whose lift
went from 0.95 to 1.20 is a better bet than one that has been flat at 1.15 for
a month, because the second is already crowded.

Every function here takes the `signals` dicts produced by `pipeline.signals`.
"""

from __future__ import annotations

from typing import Any, Sequence

# A tag needs this many examples in BOTH snapshots before a change in its lift
# is worth reporting; below that the movement is resampling noise.
MIN_SAMPLE_EACH = 5

# Lift movement smaller than this is not a signal, it is jitter.
MATERIAL_MOVE = 0.04

# A tag counts as "new" only once it has enough examples to stand on.
NEW_TAG_MIN_COUNT = 6


def _index(signals: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["tag"]: row for row in signals.get("tags", [])}


def tag_movers(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    before, after = _index(previous), _index(current)

    moved: list[dict[str, Any]] = []
    for tag, now in after.items():
        was = before.get(tag)
        if not was:
            continue
        if now["count"] < MIN_SAMPLE_EACH or was["count"] < MIN_SAMPLE_EACH:
            continue
        change = round(now["lift"] - was["lift"], 3)
        if abs(change) < MATERIAL_MOVE:
            continue
        moved.append(
            {
                "tag": tag,
                "kind": now["kind"],
                "lift": now["lift"],
                "previous_lift": was["lift"],
                "change": change,
                "count": now["count"],
                "previous_count": was["count"],
                "median_views": now["median_views"],
            }
        )

    moved.sort(key=lambda r: r["change"], reverse=True)
    fresh = [
        {
            "tag": tag,
            "kind": row["kind"],
            "lift": row["lift"],
            "count": row["count"],
            "median_views": row["median_views"],
        }
        for tag, row in after.items()
        if tag not in before and row["count"] >= NEW_TAG_MIN_COUNT
    ]
    fresh.sort(key=lambda r: r["lift"], reverse=True)

    return {
        "rising": [m for m in moved if m["change"] > 0][:12],
        "falling": [m for m in moved if m["change"] < 0][-12:][::-1],
        "new": fresh[:8],
    }


def length_shift(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any] | None:
    def best(signals: dict[str, Any]) -> dict[str, Any] | None:
        buckets = [b for b in signals.get("duration", []) if b["count"] >= MIN_SAMPLE_EACH]
        return max(buckets, key=lambda b: b["median_score"]) if buckets else None

    was, now = best(previous), best(current)
    if not now:
        return None
    return {
        "bucket": now["bucket"],
        "median_score": now["median_score"],
        "previous_bucket": was["bucket"] if was else None,
        "changed": bool(was and was["bucket"] != now["bucket"]),
    }


def new_breakouts(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    """Small accounts that appear in this week's breakout list and not last week's."""
    seen = {b["handle"] for b in previous.get("breakouts", [])}
    return [b for b in current.get("breakouts", []) if b["handle"] not in seen][:10]


def corpus_shift(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    was, now = previous.get("summary", {}), current.get("summary", {})

    def delta(key: str) -> Any:
        if key not in now or key not in was:
            return None
        return round(now[key] - was[key], 3) if isinstance(now[key], float) else now[key] - was[key]

    return {
        "reels": now.get("reels", 0),
        "reels_change": delta("reels"),
        "accounts": now.get("accounts", 0),
        "median_views": now.get("median_views", 0),
        "median_views_change": delta("median_views"),
        "median_reach_multiple": now.get("median_reach_multiple", 0),
    }


def compare(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Full diff. With no previous snapshot this returns a first-run marker."""
    if not previous:
        return {
            "first_run": True,
            "tags": {"rising": [], "falling": [], "new": []},
            "length": length_shift({}, current),
            "breakouts": [],
            "corpus": corpus_shift({}, current),
        }
    return {
        "first_run": False,
        "tags": tag_movers(previous, current),
        "length": length_shift(previous, current),
        "breakouts": new_breakouts(previous, current),
        "corpus": corpus_shift(previous, current),
    }


def headline(deltas: dict[str, Any]) -> str:
    """One sentence for the top of the weekly report."""
    if deltas.get("first_run"):
        return "First run — no previous week to compare against yet."
    rising = deltas["tags"]["rising"]
    falling = deltas["tags"]["falling"]
    parts: list[str] = []
    if rising:
        parts.append(f"{rising[0]['tag']} up {rising[0]['change']:+.2f} to {rising[0]['lift']:.2f}×")
    if falling:
        parts.append(f"{falling[0]['tag']} down {falling[0]['change']:+.2f} to {falling[0]['lift']:.2f}×")
    if deltas.get("length", {}) and deltas["length"] and deltas["length"].get("changed"):
        parts.append(f"best length moved to {deltas['length']['bucket'].replace('len:', '')}")
    return "; ".join(parts) if parts else "Nothing moved materially this week."


def evidence_pool(current: dict[str, Any], deltas: dict[str, Any], min_count: int = 8) -> dict[str, Any]:
    """The measured facts the idea generator is allowed to build on.

    Kept deliberately small and explicit: anything the generator cites has to
    come from here, so every generated idea can name the number behind it.
    """
    tags = [t for t in current.get("tags", []) if t["count"] >= min_count]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for tag in tags:
        by_kind.setdefault(tag["kind"], []).append(tag)
    for rows in by_kind.values():
        rows.sort(key=lambda r: r["lift"], reverse=True)

    lengths = [b for b in current.get("duration", []) if b["count"] >= MIN_SAMPLE_EACH]
    lengths.sort(key=lambda b: b["median_score"], reverse=True)

    return {
        "formats": by_kind.get("format", [])[:6],
        "hooks": by_kind.get("hook", [])[:6],
        "subjects": by_kind.get("subject", [])[:6],
        "ctas": by_kind.get("cta", [])[:3],
        "weak_formats": by_kind.get("format", [])[-3:],
        "best_length": lengths[0] if lengths else None,
        "lengths": lengths[:4],
        "rising": deltas.get("tags", {}).get("rising", [])[:6],
        "falling": deltas.get("tags", {}).get("falling", [])[:4],
        "new_tags": deltas.get("tags", {}).get("new", [])[:4],
        "breakouts": current.get("breakouts", [])[:8],
        "summary": current.get("summary", {}),
    }

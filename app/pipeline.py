"""Ingest -> tag -> score -> query. The glue the CLI and the server both use."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any, Iterable, Sequence

from . import analytics, db, scoring, tagging

TOP_N = 1000

# Sentinel rank ceiling meaning "no ceiling" — used by the analytics views.
ALL_ROWS = 10_000_000


def ingest(conn: sqlite3.Connection, rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    inserted, updated = db.upsert_reels(conn, rows)
    for row in rows:
        db.replace_tags(conn, row["id"], tagging.tags_for(row))
    return {"inserted": inserted, "updated": updated, "total": len(rows)}


def refresh(
    conn: sqlite3.Connection,
    half_life_days: float = scoring.DEFAULT_HALF_LIFE_DAYS,
    min_views: int = scoring.MIN_VIEWS,
    window_days: float | None = None,
) -> dict[str, Any]:
    reels = [dict(r) for r in db.all_reels(conn)]
    histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute("SELECT * FROM metric_history ORDER BY reel_id, collected_at"):
        histories[row["reel_id"]].append(dict(row))

    scored = scoring.rank_corpus(
        reels,
        histories=histories,
        half_life_days=half_life_days,
        min_views=min_views,
        window_days=window_days,
    )
    db.write_scores(conn, scored)
    return {
        "scored": len(scored),
        "excluded": len(reels) - len(scored),
        "window_days": window_days,
        "top_n": min(TOP_N, len(scored)),
    }


def _attach_tags(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    by_id = {r["reel_id"]: r for r in rows}
    for r in rows:
        r["tags"] = []
    placeholders = ",".join("?" for _ in by_id)
    for tag_row in conn.execute(
        f"SELECT reel_id, tag, kind FROM tags WHERE reel_id IN ({placeholders})", list(by_id)
    ):
        by_id[tag_row["reel_id"]]["tags"].append((tag_row["tag"], tag_row["kind"]))
    return rows


JOIN = """
SELECT s.rank, s.score, s.raw_score, s.pct_reach, s.pct_virality, s.pct_engagement,
       s.pct_intent, s.reach_multiple, s.engagement_rate, s.intent_rate, s.velocity,
       r.id AS reel_id, r.url, r.handle, r.author_name, r.followers, r.posted_at,
       r.duration_s, r.views, r.likes, r.comments, r.shares, r.saves, r.caption,
       r.audio_name, r.source, r.is_sample
FROM scores s JOIN reels r ON r.id = s.reel_id
"""

SORTABLE = {
    "score": "s.score",
    "rank": "s.rank",
    "views": "r.views",
    "velocity": "s.velocity",
    "reach_multiple": "s.reach_multiple",
    "engagement_rate": "s.engagement_rate",
    "intent_rate": "s.intent_rate",
    "posted_at": "r.posted_at",
    "followers": "r.followers",
}


def leaderboard(
    conn: sqlite3.Connection,
    limit: int = 100,
    offset: int = 0,
    top_n: int = TOP_N,
    tag: str | None = None,
    handle: str | None = None,
    query: str | None = None,
    max_followers: int | None = None,
    sort: str = "rank",
    direction: str = "asc",
    include_sample: bool = True,
) -> dict[str, Any]:
    where = ["s.rank <= ?"]
    params: list[Any] = [top_n]

    if tag:
        where.append("EXISTS (SELECT 1 FROM tags t WHERE t.reel_id = r.id AND t.tag = ?)")
        params.append(tag)
    if handle:
        where.append("r.handle = ?")
        params.append(handle.lstrip("@").lower())
    if query:
        where.append("(r.caption LIKE ? OR r.handle LIKE ? OR r.audio_name LIKE ?)")
        params.extend([f"%{query}%"] * 3)
    if max_followers:
        where.append("r.followers <= ?")
        params.append(max_followers)
    if not include_sample:
        where.append("r.is_sample = 0")

    clause = " WHERE " + " AND ".join(where)
    column = SORTABLE.get(sort, "s.rank")
    order = "ASC" if direction.lower() == "asc" else "DESC"

    total = conn.execute(f"SELECT COUNT(*) c FROM scores s JOIN reels r ON r.id=s.reel_id{clause}", params).fetchone()["c"]
    rows = [
        dict(r)
        for r in conn.execute(
            f"{JOIN}{clause} ORDER BY {column} {order}, s.rank ASC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
    ]
    return {"total": total, "limit": limit, "offset": offset, "rows": _attach_tags(conn, rows)}


def top_rows(conn: sqlite3.Connection, top_n: int = TOP_N, include_sample: bool = True) -> list[dict[str, Any]]:
    """The scored top-N with tags attached — the input to every analytics view."""
    clause = " WHERE s.rank <= ?" + ("" if include_sample else " AND r.is_sample = 0")
    rows = [dict(r) for r in conn.execute(f"{JOIN}{clause} ORDER BY s.rank", (top_n,))]
    return _attach_tags(conn, rows)


def signals(conn: sqlite3.Connection, top_n: int | None = None, include_sample: bool = True) -> dict[str, Any]:
    """Pattern-mine the corpus.

    Deliberately defaults to *every* scored reel rather than the top 1000. Lift
    measured only among winners answers "which winners won hardest", which is a
    much weaker question than "what separates a winner from an also-ran" — and
    the contrast collapses, because the top 1000 is already a filtered set.
    """
    rows = top_rows(conn, top_n=top_n or ALL_ROWS, include_sample=include_sample)
    return {
        "summary": analytics.corpus_summary(rows),
        "tags": analytics.tag_lift(rows),
        "duration": analytics.duration_curve(rows),
        "timing": analytics.posting_time(rows),
        "breakouts": analytics.breakout_accounts(rows),
        "audio": analytics.audio_leaderboard(rows),
    }


def reel_detail(conn: sqlite3.Connection, reel_id: str) -> dict[str, Any] | None:
    row = conn.execute(f"{JOIN} WHERE r.id = ?", (reel_id,)).fetchone()
    if not row:
        base = conn.execute("SELECT * FROM reels WHERE id=?", (reel_id,)).fetchone()
        if not base:
            return None
        detail = dict(base)
        detail["reel_id"] = detail.pop("id")
    else:
        detail = dict(row)
    _attach_tags(conn, [detail])
    detail["history"] = [dict(h) for h in db.history_for(conn, reel_id)]
    return detail


def purge_sample(conn: sqlite3.Connection) -> int:
    ids = [r["id"] for r in conn.execute("SELECT id FROM reels WHERE is_sample=1")]
    for reel_id in ids:
        conn.execute("DELETE FROM reels WHERE id=?", (reel_id,))
        conn.execute("DELETE FROM metric_history WHERE reel_id=?", (reel_id,))
        conn.execute("DELETE FROM tags WHERE reel_id=?", (reel_id,))
        conn.execute("DELETE FROM scores WHERE reel_id=?", (reel_id,))
    return len(ids)


def collect_iter(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(rows)

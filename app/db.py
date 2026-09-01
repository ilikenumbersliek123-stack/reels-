"""SQLite storage for the reel tracker.

Three tables carry the whole model:

  reels          one row per reel we know about, latest known metrics
  metric_history one row per observation, so we can measure real velocity
  scores         output of scoring.py, refreshed on demand

Everything is stdlib. The database is a single file you can copy, diff or
delete without ceremony.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

DEFAULT_DB = os.environ.get("REELS_DB", "reels.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reels (
    id            TEXT PRIMARY KEY,
    url           TEXT,
    handle        TEXT,
    author_name   TEXT,
    followers     INTEGER,
    posted_at     TEXT,
    collected_at  TEXT,
    duration_s    REAL,
    views         INTEGER DEFAULT 0,
    likes         INTEGER DEFAULT 0,
    comments      INTEGER DEFAULT 0,
    shares        INTEGER DEFAULT 0,
    saves         INTEGER DEFAULT 0,
    caption       TEXT DEFAULT '',
    audio_name    TEXT DEFAULT '',
    audio_id      TEXT DEFAULT '',
    source        TEXT DEFAULT 'manual',
    is_sample     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS metric_history (
    reel_id      TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    views        INTEGER DEFAULT 0,
    likes        INTEGER DEFAULT 0,
    comments     INTEGER DEFAULT 0,
    shares       INTEGER DEFAULT 0,
    saves        INTEGER DEFAULT 0,
    PRIMARY KEY (reel_id, collected_at)
);

CREATE TABLE IF NOT EXISTS tags (
    reel_id TEXT NOT NULL,
    tag     TEXT NOT NULL,
    kind    TEXT NOT NULL,
    PRIMARY KEY (reel_id, tag)
);

CREATE TABLE IF NOT EXISTS scores (
    reel_id         TEXT PRIMARY KEY,
    rank            INTEGER,
    score           REAL,
    raw_score       REAL,
    pct_reach       REAL,
    pct_virality    REAL,
    pct_engagement  REAL,
    pct_intent      REAL,
    reach_multiple  REAL,
    engagement_rate REAL,
    intent_rate     REAL,
    velocity        REAL,
    computed_at     TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    kind  TEXT NOT NULL,          -- 'account' | 'hashtag'
    value TEXT NOT NULL,
    note  TEXT DEFAULT '',
    PRIMARY KEY (kind, value)
);

CREATE INDEX IF NOT EXISTS idx_reels_handle   ON reels(handle);
CREATE INDEX IF NOT EXISTS idx_reels_posted   ON reels(posted_at);
CREATE INDEX IF NOT EXISTS idx_tags_tag       ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_scores_rank    ON scores(rank);
"""

REEL_COLUMNS = (
    "id url handle author_name followers posted_at collected_at duration_s "
    "views likes comments shares saves caption audio_name audio_id source is_sample"
).split()


def connect(path: str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session(path: str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def upsert_reels(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> tuple[int, int]:
    """Insert or update reels and append a metric_history observation.

    Returns (inserted, updated). A reel is "updated" when we already had its id;
    its previous metrics stay in metric_history so velocity survives the overwrite.
    """
    inserted = updated = 0
    placeholders = ", ".join("?" for _ in REEL_COLUMNS)
    assignments = ", ".join(f"{c}=excluded.{c}" for c in REEL_COLUMNS if c != "id")
    sql = (
        f"INSERT INTO reels ({', '.join(REEL_COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {assignments}"
    )
    for row in rows:
        existed = conn.execute("SELECT 1 FROM reels WHERE id=?", (row["id"],)).fetchone()
        conn.execute(sql, [row.get(c) for c in REEL_COLUMNS])
        conn.execute(
            "INSERT OR REPLACE INTO metric_history "
            "(reel_id, collected_at, views, likes, comments, shares, saves) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                row["id"],
                row.get("collected_at"),
                row.get("views") or 0,
                row.get("likes") or 0,
                row.get("comments") or 0,
                row.get("shares") or 0,
                row.get("saves") or 0,
            ),
        )
        if existed:
            updated += 1
        else:
            inserted += 1
    return inserted, updated


def replace_tags(conn: sqlite3.Connection, reel_id: str, tags: Iterable[tuple[str, str]]) -> None:
    conn.execute("DELETE FROM tags WHERE reel_id=?", (reel_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO tags (reel_id, tag, kind) VALUES (?,?,?)",
        [(reel_id, tag, kind) for tag, kind in tags],
    )


def all_reels(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM reels").fetchall()


def history_for(conn: sqlite3.Connection, reel_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM metric_history WHERE reel_id=? ORDER BY collected_at",
        (reel_id,),
    ).fetchall()


def write_scores(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> None:
    cols = (
        "reel_id rank score raw_score pct_reach pct_virality pct_engagement "
        "pct_intent reach_multiple engagement_rate intent_rate velocity computed_at"
    ).split()
    conn.execute("DELETE FROM scores")
    conn.executemany(
        f"INSERT INTO scores ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        [[r.get(c) for c in cols] for r in rows],
    )


def watchlist(conn: sqlite3.Connection, kind: str | None = None) -> list[sqlite3.Row]:
    if kind:
        return conn.execute("SELECT * FROM watchlist WHERE kind=? ORDER BY value", (kind,)).fetchall()
    return conn.execute("SELECT * FROM watchlist ORDER BY kind, value").fetchall()


def add_watch(conn: sqlite3.Connection, kind: str, value: str, note: str = "") -> None:
    conn.execute(
        "INSERT OR REPLACE INTO watchlist (kind, value, note) VALUES (?,?,?)",
        (kind, value.lstrip("@#").lower(), note),
    )

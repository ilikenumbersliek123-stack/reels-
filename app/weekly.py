"""The weekly job: collect → re-rank the rolling window → diff → generate ideas.

Run it by hand (`python -m app weekly`), on cron (`python -m app schedule
--install`), or on GitHub Actions (`.github/workflows/weekly.yml`). All three
call `run()` below.

The job is designed to be useful even when collection is not configured: with no
Apify token and no Graph API credentials it still re-ranks what is already in
the database against the current window, diffs it against last week, and writes
a fresh idea set. Partial failure is normal and non-fatal — a provider being
down should cost you that week's new rows, not the run.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from . import db, ideagen, ideagen_llm, pipeline, tagging, trends

DEFAULT_WINDOW_DAYS = 90
DEFAULT_IDEA_COUNT = 12
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
IDEAS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ideas.json")


def collect(conn, limit: int = 50) -> tuple[list[dict[str, Any]], list[str]]:
    """Pull fresh rows from every configured source. Never raises."""
    rows: list[dict[str, Any]] = []
    notes: list[str] = []

    from .sources import apify, graph

    try:
        own = graph.fetch_own_reels(limit=100)
        rows.extend(own)
        notes.append(f"graph: {len(own)} own reels")
    except graph.GraphNotConfigured:
        notes.append("graph: not configured (set IG_ACCESS_TOKEN and IG_USER_ID)")
    except Exception as exc:  # a provider outage must not kill the run
        notes.append(f"graph: failed — {exc}")

    for kind in ("account", "hashtag"):
        targets = [r["value"] for r in db.watchlist(conn, kind)]
        if not targets:
            continue
        try:
            found = apify.run_actor(targets, kind=kind, limit_per_target=limit)
            rows.extend(found)
            notes.append(f"apify/{kind}: {len(found)} reels from {len(targets)} targets")
        except apify.ApifyNotConfigured:
            notes.append(f"apify/{kind}: not configured (set APIFY_TOKEN)")
        except Exception as exc:
            notes.append(f"apify/{kind}: failed — {exc}")

    if not rows and not notes:
        notes.append("no sources configured — re-ranked existing rows only")
    return rows, notes


def _library_titles() -> list[str]:
    try:
        with open(IDEAS_PATH, encoding="utf-8") as fh:
            return [i["title"] for i in json.load(fh)["ideas"]]
    except (OSError, KeyError, json.JSONDecodeError):
        return []


def _previous_generated_titles(conn, limit_runs: int = 4) -> list[str]:
    """Titles from recent runs, so consecutive weeks do not repeat themselves."""
    rows = conn.execute(
        "SELECT payload_json FROM generated_ideas WHERE run_id IN "
        "(SELECT DISTINCT run_id FROM generated_ideas ORDER BY run_id DESC LIMIT ?)",
        (limit_runs,),
    ).fetchall()
    titles = []
    for row in rows:
        try:
            titles.append(json.loads(row["payload_json"])["title"])
        except (KeyError, json.JSONDecodeError):
            continue
    return titles


def make_ideas(
    conn,
    pool: dict[str, Any],
    run_id: int,
    count: int,
    llm: str = "auto",
) -> tuple[list[dict[str, Any]], str, str]:
    """Return (ideas, source, note).

    `llm` is 'auto' (use Claude when it is available, else compose), 'on'
    (require Claude, surface the reason if it fails) or 'off'.
    """
    avoid = _library_titles() + _previous_generated_titles(conn)

    if llm in ("auto", "on"):
        try:
            ideas = ideagen_llm.generate(pool, count=count, run_id=run_id, avoid_titles=avoid)
            return ideas, "claude", f"ideas written by {ideagen_llm.MODEL}"
        except ideagen_llm.LLMNotConfigured as exc:
            note = f"claude unavailable ({exc}) — composed from signals instead"
            if llm == "on":
                note = f"claude requested but unavailable: {exc}"
        except Exception as exc:
            note = f"claude call failed ({type(exc).__name__}: {exc}) — composed from signals instead"
    else:
        note = "ideas composed from measured signals"

    ideas = ideagen.generate(pool, count=count, run_id=run_id, avoid_titles=avoid)
    return ideas, "measured", note


def run(
    db_path: str = db.DEFAULT_DB,
    window_days: int = DEFAULT_WINDOW_DAYS,
    do_collect: bool = True,
    llm: str = "auto",
    idea_count: int = DEFAULT_IDEA_COUNT,
    collect_limit: int = 50,
    report_dir: str = REPORT_DIR,
    write_report: bool = True,
) -> dict[str, Any]:
    conn = db.connect(db_path)
    db.init(conn)
    run_id = db.start_run(conn, window_days)
    conn.commit()

    notes: list[str] = []
    counts = {"collected": 0, "inserted": 0, "updated": 0}

    try:
        if do_collect:
            rows, collect_notes = collect(conn, limit=collect_limit)
            notes.extend(collect_notes)
            if rows:
                result = pipeline.ingest(conn, rows)
                counts = {"collected": len(rows), "inserted": result["inserted"], "updated": result["updated"]}
        else:
            notes.append("collection skipped (--no-collect)")

        # Re-tag everything: the taxonomy may have changed since the last run,
        # and a tag that exists only on new rows would look like a trend.
        tagging.retag_all(conn)

        scored = pipeline.refresh(conn, window_days=window_days)
        signals = pipeline.signals(conn)

        previous = db.previous_successful_run(conn, run_id)
        previous_signals = json.loads(previous["signals_json"]) if previous else None
        deltas = trends.compare(previous_signals, signals)
        deltas["compared_to_run"] = previous["id"] if previous else None

        pool = trends.evidence_pool(signals, deltas)
        ideas, source, idea_note = make_ideas(conn, pool, run_id, idea_count, llm)
        notes.append(idea_note)
        db.save_generated(conn, run_id, source, ideas)

        db.finish_run(
            conn,
            run_id,
            status="ok",
            scored=scored["scored"],
            idea_count=len(ideas),
            idea_source=source,
            signals_json=json.dumps(signals, default=str),
            deltas_json=json.dumps(deltas, default=str),
            notes=" | ".join(notes),
            **counts,
        )
        conn.commit()

        report_path = None
        if write_report:
            report_path = write_markdown(
                report_dir, run_id, signals, deltas, ideas, notes, scored, window_days
            )

        return {
            "run_id": run_id,
            "status": "ok",
            "window_days": window_days,
            **counts,
            "scored": scored["scored"],
            "ranked_top": min(pipeline.TOP_N, scored["scored"]),
            "ideas": len(ideas),
            "idea_source": source,
            "headline": trends.headline(deltas),
            "compared_to_run": deltas["compared_to_run"],
            "report": report_path,
            "notes": notes,
        }

    except Exception as exc:
        db.finish_run(conn, run_id, status="failed", notes=f"{type(exc).__name__}: {exc}")
        conn.commit()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------- reporting


def write_markdown(
    report_dir: str,
    run_id: int,
    signals: dict[str, Any],
    deltas: dict[str, Any],
    ideas: list[dict[str, Any]],
    notes: list[str],
    scored: dict[str, Any],
    window_days: int,
) -> str:
    os.makedirs(report_dir, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = signals.get("summary", {})
    lines: list[str] = []

    lines.append(f"# Week of {today}")
    lines.append("")
    lines.append(f"**{trends.headline(deltas)}**")
    lines.append("")
    lines.append(
        f"Run {run_id} · {summary.get('reels', 0)} reels ranked from a {window_days}-day window · "
        f"{summary.get('accounts', 0)} accounts · median {summary.get('median_views', 0):,} views · "
        f"p90 {summary.get('p90_views', 0):,}"
    )
    if summary.get("sample_rows"):
        lines.append("")
        lines.append(
            f"> {summary['sample_rows']:,} of these rows are synthetic sample data. "
            f"Run `python -m app purge-sample` once you have real data — until then "
            f"the signals below are a demonstration, not a finding."
        )

    movers = deltas.get("tags", {})
    if movers.get("rising") or movers.get("falling"):
        lines += ["", "## Movers", "", "| Tag | Lift | Was | Change | n |", "|---|---|---|---|---|"]
        for row in movers.get("rising", [])[:8] + movers.get("falling", [])[:5]:
            lines.append(
                f"| `{row['tag']}` | {row['lift']:.2f}× | {row['previous_lift']:.2f}× | "
                f"{row['change']:+.2f} | {row['count']} |"
            )
    if movers.get("new"):
        lines += ["", "**New this week:** " + ", ".join(f"`{r['tag']}` ({r['lift']:.2f}×)" for r in movers["new"])]

    top = signals.get("tags", [])[:10]
    if top:
        lines += ["", "## Strongest tags", "", "| Tag | Lift | n | Median views |", "|---|---|---|---|"]
        for row in top:
            lines.append(f"| `{row['tag']}` | {row['lift']:.2f}× | {row['count']} | {row['median_views']:,} |")

    if deltas.get("breakouts"):
        lines += ["", "## New breakout accounts", ""]
        for row in deltas["breakouts"][:6]:
            lines.append(
                f"- **@{row['handle']}** — {row['followers']:,} followers, "
                f"best {row['best_reach_multiple']:.1f}× reach · {', '.join(row['top_tags'])}"
            )

    lines += ["", f"## Ideas for this week ({len(ideas)})", ""]
    for idea in ideas:
        lines.append(f"### {idea['title']}")
        lines.append("")
        lines.append(f"*{idea['goal']} · {idea['effort']} effort · {idea['length_s']}s · `{idea['id']}`*")
        lines.append("")
        lines.append(f"**Hook:** {idea['hook'] or '_(no hook text — open on the visual)_'}")
        lines.append("")
        for i, shot in enumerate(idea["shots"], 1):
            lines.append(f"{i}. {shot}")
        lines.append("")
        lines.append(idea["why"])
        if idea.get("cta"):
            lines.append("")
            lines.append(f"CTA: {idea['cta']}")
        if idea.get("evidence"):
            evidence = ", ".join(
                f"`{e['tag']}`" + (f" {e['lift']:.2f}×" if e.get("lift") else "") + f" (n={e['count']})"
                for e in idea["evidence"]
            )
            lines.append("")
            lines.append(f"Evidence: {evidence}")
        lines.append("")

    lines += ["---", "", "Run notes: " + "; ".join(notes)]

    path = os.path.join(report_dir, f"{today}.md")
    body = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    with open(os.path.join(report_dir, "latest.md"), "w", encoding="utf-8") as fh:
        fh.write(body)
    return path

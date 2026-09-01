"""Command line interface.

    python -m app seed                 # load labelled sample data and rank it
    python -m app serve                # open the dashboard
    python -m app import data.csv      # load your own collected data
    python -m app collect --kind account --targets a,b,c    # needs APIFY_TOKEN
    python -m app collect-own          # your own reels via the Graph API
    python -m app refresh              # recompute scores
    python -m app top --limit 25       # leaderboard in the terminal
    python -m app signals              # what the winners have in common
    python -m app export top1000.csv   # the top 1000 as a spreadsheet
    python -m app purge-sample         # delete every synthetic row

    python -m app weekly               # the weekly loop: collect, re-rank, diff, new ideas
    python -m app schedule --install   # run that every Monday at 09:00
    python -m app runs                 # history of weekly runs
    python -m app ideas                # this week's generated ideas
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any

from . import db, pipeline, scoring, seed
from .sources import files as file_source


def schedule_default() -> str:
    from . import schedule

    return schedule.DEFAULT_CRON


def _open(args: argparse.Namespace):
    conn = db.connect(args.db)
    db.init(conn)
    return conn


def cmd_seed(args: argparse.Namespace) -> int:
    rows = seed.generate(args.count)
    conn = _open(args)
    result = pipeline.ingest(conn, rows)
    result.update(pipeline.refresh(conn))
    conn.commit()
    print(json.dumps(result, indent=2))
    print("\nNOTE: these rows are synthetic and flagged is_sample=1.")
    print("Run `python -m app purge-sample` once you have real data.")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    rows = file_source.read_any(args.path)
    if not rows:
        print(f"No usable rows in {args.path}. Needs at least a view or like count per row.")
        return 1
    conn = _open(args)
    result = pipeline.ingest(conn, rows)
    result.update(pipeline.refresh(conn))
    conn.commit()
    print(json.dumps(result, indent=2))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    from .sources import apify

    conn = _open(args)
    targets = [t.strip() for t in (args.targets or "").split(",") if t.strip()]
    if not targets:
        targets = [r["value"] for r in db.watchlist(conn, args.kind)]
    if not targets:
        print(f"No {args.kind} targets. Add some with: python -m app watch --kind {args.kind} a,b,c")
        return 1
    try:
        rows = apify.run_actor(targets, kind=args.kind, limit_per_target=args.limit)
    except apify.ApifyNotConfigured as exc:
        print(str(exc))
        return 2
    result = pipeline.ingest(conn, rows)
    result.update(pipeline.refresh(conn))
    conn.commit()
    print(json.dumps(result, indent=2))
    return 0


def cmd_collect_own(args: argparse.Namespace) -> int:
    from .sources import graph

    try:
        rows = graph.fetch_own_reels(limit=args.limit)
    except graph.GraphNotConfigured as exc:
        print(str(exc))
        return 2
    conn = _open(args)
    result = pipeline.ingest(conn, rows)
    result.update(pipeline.refresh(conn))
    conn.commit()
    print(json.dumps(result, indent=2))
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    conn = _open(args)
    result = pipeline.refresh(
        conn, half_life_days=args.half_life, min_views=args.min_views, window_days=args.window_days
    )
    conn.commit()
    print(json.dumps(result, indent=2))
    return 0


def cmd_top(args: argparse.Namespace) -> int:
    conn = _open(args)
    page = pipeline.leaderboard(
        conn, limit=args.limit, tag=args.tag, max_followers=args.max_followers
    )
    if not page["rows"]:
        print("Nothing ranked yet. Try: python -m app seed")
        return 1
    print(f"{'#':>4}  {'score':>6}  {'views':>9}  {'x-reach':>7}  handle")
    print("-" * 78)
    for row in page["rows"]:
        print(
            f"{row['rank']:>4}  {row['score']:>6.1f}  {row['views']:>9,}  "
            f"{row['reach_multiple']:>7.1f}  @{row['handle'] or '?'}"
        )
        caption = (row["caption"] or "").replace("\n", " ")[:70]
        if caption:
            print(f"{'':>6}{caption}")
    print(f"\n{page['total']} reels in the ranked set.")
    return 0


def cmd_signals(args: argparse.Namespace) -> int:
    conn = _open(args)
    result = pipeline.signals(conn)
    summary = result["summary"]
    if not summary.get("reels"):
        print("Nothing ranked yet. Try: python -m app seed")
        return 1

    print(f"corpus: {summary['reels']} reels across {summary['accounts']} accounts")
    print(f"median views {summary['median_views']:,} | p90 {summary['p90_views']:,} | max {summary['max_views']:,}")
    if summary.get("sample_rows"):
        print(f"WARNING: {summary['sample_rows']} of these rows are synthetic sample data.\n")

    print("\nstrongest tags (median score vs corpus median):")
    print(f"  {'lift':>5}  {'n':>4}  {'med views':>10}  tag")
    for row in result["tags"][:15]:
        print(f"  {row['lift']:>5.2f}  {row['count']:>4}  {row['median_views']:>10,}  {row['tag']}")

    print("\nweakest tags:")
    for row in result["tags"][-8:]:
        print(f"  {row['lift']:>5.2f}  {row['count']:>4}  {row['median_views']:>10,}  {row['tag']}")

    print("\nlength:")
    for row in result["duration"]:
        print(f"  {row['bucket']:>10}  n={row['count']:>4}  median score {row['median_score']:>5.1f}")

    print("\nbreakout accounts (small following, big reach multiple):")
    for row in result["breakouts"][:10]:
        print(
            f"  @{row['handle']:<28} {row['followers']:>7,} followers  "
            f"best {row['best_reach_multiple']:>6.1f}x  {', '.join(row['top_tags'])}"
        )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = _open(args)
    rows = pipeline.top_rows(conn, top_n=args.top_n)
    if not rows:
        print("Nothing to export.")
        return 1
    fields = [
        "rank", "score", "handle", "followers", "views", "likes", "comments",
        "saves", "shares", "reach_multiple", "engagement_rate", "intent_rate",
        "velocity", "duration_s", "posted_at", "url", "audio_name", "caption",
        "is_sample",
    ]
    with open(args.path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields + ["tags"])
        writer.writeheader()
        for row in rows:
            record: dict[str, Any] = {f: row.get(f) for f in fields}
            record["tags"] = "|".join(t for t, _ in row.get("tags", []))
            writer.writerow(record)
    print(f"wrote {len(rows)} rows to {args.path}")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    conn = _open(args)
    for value in [t.strip() for t in (args.targets or "").split(",") if t.strip()]:
        db.add_watch(conn, args.kind, value)
    conn.commit()
    for row in db.watchlist(conn):
        print(f"{row['kind']:>8}  {row['value']}")
    return 0


def cmd_purge_sample(args: argparse.Namespace) -> int:
    conn = _open(args)
    removed = pipeline.purge_sample(conn)
    pipeline.refresh(conn)
    conn.commit()
    print(f"removed {removed} synthetic rows")
    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    from . import weekly

    result = weekly.run(
        db_path=args.db,
        window_days=args.window_days,
        do_collect=not args.no_collect,
        llm=args.llm,
        idea_count=args.ideas,
        collect_limit=args.limit,
    )
    print(f"run {result['run_id']} · {result['status']}")
    print(f"  {result['headline']}")
    print(
        f"  collected {result['collected']} ({result['inserted']} new, {result['updated']} updated) · "
        f"ranked {result['ranked_top']} of {result['scored']} in a {result['window_days']}-day window"
    )
    print(f"  {result['ideas']} ideas ({result['idea_source']})")
    for note in result["notes"]:
        print(f"  - {note}")
    if result.get("report"):
        print(f"  report: {result['report']}")
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    conn = _open(args)
    rows = db.runs(conn, limit=args.limit)
    if not rows:
        print("No runs yet. Try: python -m app weekly")
        return 1
    print(f"{'id':>4}  {'started':<20} {'status':<8} {'scored':>7} {'ideas':>6}  source")
    print("-" * 76)
    for row in rows:
        print(
            f"{row['id']:>4}  {str(row['started_at'])[:19]:<20} {row['status']:<8} "
            f"{row['scored'] or 0:>7} {row['idea_count'] or 0:>6}  {row['idea_source'] or ''}"
        )
    return 0


def cmd_ideas(args: argparse.Namespace) -> int:
    conn = _open(args)
    ideas = db.generated_ideas(conn, run_id=args.run)
    if not ideas:
        print("No generated ideas yet. Try: python -m app weekly")
        return 1
    for idea in ideas:
        print(f"\n{idea['title']}  [{idea['goal']} · {idea['effort']} · {idea['length_s']}s · {idea['id']}]")
        print(f"  hook: {idea['hook'] or '(none — open on the visual)'}")
        for i, shot in enumerate(idea["shots"], 1):
            print(f"  {i}. {shot}")
        print(f"  {idea['why']}")
        if idea.get("evidence"):
            bits = ", ".join(
                f"{e['tag']}" + (f" {e['lift']:.2f}x" if e.get("lift") else "") + f" (n={e['count']})"
                for e in idea["evidence"]
            )
            print(f"  evidence: {bits}")
    print(f"\n{len(ideas)} ideas.")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    from . import schedule

    try:
        if args.remove:
            print("removed" if schedule.remove() else "nothing installed")
            return 0
        if args.show:
            lines = schedule.show()
            print("\n".join(lines) if lines else "not scheduled")
            return 0
        entry = schedule.install(
            db_path=os.path.abspath(args.db),
            cron=args.cron,
            window_days=args.window_days,
            llm=args.llm,
            ideas=args.ideas,
        )
        print("installed:")
        print(f"  {entry}")
        print("\nCheck it with: python -m app schedule --show")
        return 0
    except schedule.CronUnavailable as exc:
        print(str(exc))
        return 2


def cmd_serve(args: argparse.Namespace) -> int:
    from . import server

    server.serve(host=args.host, port=args.port, db_path=args.db)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=db.DEFAULT_DB, help="sqlite file (default: reels.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("seed", help="load labelled synthetic sample data")
    p.add_argument("--count", type=int, default=2000)
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("import", help="load a CSV/JSON/JSONL file")
    p.add_argument("path")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("collect", help="collect via Apify (needs APIFY_TOKEN)")
    p.add_argument("--kind", choices=["account", "hashtag"], default="account")
    p.add_argument("--targets", default="")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("collect-own", help="your own reels via the Instagram Graph API")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_collect_own)

    p = sub.add_parser("refresh", help="recompute scores and ranks")
    p.add_argument("--half-life", dest="half_life", type=float, default=scoring.DEFAULT_HALF_LIFE_DAYS)
    p.add_argument("--min-views", dest="min_views", type=int, default=scoring.MIN_VIEWS)
    p.add_argument("--window-days", dest="window_days", type=int, default=None,
                   help="only rank reels posted within this many days")
    p.set_defaults(func=cmd_refresh)

    p = sub.add_parser("weekly", help="collect, re-rank the window, diff vs last week, write new ideas")
    p.add_argument("--window-days", dest="window_days", type=int, default=90)
    p.add_argument("--no-collect", dest="no_collect", action="store_true",
                   help="skip providers and re-rank what is already stored")
    p.add_argument("--llm", choices=["auto", "on", "off"], default="auto",
                   help="auto: let Claude write the ideas when available (default)")
    p.add_argument("--ideas", type=int, default=12)
    p.add_argument("--limit", type=int, default=50, help="reels per collection target")
    p.set_defaults(func=cmd_weekly)

    p = sub.add_parser("runs", help="history of weekly runs")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("ideas", help="print the generated ideas from a run")
    p.add_argument("--run", type=int, default=None, help="run id (default: most recent)")
    p.set_defaults(func=cmd_ideas)

    p = sub.add_parser("schedule", help="install the weekly job into your crontab")
    p.add_argument("--cron", default=schedule_default(), help="cron expression (default: Mondays 09:00)")
    p.add_argument("--window-days", dest="window_days", type=int, default=90)
    p.add_argument("--llm", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--ideas", type=int, default=12)
    p.add_argument("--remove", action="store_true", help="remove the scheduled job")
    p.add_argument("--show", action="store_true", help="show the installed entry")
    p.set_defaults(func=cmd_schedule)

    p = sub.add_parser("top", help="print the leaderboard")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--tag", default=None)
    p.add_argument("--max-followers", dest="max_followers", type=int, default=None)
    p.set_defaults(func=cmd_top)

    p = sub.add_parser("signals", help="what the top reels have in common")
    p.set_defaults(func=cmd_signals)

    p = sub.add_parser("export", help="write the top N to CSV")
    p.add_argument("path")
    p.add_argument("--top-n", dest="top_n", type=int, default=pipeline.TOP_N)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("watch", help="add accounts/hashtags to the collection watchlist")
    p.add_argument("targets")
    p.add_argument("--kind", choices=["account", "hashtag"], default="account")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("purge-sample", help="delete every synthetic row")
    p.set_defaults(func=cmd_purge_sample)

    p = sub.add_parser("serve", help="run the dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8420)
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

# Reel Tracker — minimal / deep tech

A local app that ranks the top 1000 performing Instagram Reels in the minimal /
deep tech niche, re-scans them every week, and turns what it measures into
promotional video ideas — 96 hand-written formats as a baseline, plus a fresh
set generated from each scan — alongside a 90-day plan for going from zero
followers.

No dependencies. Python 3.9+ stdlib, SQLite, and a vanilla JS frontend. The one
optional extra is `anthropic`, if you want Claude writing the weekly ideas
instead of the built-in generator.

```bash
python -m app seed                 # load the labelled sample corpus and rank it
python -m app serve                # http://127.0.0.1:8420
python -m app schedule --install   # then re-scan and re-generate every Monday
```

---

## Read this before you trust a number

**Instagram has no public API that returns view counts for other people's
Reels.** The Graph API gives insights only for accounts you own. There is no
sanctioned endpoint for anyone else's, and automated scraping is against
Instagram's Terms of Use.

So the app is built as an ingestion pipeline with three honest inputs rather
than a magic scraper:

1. **CSV / JSON import** — collect manually or from any tool. Always works.
2. **A third-party provider (Apify)** — fast, costs money, ToS risk is yours.
3. **Your own account via the Graph API** — sanctioned, free, and the only
   source of true saves, shares and reach. Most important of the three.

`python -m app seed` loads a **synthetic** corpus so nothing is empty on day
one. Every one of those rows is flagged `is_sample=1`, the dashboard shows an
amber banner while any survive, and `python -m app purge-sample` removes them.
The sample data encodes general short-form-video priors, not measurements of
this niche — it demonstrates the method, it does not tell you what to post.

Full detail: [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

---

## The dashboard

| Tab | What it is for |
|---|---|
| **Top 1000** | The ranked leaderboard. Filter by tag, account size, or text; sort by score, reach multiple, save+share rate, or views/day. Click any row for the full breakdown. |
| **Signals** | **Movers** — what changed since last week's scan — then what separates winners from also-rans: tag lift, length curve, posting time, breakout accounts, audio. |
| **Ideas** | **This week** — ideas generated from the latest scan, each carrying the lifts and sample sizes behind it — and **Library**, the 96 hand-written formats. Filter by goal and effort. |
| **Plan** | The 90-day playbook, rendered from `docs/PLAYBOOK.md`. |
| **Data** | Load, collect, recompute, manage the watchlist. |

## How the ranking works

Raw views make a bad leaderboard. A 2M-view reel from a 400k account teaches
you less than a 180k-view reel from a 900-follower account. So the score blends
four signals, each converted to a **percentile rank across the corpus** before
weighting — no magic scaling constants, and units that cannot dominate each
other:

| Weight | Signal | Meaning |
|---|---|---|
| 40% | reach | `log10(views)` — how far it actually went |
| 25% | virality | `views / followers` — how far it went relative to the audience it started with. **The column that matters when you are at zero.** |
| 20% | engagement | `(likes + 3×comments) / views` |
| 15% | intent | `(saves + 1.5×shares) / views` — the behaviours that precede a follow |

A recency factor then discounts old reels (180-day half-life, configurable),
because the goal is to learn what is rewarded *now*. `raw_score` keeps the
pre-recency number so you can see both.

Re-collecting the same reel appends to `metric_history`, which turns
`velocity` into a real current rate rather than a lifetime average. A reel
doing 40k/day three weeks after posting is a different animal from one that
did 800k on day one and flatlined.

## CLI

```bash
python -m app seed [--count 2000]        # labelled synthetic corpus
python -m app import reels.csv           # CSV / JSON / JSONL, flexible columns
python -m app collect --kind account --targets a,b,c    # needs APIFY_TOKEN
python -m app collect-own                # your reels, real insights, via Graph API
python -m app refresh [--window-days 90] # recompute scores
python -m app top --limit 25 [--tag format:tutorial] [--max-followers 5000]
python -m app signals                    # pattern mining in the terminal
python -m app export top1000.csv         # spreadsheet of the top 1000
python -m app watch "a,b,c" --kind account
python -m app purge-sample

python -m app weekly [--window-days 90] [--ideas 12] [--llm auto|on|off]
python -m app schedule --install [--cron "0 9 * * 1"] | --show | --remove
python -m app runs                       # history of weekly runs
python -m app ideas [--run N]            # generated ideas, with their evidence
python -m app serve [--port 8420]
```

All commands take `--db path.db` (default `reels.db`, or `$REELS_DB`).

## The weekly loop

```bash
python -m app weekly               # collect, re-rank, diff, generate
python -m app schedule --install    # every Monday at 09:00
```

One command collects from every configured source, re-ranks a **rolling 90-day
window** — "the best reels right now", not "the best ever collected" — diffs the
result against last week's stored snapshot, and writes a fresh set of ideas plus
a dated report in `reports/`.

Every generated idea carries the evidence behind it: the tags, their lift, and
the sample size. That is the whole point — you can disagree with the evidence
rather than with a vibe. The generator only builds on tags at 1.00× or above,
prefers ones that are **rising**, and refuses incompatible pairings (a DJ cam
cannot "blend" sidechain depth).

Two generators are available. The default composes from the signals with no
dependencies. The optional one has Claude write them from the same evidence —
better prose, sharper hooks:

```bash
pip install anthropic && export ANTHROPIC_API_KEY=...
python -m app weekly --llm on
```

It is given only the measured numbers and told not to invent any; lifts on the
cards are re-resolved from the database afterwards, so a generated idea can
never quote a statistic your corpus does not contain. If the package,
credentials or network are missing, the run says so and composes instead.

`.github/workflows/weekly.yml` runs the same job on a schedule without needing a
machine left awake. Full detail: [`docs/WEEKLY.md`](docs/WEEKLY.md).

## Layout

```
app/
  db.py          SQLite schema and queries
  scoring.py     the composite ranking model, incl. the rolling window
  tagging.py     caption -> tags, via data/taxonomy.json
  analytics.py   tag lift, length curve, breakout accounts, audio
  trends.py      week-over-week diffing and the evidence pool
  ideagen.py     compose ideas from measured signals (no dependencies)
  ideagen_llm.py optional: have Claude write them from the same evidence
  weekly.py      the loop — collect, re-rank, diff, generate, report
  schedule.py    crontab install/remove
  pipeline.py    ingest -> tag -> score -> query
  seed.py        labelled synthetic corpus
  server.py      stdlib HTTP dashboard, localhost only
  sources/       files.py · apify.py · graph.py · base.py (normalisation)
web/             index.html · app.js · styles.css — no build step
data/            ideas.json (96 ideas) · taxonomy.json (edit this)
docs/            PLAYBOOK.md · DATA_SOURCES.md · WEEKLY.md
reports/         dated weekly reports, written by the job
tests/           python -m unittest discover tests -v
```

`data/taxonomy.json` is meant to be edited. Every tag you add becomes a
measurable hypothesis: the Signals tab reports the lift of whatever it finds,
so adding a keyword group is how you test a hunch about what works.

## Tests

```bash
python -m unittest discover tests -v      # 55 tests, no dependencies
```

## Adding another provider

Write a module in `app/sources/` that returns records and calls
`base.normalize_many(records, source="yourthing")`. That is the whole contract —
column names are mapped by the alias table in `app/sources/base.py`, so most
providers need no per-field work.

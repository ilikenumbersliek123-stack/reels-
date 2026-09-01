# Reel Tracker — minimal / deep tech

A local app that ranks the top 1000 performing Instagram Reels in the minimal /
deep tech niche, mines them for what the winners have in common, and pairs that
with 96 promotional video ideas and a 90-day plan for going from zero followers.

No dependencies. Python 3.9+ stdlib, SQLite, and a vanilla JS frontend.

```bash
python -m app seed      # load the labelled sample corpus and rank it
python -m app serve     # http://127.0.0.1:8420
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
| **Signals** | What separates winners from also-rans: tag lift, length curve, posting time, breakout accounts, audio. |
| **Ideas** | 96 video ideas, each with the literal on-screen hook, a shot list, and the one metric it is built to move. Filter by goal and effort. |
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
python -m app refresh [--half-life 180]  # recompute scores
python -m app top --limit 25 [--tag format:tutorial] [--max-followers 5000]
python -m app signals                    # pattern mining in the terminal
python -m app export top1000.csv         # spreadsheet of the top 1000
python -m app watch "a,b,c" --kind account
python -m app purge-sample
python -m app serve [--port 8420]
```

All commands take `--db path.db` (default `reels.db`, or `$REELS_DB`).

## Weekly routine

```bash
python -m app collect-own      # your own numbers, including saves and shares
python -m app collect          # the watchlist, if you use a provider
python -m app signals          # what changed
```

Then read the three numbers that matter, in `docs/PLAYBOOK.md` → *Measuring,
without lying to yourself*.

## Layout

```
app/
  db.py          SQLite schema and queries
  scoring.py     the composite ranking model
  tagging.py     caption -> tags, via data/taxonomy.json
  analytics.py   tag lift, length curve, breakout accounts, audio
  pipeline.py    ingest -> tag -> score -> query
  seed.py        labelled synthetic corpus
  server.py      stdlib HTTP dashboard, localhost only
  sources/       files.py · apify.py · graph.py · base.py (normalisation)
web/             index.html · app.js · styles.css — no build step
data/            ideas.json (96 ideas) · taxonomy.json (edit this)
docs/            PLAYBOOK.md · DATA_SOURCES.md
tests/           python -m unittest discover tests -v
```

`data/taxonomy.json` is meant to be edited. Every tag you add becomes a
measurable hypothesis: the Signals tab reports the lift of whatever it finds,
so adding a keyword group is how you test a hunch about what works.

## Tests

```bash
python -m unittest discover tests -v      # 25 tests, no dependencies
```

## Adding another provider

Write a module in `app/sources/` that returns records and calls
`base.normalize_many(records, source="yourthing")`. That is the whole contract —
column names are mapped by the alias table in `app/sources/base.py`, so most
providers need no per-field work.

# The weekly loop

```bash
python -m app weekly                 # run it once, now
python -m app schedule --install     # then every Monday at 09:00
```

One command does four things:

1. **Collect** from every configured source — your own account via the Graph
   API, and your watchlist via Apify. Sources that are not configured are
   skipped with a note; a provider being down costs you that week's new rows,
   not the run.
2. **Re-rank a rolling window.** Default 90 days. This is the difference
   between "the best reels ever collected" and "the best reels right now", and
   it is what makes the top 1000 mean something in week 30.
3. **Diff against last week.** Every run stores its full signal snapshot, so the
   next one can report what moved rather than just what is.
4. **Generate ideas** from the result, and write a dated report to `reports/`.

## What "updated ideas" actually means

Each generated idea carries an `evidence` list naming the tags, lifts and sample
sizes behind it. That is the point of the whole exercise — you can disagree with
the evidence rather than with a vibe. An idea standing on `format:before_after`
at 1.23× with n=9 is a much weaker bet than one at 1.10× with n=200, and the
card shows you which you are looking at.

Selection rules the generator follows:

- Only tags at **1.00× or above** are used. Building a week's plan on a format
  the data says is underperforming is the exact mistake this app exists to stop.
- Tags that are **rising** get picked first. A format climbing from 0.95 to 1.20
  is a better bet than one flat at 1.15 for a month — the second is crowded.
- Formats, hooks and subjects are only combined where they are **compatible**.
  A DJ cam cannot "blend" sidechain depth; a meme does not take a
  "watch it become a track" hook.
- Titles are checked against the 96-idea library and the last four runs, so
  consecutive weeks do not hand you the same thing back.
- One variant per set ships with **no hook text**, as a standing control. You
  cannot tell whether your hook writing helps if every post has a hook.

### Two generators

**Composed (default, no dependencies).** Measured signals choose the format,
hook and subject; a bank of genre-specific material fills them in. Always
available, fully deterministic, explains itself.

**Written by Claude (optional).** Same evidence, better prose and sharper hooks
— writing a hook is a language task and template composition has a ceiling.

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...     # or run `ant auth login`
python -m app weekly --llm on
```

It uses `claude-opus-5` with adaptive thinking and a strict JSON schema, and it
is given only the measured evidence, with an instruction not to invent
statistics. Lifts shown on the cards are re-resolved from the database
afterwards, so a generated idea can never quote a number the corpus does not
contain. Server-side refusal fallbacks are enabled by default; if the package,
the credentials or the network are missing, the run logs why and falls back to
the composed generator rather than failing. Cost is roughly a cent or two per
run — one request in, a dozen ideas out.

`--llm auto` (the default) uses Claude when it is available and composes
otherwise. `--llm off` never calls out.

## Scheduling

**Cron (your machine):**

```bash
python -m app schedule --install                 # Mondays 09:00
python -m app schedule --install --cron "0 7 * * 0" --ideas 16
python -m app schedule --show
python -m app schedule --remove
```

It writes one marked line to your crontab and can remove exactly that line
again. Output goes to `reports/cron.log`. The machine has to be awake.

**GitHub Actions (nothing to keep awake):** `.github/workflows/weekly.yml` runs
the same command on the same schedule and commits the report. Add whichever of
`APIFY_TOKEN`, `IG_ACCESS_TOKEN`, `IG_USER_ID` and `ANTHROPIC_API_KEY` you use
as repository secrets. The database is kept in the Actions cache between runs;
if that cache is ever evicted, the next run reports itself as a first run and
the week-over-week diff resumes the run after.

## Reading the output

`reports/YYYY-MM-DD.md` (and `reports/latest.md`) has the headline, the movers
table, the strongest tags, new breakout accounts, and the full ideas with their
evidence. In the dashboard the same data appears as **Movers** at the top of
Signals, and as **This week** in the Ideas tab.

```bash
python -m app runs        # history of runs
python -m app ideas       # this week's ideas in the terminal
```

## Tuning

| Flag | Default | When to change it |
|---|---|---|
| `--window-days` | 90 | Shorten to 30 if your corpus is large and you want faster-moving signal; lengthen if you collect infrequently and 90 days is too few reels to be stable. |
| `--ideas` | 12 | More than you can film is wasted. Twelve is roughly two weeks of posting. |
| `--limit` | 50 | Reels per collection target. Raising it costs provider credits. |
| `--no-collect` | off | Re-rank and regenerate without spending anything on providers. |

## A caveat worth repeating

While the sample data is still loaded, the movers and lifts are measuring the
synthetic generator's assumptions, not Instagram. `python -m app purge-sample`
once you have real rows. The report says so at the top whenever sample rows are
in the corpus.

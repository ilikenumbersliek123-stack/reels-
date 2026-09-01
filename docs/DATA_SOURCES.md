# Getting real data in

The honest constraint first, because it shapes everything about how this app is
built.

## There is no public API for other people's Reel metrics

Instagram's Graph API returns insights — views, reach, saves, shares, watch time
— **only for accounts you own or manage**. There is no sanctioned endpoint that
hands you the view count of an arbitrary creator's reel. The Hashtag Search API
can return recent or top media for a hashtag, but it is limited to 30 hashtags
per rolling 7 days per app, excludes most metrics, and is aimed at business
accounts monitoring their own tags.

Automated scraping of Instagram is against its Terms of Use. Whether you do it,
or pay a provider who does it, is a decision with real risk attached, and it is
yours to make rather than mine to make quietly on your behalf.

So this app supports three routes. All three feed the same schema and the same
leaderboard.

---

## 1. Manual / assisted collection — always works, zero risk

Keep a spreadsheet. Watch the accounts you care about, and log the reels that
visibly did well. Twenty minutes a week gets you a few hundred rows, which is
enough for the pattern miner to say something useful.

Export to CSV and:

```bash
python -m app import my-reels.csv
```

Column names do not have to match — the importer recognises common aliases
(`play_count`, `videoPlayCount`, `plays`, `views`…). See
`app/sources/base.py` for the full alias table. The minimum useful row:

```csv
url,handle,followers,posted_at,duration,views,likes,comments,caption
https://www.instagram.com/reel/ABC123/,someartist,4200,2026-08-14,22,84000,5100,210,"stop quantising your hats #minimal"
```

`saves` and `shares` are private to the account owner. Leave them blank; the
scorer simply gives that reel no credit on the intent signal rather than
breaking.

A useful trick: you can see view counts on any public reel yourself. The
tedious part is transcribing them, not obtaining them — so collect in bursts,
and prioritise reels from small accounts, which are the most instructive rows
you can have.

---

## 2. A third-party provider (Apify) — fast, costs money, ToS risk is real

```bash
export APIFY_TOKEN=apify_api_...
python -m app watch "someartist,anotherartist" --kind account
python -m app collect --kind account --limit 50
```

`app/sources/apify.py` runs the actor synchronously and normalises whatever
comes back. Notes:

- Fields vary by actor and change over time. `saves` will essentially always be
  0 — no scraper can see it.
- Runs cost credits. Start with a handful of accounts and a low `--limit`.
- Re-running the same targets weekly is what makes the `velocity` column
  meaningful: every collection appends a row to `metric_history`, and two
  observations of the same reel give you its *current* rate rather than its
  lifetime average.
- Other providers work equally well — write a module alongside `apify.py` that
  returns records and calls `base.normalize_many`. That is the entire contract.

---

## 3. Your own account, via the Graph API — the one that matters most

This is sanctioned, free, and returns the metrics nobody else can see:
true reach, saves, shares, and watch time on your own reels.

Requirements: an Instagram professional (Business or Creator) account linked to
a Facebook Page, and a long-lived token with `instagram_basic` and
`instagram_manage_insights`.

```bash
export IG_ACCESS_TOKEN=...
export IG_USER_ID=...        # your Instagram Business account id
python -m app collect-own
```

Your reels then sit in the same leaderboard as everyone else's, scored the same
way. Filter the board to `under 5k followers` and you can see exactly where you
rank against accounts your own size — which is the only comparison that tells
you anything.

Tokens expire. Long-lived user tokens last 60 days and need refreshing; put a
calendar reminder in, or the weekly collection will start failing silently on a
`400`.

---

## Keeping the corpus honest

- `python -m app purge-sample` deletes every synthetic row. Do this as soon as
  you have a few hundred real ones — the sample data encodes assumptions, and
  leaving it in means the Signals tab is partly measuring my guesses rather
  than reality.
- Re-collect the same targets on a schedule (weekly is plenty). Growth over
  time is the most valuable thing this database can hold, and it only exists if
  you observe the same reel twice.
- Keep the corpus to the niche. A leaderboard polluted with general
  music-producer content will tell you to make general music-producer content.

## What to track

Aim for roughly:

- **30–60 accounts** across three tiers: peers (under 5k), the tier above
  (5k–50k), and the names everyone knows. The small tier is the most useful and
  the one people skip.
- **6–10 hashtags**, specific rather than broad: `#rominimal`, `#minimalhouse`,
  `#dawless`, `#deeptech`, `#microhouse`.
- **Your own account**, weekly, without fail.

Seed the watchlist:

```bash
python -m app watch "artist1,artist2,artist3" --kind account
python -m app watch "rominimal,minimalhouse,deeptech" --kind hashtag
```

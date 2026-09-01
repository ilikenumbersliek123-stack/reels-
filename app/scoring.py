"""The ranking model.

Raw view counts alone are a bad leaderboard: a 2M-view reel from a 400k account
tells you less about *what works* than a 180k-view reel from a 900-follower
account. So the composite score blends four percentile-ranked signals:

  reach      log10(views)                     how far it actually went
  virality   views / followers_at_post        how far it went *relative to the
                                              audience it started with* — the
                                              single most useful column when you
                                              are at zero followers
  engagement (likes + 3*comments) / views     did people react
  intent     (saves + 1.5*shares) / views     did people file it away or send it
                                              to a friend, which is what actually
                                              converts a viewer into a follower

Each signal is converted to a percentile rank across the whole corpus before
weighting, so no single unit dominates and no magic scaling constants are
needed. The result is a 0-100 number that is comparable across accounts of
wildly different sizes.

A recency factor then discounts old reels, because the goal is to learn what
the algorithm is rewarding *now*, not in 2022.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Sequence

WEIGHTS = {
    "reach": 0.40,
    "virality": 0.25,
    "engagement": 0.20,
    "intent": 0.15,
}

# Reels below this are noise for pattern-mining and skew the percentiles.
MIN_VIEWS = 500

# Floor on follower count so a brand-new/unknown account cannot produce an
# infinite virality multiple.
FOLLOWER_FLOOR = 50

DEFAULT_HALF_LIFE_DAYS = 180.0

# How much of the final score recency is allowed to move. 0.4 means an ancient
# reel keeps 60% of its earned score rather than being erased.
RECENCY_INFLUENCE = 0.4


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for parse in (
        lambda t: datetime.fromisoformat(t),
        lambda t: datetime.strptime(t, "%Y-%m-%d %H:%M:%S"),
        lambda t: datetime.strptime(t, "%Y-%m-%d"),
    ):
        try:
            dt = parse(text)
        except (ValueError, TypeError):
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def age_days(posted_at: Any, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    dt = _parse_ts(posted_at)
    if dt is None:
        return 30.0
    return max((now - dt).total_seconds() / 86400.0, 0.05)


def percentile_ranks(values: Sequence[float]) -> list[float]:
    """Fractional rank in [0, 1]; ties share the average of their positions."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 / (n - 1)
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def signals(reel: dict[str, Any]) -> dict[str, float]:
    views = max(int(reel.get("views") or 0), 0)
    followers = max(int(reel.get("followers") or 0), FOLLOWER_FLOOR)
    likes = int(reel.get("likes") or 0)
    comments = int(reel.get("comments") or 0)
    saves = int(reel.get("saves") or 0)
    shares = int(reel.get("shares") or 0)
    denom = max(views, 1)
    return {
        "reach": math.log10(views + 1),
        "virality": views / followers,
        "engagement": (likes + 3 * comments) / denom,
        "intent": (saves + 1.5 * shares) / denom,
    }


def velocity(reel: dict[str, Any], history: Sequence[dict[str, Any]] | None = None) -> float:
    """Views per day.

    Two snapshots of the same reel give the real current rate; a single snapshot
    falls back to lifetime average. The distinction matters — a reel doing 40k/day
    three weeks after posting is a very different animal from one that did 800k
    on day one and flatlined.
    """
    if history and len(history) >= 2:
        first, last = history[0], history[-1]
        t0, t1 = _parse_ts(first.get("collected_at")), _parse_ts(last.get("collected_at"))
        if t0 and t1:
            span = (t1 - t0).total_seconds() / 86400.0
            if span > 0.02:
                gained = (last.get("views") or 0) - (first.get("views") or 0)
                return max(gained / span, 0.0)
    return (reel.get("views") or 0) / age_days(reel.get("posted_at"))


def recency_factor(posted_at: Any, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (age_days(posted_at) / half_life_days)


def rank_corpus(
    reels: Sequence[dict[str, Any]],
    histories: dict[str, Sequence[dict[str, Any]]] | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    min_views: int = MIN_VIEWS,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Score every eligible reel and return rows ordered best-first, rank 1..N."""
    histories = histories or {}
    eligible = [r for r in reels if (r.get("views") or 0) >= min_views]
    if not eligible:
        return []

    computed = [signals(r) for r in eligible]
    ranks = {
        key: percentile_ranks([c[key] for c in computed])
        for key in WEIGHTS
    }

    stamp = (now or datetime.now(timezone.utc)).isoformat()
    rows: list[dict[str, Any]] = []
    for i, reel in enumerate(eligible):
        pct = {key: ranks[key][i] for key in WEIGHTS}
        raw = 100.0 * sum(WEIGHTS[k] * pct[k] for k in WEIGHTS)
        fresh = recency_factor(reel.get("posted_at"), half_life_days)
        final = raw * ((1.0 - RECENCY_INFLUENCE) + RECENCY_INFLUENCE * fresh)
        sig = computed[i]
        rows.append(
            {
                "reel_id": reel["id"],
                "score": round(final, 3),
                "raw_score": round(raw, 3),
                "pct_reach": round(pct["reach"], 4),
                "pct_virality": round(pct["virality"], 4),
                "pct_engagement": round(pct["engagement"], 4),
                "pct_intent": round(pct["intent"], 4),
                "reach_multiple": round(sig["virality"], 3),
                "engagement_rate": round(sig["engagement"], 5),
                "intent_rate": round(sig["intent"], 5),
                "velocity": round(velocity(reel, histories.get(reel["id"])), 1),
                "computed_at": stamp,
            }
        )

    rows.sort(key=lambda r: r["score"], reverse=True)
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows

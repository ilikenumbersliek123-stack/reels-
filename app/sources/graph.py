"""Instagram Graph API — your own account only.

This is the sanctioned path, and it is the one that matters most once you start
posting: it returns true insights (reach, saves, shares, average watch time)
for your own Reels, which no scraper can see. Feeding your own reels into the
same leaderboard as the corpus you track is the point — you get to see where
your work actually sits against the field.

Requirements: an Instagram professional (Business or Creator) account linked to
a Facebook Page, and a long-lived token with instagram_basic +
instagram_manage_insights.

    export IG_ACCESS_TOKEN=...
    export IG_USER_ID=...            # the Instagram Business account id
    python -m app collect-own
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import normalize_many

API_VERSION = os.environ.get("IG_API_VERSION", "v21.0")
API_ROOT = f"https://graph.facebook.com/{API_VERSION}"
TIMEOUT = 60

MEDIA_FIELDS = (
    "id,caption,media_type,media_product_type,permalink,timestamp,"
    "like_count,comments_count"
)
# Reels-specific metrics. `saved` and `shares` are only available here — this is
# the whole reason to connect your own account.
INSIGHT_METRICS = "views,reach,likes,comments,shares,saved,total_interactions"


class GraphNotConfigured(RuntimeError):
    pass


def _credentials() -> tuple[str, str]:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("IG_USER_ID", "").strip()
    if not token or not user_id:
        raise GraphNotConfigured(
            "Set IG_ACCESS_TOKEN and IG_USER_ID to pull your own Reel insights."
        )
    return token, user_id


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{API_ROOT}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"Graph API HTTP {exc.code}: {detail}") from exc


def account_profile() -> dict[str, Any]:
    token, user_id = _credentials()
    return _get(user_id, {"fields": "username,followers_count,media_count", "access_token": token})


def fetch_own_reels(limit: int = 100) -> list[dict[str, Any]]:
    token, user_id = _credentials()
    profile = account_profile()
    followers = int(profile.get("followers_count") or 0)
    username = profile.get("username") or "me"

    page = _get(f"{user_id}/media", {"fields": MEDIA_FIELDS, "limit": min(limit, 100), "access_token": token})
    records: list[dict[str, Any]] = []

    for media in page.get("data", []):
        if str(media.get("media_product_type") or "").upper() not in ("REELS", "CLIPS"):
            continue
        record: dict[str, Any] = {
            "id": media.get("id"),
            "url": media.get("permalink"),
            "handle": username,
            "followers": followers,
            "posted_at": media.get("timestamp"),
            "caption": media.get("caption") or "",
            "likes": media.get("like_count") or 0,
            "comments": media.get("comments_count") or 0,
        }
        try:
            insights = _get(
                f"{media['id']}/insights", {"metric": INSIGHT_METRICS, "access_token": token}
            )
        except RuntimeError:
            insights = {"data": []}

        for metric in insights.get("data", []):
            name = metric.get("name")
            values = metric.get("values") or [{}]
            value = values[0].get("value", 0)
            if name in ("views", "reach"):
                record["views"] = max(int(record.get("views") or 0), int(value))
            elif name == "saved":
                record["saves"] = int(value)
            elif name == "shares":
                record["shares"] = int(value)
            elif name in ("likes", "comments"):
                record[name] = max(int(record.get(name) or 0), int(value))
        records.append(record)
        if len(records) >= limit:
            break

    return normalize_many(records, source="graph:own")

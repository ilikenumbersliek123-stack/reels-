"""Optional collection through Apify's Instagram scraper actors.

Why a third party at all: Instagram's Graph API returns insights only for
accounts you own or manage. There is no sanctioned endpoint that hands you view
counts for other creators' Reels. Compliant options are therefore (a) a data
provider that carries the terms-of-service risk and licensing itself, or (b)
manual collection. This module covers (a); files.py covers (b).

Set APIFY_TOKEN in the environment to use it. Without a token every call raises
before touching the network, and the rest of the app carries on unaffected.

Run cost is yours, and scraped fields vary by actor — `saves` in particular is
private to the account owner and will usually come back as 0, which the scorer
handles (it simply contributes nothing to the intent signal).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Sequence

from .base import normalize_many

API_ROOT = "https://api.apify.com/v2"
DEFAULT_ACTOR = os.environ.get("APIFY_ACTOR", "apify~instagram-scraper")
TIMEOUT = 300


class ApifyNotConfigured(RuntimeError):
    pass


def _token() -> str:
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise ApifyNotConfigured(
            "APIFY_TOKEN is not set. Export a token, or collect with "
            "`python -m app import <file.csv>` instead."
        )
    return token


def _post(url: str, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8") or "[]")


def run_actor(
    targets: Sequence[str],
    kind: str = "account",
    limit_per_target: int = 50,
    actor: str = DEFAULT_ACTOR,
) -> list[dict[str, Any]]:
    """Run the actor synchronously and return normalised reels.

    `kind` is 'account' or 'hashtag'. `targets` are bare handles or tags — the
    leading @ or # is optional.
    """
    token = _token()
    cleaned = [t.lstrip("@#").strip() for t in targets if t.strip()]
    if not cleaned:
        return []

    payload: dict[str, Any] = {
        "resultsType": "posts",
        "resultsLimit": limit_per_target,
        "searchType": "hashtag" if kind == "hashtag" else "user",
        "addParentData": True,
    }
    if kind == "hashtag":
        payload["hashtags"] = cleaned
        payload["directUrls"] = [f"https://www.instagram.com/explore/tags/{t}/" for t in cleaned]
    else:
        payload["username"] = cleaned
        payload["directUrls"] = [f"https://www.instagram.com/{t}/" for t in cleaned]

    url = f"{API_ROOT}/acts/{actor}/run-sync-get-dataset-items?token={urllib.parse.quote(token)}"
    try:
        items = _post(url, payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"Apify returned HTTP {exc.code}: {detail}") from exc

    if not isinstance(items, list):
        return []

    reels = [i for i in items if _is_reel(i)]
    return normalize_many(reels, source=f"apify:{kind}")


def _is_reel(item: dict[str, Any]) -> bool:
    product = str(item.get("productType") or item.get("type") or "").lower()
    if "clips" in product or "reel" in product or "video" in product:
        return True
    return bool(item.get("videoPlayCount") or item.get("videoViewCount"))

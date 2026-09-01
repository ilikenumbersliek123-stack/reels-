"""Optional: have Claude write the week's ideas from the measured signals.

The deterministic generator in `ideagen.py` is the default and always works.
This module is the upgrade path — same input (the evidence pool), same output
schema, better prose and sharper hooks, because writing a hook is a language
task and template composition has a ceiling.

It is opt-in and isolated on purpose: `anthropic` is imported inside the
function, so the rest of the app stays dependency-free and a missing package
degrades to the deterministic generator instead of crashing the weekly job.

    pip install anthropic
    export ANTHROPIC_API_KEY=...          # or run `ant auth login`
    python -m app weekly --llm on

Cost is roughly a cent or two per run — one request, a small brief in, a dozen
ideas out.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Sequence

MODEL = "claude-opus-5"
MAX_TOKENS = 16000

GOALS = ["reach", "saves", "shares", "comments", "follows"]
EFFORTS = ["low", "med", "high"]

SYSTEM = """You write short-form video concepts for an underground electronic music artist \
in the minimal / deep tech scene (rominimal, microhouse, tech house, dub-influenced house). \
They are growing an Instagram account from a small base and film everything themselves on a phone.

You will be given real measured performance data from a corpus of reels in this niche: which \
content tags are outperforming the median, how sample sizes compare, what moved since last week, \
and which small accounts are getting disproportionate reach.

Rules:
- Every idea must be grounded in the supplied evidence. Name the tags you used in evidence_tags. \
Do not invent statistics or reference data you were not given.
- Ideas must be filmable this week, alone, with a phone and the gear a bedroom producer owns. \
No crew, no actors, no location permits, no drone shots.
- `hook` is the LITERAL on-screen text for the first 1.5 seconds. Lowercase, seven words maximum, \
no hashtags, no emoji. It must work on a muted phone. An empty string is allowed and correct when \
the idea should open on the visual instead.
- `shots` is exactly three shots. Each names what is on screen, not what it means.
- `why` is one or two sentences explaining the mechanism — why this earns the goal metric. \
Reference the measured lift where it is the reason.
- Be specific to this genre. "Make a tutorial" is useless; "solo the third shaker layer and \
show the velocity lane" is the job. Use real terms of art: swing percentage, ghost notes, dub \
chords, rolling basslines, resampling, dawless, LUFS, bar counts.
- Do not repeat or lightly reword any title in the avoid list.
- Vary the formats and goals across the set. Do not write twelve tutorials."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "shots": {"type": "array", "items": {"type": "string"}},
                    "why": {"type": "string"},
                    "goal": {"type": "string", "enum": GOALS},
                    "effort": {"type": "string", "enum": EFFORTS},
                    "length_s": {"type": "string"},
                    "cta": {"type": "string"},
                    "evidence_tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "hook", "shots", "why", "goal", "effort", "length_s", "cta", "evidence_tags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}


class LLMNotConfigured(RuntimeError):
    pass


def available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _brief(pool: dict[str, Any], count: int, avoid_titles: Sequence[str]) -> str:
    def rows(key: str) -> list[dict[str, Any]]:
        return [
            {"tag": r["tag"], "lift": r["lift"], "n": r["count"], "median_views": r.get("median_views")}
            for r in pool.get(key, [])
        ]

    payload = {
        "corpus": pool.get("summary", {}),
        "strongest_formats": rows("formats"),
        "strongest_hooks": rows("hooks"),
        "strongest_subjects": rows("subjects"),
        "underperforming_formats": rows("weak_formats"),
        "best_length_bucket": pool.get("best_length"),
        "length_curve": pool.get("lengths"),
        "rising_since_last_week": [
            {"tag": r["tag"], "lift": r["lift"], "was": r["previous_lift"], "change": r["change"], "n": r["count"]}
            for r in pool.get("rising", [])
        ],
        "falling_since_last_week": [
            {"tag": r["tag"], "lift": r["lift"], "was": r["previous_lift"], "change": r["change"], "n": r["count"]}
            for r in pool.get("falling", [])
        ],
        "new_tags_this_week": pool.get("new_tags", []),
        "breakout_small_accounts": [
            {"followers": b["followers"], "best_reach_multiple": b["best_reach_multiple"], "tags": b["top_tags"]}
            for b in pool.get("breakouts", [])
        ],
    }
    return (
        f"Here is this week's measured data for the minimal / deep tech reel corpus.\n\n"
        f"```json\n{json.dumps(payload, indent=2, default=str)}\n```\n\n"
        f"Write {count} video ideas grounded in it.\n\n"
        f"Do not repeat these existing titles:\n"
        + "\n".join(f"- {t}" for t in avoid_titles[:120])
    )


def _request(client: Any, prompt: str, use_fallbacks: bool) -> Any:
    """One call. `use_fallbacks` adds server-side refusal fallbacks (beta)."""
    common: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [{"role": "user", "content": prompt}],
    }
    if use_fallbacks:
        return client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **common
        )
    return client.messages.create(**common)


def generate(
    pool: dict[str, Any],
    count: int = 12,
    run_id: int = 0,
    avoid_titles: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Ask Claude for `count` ideas. Raises LLMNotConfigured if unusable."""
    try:
        import anthropic
    except ImportError as exc:
        raise LLMNotConfigured("anthropic package not installed — `pip install anthropic`") from exc

    try:
        client = anthropic.Anthropic()
    except Exception as exc:  # missing/!invalid credentials surface here
        raise LLMNotConfigured(f"could not build an Anthropic client: {exc}") from exc

    prompt = _brief(pool, count, avoid_titles)

    try:
        response = _request(client, prompt, use_fallbacks=True)
    except (anthropic.BadRequestError, TypeError):
        # Older SDK or an account without the fallback beta: same request, no fallbacks.
        response = _request(client, prompt, use_fallbacks=False)
    except anthropic.AuthenticationError as exc:
        raise LLMNotConfigured(f"Anthropic credentials rejected: {exc}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMNotConfigured(f"could not reach the Anthropic API: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        details = getattr(response, "stop_details", None)
        raise LLMNotConfigured(f"request declined ({getattr(details, 'category', 'unknown')})")

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text.strip():
        raise LLMNotConfigured("empty response")

    return _adopt(json.loads(text).get("ideas", []), pool, run_id)


def _adopt(raw: Sequence[dict[str, Any]], pool: dict[str, Any], run_id: int) -> list[dict[str, Any]]:
    """Validate the model's output and attach the real numbers behind each tag.

    Lifts are resolved from our own pool rather than taken from the response, so
    a generated idea can never quote a statistic the corpus does not contain.
    """
    by_tag = {
        r["tag"]: r
        for key in ("formats", "hooks", "subjects", "ctas", "rising")
        for r in pool.get(key, [])
    }
    rising = {r["tag"] for r in pool.get("rising", [])}

    out: list[dict[str, Any]] = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for item in raw:
        shots = [str(s) for s in item.get("shots", []) if str(s).strip()][:4]
        if not item.get("title") or not shots:
            continue
        evidence = [
            {
                "tag": tag,
                "lift": by_tag[tag]["lift"],
                "count": by_tag[tag]["count"],
                "rising": tag in rising,
            }
            for tag in item.get("evidence_tags", [])
            if tag in by_tag
        ]
        out.append(
            {
                "id": f"gen-{run_id:03d}-{len(out) + 1:02d}",
                "category": "generated",
                "title": str(item["title"])[:120],
                "hook": str(item.get("hook", ""))[:120],
                "shots": shots,
                "why": str(item.get("why", "")),
                "goal": item["goal"] if item.get("goal") in GOALS else "reach",
                "effort": item["effort"] if item.get("effort") in EFFORTS else "low",
                "length_s": str(item.get("length_s", "12-25")),
                "cta": str(item.get("cta", "")),
                "evidence": evidence,
                "generated_on": stamp,
                "source": "claude",
            }
        )
    if not out:
        raise LLMNotConfigured("response contained no usable ideas")
    return out

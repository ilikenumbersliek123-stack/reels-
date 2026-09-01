"""Turn this week's measured signals into concrete video ideas.

The rule this module follows: **every generated idea must be traceable to a
number**. Each one carries an `evidence` list naming the tags, lifts and sample
sizes that produced it, so you can disagree with the machine on the evidence
rather than on vibes. An idea whose evidence is one tag at n=6 should be treated
very differently from one standing on three tags at n=200, and the card shows
you which is which.

Composition is deliberate rather than random: the measured signals choose the
*format*, *hook* and *subject*, and the banks below supply the genre-specific
material to instantiate them. That keeps the output specific to minimal / deep
tech instead of the generic "post a tutorial!" advice a pure statistics readout
would give you.
"""

from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

# ---------------------------------------------------------------- the banks

# Concrete, filmable material per format. `shots` takes the chosen subject so
# the shot list is about that subject rather than a generic template.
FORMAT_BANK: dict[str, dict[str, Any]] = {
    "format:tutorial": {
        "hooks": ['hook:controversy', 'hook:numbered_list', 'hook:question', 'hook:wait_for_it'],
        "subjects": ['subject:groove', 'subject:bass', 'subject:sound_design', 'subject:arrangement', 'subject:mixing'],
        "label": "tutorial",
        "effort": "med",
        "goal": "saves",
        "titles": ["How I fix {subject}", "The {subject} move, in one take", "{subject}, explained properly"],
        "shots": lambda s: [
            f"Play the loop with {s} obviously wrong — let it sound bad for two seconds",
            f"Make the single change on camera, with the parameter visible on screen",
            "Play the fixed loop, phone-speaker loud, and stop dead on the last hit",
        ],
    },
    "format:before_after": {
        "hooks": ['hook:wait_for_it', 'hook:question', 'hook:controversy'],
        "subjects": ['subject:groove', 'subject:bass', 'subject:sound_design', 'subject:mixing'],
        "label": "before / after",
        "effort": "low",
        "goal": "shares",
        "titles": ["{subject}: before and after", "With vs without {subject}", "Same 8 bars, {subject} switched off"],
        "shots": lambda s: [
            f"Version A — the loop with {s} removed entirely",
            f"Hard cut, no transition, to version B with {s} back in",
            "Split screen of both, waveforms visible, so the difference is seen as well as heard",
        ],
    },
    "format:gear": {
        "hooks": ['hook:transformation', 'hook:identity', 'hook:numbered_list', 'hook:none'],
        "subjects": ['subject:groove', 'subject:bass', 'subject:sound_design'],
        "label": "hardware",
        "effort": "low",
        "goal": "reach",
        "titles": ["One box, {subject}", "{subject} on hardware only", "No computer: {subject}"],
        "shots": lambda s: [
            "Locked-off overhead of the machine, hands only, no face",
            f"Build {s} live — one take, no cuts, let the mistakes stay in",
            "Pull focus to the sequencer lights as the loop settles",
        ],
    },
    "format:studio_session": {
        "hooks": ['hook:transformation', 'hook:identity', 'hook:none'],
        "subjects": ['subject:groove', 'subject:sound_design', 'subject:arrangement', 'subject:bass'],
        "label": "studio session",
        "effort": "low",
        "goal": "follows",
        "titles": ["Session: {subject}", "Working on {subject} at 2am", "{subject} — work in progress"],
        "shots": lambda s: [
            "Wide of the room, screen glow, no talking",
            f"Close on the hands and the screen while {s} takes shape",
            "End on the loop running with your hands off everything",
        ],
    },
    "format:dj_cam": {
        "stage": True,
        "hooks": ['hook:wait_for_it', 'hook:identity', 'hook:none'],
        "subjects": ['subject:groove', 'subject:bass', 'subject:arrangement'],
        "label": "DJ cam",
        "effort": "low",
        "goal": "reach",
        "titles": ["The blend where {subject} lands", "Booth cam: {subject}", "Playing out {subject}"],
        "shots": lambda s: [
            "Overhead of the decks, both records visible, EQ moves in frame",
            f"Hold on the moment {s} takes over the mix",
            "Cut to the floor for the last three seconds",
        ],
    },
    "format:crowd_cam": {
        "stage": True,
        "hooks": ['hook:wait_for_it', 'hook:identity', 'hook:none'],
        "subjects": ['subject:groove', 'subject:bass', 'subject:arrangement'],
        "label": "crowd",
        "effort": "low",
        "goal": "shares",
        "titles": ["The floor when {subject} came back", "6am, {subject}", "{subject} on a real system"],
        "shots": lambda s: [
            "Phone held low, dark room, one light source",
            f"The moment {s} drops back in — do not cut away from the reaction",
            "Hold on one person dancing for the last two seconds",
        ],
    },
    "format:meme": {
        "hooks": ['hook:identity', 'hook:controversy', 'hook:none'],
        "subjects": ['subject:career', 'subject:mixing', 'subject:arrangement'],
        "label": "meme",
        "effort": "low",
        "goal": "shares",
        "titles": ["POV: {subject}", "Nobody warns you about {subject}", "Nobody talks about {subject}"],
        "shots": lambda s: [
            "Staged cold open, one static shot, no setup line",
            f"The joke about {s} lands by second four",
            "Cut to black on the punchline — no outro, no logo",
        ],
    },
    "format:plugin_daw": {
        "hooks": ['hook:numbered_list', 'hook:controversy', 'hook:transformation', 'hook:question'],
        "subjects": ['subject:sound_design', 'subject:mixing', 'subject:bass', 'subject:groove'],
        "label": "in the box",
        "effort": "low",
        "goal": "saves",
        "titles": ["{subject} with stock plugins only", "Three plugins for {subject}", "{subject} without spending anything"],
        "shots": lambda s: [
            "Dry loop, plugin chain empty, everything visible on screen",
            f"Add each plugin one at a time with the setting readable — all aimed at {s}",
            "Wet loop, then the plugin list on screen for people to screenshot",
        ],
    },
    "format:track_id": {
        "hooks": ['hook:identity', 'hook:wait_for_it', 'hook:none'],
        "subjects": ['subject:groove', 'subject:bass', 'subject:sound_design'],
        "label": "track ID",
        "effort": "low",
        "goal": "comments",
        "titles": ["ID: the one with {subject}", "Unreleased — {subject}", "The one everyone asked about: {subject}"],
        "shots": lambda s: [
            "Open on the loudest eight bars, no intro",
            f"Text on screen naming what makes it — {s}",
            "End mid-phrase so the loop restarts seamlessly",
        ],
    },
    "format:talking_head": {
        "hooks": ['hook:controversy', 'hook:numbered_list', 'hook:identity'],
        "subjects": ['subject:career', 'subject:mixing', 'subject:arrangement'],
        "label": "to camera",
        "effort": "med",
        "goal": "follows",
        "titles": ["My honest take on {subject}", "Why {subject} matters more than gear", "What nobody says about {subject}"],
        "shots": lambda s: [
            "Straight to camera in the studio, four seconds maximum, no greeting",
            f"Cut to the screen or the gear and demonstrate {s} rather than describing it",
            "Back to camera for one sentence that lands the point",
        ],
    },
    "format:visualizer": {
        "hooks": ['hook:none', 'hook:identity'],
        "subjects": ['subject:groove', 'subject:sound_design'],
        "label": "visual",
        "effort": "med",
        "goal": "reach",
        "titles": ["{subject}, rendered", "Audio-reactive: {subject}", "Watching {subject}"],
        "shots": lambda s: [
            "Monochrome render, one moving element, no text",
            f"The visual reacts only to {s} so the eye learns to hear it",
            "Loop the last frame into the first exactly",
        ],
    },
}

# Genre-specific material. This is where the output stays about minimal / deep
# tech rather than about "content".
# NOTE: subject:career holds situations rather than musical elements, so only the
# conversational formats (meme, talking head) list it as compatible — a DJ cam
# cannot "blend" playing to an empty room.
SUBJECT_BANK: dict[str, list[str]] = {
    "subject:groove": [
        "the shaker layer", "swing at 56%", "ghost notes on the percussion bus",
        "the off-beat hat", "the third perc layer nobody consciously hears",
        "a muted beat on the turnaround", "the groove template off an old record",
    ],
    "subject:bass": [
        "the rolling bassline", "the kick and bass sharing one EQ move",
        "sub content below 40Hz", "the bass note that changes on bar 9",
        "sidechain depth", "a bassline built from one filtered sample",
    ],
    "subject:sound_design": [
        "a dub chord stab from one piano note", "a hi-hat made from a train recording",
        "five rounds of resampling", "room tone as a texture bed",
        "a delay throw on the off-beat", "a field recording from the walk home",
    ],
    "subject:arrangement": [
        "the first 32 bars", "the breakdown that removes instead of adds",
        "turning 8 bars into six minutes", "the second variation that stops it getting boring",
        "the transition nobody notices", "what happens after the drop",
    ],
    "subject:mixing": [
        "headroom before the master", "the low end at −14 LUFS",
        "saturation on the drum bus", "mono below 120Hz",
        "why it sounds thin on a phone", "the mix decision that took twenty hours",
    ],
    "subject:career": [
        "the demo that got a reply", "playing to an empty room",
        "the eight months a label ghosted me", "why the first track never gets signed",
        "pricing a first gig", "the promo email that actually worked",
    ],
}

# Hook templates. `{subject}` is filled from the subject bank; templates are
# written to survive being read at 2× speed on a muted phone.
HOOK_BANK: dict[str, list[str]] = {
    "hook:wait_for_it": ["wait for {subject}", "wait for it — {subject}", "keep watching, {subject} comes back"],
    "hook:controversy": ["stop ignoring {subject}", "you are getting {subject} wrong", "{subject} is why it sounds amateur"],
    "hook:numbered_list": ["3 things about {subject}", "1 change: {subject}", "one fix: {subject}"],
    "hook:transformation": ["{subject} — from nothing to this", "i turned one sample into {subject}", "watch {subject} become a track"],
    "hook:identity": ["if you make minimal, {subject} is for you", "iykyk: {subject}", "this one is for people who care about {subject}"],
    "hook:question": ["can you hear {subject}?", "which one has {subject}?", "does {subject} actually matter?"],
    "hook:none": [""],
}

# Subject phrases that only make sense with a screen and a session open. A DJ
# cam or a crowd shot can show a bassline arriving; it cannot show two channels
# sharing an EQ move. Formats flagged "stage" draw only from the rest.
STUDIO_ONLY = {
    "the kick and bass sharing one EQ move", "sidechain depth", "sub content below 40Hz",
    "a bassline built from one filtered sample", "the groove template off an old record",
    "ghost notes on the percussion bus", "swing at 56%",
    "headroom before the master", "the low end at −14 LUFS", "saturation on the drum bus",
    "mono below 120Hz", "why it sounds thin on a phone", "the mix decision that took twenty hours",
    "five rounds of resampling", "room tone as a texture bed",
    "a dub chord stab from one piano note", "a hi-hat made from a train recording",
    "turning 8 bars into six minutes", "the second variation that stops it getting boring",
}

CTA_BY_GOAL = {
    "saves": "Save this before your next session",
    "shares": "Send this to the producer who needs it",
    "comments": "A or B in the comments",
    "follows": "Follow — this is part of a series",
    "reach": "",
}


def _length_from_bucket(bucket: str | None) -> str:
    if not bucket:
        return "12-25"
    match = re.findall(r"\d+", bucket)
    if len(match) >= 2:
        return f"{match[0]}-{match[1]}"
    return f"{match[0]}-{int(match[0]) + 20}" if match else "12-25"


def _normalise(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3}


def _too_similar(title: str, existing: Sequence[str], threshold: float = 0.6) -> bool:
    words = _normalise(title)
    if not words:
        return False
    for other in existing:
        other_words = _normalise(other)
        if not other_words:
            continue
        overlap = len(words & other_words) / max(len(words), 1)
        if overlap >= threshold:
            return True
    return False


def _pick(rows: Sequence[dict[str, Any]], bank: dict[str, Any], fallback: str) -> list[str]:
    """Measured tags we have material for, best first, with a safe default.

    Tags below 1.00× are dropped while anything above it remains — building a
    week's plan on a format the data says is underperforming is exactly the
    mistake this app exists to stop.
    """
    usable = [r["tag"] for r in rows if r["tag"] in bank]
    winning = [r["tag"] for r in rows if r["tag"] in bank and r["lift"] >= 1.0]
    return winning or usable or [fallback]


def _compatible(candidates: Sequence[str], allowed: Sequence[str], bank: dict[str, Any]) -> list[str]:
    """Measured order, restricted to what actually works with this format.

    Without this the round-robin cheerfully pairs a meme with a "watch it become
    a track" hook, or a DJ cam with sidechain depth. Both are nonsense to film.
    """
    ranked = [tag for tag in candidates if tag in allowed]
    return ranked or [tag for tag in allowed if tag in bank][:1]


def _goal_for(tag_row: dict[str, Any] | None, summary: dict[str, Any], default: str) -> str:
    """Let the measured behaviour of the tag choose what the idea optimises for.

    Each comparison is against the corpus median for that same metric, so a
    format only claims a goal when it genuinely beats the field on it.
    """
    if not tag_row:
        return default
    intent = tag_row.get("median_intent_rate") or 0
    reach = tag_row.get("median_reach_multiple") or 0
    median_intent = summary.get("median_intent_rate") or 0
    median_reach = summary.get("median_reach_multiple") or 0

    beats_intent = median_intent > 0 and intent > median_intent
    beats_reach = median_reach > 0 and reach > median_reach
    if beats_intent and not beats_reach:
        return "saves"
    if beats_reach and not beats_intent:
        return "reach"
    return default


def generate(
    pool: dict[str, Any],
    count: int = 12,
    run_id: int = 0,
    avoid_titles: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Compose `count` ideas from the evidence pool built by `trends.evidence_pool`."""
    rng = random.Random(f"reels-{run_id}-{pool.get('summary', {}).get('reels', 0)}")

    # Tags that are climbing get first pick — a format on the way up is a better
    # bet than one that has been saturated at the top for a month.
    rising = {r["tag"] for r in pool.get("rising", [])}

    def order(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(rows, key=lambda r: (r["tag"] in rising, r["lift"]), reverse=True)

    formats = _pick(order(pool.get("formats", [])), FORMAT_BANK, "format:tutorial")
    hooks = _pick(order(pool.get("hooks", [])), HOOK_BANK, "hook:wait_for_it")
    subjects = _pick(order(pool.get("subjects", [])), SUBJECT_BANK, "subject:groove")

    by_tag = {r["tag"]: r for group in ("formats", "hooks", "subjects") for r in pool.get(group, [])}
    summary = pool.get("summary", {})
    length = _length_from_bucket((pool.get("best_length") or {}).get("bucket"))
    best_length = pool.get("best_length") or {}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Some formats carry a no-hook-text variant, which doubles as a standing
    # control against your own hook writing — you cannot tell whether the text
    # is helping if every post has it.
    hook_cycle = list(hooks) + ["hook:none"]

    ideas: list[dict[str, Any]] = []
    used_titles = list(avoid_titles)
    attempts = 0

    while len(ideas) < count and attempts < count * 8:
        i = attempts
        attempts += 1
        fmt_tag = formats[i % len(formats)]
        fmt = FORMAT_BANK[fmt_tag]

        # Rotate through each format's own compatible options rather than a
        # global cycle, so the pairings stay filmable.
        fmt_hooks = _compatible(hook_cycle, fmt["hooks"], HOOK_BANK)
        fmt_subjects = _compatible(subjects, fmt["subjects"], SUBJECT_BANK)
        hook_tag = fmt_hooks[(i // max(len(formats), 1)) % len(fmt_hooks)]
        subj_tag = fmt_subjects[(i // max(len(formats), 1) + i) % len(fmt_subjects)]

        phrases = SUBJECT_BANK[subj_tag]
        if fmt.get("stage"):
            phrases = [p for p in phrases if p not in STUDIO_ONLY] or phrases
        subject = rng.choice(phrases)
        title = rng.choice(fmt["titles"]).format(subject=subject)
        title = title[0].upper() + title[1:]

        if _too_similar(title, used_titles):
            continue

        hook = rng.choice(HOOK_BANK[hook_tag]).format(subject=subject)
        goal = _goal_for(by_tag.get(fmt_tag), summary, fmt["goal"])

        evidence = []
        for tag in (fmt_tag, hook_tag, subj_tag):
            row = by_tag.get(tag)
            if row:
                evidence.append(
                    {
                        "tag": tag,
                        "lift": row["lift"],
                        "count": row["count"],
                        "rising": tag in rising,
                    }
                )
        if best_length:
            evidence.append(
                {
                    "tag": best_length["bucket"],
                    "lift": None,
                    "count": best_length["count"],
                    "median_score": best_length["median_score"],
                    "rising": False,
                }
            )

        ideas.append(
            {
                "id": f"gen-{run_id:03d}-{len(ideas) + 1:02d}",
                "category": "generated",
                "title": title,
                "hook": hook,
                "shots": fmt["shots"](subject),
                "why": _rationale(fmt, fmt_tag, hook_tag, subj_tag, by_tag, rising, best_length),
                "goal": goal,
                "effort": fmt["effort"],
                "length_s": length,
                "cta": CTA_BY_GOAL.get(goal, ""),
                "evidence": evidence,
                "generated_on": stamp,
                "source": "measured",
            }
        )
        used_titles.append(title)

    return ideas


def _rationale(
    fmt: dict[str, Any],
    fmt_tag: str,
    hook_tag: str,
    subj_tag: str,
    by_tag: dict[str, dict[str, Any]],
    rising: set[str],
    best_length: dict[str, Any],
) -> str:
    clauses: list[str] = []
    fmt_row = by_tag.get(fmt_tag)
    if fmt_row:
        verb = "climbing to" if fmt_tag in rising else "running at"
        lead = (
            f"{fmt['label'].capitalize()} posts are {verb} {fmt_row['lift']:.2f}× the corpus "
            f"median across {fmt_row['count']} reels in this window"
        )
    else:
        lead = f"{fmt['label'].capitalize()} is the strongest format with material available"

    hook_row = by_tag.get(hook_tag)
    if hook_tag == "hook:none":
        clauses.append("it ships without hook text, as a control against your own hook writing")
    elif hook_row:
        clauses.append(
            f"{hook_tag.split(':')[1].replace('_', ' ')} hooks are at {hook_row['lift']:.2f}×"
        )

    subj_row = by_tag.get(subj_tag)
    if subj_row:
        clauses.append(
            f"{subj_tag.split(':')[1].replace('_', ' ')} is at {subj_row['lift']:.2f}× "
            f"on {subj_row['count']} reels"
        )

    if best_length:
        clauses.append(
            f"and {best_length['bucket'].replace('len:', '')} is the strongest length bucket"
        )

    if not clauses:
        return lead + "."
    return f"{lead}. Pairing that with what else the week measured: " + ", ".join(clauses) + "."

"""Synthetic sample corpus.

IMPORTANT: every row this module produces is fabricated. The handles are not
real people, and the numbers are not real Instagram metrics. It exists so the
dashboard, the scorer and the pattern miner have something to chew on the
minute you clone the repo, and so you can verify the maths before you spend
money on collection.

The generator deliberately bakes in effects (educational content earns saves,
memes earn shares, a clear hook beats a vague one, sub-20-second clips retain
better) so the Signals tab shows real structure. Those effects are *priors from
short-form video generally*, not measurements of the minimal / deep tech niche.
Treat anything the Signals tab tells you while `is_sample` rows dominate the
corpus as a demo of the method, not a finding. Replace it with real data —
`python -m app purge-sample` wipes it in one command.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from .sources.base import normalize_many

RNG_SEED = 7

# (label, body templates, duration range, latent lift, engagement profile)
FORMATS: list[dict[str, Any]] = [
    {
        "name": "tutorial",
        "lift": 1.32,
        "duration": (18, 52),
        "profile": {"er": 0.055, "save": 0.031, "share": 0.014, "comment": 0.006},
        "bodies": [
            "how to get that rolling bassline without muddying the low end",
            "the shaker trick that makes a minimal groove breathe — step by step",
            "how i turn one 2 bar loop into a 6 minute deep tech track",
            "3 ways to add swing to stock hats in ableton",
            "the ghost note technique behind every rominimal percussion loop",
            "mixing tip: eq the kick and bass together, never separately",
            "how to make a dub chord stab from a single piano sample",
            "arrangement breakdown: what happens in the first 32 bars",
        ],
    },
    {
        "name": "gear",
        "lift": 1.18,
        "duration": (12, 40),
        "profile": {"er": 0.061, "save": 0.019, "share": 0.010, "comment": 0.008},
        "bodies": [
            "digitakt only minimal jam, no computer",
            "octatrack resampling into a deep tech groove",
            "eurorack modular shaker patch that never repeats",
            "sp-404 dub delay on a minimal loop",
            "elektron digitone pad through a real spring reverb",
            "dawless hardware jam, one take, no edits",
            "mpc live groove with the swing pushed to 58%",
            "korg minilogue bassline into an analog compressor",
        ],
    },
    {
        "name": "dj_cam",
        "lift": 1.05,
        "duration": (14, 60),
        "profile": {"er": 0.048, "save": 0.008, "share": 0.011, "comment": 0.004},
        "bodies": [
            "closing set at the warehouse, 6am, minimal only",
            "b2b with a friend, vinyl only, deep tech",
            "sunrise open air terrace set, rominimal selection",
            "warm up set — slow rolling grooves for an empty room",
            "the mix that took the floor from 40 people to full",
            "three deck blend, all unreleased",
            "last track of the night, everyone stayed",
            "basement party, one speaker stack, no lights",
        ],
    },
    {
        "name": "meme",
        "lift": 1.11,
        "duration": (6, 18),
        "profile": {"er": 0.072, "save": 0.006, "share": 0.028, "comment": 0.011},
        "bodies": [
            "pov: you play minimal at a tech house party",
            "when the promoter asks you to play something people know",
            "producers be like: 47 shaker layers, still sounds empty",
            "nobody: — me at 5am adding another hi hat",
            "every dj checking their usb for the third time",
            "me explaining rominimal to my family at christmas",
            "when the drop is just the hats coming back",
            "that one guy filming the whole set on his ipad",
        ],
    },
    {
        "name": "before_after",
        "lift": 1.27,
        "duration": (10, 30),
        "profile": {"er": 0.066, "save": 0.024, "share": 0.017, "comment": 0.007},
        "bodies": [
            "flat loop vs the same loop with groove — wait for it",
            "unmixed vs mixed, same 8 bars",
            "before and after saturation on the whole drum bus",
            "raw field recording vs processed into a texture bed",
            "with vs without the off beat percussion layer",
            "boring kick vs layered kick, same track",
            "dry stab vs dub delay throw — keep watching",
            "one shaker vs three shakers at different swing values",
        ],
    },
    {
        "name": "studio_session",
        "lift": 1.02,
        "duration": (20, 75),
        "profile": {"er": 0.044, "save": 0.013, "share": 0.007, "comment": 0.005},
        "bodies": [
            "work in progress, deep tech roller, 126 bpm",
            "in the studio finishing the ep, minimal cuts only",
            "making of the b2 track — forthcoming on vinyl",
            "live jam session, three hours cut into forty seconds",
            "sound design session: turning a door creak into a lead",
            "sunday studio, no plan, just groove",
            "rebuilding an old track from 2019 with better low end",
            "session with a friend, one loop each, then we swap",
        ],
    },
    {
        "name": "talking_head",
        "lift": 0.94,
        "duration": (25, 70),
        "profile": {"er": 0.051, "save": 0.015, "share": 0.009, "comment": 0.014},
        "bodies": [
            "unpopular opinion: most minimal tracks are too long",
            "storytime: the label that ghosted me for eight months",
            "here's why your demo gets ignored — it's not the music",
            "hot take: loudness is killing deep tech grooves",
            "let me explain what a&rs actually listen for in the first 20 seconds",
            "my take on playing to an empty room and why it matters",
            "rant: stop sending 12 track demos to labels",
            "the booking email that actually worked",
        ],
    },
    {
        "name": "track_id",
        "lift": 0.97,
        "duration": (8, 25),
        "profile": {"er": 0.058, "save": 0.011, "share": 0.012, "comment": 0.019},
        "bodies": [
            "track id? forthcoming, no release date yet",
            "unreleased minimal roller — out next month",
            "vinyl only, 300 copies, deep tech",
            "premiere: the a1 from the new va",
            "new track out now, link in bio",
            "the one everyone asked about after the set",
            "id from saturday — finally finished it",
            "forthcoming on the label, 12 inch only",
        ],
    },
    {
        "name": "visualizer",
        "lift": 0.88,
        "duration": (15, 45),
        "profile": {"er": 0.039, "save": 0.009, "share": 0.006, "comment": 0.003},
        "bodies": [
            "audio reactive visualizer built in touchdesigner",
            "oscilloscope loop video for the new minimal cut",
            "generative blender render synced to the groove",
            "waveform visual for the deep tech roller",
            "3d render loop, 126 bpm, minimal",
            "audio reactive particles reacting to the shaker bus",
            "monochrome visualizer for the vinyl only edit",
            "slow generative loop under a dub chord bed",
        ],
    },
    {
        "name": "crowd_cam",
        "lift": 1.09,
        "duration": (8, 26),
        "profile": {"er": 0.069, "save": 0.007, "share": 0.021, "comment": 0.005},
        "bodies": [
            "the dancefloor when the bassline came back",
            "sunrise on the terrace, hands up, minimal only",
            "afters in a warehouse with 200 people and one strobe",
            "crowd reaction to an unreleased deep tech roller",
            "open air, 7am, nobody left",
            "rave in a car park, sound system on a trailer",
            "the moment the hats dropped back in",
            "after hours crowd, no phones, just dancing",
        ],
    },
]

HOOKS = [
    ("wait for it 👀", 1.24),
    ("wait for the drop", 1.18),
    ("keep watching till the end", 1.15),
    ("stop doing this to your hi hats", 1.30),
    ("nobody tells you this about groove", 1.28),
    ("3 things i wish i knew at 0 followers", 1.21),
    ("if you like rominimal you'll get this", 1.12),
    ("do you hear the difference?", 1.09),
    ("i turned one sample into a whole track", 1.19),
    ("", 0.82),
    ("", 0.82),
    ("new upload", 0.74),
]

HASHTAG_POOL = [
    "#minimal", "#deeptech", "#rominimal", "#microhouse", "#techhouse",
    "#minimaltechno", "#undergroundhouse", "#housemusic", "#dawless",
    "#abletonlive", "#producerlife", "#vinylonly", "#djset", "#groove",
    "#sunwaves", "#ade", "#studiolife", "#electronicmusic",
]

AUDIO_NAMES = [
    "original audio", "original audio", "original audio",
    "minimal roller (unreleased)", "deep tech groove 126",
    "rominimal loop — forthcoming", "dub chord bed", "shaker jam 124",
]

NO_HOOK_FORMATS = {"meme", "crowd_cam", "dj_cam", "visualizer", "track_id"}

ADJECTIVES = ["low", "dub", "grey", "soft", "raw", "deep", "slow", "night", "sub", "echo"]
NOUNS = ["room", "shaker", "groove", "loop", "hat", "chord", "cell", "tape", "drift", "form"]


def _handle(rng: random.Random, index: int) -> str:
    return f"sample_{rng.choice(ADJECTIVES)}{rng.choice(NOUNS)}_{index:03d}"


def generate(count: int = 2000, seed: int = RNG_SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)

    accounts = []
    for i in range(140):
        followers = int(rng.lognormvariate(8.0, 1.45))
        accounts.append(
            {
                "handle": _handle(rng, i),
                "followers": max(120, min(followers, 600_000)),
                "skill": rng.lognormvariate(0.0, 0.42),  # per-account consistency
            }
        )

    records: list[dict[str, Any]] = []
    for n in range(count):
        account = rng.choice(accounts)
        fmt = rng.choices(FORMATS, weights=[3, 3, 4, 2, 2, 3, 2, 3, 2, 3])[0]
        # Formats whose caption is already the joke or the atmosphere usually ship
        # without a separate hook line; forcing one on would read as noise.
        if fmt["name"] in NO_HOOK_FORMATS and rng.random() < 0.6:
            hook_text, hook_lift = "", 0.86
        else:
            hook_text, hook_lift = rng.choice(HOOKS)
        duration = round(rng.uniform(*fmt["duration"]), 1)

        # Short-form retention prior: attention falls off with length.
        length_fit = 1.30 if duration < 15 else 1.12 if duration < 30 else 0.95 if duration < 60 else 0.80

        body = rng.choice(fmt["bodies"])
        tags = " ".join(rng.sample(HASHTAG_POOL, rng.randint(3, 7)))
        caption = " ".join(part for part in (hook_text, body, tags) if part).strip()

        posted = now - timedelta(days=rng.uniform(1, 420), hours=rng.uniform(0, 24))

        # Reach is sub-linear in followers — that is exactly why a new account
        # can compete on the virality column.
        audience_pull = account["followers"] ** 0.58
        luck = rng.lognormvariate(0.0, 1.3)  # fat tail — a few genuine outliers
        views = int(
            audience_pull * 12 * fmt["lift"] * hook_lift * length_fit * account["skill"] * luck
        )
        views = max(views, 40)

        profile = fmt["profile"]
        jitter = lambda base: max(0.0005, rng.gauss(base, base * 0.28))  # noqa: E731
        likes = int(views * jitter(profile["er"]))
        comments = int(views * jitter(profile["comment"]))
        saves = int(views * jitter(profile["save"]))
        shares = int(views * jitter(profile["share"]))

        records.append(
            {
                "id": f"sample-{n:05d}",
                "url": f"https://example.invalid/sample/{n:05d}",
                "handle": account["handle"],
                "author_name": account["handle"].replace("_", " ").title(),
                "followers": account["followers"],
                "posted_at": posted.isoformat(),
                "collected_at": now.isoformat(),
                "duration_s": duration,
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "saves": saves,
                "caption": caption,
                "audio_name": rng.choice(AUDIO_NAMES),
                "audio_id": "",
            }
        )

    return normalize_many(records, source="sample", is_sample=True)

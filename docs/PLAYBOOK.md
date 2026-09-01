# 0 → followers: a 90-day plan for a minimal / deep tech artist

This is the plan the tracker is built to serve. The tracker tells you what is
working; this tells you what to do with that.

## The premise, stated honestly

Instagram will show a reel from a zero-follower account to a few hundred
strangers. That is the whole opportunity, and it is enough. Everything that
follows is about making those few hundred impressions convert, and then making
that repeatable.

Three things are true and worth internalising before you post anything:

1. **Views are not the goal. Follows are.** A reel with 200k views that gains
   you 40 followers is worse than one with 9k views that gains you 300. The
   tracker weights saves and shares heavily for exactly this reason — they are
   the behaviours that precede a follow.
2. **Nobody follows a track. They follow a person with a point of view.** Music
   alone is a like. A recognisable, repeated *angle* is a follow.
3. **Your niche is an advantage, not a handicap.** Minimal and deep tech is a
   small pond, which means a reel that lands is seen by people who genuinely
   care, and the same 2,000 people keep showing up. Do not water the music down
   to chase a wider audience — the wider audience does not convert.

> The realistic outcome of following this properly for 90 days, from zero, is
> somewhere between 500 and 5,000 followers. The variance is mostly down to
> whether one or two reels break out. You cannot force a breakout; you can only
> take enough shots that one becomes likely.

---

## Week 0: the two hours that make everything else work

Do this before your first post. Most of the compounding comes from here.

**The Name field is a search field.** Instagram searches the *name* field, not
the bio. Set it to something like `Alex · minimal & deep tech`. Not your name
alone.

**The bio does one job: tell a stranger why to press follow.** Not what you are,
what they get.

- Bad: `Producer / DJ. Based in Manchester. Bookings below.`
- Good: `Groove science for minimal producers · new loop every day · Manchester`

**Pin three reels** as soon as you have them: your best hook, your best proof of
skill, and your best "who I am". These three are your real homepage — most
visitors will judge you on the pinned row and nothing else.

**Turn on a professional account** (Creator). You need it for insights, and
`python -m app collect-own` needs it to pull your own reach and saves numbers.

**Decide your one sentence.** Write it down. It is what someone should be able
to say about you after watching three of your reels. "The guy who explains
groove." "The person documenting a year of daily loops." "The one who makes
tracks out of found objects." Everything you post should be recognisably from
that person. If you cannot say it in a sentence, your audience cannot either,
and they will not follow.

---

## The content ratio

Per 10 posts:

| Count | Type | Purpose |
|---|---|---|
| 4 | **Teach** — a technique, a comparison, a fix | Earns saves. Saves are the strongest follow predictor you can influence. |
| 3 | **Show** — jam, loop, DJ cam, studio, crowd | Proves you can actually do it. Carries the music. |
| 2 | **Relate** — meme, opinion, scene humour | Earns shares. Shares are how you reach outside your existing viewers. |
| 1 | **Ask** — poll, rate-my-loop, A/B | Earns comments and tells you what people want. |

Notice what is missing: pure promotion. Release announcements go inside a
*teach* or *show* post, never on their own. "Out now" is not content.

---

## The 90 days

### Days 1–14 — volume and calibration

**Post once a day. Do not skip.** The goal in this phase is not growth, it is
data: fourteen posts is enough to see which of your formats have a pulse.

- Use ideas from the `Ideas` tab, one per day. Keep production cheap — a phone
  on a stack of books is fine, and often better.
- Vary one thing at a time: hook style, length, format. If you change
  everything at once you learn nothing.
- Log every post into the tracker (`python -m app collect-own`) at 48 hours and
  again at day 7. Two observations is what makes the velocity column real.
- **Reply to every single comment**, within the hour if you can. At this scale
  it is 5 minutes a day and it is the difference between a viewer and a regular.

At the end of week two, run `python -m app signals` and look at which of your
own tags carry a lift above 1.0. That is your shortlist.

### Days 15–45 — double down and start a series

- **Cut to your best three formats.** Post those, and only those, five to six
  times a week.
- **Start one series with a visible counter** (`si-01` "Loop a day",
  `si-05` "Bedroom to booth"). A counter is a promise of a next episode, and it
  is the single most reliable follow mechanic available to a small account.
- **Rewrite hooks on your best-performing bodies and repost.** If a video's
  content was good but the reach was poor, the hook failed, not the video. Idea
  `ex-06` is the controlled version of this test.
- **Begin collaborating** (`cc-01` loop swaps, `cc-04` featuring smaller
  artists). Two accounts of 400 followers each posting the same collab reach
  more people than either alone, and the effect is immediate.

Target: 20–30 posts in this window. Expect one to outperform the rest by 10×.
That one tells you more than the other 29 combined — take its hook, its length
and its format, and make four more like it.

### Days 46–90 — compound

- **Post 5×/week, with one long-form (60–90s) per week.** Long-form has lower
  reach but a much higher follow-per-view rate. Judge it on follows, not views.
- **Convert attention into something you own.** Every fourth or fifth post,
  give something away that costs a comment: a loop pack, a groove template, the
  stems (`rp-08`, `cc-08`). This builds the list of people who will actually
  buy or stream the release.
- **Tie a release into the series** you have been running, rather than
  interrupting it. Idea `rp-02` — the made-of teardown — turns a promo into a
  tutorial, and tutorials get saved.
- **Rerun the winners.** A reel that did well 8 weeks ago will do well again
  with a new hook. Your audience has turned over; almost nobody remembers.

---

## Writing the first two seconds

This is 80% of the outcome. Everything else on this page is the other 20%.

- **The first frame must not look like an intro.** No logo, no "hey guys", no
  slow push-in. Open on the loudest, strangest, or most tactile thing you have.
- **State a claim, not a topic.** "Stop quantising your hats" beats "hi hat
  tips". A claim invites disagreement; a topic invites a scroll.
- **Keep on-screen text to seven words**, top third of the frame, high
  contrast, present from frame one.
- **Give a reason to stay.** "wait for bar 16", "the third one is the point",
  "the reveal is at the end". Then actually deliver it — a hook that lies gets
  the watch but costs the follow.
- **Assume no sound.** Most people scroll muted. If the first two seconds only
  work with audio, they mostly do not work.
- **Loop the end into the beginning** where you can. A seamless loop turns one
  view into three, and rewatch is the cheapest retention you can manufacture.

---

## Production spec

Enough to be sharp, cheap enough to sustain daily.

- **Vertical 1080×1920, 30fps.** Shoot on a phone. Lock it off — handheld
  wobble reads as amateur far more than low resolution does.
- **One light.** A desk lamp bounced off a wall beats a ring light. Get the
  gear's LEDs and screens in shot; that glow is the aesthetic of the genre and
  it does a lot of work for free.
- **Record audio direct, not through the phone mic**, whenever the audio is the
  point. A phone mic in a room makes a good groove sound bad, and the groove is
  what you are selling.
- **Master your reel audio quieter than you think** — around -14 LUFS. Instagram
  normalises, and squashed audio on a phone speaker sounds worse, not louder.
- **Caption: first line is a second hook.** Only the first line shows before
  "more". Put the payoff or the question there.
- **Hashtags: 3–5, specific.** `#rominimal #minimalhouse #dawless` beats
  `#music #edm #producer`. Large tags put you in a feed you cannot win. Put
  them in the caption; the comment-vs-caption debate is noise.
- **Cover frame matters more than you think** — it is what your profile grid
  looks like, and the pinned row is what converts profile visits.

---

## Distribution: what to do after you post

The post is half the work.

- **First 30 minutes: be present.** Reply to every comment. Early comment
  velocity genuinely matters, and it is the only lever you control after
  publishing.
- **Share to your story with a different framing** — "the bit I cut out",
  "why I made this". Not just a repost.
- **Comment on ten larger accounts in the niche, daily.** Not "🔥". Something
  with an actual observation — the kind of comment that makes twenty people tap
  your profile. This is the highest-yield 15 minutes in the whole plan when you
  are under 1,000 followers.
- **DM three people a week** who posted something you genuinely liked. Say the
  specific thing you liked. Do not pitch. Roughly one in three becomes a collab
  eventually, and collabs are the fastest legitimate growth mechanic there is.
- **Send your best reel to the label, shop, or artist it features.** Reposts
  from an account 50× your size are free, and they happen more often than you
  would expect because most people never ask.

---

## Measuring, without lying to yourself

Weekly, run:

```
python -m app collect-own          # pull your own reels and true insights
python -m app refresh
python -m app signals
```

Then check three things and ignore the rest:

1. **Follows per 1,000 views**, per format. This is the only number that ranks
   your formats correctly. A format under 1 follow / 1,000 views is
   entertainment, not growth — cap it at two posts a week.
2. **Save rate and share rate** (the `intent` column). If a teaching post is
   under ~1% saves, the idea was not useful enough or the payoff came too late.
3. **Your own reels' rank inside the corpus.** Filter the leaderboard to
   `under 5k followers` and see where you actually sit against people at your
   size. This is the honest comparison; comparing yourself to a 300k account is
   not informative.

What to explicitly ignore: total follower count on any given day, a single
post's view count, and anyone else's growth screenshots.

---

## What not to do

- **Do not buy followers or use engagement pods.** Both wreck the ratio that
  determines your future reach. An account with 10,000 fake followers gets less
  distribution than one with 400 real ones.
- **Do not follow/unfollow.** It works slightly, briefly, and it destroys the
  reputation you are actually trying to build in a scene where everyone knows
  everyone.
- **Do not repost TikToks with the watermark.** Export clean.
- **Do not post the same reel to a second account to "double reach".**
- **Do not chase a trending audio that does not fit the music.** Your audience
  is here for a specific sound. Trend-chasing brings viewers who will never
  listen to a nine-minute rominimal cut, and they dilute who Instagram thinks
  your audience is.
- **Do not delete underperforming posts.** They cost you nothing and they are
  your data.
- **Do not go quiet for two weeks after a good post.** This is the single most
  common way people waste a breakout.

---

## The two-week failure check

If after 30 posts nothing has cleared roughly 3× your follower count in views,
the problem is almost certainly one of these, in order of likelihood:

1. **The first two seconds.** Rewrite hooks on five existing videos and repost.
2. **No point of view.** Someone watching three of your posts cannot say what
   you are about. Fix the one sentence, then rebuild the content around it.
3. **Too long.** Cut everything to under 20 seconds for a fortnight and compare.
4. **The music is the only content.** Add the person, the process, or the
   teaching. The music is the reward, not the hook.

It is very rarely the posting time, the hashtags, or the algorithm.

"""Tests for the weekly loop: windowing, trends, idea generation, scheduling.

    python -m unittest discover tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, ideagen, ideagen_llm, pipeline, schedule, scoring, seed, trends, weekly  # noqa: E402
from app.sources import base  # noqa: E402


def _signals(tags, summary=None, duration=None, breakouts=None):
    return {
        "summary": summary or {"reels": 100, "median_reach_multiple": 2.0, "median_intent_rate": 0.01},
        "tags": tags,
        "duration": duration or [{"bucket": "len:7-15s", "count": 40, "median_score": 60.0}],
        "breakouts": breakouts or [],
        "audio": [],
        "timing": {"by_hour": [], "by_weekday": []},
    }


def _tag(name, lift, count=30, kind="format", **extra):
    row = {
        "tag": name, "kind": kind, "lift": lift, "count": count,
        "median_score": 50.0, "median_views": 5000,
        "median_reach_multiple": 2.0, "median_intent_rate": 0.01,
        "in_top_decile": 3, "share_of_top": 0.1,
    }
    row.update(extra)
    return row


class TestWindow(unittest.TestCase):
    def test_window_excludes_old_reels(self):
        now = datetime.now(timezone.utc)
        recent = {"id": "new", "views": 9000, "followers": 1000, "likes": 300,
                  "posted_at": (now - timedelta(days=10)).isoformat()}
        old = {"id": "old", "views": 90000, "followers": 1000, "likes": 3000,
               "posted_at": (now - timedelta(days=200)).isoformat()}

        ranked = scoring.rank_corpus([recent, old], window_days=90)
        self.assertEqual([r["reel_id"] for r in ranked], ["new"])
        # Without a window both are ranked and the bigger reel wins.
        self.assertEqual(len(scoring.rank_corpus([recent, old])), 2)

    def test_missing_date_is_kept(self):
        """Absent evidence of age is not evidence of age."""
        reel = {"id": "undated", "views": 9000, "followers": 500, "posted_at": None}
        self.assertTrue(scoring.within_window(None, 30))
        self.assertEqual(len(scoring.rank_corpus([reel], window_days=30)), 1)

    def test_window_none_keeps_everything(self):
        self.assertTrue(scoring.within_window("2019-01-01", None))


class TestTrends(unittest.TestCase):
    def test_rising_and_falling(self):
        before = _signals([_tag("format:gear", 1.00), _tag("format:meme", 1.30)])
        after = _signals([_tag("format:gear", 1.25), _tag("format:meme", 1.05)])
        movers = trends.tag_movers(before, after)
        self.assertEqual([r["tag"] for r in movers["rising"]], ["format:gear"])
        self.assertEqual([r["tag"] for r in movers["falling"]], ["format:meme"])
        self.assertAlmostEqual(movers["rising"][0]["change"], 0.25)

    def test_jitter_is_not_a_mover(self):
        before = _signals([_tag("format:gear", 1.10)])
        after = _signals([_tag("format:gear", 1.12)])
        movers = trends.tag_movers(before, after)
        self.assertEqual(movers["rising"], [])
        self.assertEqual(movers["falling"], [])

    def test_small_samples_are_ignored(self):
        before = _signals([_tag("format:gear", 1.00, count=2)])
        after = _signals([_tag("format:gear", 1.60, count=3)])
        self.assertEqual(trends.tag_movers(before, after)["rising"], [])

    def test_new_tags_need_a_floor(self):
        before = _signals([])
        after = _signals([_tag("format:meme", 1.4, count=20), _tag("format:gear", 1.9, count=2)])
        new = trends.tag_movers(before, after)["new"]
        self.assertEqual([r["tag"] for r in new], ["format:meme"])

    def test_first_run_marker(self):
        deltas = trends.compare(None, _signals([_tag("format:gear", 1.1)]))
        self.assertTrue(deltas["first_run"])
        self.assertIn("First run", trends.headline(deltas))

    def test_new_breakouts_only(self):
        before = _signals([], breakouts=[{"handle": "a"}])
        after = _signals([], breakouts=[{"handle": "a"}, {"handle": "b"}])
        self.assertEqual([b["handle"] for b in trends.new_breakouts(before, after)], ["b"])

    def test_evidence_pool_filters_and_sorts(self):
        signals = _signals([
            _tag("format:meme", 1.4, count=40),
            _tag("format:gear", 1.1, count=40),
            _tag("format:tutorial", 1.9, count=3),  # too few to trust
            _tag("hook:wait_for_it", 1.2, count=40, kind="hook"),
        ])
        pool = trends.evidence_pool(signals, trends.compare(None, signals))
        self.assertEqual([f["tag"] for f in pool["formats"]], ["format:meme", "format:gear"])
        self.assertEqual([h["tag"] for h in pool["hooks"]], ["hook:wait_for_it"])
        self.assertEqual(pool["best_length"]["bucket"], "len:7-15s")


class TestIdeaGeneration(unittest.TestCase):
    def _pool(self):
        signals = _signals([
            _tag("format:before_after", 1.30, count=40),
            _tag("format:dj_cam", 1.10, count=60),
            _tag("format:meme", 1.05, count=30),
            _tag("hook:wait_for_it", 1.20, count=50, kind="hook"),
            _tag("hook:identity", 1.05, count=30, kind="hook"),
            _tag("subject:groove", 1.15, count=80, kind="subject"),
            _tag("subject:career", 1.02, count=20, kind="subject"),
        ])
        return trends.evidence_pool(signals, trends.compare(None, signals))

    def test_shape_and_evidence(self):
        ideas = ideagen.generate(self._pool(), count=6, run_id=3)
        self.assertEqual(len(ideas), 6)
        for idea in ideas:
            self.assertTrue(idea["title"])
            self.assertEqual(len(idea["shots"]), 3)
            self.assertIn(idea["goal"], {"reach", "saves", "shares", "comments", "follows"})
            self.assertIn(idea["effort"], {"low", "med", "high"})
            self.assertTrue(idea["evidence"], "every idea must cite the data behind it")
            self.assertTrue(idea["id"].startswith("gen-003-"))
        self.assertEqual(len({i["id"] for i in ideas}), 6)

    def test_only_uses_compatible_pairings(self):
        """A DJ cam must never be handed a subject it cannot film."""
        ideas = ideagen.generate(self._pool(), count=12, run_id=1)
        for idea in ideas:
            tags = {e["tag"] for e in idea["evidence"]}
            for fmt_tag, spec in ideagen.FORMAT_BANK.items():
                if fmt_tag in tags:
                    for tag in tags:
                        if tag.startswith("subject:"):
                            self.assertIn(tag, spec["subjects"], f"{fmt_tag} + {tag}")
                        if tag.startswith("hook:"):
                            self.assertIn(tag, spec["hooks"], f"{fmt_tag} + {tag}")

    def test_stage_formats_avoid_studio_only_subjects(self):
        """A booth or a dancefloor cannot show two channels sharing an EQ move."""
        signals = _signals([
            _tag("format:dj_cam", 1.30, count=60),
            _tag("format:crowd_cam", 1.25, count=60),
            _tag("subject:bass", 1.20, count=80, kind="subject"),
        ])
        pool = trends.evidence_pool(signals, trends.compare(None, signals))
        ideas = ideagen.generate(pool, count=10, run_id=1)
        self.assertTrue(ideas)
        for idea in ideas:
            body = idea["title"] + " " + " ".join(idea["shots"])
            for phrase in ideagen.STUDIO_ONLY:
                self.assertNotIn(phrase, body, f"{idea['title']} used a studio-only subject")

    def test_underperforming_tags_are_not_used(self):
        signals = _signals([
            _tag("format:visualizer", 0.60, count=40),
            _tag("format:meme", 1.20, count=40),
        ])
        pool = trends.evidence_pool(signals, trends.compare(None, signals))
        ideas = ideagen.generate(pool, count=5, run_id=1)
        used = {e["tag"] for i in ideas for e in i["evidence"]}
        self.assertNotIn("format:visualizer", used)

    def test_avoids_existing_titles(self):
        pool = self._pool()
        first = ideagen.generate(pool, count=5, run_id=1)
        second = ideagen.generate(pool, count=5, run_id=2, avoid_titles=[i["title"] for i in first])
        self.assertFalse({i["title"] for i in first} & {i["title"] for i in second})

    def test_rising_tags_are_preferred(self):
        before = _signals([_tag("format:meme", 1.30, count=40), _tag("format:gear", 0.98, count=40)])
        after = _signals([_tag("format:meme", 1.30, count=40), _tag("format:gear", 1.28, count=40)])
        pool = trends.evidence_pool(after, trends.compare(before, after))
        ideas = ideagen.generate(pool, count=2, run_id=1)
        self.assertIn("format:gear", {e["tag"] for e in ideas[0]["evidence"]})

    def test_empty_pool_still_produces_ideas(self):
        pool = trends.evidence_pool(_signals([]), trends.compare(None, _signals([])))
        self.assertTrue(ideagen.generate(pool, count=3, run_id=1))

    def test_length_comes_from_the_winning_bucket(self):
        signals = _signals(
            [_tag("format:meme", 1.2, count=40)],
            duration=[
                {"bucket": "len:7-15s", "count": 30, "median_score": 40.0},
                {"bucket": "len:30-60s", "count": 30, "median_score": 70.0},
            ],
        )
        pool = trends.evidence_pool(signals, trends.compare(None, signals))
        self.assertEqual(ideagen.generate(pool, count=1, run_id=1)[0]["length_s"], "30-60")


class TestLLMAdoption(unittest.TestCase):
    """The LLM path is optional, but its output handling must be safe."""

    def _pool(self):
        signals = _signals([_tag("format:meme", 1.4, count=40), _tag("hook:identity", 1.1, count=20, kind="hook")])
        return trends.evidence_pool(signals, trends.compare(None, signals))

    def test_adopt_resolves_lifts_from_our_own_data(self):
        raw = [{
            "title": "A test idea", "hook": "wait for it", "shots": ["one", "two", "three"],
            "why": "because", "goal": "saves", "effort": "low", "length_s": "10-20",
            "cta": "save it", "evidence_tags": ["format:meme", "format:invented"],
        }]
        ideas = ideagen_llm._adopt(raw, self._pool(), run_id=7)
        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["source"], "claude")
        # An invented tag is dropped; the real one gets our measured lift.
        self.assertEqual([e["tag"] for e in ideas[0]["evidence"]], ["format:meme"])
        self.assertEqual(ideas[0]["evidence"][0]["lift"], 1.4)

    def test_adopt_rejects_unusable_items(self):
        raw = [{"title": "", "shots": []}, {"title": "No shots", "shots": []}]
        with self.assertRaises(ideagen_llm.LLMNotConfigured):
            ideagen_llm._adopt(raw, self._pool(), run_id=1)

    def test_adopt_clamps_invalid_enums(self):
        raw = [{"title": "T", "hook": "h", "shots": ["a"], "why": "w",
                "goal": "virality", "effort": "extreme", "length_s": "5", "cta": "", "evidence_tags": []}]
        idea = ideagen_llm._adopt(raw, self._pool(), run_id=1)[0]
        self.assertEqual(idea["goal"], "reach")
        self.assertEqual(idea["effort"], "low")

    def test_missing_package_is_reported_not_raised_generically(self):
        if ideagen_llm.available():
            self.skipTest("anthropic is installed in this environment")
        with self.assertRaises(ideagen_llm.LLMNotConfigured):
            ideagen_llm.generate(self._pool(), count=2)


class TestWeeklyRun(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.dir.name, "w.db")
        self.reports = os.path.join(self.dir.name, "reports")
        conn = db.connect(self.db)
        db.init(conn)
        pipeline.ingest(conn, seed.generate(900))
        conn.commit()
        conn.close()

    def tearDown(self):
        self.dir.cleanup()

    def _run(self, **kwargs):
        return weekly.run(
            db_path=self.db, do_collect=False, llm="off", idea_count=5,
            report_dir=self.reports, **kwargs
        )

    def test_first_run_then_diff(self):
        first = self._run()
        self.assertEqual(first["status"], "ok")
        self.assertGreater(first["scored"], 0)
        self.assertEqual(first["ideas"], 5)
        self.assertIsNone(first["compared_to_run"])
        self.assertTrue(os.path.isfile(first["report"]))
        self.assertTrue(os.path.isfile(os.path.join(self.reports, "latest.md")))

        second = self._run()
        self.assertEqual(second["compared_to_run"], first["run_id"])

        conn = db.connect(self.db)
        self.assertEqual(len(db.runs(conn)), 2)
        self.assertEqual(len(db.generated_ideas(conn)), 5)
        self.assertEqual(len(db.generated_ideas(conn, run_id=first["run_id"])), 5)
        conn.close()

    def test_report_flags_sample_data(self):
        result = self._run()
        with open(result["report"], encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("synthetic sample data", body)
        self.assertIn("## Ideas for this week", body)

    def test_window_restricts_the_ranked_set(self):
        wide = self._run(window_days=3650)
        narrow = self._run(window_days=30)
        self.assertLess(narrow["scored"], wide["scored"])

    def test_consecutive_runs_do_not_repeat_titles(self):
        first = self._run()
        second = self._run()
        conn = db.connect(self.db)
        a = {i["title"] for i in db.generated_ideas(conn, run_id=first["run_id"])}
        b = {i["title"] for i in db.generated_ideas(conn, run_id=second["run_id"])}
        conn.close()
        self.assertFalse(a & b)

    def test_failed_run_is_recorded(self):
        conn = db.connect(self.db)
        run_id = db.start_run(conn, 90)
        db.finish_run(conn, run_id, status="failed", notes="boom")
        conn.commit()
        # A failed run must not become the baseline for next week's diff.
        self.assertIsNone(db.previous_successful_run(conn, run_id + 1))
        conn.close()

    def test_collect_survives_unconfigured_providers(self):
        conn = db.connect(self.db)
        db.add_watch(conn, "account", "someone")
        conn.commit()
        rows, notes = weekly.collect(conn)
        conn.close()
        self.assertEqual(rows, [])
        self.assertTrue(any("not configured" in n for n in notes))


class TestSchedule(unittest.TestCase):
    def test_command_is_absolute_and_self_contained(self):
        command = schedule.command("/tmp/x.db", 90, "auto", 12)
        self.assertIn("-m app", command)
        self.assertIn("--window-days 90", command)
        self.assertIn("cd /", command)
        self.assertIn(">>", command)  # output has somewhere to go

    def test_marker_removal_is_exact(self):
        lines = ["0 1 * * * something-else", schedule.MARKER, "0 9 * * 1 the-job", "@daily other"]
        kept = schedule._without_ours(lines)
        self.assertEqual(kept, ["0 1 * * * something-else", "@daily other"])


if __name__ == "__main__":
    unittest.main()

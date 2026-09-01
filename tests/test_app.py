"""Stdlib unittest suite:  python -m unittest discover tests -v"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import analytics, db, pipeline, scoring, seed, tagging  # noqa: E402
from app.sources import base, files  # noqa: E402


class TestNormalise(unittest.TestCase):
    def test_alias_mapping(self):
        row = base.normalize(
            {
                "shortcode": "ABC123",
                "ownerUsername": "@SomeArtist",
                "videoPlayCount": "84,000",
                "likesCount": 5100,
                "commentsCount": 210,
                "followersCount": "4.2k",
                "takenAt": "2026-08-14",
                "videoDuration": "22.5",
                "edge_media_to_caption": {"edges": [{"node": {"text": "stop quantising #minimal"}}]},
            }
        )
        self.assertEqual(row["id"], "ABC123")
        self.assertEqual(row["handle"], "someartist")
        self.assertEqual(row["views"], 84000)
        self.assertEqual(row["followers"], 4200)
        self.assertEqual(row["duration_s"], 22.5)
        self.assertIn("quantising", row["caption"])
        self.assertTrue(row["url"].endswith("/reel/ABC123/"))

    def test_rejects_unmeasurable_rows(self):
        self.assertIsNone(base.normalize({"url": "https://x/1", "views": 0, "likes": 0}))

    def test_synthesises_id_when_absent(self):
        row = base.normalize({"url": "https://x/1", "handle": "a", "views": 10})
        self.assertTrue(row["id"])

    def test_epoch_timestamps(self):
        row = base.normalize({"id": "z", "views": 5, "timestamp": 1755000000})
        self.assertTrue(row["posted_at"].startswith("2025-"))

    def test_deduplicates_by_id(self):
        rows = base.normalize_many([{"id": "a", "views": 1}, {"id": "a", "views": 2}])
        self.assertEqual(len(rows), 1)


class TestScoring(unittest.TestCase):
    def test_percentile_ranks_bounds_and_ties(self):
        self.assertEqual(scoring.percentile_ranks([5, 1, 3]), [1.0, 0.0, 0.5])
        self.assertEqual(scoring.percentile_ranks([2, 2]), [0.5, 0.5])
        self.assertEqual(scoring.percentile_ranks([]), [])
        self.assertEqual(scoring.percentile_ranks([9]), [1.0])

    def test_small_account_can_outrank_large_one(self):
        """The whole point of the virality signal."""
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(days=3)).isoformat()
        corpus = [
            {"id": "small", "views": 120_000, "followers": 800, "likes": 9000,
             "comments": 400, "saves": 3000, "shares": 1500, "posted_at": recent},
            {"id": "big", "views": 300_000, "followers": 400_000, "likes": 6000,
             "comments": 100, "saves": 200, "shares": 90, "posted_at": recent},
        ]
        ranked = scoring.rank_corpus(corpus)
        self.assertEqual(ranked[0]["reel_id"], "small")
        self.assertEqual(ranked[0]["rank"], 1)

    def test_min_views_filter(self):
        corpus = [{"id": "a", "views": 10, "followers": 100, "posted_at": None}]
        self.assertEqual(scoring.rank_corpus(corpus), [])

    def test_recency_discounts_old_reels(self):
        now = datetime.now(timezone.utc)
        fresh = {"id": "fresh", "views": 50_000, "followers": 5000, "likes": 2000,
                 "comments": 50, "saves": 300, "shares": 100,
                 "posted_at": (now - timedelta(days=2)).isoformat()}
        stale = dict(fresh, id="stale", posted_at=(now - timedelta(days=900)).isoformat())
        ranked = {r["reel_id"]: r for r in scoring.rank_corpus([fresh, stale])}
        self.assertGreater(ranked["fresh"]["score"], ranked["stale"]["score"])
        # Identical signals, so the pre-recency score must match exactly.
        self.assertAlmostEqual(ranked["fresh"]["raw_score"], ranked["stale"]["raw_score"])

    def test_velocity_uses_two_observations(self):
        now = datetime.now(timezone.utc)
        history = [
            {"collected_at": (now - timedelta(days=2)).isoformat(), "views": 10_000},
            {"collected_at": now.isoformat(), "views": 30_000},
        ]
        reel = {"id": "v", "views": 30_000, "posted_at": (now - timedelta(days=100)).isoformat()}
        self.assertAlmostEqual(scoring.velocity(reel, history), 10_000, delta=200)
        # Without history it falls back to the lifetime average, which is far lower.
        self.assertLess(scoring.velocity(reel), 500)

    def test_follower_floor_prevents_blowup(self):
        sig = scoring.signals({"views": 1000, "followers": 0})
        self.assertEqual(sig["virality"], 1000 / scoring.FOLLOWER_FLOOR)


class TestTagging(unittest.TestCase):
    def test_matches_formats_hooks_and_hashtags(self):
        tags = dict(tagging.tags_for({
            "caption": "wait for it — how to get a rolling bassline #rominimal",
            "duration_s": 12,
        }))
        self.assertIn("hook:wait_for_it", tags)
        self.assertIn("format:tutorial", tags)
        self.assertIn("subject:bass", tags)
        self.assertIn("genre:minimal", tags)
        self.assertIn("tag:rominimal", tags)
        self.assertIn("len:7-15s", tags)

    def test_no_partial_word_matches(self):
        tags = dict(tagging.tags_for({"caption": "unmemeable subminimalist", "duration_s": 5}))
        self.assertNotIn("format:meme", tags)

    def test_keyword_ending_in_punctuation(self):
        self.assertIn("format:meme", dict(tagging.tags_for({"caption": "nobody: me at 5am"})))

    def test_duration_buckets(self):
        self.assertEqual(tagging.duration_tag(6.9), "len:0-7s")
        self.assertEqual(tagging.duration_tag(7), "len:7-15s")
        self.assertEqual(tagging.duration_tag(500), "len:90s+")
        self.assertIsNone(tagging.duration_tag(None))


class TestAnalytics(unittest.TestCase):
    def _rows(self):
        rows = []
        for i in range(20):
            good = i < 10
            rows.append({
                "reel_id": f"r{i}",
                "score": 80.0 if good else 20.0,
                "views": 1000,
                "reach_multiple": 2.0,
                "intent_rate": 0.01,
                "engagement_rate": 0.05,
                "followers": 500,
                "handle": f"h{i}",
                "tags": [("format:tutorial", "format")] if good else [("format:visualizer", "format")],
            })
        return rows

    def test_lift_separates_winners_from_losers(self):
        lifts = {r["tag"]: r["lift"] for r in analytics.tag_lift(self._rows())}
        self.assertGreater(lifts["format:tutorial"], 1.0)
        self.assertLess(lifts["format:visualizer"], 1.0)

    def test_min_sample_suppresses_noise(self):
        rows = self._rows()
        rows[0]["tags"].append(("format:meme", "format"))
        tags = {r["tag"] for r in analytics.tag_lift(rows)}
        self.assertNotIn("format:meme", tags)

    def test_empty_corpus_is_safe(self):
        self.assertEqual(analytics.tag_lift([]), [])
        self.assertEqual(analytics.corpus_summary([]), {"reels": 0})


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "t.db")
        self.conn = db.connect(self.path)
        db.init(self.conn)

    def tearDown(self):
        self.conn.close()
        self.dir.cleanup()

    def test_seed_ingest_rank_and_query(self):
        rows = seed.generate(300)
        self.assertTrue(all(r["is_sample"] == 1 for r in rows))
        pipeline.ingest(self.conn, rows)
        result = pipeline.refresh(self.conn)
        self.assertGreater(result["scored"], 0)

        page = pipeline.leaderboard(self.conn, limit=10)
        self.assertEqual(len(page["rows"]), 10)
        self.assertEqual(page["rows"][0]["rank"], 1)
        scores = [r["score"] for r in page["rows"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

        signals = pipeline.signals(self.conn)
        self.assertGreater(signals["summary"]["reels"], 0)
        self.assertEqual(signals["summary"]["sample_rows"], signals["summary"]["reels"])

    def test_reingest_keeps_history_and_updates_metrics(self):
        now = datetime.now(timezone.utc)
        first = base.normalize_many([{
            "id": "x1", "handle": "a", "followers": 1000, "views": 5000, "likes": 100,
            "posted_at": (now - timedelta(days=10)).isoformat(),
            "collected_at": (now - timedelta(days=5)).isoformat(),
        }])
        second = base.normalize_many([{
            "id": "x1", "handle": "a", "followers": 1000, "views": 25000, "likes": 900,
            "posted_at": (now - timedelta(days=10)).isoformat(),
            "collected_at": now.isoformat(),
        }])
        pipeline.ingest(self.conn, first)
        result = pipeline.ingest(self.conn, second)
        self.assertEqual(result["updated"], 1)

        self.assertEqual(len(db.history_for(self.conn, "x1")), 2)
        row = self.conn.execute("SELECT views FROM reels WHERE id='x1'").fetchone()
        self.assertEqual(row["views"], 25000)

        pipeline.refresh(self.conn)
        detail = pipeline.reel_detail(self.conn, "x1")
        self.assertAlmostEqual(detail["velocity"], 4000, delta=100)

    def test_purge_sample_leaves_real_rows(self):
        pipeline.ingest(self.conn, seed.generate(120))
        pipeline.ingest(self.conn, base.normalize_many([
            {"id": "real1", "handle": "me", "followers": 100, "views": 9000, "likes": 400}
        ]))
        pipeline.refresh(self.conn)
        removed = pipeline.purge_sample(self.conn)
        self.assertGreater(removed, 0)
        remaining = [dict(r) for r in db.all_reels(self.conn)]
        self.assertEqual([r["id"] for r in remaining], ["real1"])

    def test_leaderboard_filters(self):
        pipeline.ingest(self.conn, seed.generate(400))
        pipeline.refresh(self.conn)
        small = pipeline.leaderboard(self.conn, limit=100, max_followers=2000)
        self.assertTrue(all(r["followers"] <= 2000 for r in small["rows"]))
        tagged = pipeline.leaderboard(self.conn, limit=50, tag="format:tutorial")
        for row in tagged["rows"]:
            self.assertIn("format:tutorial", [t for t, _ in row["tags"]])
        self.assertEqual(pipeline.leaderboard(self.conn, limit=5, include_sample=False)["total"], 0)

    def test_csv_round_trip(self):
        path = os.path.join(self.dir.name, "in.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("url,username,follower_count,play_count,like_count,comment_count,date,duration,caption\n")
            fh.write("https://x/1,someone,3000,42000,2100,88,2026-07-01,18,\"wait for it #minimal\"\n")
        rows = files.read_csv(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["views"], 42000)
        pipeline.ingest(self.conn, rows)
        pipeline.refresh(self.conn)
        self.assertEqual(pipeline.leaderboard(self.conn)["total"], 1)


class TestServerRoutes(unittest.TestCase):
    """Exercise the handlers directly — no socket needed."""

    def test_route_tables_are_wired(self):
        from app import server

        handler = server.Handler.__new__(server.Handler)
        gets = server.Handler._get_routes(handler)
        posts = server.Handler._post_routes(handler)
        self.assertIn("/api/leaderboard", gets)
        self.assertIn("/api/purge-sample", posts)
        for route, fn in {**gets, **posts}.items():
            self.assertTrue(callable(fn), route)

    def test_ideas_file_is_valid(self):
        import json

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "data", "ideas.json"), encoding="utf-8") as fh:
            blob = json.load(fh)
        ids = [i["id"] for i in blob["ideas"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate idea ids")
        self.assertGreaterEqual(len(ids), 90)
        for idea in blob["ideas"]:
            self.assertIn(idea["category"], blob["categories"], idea["id"])
            self.assertIn(idea["goal"], {"reach", "saves", "shares", "comments", "follows"})
            self.assertIn(idea["effort"], {"low", "med", "high"})
            self.assertTrue(idea["shots"], idea["id"])


if __name__ == "__main__":
    unittest.main()

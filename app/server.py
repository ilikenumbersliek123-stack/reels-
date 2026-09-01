"""Local dashboard server. Stdlib only, binds to localhost by default.

    python -m app serve

There is no authentication because there is no reason to expose this beyond
your own machine. If you change the host, put something in front of it.
"""

from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import db, pipeline, scoring, seed
from .sources import files as file_source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")
DATA_DIR = os.path.join(ROOT, "data")
DOCS_DIR = os.path.join(ROOT, "docs")


def _int(params: dict[str, list[str]], key: str, default: int | None = None) -> int | None:
    raw = params.get(key, [None])[0]
    if raw in (None, ""):
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _str(params: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    value = params.get(key, [None])[0]
    return value if value not in (None, "") else default


def _bool(params: dict[str, list[str]], key: str, default: bool) -> bool:
    raw = params.get(key, [None])[0]
    if raw is None:
        return default
    return raw.lower() not in ("0", "false", "no")


class Handler(BaseHTTPRequestHandler):
    db_path: str = db.DEFAULT_DB
    server_version = "ReelTracker/1.0"

    # ---------------------------------------------------------------- plumbing

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter default logging
        if os.environ.get("REELS_VERBOSE"):
            super().log_message(fmt, *args)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str) -> None:
        if not os.path.isfile(path):
            self._send_json({"error": "not found", "path": os.path.basename(path)}, 404)
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------------ routes

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        params = parse_qs(parsed.query)

        try:
            if route.startswith("/api/"):
                handler = self._get_routes().get(route)
                if not handler:
                    self._send_json({"error": f"unknown endpoint {route}"}, 404)
                    return
                self._send_json(handler(params))
                return
            self._serve_static(route)
        except Exception as exc:  # surfaced in the UI rather than swallowed
            traceback.print_exc()
            self._send_json({"error": str(exc), "type": type(exc).__name__}, 500)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            handler = self._post_routes().get(route)
            if not handler:
                self._send_json({"error": f"unknown endpoint {route}"}, 404)
                return
            self._send_json(handler(self._body()))
        except Exception as exc:
            traceback.print_exc()
            self._send_json({"error": str(exc), "type": type(exc).__name__}, 500)

    def _serve_static(self, route: str) -> None:
        if route in ("/", ""):
            route = "/index.html"
        # Normalise away any ../ before joining, so the web dir is a hard boundary.
        safe = posixpath.normpath(route).lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, safe))
        if not full.startswith(WEB_DIR):
            self._send_json({"error": "forbidden"}, 403)
            return
        self._send_file(full)

    # ---------------------------------------------------------------- handlers

    def _get_routes(self) -> dict[str, Callable[[dict[str, list[str]]], Any]]:
        return {
            "/api/health": self.api_health,
            "/api/summary": self.api_summary,
            "/api/leaderboard": self.api_leaderboard,
            "/api/signals": self.api_signals,
            "/api/reel": self.api_reel,
            "/api/ideas": self.api_ideas,
            "/api/playbook": self.api_playbook,
            "/api/watchlist": self.api_watchlist,
        }

    def _post_routes(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return {
            "/api/refresh": self.api_refresh,
            "/api/seed": self.api_seed,
            "/api/import": self.api_import,
            "/api/collect": self.api_collect,
            "/api/purge-sample": self.api_purge_sample,
            "/api/watchlist/add": self.api_watch_add,
        }

    def api_health(self, params: dict[str, list[str]]) -> Any:
        with db.session(self.db_path) as conn:
            db.init(conn)
            counts = conn.execute(
                "SELECT (SELECT COUNT(*) FROM reels) reels, (SELECT COUNT(*) FROM scores) scored"
            ).fetchone()
        return {"ok": True, "db": self.db_path, "reels": counts["reels"], "scored": counts["scored"]}

    def api_summary(self, params: dict[str, list[str]]) -> Any:
        with db.session(self.db_path) as conn:
            db.init(conn)
            rows = pipeline.top_rows(conn, top_n=_int(params, "top_n", pipeline.TOP_N))
            from . import analytics

            summary = analytics.corpus_summary(rows)
            summary["weights"] = scoring.WEIGHTS
            summary["min_views"] = scoring.MIN_VIEWS
            return summary

    def api_leaderboard(self, params: dict[str, list[str]]) -> Any:
        with db.session(self.db_path) as conn:
            db.init(conn)
            return pipeline.leaderboard(
                conn,
                limit=min(_int(params, "limit", 50) or 50, 1000),
                offset=_int(params, "offset", 0) or 0,
                top_n=_int(params, "top_n", pipeline.TOP_N) or pipeline.TOP_N,
                tag=_str(params, "tag"),
                handle=_str(params, "handle"),
                query=_str(params, "q"),
                max_followers=_int(params, "max_followers"),
                sort=_str(params, "sort", "rank") or "rank",
                direction=_str(params, "dir", "asc") or "asc",
                include_sample=_bool(params, "sample", True),
            )

    def api_signals(self, params: dict[str, list[str]]) -> Any:
        with db.session(self.db_path) as conn:
            db.init(conn)
            return pipeline.signals(
                conn,
                top_n=_int(params, "top_n"),  # None = the whole scored corpus
                include_sample=_bool(params, "sample", True),
            )

    def api_reel(self, params: dict[str, list[str]]) -> Any:
        reel_id = _str(params, "id")
        if not reel_id:
            return {"error": "id required"}
        with db.session(self.db_path) as conn:
            db.init(conn)
            return pipeline.reel_detail(conn, reel_id) or {"error": "not found"}

    def api_ideas(self, params: dict[str, list[str]]) -> Any:
        with open(os.path.join(DATA_DIR, "ideas.json"), encoding="utf-8") as fh:
            blob = json.load(fh)
        category = _str(params, "category")
        goal = _str(params, "goal")
        ideas = blob["ideas"]
        if category:
            ideas = [i for i in ideas if i["category"] == category]
        if goal:
            ideas = [i for i in ideas if i["goal"] == goal]
        return {"categories": blob["categories"], "count": len(ideas), "ideas": ideas}

    def api_playbook(self, params: dict[str, list[str]]) -> Any:
        path = os.path.join(DOCS_DIR, "PLAYBOOK.md")
        if not os.path.isfile(path):
            return {"markdown": "# Playbook missing\n"}
        with open(path, encoding="utf-8") as fh:
            return {"markdown": fh.read()}

    def api_watchlist(self, params: dict[str, list[str]]) -> Any:
        with db.session(self.db_path) as conn:
            db.init(conn)
            return {"watchlist": [dict(r) for r in db.watchlist(conn)]}

    def api_watch_add(self, body: dict[str, Any]) -> Any:
        kind = body.get("kind", "account")
        values = body.get("values") or ([body["value"]] if body.get("value") else [])
        with db.session(self.db_path) as conn:
            db.init(conn)
            for value in values:
                db.add_watch(conn, kind, str(value), body.get("note", ""))
            return {"watchlist": [dict(r) for r in db.watchlist(conn)]}

    def api_refresh(self, body: dict[str, Any]) -> Any:
        with db.session(self.db_path) as conn:
            db.init(conn)
            return pipeline.refresh(
                conn,
                half_life_days=float(body.get("half_life_days", scoring.DEFAULT_HALF_LIFE_DAYS)),
                min_views=int(body.get("min_views", scoring.MIN_VIEWS)),
            )

    def api_seed(self, body: dict[str, Any]) -> Any:
        rows = seed.generate(int(body.get("count", 2000)))
        with db.session(self.db_path) as conn:
            db.init(conn)
            result = pipeline.ingest(conn, rows)
            result.update(pipeline.refresh(conn))
            return result

    def api_import(self, body: dict[str, Any]) -> Any:
        path = body.get("path")
        if not path or not os.path.isfile(path):
            return {"error": f"file not found: {path}"}
        rows = file_source.read_any(path)
        with db.session(self.db_path) as conn:
            db.init(conn)
            result = pipeline.ingest(conn, rows)
            result.update(pipeline.refresh(conn))
            return result

    def api_collect(self, body: dict[str, Any]) -> Any:
        from .sources import apify

        targets = body.get("targets") or []
        if not targets:
            with db.session(self.db_path) as conn:
                db.init(conn)
                targets = [r["value"] for r in db.watchlist(conn, body.get("kind", "account"))]
        rows = apify.run_actor(
            targets,
            kind=body.get("kind", "account"),
            limit_per_target=int(body.get("limit", 50)),
        )
        with db.session(self.db_path) as conn:
            db.init(conn)
            result = pipeline.ingest(conn, rows)
            result.update(pipeline.refresh(conn))
            return result

    def api_purge_sample(self, body: dict[str, Any]) -> Any:
        with db.session(self.db_path) as conn:
            db.init(conn)
            removed = pipeline.purge_sample(conn)
            pipeline.refresh(conn)
            return {"removed": removed}


def serve(host: str = "127.0.0.1", port: int = 8420, db_path: str = db.DEFAULT_DB) -> None:
    Handler.db_path = db_path
    with db.session(db_path) as conn:
        db.init(conn)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Reel tracker on http://{host}:{port}  (db: {db_path})")
    print("Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()

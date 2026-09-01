"""Ingestion sources.

Every source returns a list of dicts already normalised to the reels schema by
`base.normalize_many`, so `app.pipeline` can treat them identically.
"""

from . import apify, base, files, graph  # noqa: F401

__all__ = ["apify", "base", "files", "graph"]

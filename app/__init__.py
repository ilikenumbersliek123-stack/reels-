"""Minimal / deep tech Instagram Reels tracker.

Modules:
    db          SQLite storage
    scoring     the composite ranking model
    tagging     caption -> tags
    analytics   pattern mining over the ranked corpus
    pipeline    ingest -> tag -> score -> query
    seed        labelled synthetic sample data
    server      local dashboard
    sources/    ingestion adapters (files, apify, graph)
"""

__version__ = "1.0.0"

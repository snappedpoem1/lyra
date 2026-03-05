from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from oracle.playlust import Playlust


def test_get_deepcut_paths_reads_payload_json(monkeypatch, tmp_path: Path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE enrich_cache (
            provider TEXT,
            lookup_key TEXT,
            payload_json TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO enrich_cache(provider, lookup_key, payload_json) VALUES (?, ?, ?)",
        (
            "deepcut_score",
            "artist::track",
            json.dumps({"obscurity_score": 0.9, "filepath": r"A:\\Music\\artist\\track.flac"}),
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("oracle.playlust.get_connection", lambda: sqlite3.connect(db))
    paths = Playlust()._get_deepcut_paths(limit=10)
    assert r"A:\\Music\\artist\\track.flac" in paths


def test_get_deepcut_paths_supports_legacy_payload_column(monkeypatch, tmp_path: Path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE enrich_cache (
            provider TEXT,
            lookup_key TEXT,
            payload TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO enrich_cache(provider, lookup_key, payload) VALUES (?, ?, ?)",
        (
            "deepcut_score",
            "artist::track",
            json.dumps({"obscurity_score": 1.1, "filepath": r"A:\\Music\\legacy\\track.flac"}),
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("oracle.playlust.get_connection", lambda: sqlite3.connect(db))
    paths = Playlust()._get_deepcut_paths(limit=10)
    assert r"A:\\Music\\legacy\\track.flac" in paths

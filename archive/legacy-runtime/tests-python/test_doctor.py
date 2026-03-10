from __future__ import annotations

from pathlib import Path
import sqlite3
from oracle.doctor import _check_chroma_storage


def test_check_chroma_storage_reports_embedding_count(monkeypatch, tmp_path: Path):
    chroma_dir = tmp_path / "chroma_storage"
    chroma_dir.mkdir()
    (chroma_dir / "chroma.sqlite3").write_text("db")
    db_path = tmp_path / "lyra_registry.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE embeddings (track_id TEXT, model TEXT, dimension INTEGER, indexed_at REAL)")
    conn.executemany(
        "INSERT INTO embeddings (track_id, model, dimension, indexed_at) VALUES (?, ?, ?, ?)",
        [(f"track-{index}", "clap", 512, 0.0) for index in range(2472)],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("oracle.doctor.CHROMA_PATH", chroma_dir)
    monkeypatch.setattr("oracle.doctor.DB_PATH", db_path)

    result = _check_chroma_storage()

    assert result.status == "PASS"
    assert result.name == "ChromaDB (local)"
    assert "2472 embeddings" in result.details


def test_check_chroma_storage_warns_when_collection_probe_fails(monkeypatch, tmp_path: Path):
    chroma_dir = tmp_path / "chroma_storage"
    chroma_dir.mkdir()
    (chroma_dir / "segment.bin").write_text("x")

    monkeypatch.setattr("oracle.doctor.CHROMA_PATH", chroma_dir)
    monkeypatch.setattr("oracle.doctor.DB_PATH", tmp_path / "missing.db")

    result = _check_chroma_storage()

    assert result.status == "WARNING"
    assert "collection check failed" in result.details


def test_check_lidarr_passes_api_key_header(monkeypatch):
    monkeypatch.setenv("LIDARR_URL", "http://localhost:8686")
    monkeypatch.setenv("LIDARR_API_KEY", "test-key")
    seen: dict[str, object] = {}

    def fake_http_get(url: str, timeout: int = 4, headers=None):
        seen["url"] = url
        seen["timeout"] = timeout
        seen["headers"] = headers
        return 200, ""

    monkeypatch.setattr("oracle.doctor._http_get", fake_http_get)

    result = _check_lidarr()

    assert result.status == "PASS"
    assert seen["url"] == "http://localhost:8686/api/v1/system/status"
    assert seen["headers"] == {"X-Api-Key": "test-key"}

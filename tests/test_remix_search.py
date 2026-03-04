import sqlite3
import unittest
from unittest.mock import patch

from oracle.search import find_remixes


class RemixSearchTests(unittest.TestCase):
    def _seed_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE tracks (
                track_id TEXT PRIMARY KEY,
                artist TEXT,
                title TEXT,
                album TEXT,
                year TEXT,
                status TEXT,
                version_type TEXT,
                confidence REAL,
                filepath TEXT,
                updated_at REAL
            )
            """
        )
        cur.executemany(
            """
            INSERT INTO tracks
            (track_id, artist, title, album, year, status, version_type, confidence, filepath, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "1",
                    "Artist A",
                    "Song One (Remix)",
                    "Alpha",
                    "2020",
                    "active",
                    "remix",
                    0.9,
                    "/library/song1.flac",
                    100.0,
                ),
                (
                    "2",
                    "Artist A",
                    "Song Two",
                    "Alpha (VIP Mix)",
                    "2021",
                    "active",
                    "original",
                    0.6,
                    "/library/song2.flac",
                    101.0,
                ),
                (
                    "3",
                    "Artist B",
                    "Song Three",
                    "Beta",
                    "2022",
                    "active",
                    "original",
                    0.8,
                    "/library/song3.flac",
                    102.0,
                ),
                (
                    "4",
                    "Artist A",
                    "Quarantine Remix Cut",
                    "Gamma",
                    "2023",
                    "quarantine",
                    "remix",
                    0.95,
                    "/library/song4.flac",
                    103.0,
                ),
            ],
        )
        conn.commit()
        return conn

    def test_find_remixes_artist_scope(self) -> None:
        conn = self._seed_db()
        try:
            with patch("oracle.search.get_connection", return_value=conn):
                results = find_remixes(artist="artist a", n=50, include_candidates=True)
            ids = [r["track_id"] for r in results]
            self.assertIn("1", ids)
            self.assertIn("2", ids)
            self.assertNotIn("3", ids)
            self.assertNotIn("4", ids)  # non-active status excluded
        finally:
            conn.close()

    def test_find_remixes_without_candidates(self) -> None:
        conn = self._seed_db()
        try:
            with patch("oracle.search.get_connection", return_value=conn):
                results = find_remixes(artist="artist a", include_candidates=False)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["track_id"], "1")
            self.assertTrue(results[0]["is_strict_remix"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

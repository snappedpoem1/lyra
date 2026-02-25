import sqlite3
import unittest

from oracle.db import schema


class SchemaIdempotenceTests(unittest.TestCase):
    def test_ensure_tracks_columns_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE tracks (
                track_id TEXT,
                filepath TEXT,
                content_hash TEXT
            )
            """
        )

        schema._ensure_tracks_columns(cursor)
        cursor.execute("PRAGMA table_info(tracks)")
        first = [row[1] for row in cursor.fetchall()]
<<<<<<< HEAD
=======
        for expected in (
            "subgenres",
            "artist_mbid",
            "recording_mbid",
            "release_mbid",
            "release_group_mbid",
            "isrc",
            "discogs_release_id",
            "metadata_source",
            "canonical_confidence",
            "last_enriched_at",
        ):
            self.assertIn(expected, first)
>>>>>>> fc77b41 (Update workspace state and diagnostics)

        schema._ensure_tracks_columns(cursor)
        cursor.execute("PRAGMA table_info(tracks)")
        second = [row[1] for row in cursor.fetchall()]

        self.assertEqual(first, second)
        conn.close()

    def test_ensure_queue_columns_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE acquisition_queue (
                id INTEGER PRIMARY KEY,
                artist TEXT,
                title TEXT
            )
            """
        )

        schema._ensure_acquisition_queue_columns(cursor)
        cursor.execute("PRAGMA table_info(acquisition_queue)")
        first = [row[1] for row in cursor.fetchall()]

        schema._ensure_acquisition_queue_columns(cursor)
        cursor.execute("PRAGMA table_info(acquisition_queue)")
        second = [row[1] for row in cursor.fetchall()]

        self.assertEqual(first, second)
        conn.close()


if __name__ == "__main__":
    unittest.main()

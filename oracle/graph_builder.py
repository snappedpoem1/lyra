"""Graph Auto-Builder — Proactive Artist Relationship Builder.

Builds the connection graph by running all library artists through the
Lore historian engine on pipeline completion, rather than waiting for
on-demand trace requests.

Runs incrementally: only processes artists added since the last build run.
Stores progress in the ``meta`` table (key=graph_builder_last_run_ts).

Usage::

    from oracle.graph_builder import GraphBuilder

    gb = GraphBuilder()
    count = gb.build_incremental()
    print(f"Added {count} new connections")

    # Or run full rebuild (slow on large libraries):
    count = gb.build_full_graph()

Author: Lyra Oracle — Sprint 1
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)

_META_KEY_LAST_RUN = "graph_builder_last_run_ts"


class GraphBuilder:
    """Proactively builds the artist relationship graph.

    Designed to run automatically at the end of ``oracle pipeline``
    and incrementally (only new artists) on subsequent runs.
    """

    def build_full_graph(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        depth: int = 1,
    ) -> int:
        """Build relationships for ALL unique artists in the library.

        This is a full rebuild — slower but thorough. Useful for the
        first run or after a major library import.

        Args:
            progress_callback: Optional callable(current, total, artist_name).
            depth: Genealogy depth passed to Lore.trace_lineage (1–2 recommended).

        Returns:
            Count of new connection edges added to the database.
        """
        artists = self._get_all_unique_artists()
        logger.info("GraphBuilder: full build for %d artists (depth=%d)", len(artists), depth)
        return self._process_artists(artists, progress_callback=progress_callback, depth=depth)

    def build_incremental(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        depth: int = 1,
    ) -> int:
        """Build relationships for artists added since the last graph build.

        Much faster than full rebuild — safe to run after every pipeline run.

        Args:
            progress_callback: Optional callable(current, total, artist_name).
            depth: Genealogy depth passed to Lore.trace_lineage.

        Returns:
            Count of new connection edges added.
        """
        last_run_ts = self._get_last_run_ts()
        artists = self._get_new_artists_since(last_run_ts)

        if not artists:
            logger.info("GraphBuilder: no new artists since last run (ts=%.0f)", last_run_ts)
            return 0

        logger.info("GraphBuilder: incremental build for %d new artists (since=%.0f)", len(artists), last_run_ts)
        count = self._process_artists(artists, progress_callback=progress_callback, depth=depth)
        self._set_last_run_ts(time.time())
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Return graph statistics for diagnostics.

        Returns:
            Dict with keys: total_artists, total_connections, last_run_ts, top_connected.
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(DISTINCT source) FROM connections")
            total_artists = c.fetchone()[0] or 0

            c.execute("SELECT COUNT(*) FROM connections")
            total_connections = c.fetchone()[0] or 0

            c.execute(
                """
                SELECT source, COUNT(*) as cnt
                FROM connections
                GROUP BY source
                ORDER BY cnt DESC
                LIMIT 5
                """
            )
            top_connected = [{"artist": r[0], "connections": r[1]} for r in c.fetchall()]

            return {
                "total_artists": total_artists,
                "total_connections": total_connections,
                "last_run_ts": self._get_last_run_ts(),
                "top_connected": top_connected,
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_all_unique_artists(self) -> List[str]:
        """Return sorted list of all unique, non-empty artist names."""
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT DISTINCT artist FROM tracks "
                "WHERE artist IS NOT NULL AND trim(artist) != '' "
                "ORDER BY artist"
            )
            return [row[0].strip() for row in c.fetchall()]
        finally:
            conn.close()

    def _get_new_artists_since(self, ts: float) -> List[str]:
        """Return artists from tracks added after the given Unix timestamp."""
        conn = get_connection()
        try:
            c = conn.cursor()
            # artists in tracks added after ts, excluding those already in connections
            c.execute(
                """
                SELECT DISTINCT t.artist
                FROM tracks t
                WHERE t.artist IS NOT NULL
                  AND trim(t.artist) != ''
                  AND (t.added_at > ? OR t.created_at > ?)
                  AND t.artist NOT IN (SELECT DISTINCT source FROM connections)
                ORDER BY t.artist
                """,
                (ts, ts),
            )
            return [row[0].strip() for row in c.fetchall()]
        finally:
            conn.close()

    def _process_artists(
        self,
        artists: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]],
        depth: int,
    ) -> int:
        """Run Lore.trace_lineage for each artist and count new edges.

        Args:
            artists: List of artist name strings.
            progress_callback: Optional progress reporter.
            depth: Lore trace depth.

        Returns:
            Total new connection rows inserted.
        """
        # Lazy import to avoid circular dependency at module level
        try:
            from oracle.lore import Lore
            lore = Lore()
        except Exception as exc:
            logger.error("GraphBuilder: could not import Lore — %s", exc)
            return 0

        total = len(artists)
        new_edges = 0

        for i, artist_name in enumerate(artists):
            if progress_callback:
                progress_callback(i + 1, total, artist_name)

            before = self._count_connections_for(artist_name)
            try:
                lore.trace_lineage(artist_name, depth=depth)
            except Exception as exc:
                logger.debug("GraphBuilder: trace_lineage failed for '%s': %s", artist_name, exc)
                continue
            after = self._count_connections_for(artist_name)
            new_edges += max(0, after - before)

            # MusicBrainz is rate-limited; respect that
            time.sleep(1.2)

        logger.info("GraphBuilder: done — %d new edges", new_edges)
        return new_edges

    def _count_connections_for(self, artist: str) -> int:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM connections WHERE source = ?", (artist,))
            return c.fetchone()[0] or 0
        finally:
            conn.close()

    def _get_last_run_ts(self) -> float:
        """Read last run timestamp from meta table. Returns 0.0 if missing."""
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT value FROM meta WHERE key = ? LIMIT 1",
                (_META_KEY_LAST_RUN,),
            )
            row = c.fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            return 0.0
        finally:
            conn.close()

    def _set_last_run_ts(self, ts: float) -> None:
        """Persist last run timestamp to meta table."""
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (_META_KEY_LAST_RUN, str(ts)),
            )
            conn.commit()
        except Exception as exc:
            logger.debug("GraphBuilder: could not write meta — %s", exc)
        finally:
            conn.close()

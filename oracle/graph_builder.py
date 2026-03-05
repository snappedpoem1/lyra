"""Graph Auto-Builder — Proactive Artist Relationship Builder.

Builds the connection graph by running all library artists through the
Lore historian engine on pipeline completion, rather than waiting for
on-demand trace requests.

Two complementary edge types are generated:

lineage edges (via Lore / MusicBrainz):
  member_of, collab, influence, rivalry

dimension_affinity edges (local-only, no API):
  Artists whose track_scores centroids are cosine-similar (>= threshold).
  These edges represent shared emotional DNA — artists who occupy similar
  sonic space in your library, regardless of genre or history.  They are
  cheap to compute, require no external calls, and massively increase graph
  density for constellation and discovery.

Runs incrementally: only processes artists added since the last build run.
Stores progress in the ``meta`` table (key=graph_builder_last_run_ts).

Usage::

    from oracle.graph_builder import GraphBuilder

    gb = GraphBuilder()
    count = gb.build_incremental()
    print(f"Added {count} new connections")

    # Dimension edges only (fast, no rate limiting):
    count = gb.build_dimension_edges()

    # Or run full rebuild (slow on large libraries):
    count = gb.build_full_graph()

Author: Lyra Oracle — Sprint 1
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)

_META_KEY_LAST_RUN = "graph_builder_last_run_ts"

# Pearson correlation (z-score-normalised cosine) threshold for dimension_affinity edges.
# With raw cosine on absolute CLAP scores, 0.82 would include nearly every pair because
# all scores are positive and cluster in the same direction.  After z-score standardisation
# the metric is equivalent to Pearson correlation and 0.60 gives a meaningful neighbourhood
# of similar sonic profiles without drowning the graph.
# Override with LYRA_GRAPH_DIMENSION_THRESHOLD in .env.
_DIMENSION_SIM_THRESHOLD = float(
    __import__("os").getenv("LYRA_GRAPH_DIMENSION_THRESHOLD", "0.60")
)
_DIMENSIONS = ["energy", "valence", "tension", "density", "warmth", "movement", "space", "rawness", "complexity", "nostalgia"]

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
        count = self._process_artists(artists, progress_callback=progress_callback, depth=depth)
        count += self.build_dimension_edges()
        return count

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
        count += self.build_dimension_edges()
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

    def build_dimension_edges(
        self,
        threshold: float = _DIMENSION_SIM_THRESHOLD,
        top_k: int = 8,
    ) -> int:
        """Add ``dimension_affinity`` edges between artists with similar sonic profiles.

        Uses per-artist centroid vectors computed from ``track_scores``.
        No external API calls — purely local DB data.

        Scores are z-score standardised across all artists before comparison
        (equivalent to Pearson correlation) so that the metric captures relative
        profile shape, not absolute score level.  Without standardisation,
        every artist looks similar because all CLAP scores are positive and
        cluster in the same quadrant.

        For each artist the *top_k* most-similar neighbours are kept.  Only
        pairs whose standardised cosine similarity >= *threshold* AND who don't
        already have a ``dimension_affinity`` edge receive a new edge.

        Args:
            threshold: Minimum standardised cosine similarity (default 0.82).
            top_k: Maximum neighbours per artist to consider (default 8).

        Returns:
            Number of new edges inserted.
        """
        conn = get_connection()
        try:
            c = conn.cursor()
            cols = ", ".join(f"AVG(ts.{d})" for d in _DIMENSIONS)
            c.execute(
                f"""
                SELECT t.artist, {cols}
                FROM tracks t
                JOIN track_scores ts ON ts.track_id = t.track_id
                WHERE t.artist IS NOT NULL AND trim(t.artist) != ''
                  AND t.status = 'active'
                GROUP BY t.artist
                HAVING COUNT(ts.track_id) >= 1
                """,
            )
            rows = c.fetchall()
        finally:
            conn.close()

        if len(rows) < 2:
            logger.info("[graph] build_dimension_edges: not enough artist data (%d artists)", len(rows))
            return 0

        artists = [r[0] for r in rows]
        raw_vecs = np.array([[v if v is not None else 0.0 for v in r[1:]] for r in rows], dtype=np.float64)

        # Z-score standardise each dimension across all artists so that similarity
        # reflects shape/pattern of the profile, not absolute level.
        means = raw_vecs.mean(axis=0, keepdims=True)
        stds = raw_vecs.std(axis=0, keepdims=True)
        stds[stds < 1e-9] = 1.0  # guard zero-variance dimensions
        z_vecs = (raw_vecs - means) / stds

        # L2-normalise for cosine similarity
        norms = np.linalg.norm(z_vecs, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        vecs = z_vecs / norms

        # Pairwise similarity; zero the diagonal so self-matches are excluded
        sim_matrix = (vecs @ vecs.T).astype(np.float32)
        np.fill_diagonal(sim_matrix, 0.0)

        # Load existing dimension_affinity pairs to avoid duplicates
        conn2 = get_connection()
        try:
            c2 = conn2.cursor()
            c2.execute(
                "SELECT source, target FROM connections WHERE type = 'dimension_affinity'"
            )
            existing = {(r[0], r[1]) for r in c2.fetchall()}
        finally:
            conn2.close()

        new_edges: list[tuple] = []
        seen_pairs: set[tuple] = set()
        n = len(artists)

        for i in range(n):
            # top_k neighbours for artist i
            top_indices = np.argpartition(sim_matrix[i], -top_k)[-top_k:]
            for j in top_indices:
                j = int(j)
                if j == i:
                    continue
                sim = float(sim_matrix[i, j])
                if sim < threshold:
                    continue
                a, b = artists[i], artists[j]
                pair = (min(a, b), max(a, b))
                if pair in seen_pairs:
                    continue
                if (a, b) in existing or (b, a) in existing:
                    continue
                seen_pairs.add(pair)

                # strongest shared dimensions for evidence
                avg_z = ((z_vecs[i] + z_vecs[j]) / 2.0)
                top_dims = sorted(
                    zip(_DIMENSIONS, avg_z.tolist()), key=lambda x: abs(x[1]), reverse=True
                )[:3]
                evidence = json.dumps({
                    "similarity": round(sim, 4),
                    "top_dims": [{"dim": d, "zscore": round(float(v), 3)} for d, v in top_dims],
                })
                new_edges.append((a, b, "dimension_affinity", round(sim, 4), evidence))
                new_edges.append((b, a, "dimension_affinity", round(sim, 4), evidence))

        if not new_edges:
            logger.info("[graph] build_dimension_edges: 0 new edges (threshold=%.2f, top_k=%d)", threshold, top_k)
            return 0

        conn3 = get_connection()
        try:
            c3 = conn3.cursor()
            c3.executemany(
                "INSERT INTO connections (source, target, type, weight, evidence) VALUES (?, ?, ?, ?, ?)",
                new_edges,
            )
            conn3.commit()
        finally:
            conn3.close()

        added = len(new_edges) // 2  # bidirectional pairs
        logger.info(
            "[graph] build_dimension_edges: %d new artist pairs (threshold=%.2f, top_k=%d, artists=%d)",
            added, threshold, top_k, n,
        )
        return added

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

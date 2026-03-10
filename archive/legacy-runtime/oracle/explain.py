"""
Playlist Explainability Engine — F-007

Builds structured reasons for why each track was included in a playlist.
Works entirely from local data (no external API calls) by querying:
  - track_scores  → dimensional similarity reasons
  - connections   → artist graph reasons
  - enrich_cache  → deep cut potential
  - taste_profile → personal taste alignment

Reason types:
  - ``similar-energy``     — energy/valence/tension scores close to seed or query average
  - ``artist-connection``  — artist appears in relationship graph connected to seed artist
  - ``deep-cut``           — obscurity score suggests acclaimed-but-obscure track
  - ``mood-bridge``        — smooth emotional transition between adjacent tracks in sequence
  - ``taste-match``        — aligns with user taste profile dimensions
  - ``semantic_search``    — matched via CLAP embedding similarity (passthrough, not generated here)

Usage::

    from oracle.explain import ReasonBuilder
    from oracle.types import PlaylistTrack, TrackReason

    builder = ReasonBuilder()

    # Enrich a list of PlaylistTrack objects
    enriched = builder.enrich_playlist(tracks, seed_artist="Slowdive", query="dreamy shoegaze")

    # Build reasons for a single track
    reasons = builder.build_reasons(track_id="abc123", artist="Slowdive", score=0.91,
                                     context={"seed_artist": "My Bloody Valentine"})

Author: Lyra Oracle — Sprint 2, F-007
"""

from __future__ import annotations

import json
import logging
import math
from typing import Dict, List, Optional, Tuple

from oracle.db.schema import get_connection
from oracle.types import PlaylistTrack, TrackReason

logger = logging.getLogger(__name__)

# Dimension set from oracle/anchors.py
_DIMENSIONS = [
    "energy", "valence", "tension", "density",
    "warmth", "movement", "space", "rawness",
    "complexity", "nostalgia",
]

# Minimum similarity threshold to generate a dimensional reason
_DIM_SIMILARITY_THRESHOLD = 0.75


class ReasonBuilder:
    """
    Build structured reasons explaining why each track belongs in a playlist.

    Operates from local DB data only — no API calls, suitable for real-time
    invocation during playlist generation.

    Attributes:
        _score_cache: Dict[track_id → {dim → float}] loaded on first use.
        _taste_profile: User taste profile dict loaded from taste_profile table.
    """

    def __init__(self) -> None:
        self._score_cache: Optional[Dict[str, Dict[str, float]]] = None
        self._taste_profile: Optional[Dict[str, float]] = None
        self._connection_cache: Optional[Dict[str, List[str]]] = None

    # ─── Public API ────────────────────────────────────────────────────────────

    def enrich_playlist(
        self,
        tracks: List[PlaylistTrack],
        seed_artist: Optional[str] = None,
        query: Optional[str] = None,
        include_mood_bridge: bool = True,
    ) -> List[PlaylistTrack]:
        """
        Enrich a list of PlaylistTrack objects with additional reasons.

        Existing reasons (e.g., ``semantic_search``) are preserved. New reasons
        are appended only when they clear the confidence threshold.

        Args:
            tracks: List of PlaylistTrack objects (mutated in-place).
            seed_artist: Optional seed artist for connection reasoning.
            query: The original search query (used for display in reasons).
            include_mood_bridge: Whether to generate mood-bridge reasons
                                  between adjacent tracks.

        Returns:
            The same list with enhanced reason lists.
        """
        if not tracks:
            return tracks

        # Pre-load data in bulk
        track_ids = [t.path for t in tracks]  # path used as track identifier in playlist context
        self._preload_scores(track_ids)
        self._preload_taste_profile()
        if seed_artist:
            self._preload_connections_for_artist(seed_artist)

        for i, track in enumerate(tracks):
            extra_reasons = self._build_extra_reasons(
                track=track,
                seed_artist=seed_artist,
                query=query,
            )

            # Mood bridge — compare to previous track
            if include_mood_bridge and i > 0:
                bridge = self._build_mood_bridge_reason(tracks[i - 1], track)
                if bridge:
                    extra_reasons.append(bridge)

            # Append only novel reason types
            existing_types = {r.type for r in track.reasons}
            for reason in extra_reasons:
                if reason.type not in existing_types:
                    track.reasons.append(reason)
                    existing_types.add(reason.type)

        return tracks

    def build_reasons(
        self,
        track_id: str,
        artist: str,
        title: str,
        score: float,
        context: Optional[Dict] = None,
    ) -> List[TrackReason]:
        """
        Build reasons for a single track in isolation.

        Args:
            track_id: Track ID (or filepath used as playlist_tracks.track_path).
            artist: Artist name.
            title: Track title.
            score: Similarity score (0–1).
            context: Optional context dict::

                {
                    "seed_artist": "...",
                    "query": "...",
                    "taste_profile": {...}
                }

        Returns:
            List of TrackReason objects.
        """
        context = context or {}
        reasons: List[TrackReason] = []

        self._preload_taste_profile()

        # Score-based reason (always)
        if score > 0:
            reasons.append(TrackReason(
                type="semantic_search",
                score=round(score, 4),
                text=f"Matched query: {context.get('query', 'vibe prompt')}",
            ))

        # Artist connection
        seed = context.get("seed_artist")
        if seed and seed.lower() != artist.lower():
            self._preload_connections_for_artist(seed)
            if self._artist_is_connected(seed, artist):
                reasons.append(TrackReason(
                    type="artist-connection",
                    score=0.9,
                    text=f"Connected to {seed} in the relationship graph",
                ))

        # Taste alignment
        taste_reason = self._build_taste_match_reason(track_id)
        if taste_reason:
            reasons.append(taste_reason)

        # Deep cut detection (from enrich_cache)
        deepcut_reason = self._build_deepcut_reason(artist, title)
        if deepcut_reason:
            reasons.append(deepcut_reason)

        return reasons

    def explain_run(self, run_id: int) -> Dict:
        """
        Load and return stored reasons for all tracks in a playlist run.

        Reads from the ``playlist_tracks`` table. Does not re-compute reasons.

        Args:
            run_id: The playlist_runs.id to explain.

        Returns:
            Dict with ``run_id``, ``track_count``, and ``tracks`` list where
            each item has ``rank``, ``track_path``, ``score``, ``reasons``.
        """
        conn = get_connection()
        c = conn.cursor()

        c.execute(
            """SELECT pt.rank, pt.track_path, pt.score, pt.reasons,
                      t.artist, t.title, t.album
               FROM playlist_tracks pt
               LEFT JOIN tracks t ON pt.track_path = t.filepath
               WHERE pt.run_id = ?
               ORDER BY pt.rank""",
            (run_id,),
        )
        rows = c.fetchall()
        conn.close()

        tracks = []
        for row in rows:
            rank, path, score, reasons_json, artist, title, album = row
            try:
                reasons = json.loads(reasons_json) if reasons_json else []
            except (json.JSONDecodeError, TypeError):
                reasons = []

            tracks.append({
                "rank": rank,
                "track_path": path,
                "score": score,
                "artist": artist or "",
                "title": title or "",
                "album": album or "",
                "reasons": reasons,
                "reasons_summary": _summarise_reasons(reasons),
            })

        return {
            "run_id": run_id,
            "track_count": len(tracks),
            "tracks": tracks,
        }

    # ─── Internal Reason Builders ──────────────────────────────────────────────

    def _build_extra_reasons(
        self,
        track: PlaylistTrack,
        seed_artist: Optional[str],
        query: Optional[str],
    ) -> List[TrackReason]:
        """Build non-sequencing reasons for a single PlaylistTrack."""
        reasons: List[TrackReason] = []
        track_id = track.path  # path acts as track identifier in playlist_tracks

        # 1. Taste alignment
        taste_reason = self._build_taste_match_reason(track_id)
        if taste_reason:
            reasons.append(taste_reason)

        # 2. Artist connection
        if seed_artist and seed_artist.lower() != track.artist.lower():
            if self._artist_is_connected(seed_artist, track.artist):
                reasons.append(TrackReason(
                    type="artist-connection",
                    score=0.85,
                    text=f"Artist connected to {seed_artist} in relationship graph",
                ))

        # 3. Deep cut
        dc_reason = self._build_deepcut_reason(track.artist, track.title)
        if dc_reason:
            reasons.append(dc_reason)

        # 4. Dimensional similarity to seed/average
        dim_reason = self._build_dimensional_reason(track_id, track.artist)
        if dim_reason:
            reasons.append(dim_reason)

        return reasons

    def _build_mood_bridge_reason(
        self, prev: PlaylistTrack, curr: PlaylistTrack
    ) -> Optional[TrackReason]:
        """
        Check if the current track makes a smooth emotional transition from the previous.

        Returns a TrackReason if the transition is smooth, None if it's jarring.
        Smoothness = L1 distance across energy + valence + tension dimensions < 0.3.
        """
        prev_scores = self._get_cached_scores(prev.path)
        curr_scores = self._get_cached_scores(curr.path)

        if not prev_scores or not curr_scores:
            return None

        key_dims = ["energy", "valence", "tension"]
        total_dist = sum(
            abs(curr_scores.get(d, 0.5) - prev_scores.get(d, 0.5))
            for d in key_dims
        )
        avg_dist = total_dist / len(key_dims)

        if avg_dist < 0.25:
            smoothness = round(1.0 - avg_dist / 0.25, 3)
            prev_desc = _describe_position(prev_scores)
            curr_desc = _describe_position(curr_scores)
            return TrackReason(
                type="mood-bridge",
                score=smoothness,
                text=f"Smooth transition: {prev_desc} -> {curr_desc}",
            )
        return None

    def _build_taste_match_reason(self, track_id: str) -> Optional[TrackReason]:
        """Check track scores against user taste profile."""
        if not self._taste_profile:
            return None

        scores = self._get_cached_scores(track_id)
        if not scores:
            return None

        total_dist = 0.0
        matched_dims = 0
        for dim in _DIMENSIONS:
            if dim in self._taste_profile and self._taste_profile[dim] is not None:
                dist = abs(scores.get(dim, 0.5) - float(self._taste_profile[dim]))
                total_dist += dist
                matched_dims += 1

        if matched_dims == 0:
            return None

        alignment = 1.0 - (total_dist / matched_dims)
        if alignment >= _DIM_SIMILARITY_THRESHOLD:
            # Find the strongest matching dimensions
            top_dims = _top_aligned_dims(scores, self._taste_profile, n=2)
            dim_text = " + ".join(top_dims) if top_dims else "multiple dimensions"
            return TrackReason(
                type="taste-match",
                score=round(alignment, 3),
                text=f"Strong alignment in {dim_text}",
            )
        return None

    def _build_dimensional_reason(
        self, track_id: str, artist: str
    ) -> Optional[TrackReason]:
        """Build a reason based on dominant dimensional characteristics."""
        scores = self._get_cached_scores(track_id)
        if not scores:
            return None

        # Find the dimension furthest from 0.5 (most distinctive)
        best_dim = None
        best_dist = 0.0
        best_value = 0.5
        for dim in _DIMENSIONS:
            val = scores.get(dim, 0.5)
            dist = abs(val - 0.5)
            if dist > best_dist:
                best_dist = dist
                best_dim = dim
                best_value = val

        if not best_dim or best_dist < 0.3:
            return None

        direction = "high" if best_value > 0.5 else "low"
        return TrackReason(
            type=f"similar-{best_dim}",
            score=round(0.5 + best_dist, 3),
            text=f"{direction.capitalize()} {best_dim} ({best_value:.2f})",
        )

    def _build_deepcut_reason(self, artist: str, title: str) -> Optional[TrackReason]:
        """Check enrich_cache for stored deep cut score."""
        try:
            from oracle.enrichers.cache import make_lookup_key, get_cached_payload
            cache_key = make_lookup_key("deepcut_score", artist, title)
            payload = get_cached_payload("deepcut_score", cache_key, max_age_seconds=86400 * 7)
            if not payload or payload.get("_miss"):
                return None
            os_score = float(payload.get("obscurity_score", 0.0))
            if os_score >= 0.8:
                tier = "holy grail" if os_score >= 1.5 else "hidden gem" if os_score >= 1.0 else "deep cut"
                return TrackReason(
                    type="deep-cut",
                    score=round(min(1.0, os_score / 2.0), 3),
                    text=f"Acclaimed {tier} (obscurity score: {os_score:.2f})",
                )
        except Exception as exc:
            logger.debug("DeepCut reason lookup failed for %s - %s: %s", artist, title, exc)
        return None

    # ─── Data Loaders ──────────────────────────────────────────────────────────

    def _preload_scores(self, track_ids: List[str]) -> None:
        """Batch-load track_scores for all playlist track paths."""
        if self._score_cache is None:
            self._score_cache = {}

        conn = get_connection()
        c = conn.cursor()
        # Scores are keyed by track_id; playlist_tracks uses filepath.
        # Join tracks to get both identifiers.
        c.execute(
            f"""SELECT t.filepath, ts.energy, ts.valence, ts.tension, ts.density,
                       ts.warmth, ts.movement, ts.space, ts.rawness,
                       ts.complexity, ts.nostalgia
                FROM track_scores ts
                JOIN tracks t ON ts.track_id = t.track_id
                LIMIT 10000"""
        )
        for row in c.fetchall():
            filepath = row[0]
            self._score_cache[filepath] = dict(zip(_DIMENSIONS, row[1:]))
        conn.close()

    def _preload_taste_profile(self) -> None:
        """Load the most recent taste profile from the taste_profile table."""
        if self._taste_profile is not None:
            return

        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute(
                "SELECT dimension, score FROM taste_profile ORDER BY updated_at DESC"
            )
            rows = c.fetchall()
            if rows:
                self._taste_profile = {r[0]: float(r[1]) for r in rows}
            else:
                self._taste_profile = {}
        except Exception:
            self._taste_profile = {}
        finally:
            conn.close()

    def _preload_connections_for_artist(self, artist: str) -> None:
        """Load all artists connected to the given artist from the connections table."""
        if self._connection_cache is None:
            self._connection_cache = {}

        if artist in self._connection_cache:
            return

        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute(
                """SELECT entity_b FROM connections
                   WHERE entity_a = ? AND entity_type = 'artist'
                   UNION
                   SELECT entity_a FROM connections
                   WHERE entity_b = ? AND entity_type = 'artist'""",
                (artist, artist),
            )
            connected = [row[0] for row in c.fetchall()]
            self._connection_cache[artist] = [c.lower() for c in connected]
        except Exception as exc:
            logger.debug("Connection load failed for %s: %s", artist, exc)
            self._connection_cache[artist] = []
        finally:
            conn.close()

    def _get_cached_scores(self, track_path: str) -> Optional[Dict[str, float]]:
        """Return cached dimension scores for a track path, or None."""
        if self._score_cache is None:
            return None
        return self._score_cache.get(track_path)

    def _artist_is_connected(self, seed_artist: str, candidate: str) -> bool:
        """Return True if candidate artist is connected to seed_artist in the graph."""
        if self._connection_cache is None:
            return False
        connected = self._connection_cache.get(seed_artist, [])
        return candidate.lower() in connected


# ─── Module-level Helpers ──────────────────────────────────────────────────────

def _summarise_reasons(reasons: List[Dict]) -> str:
    """Produce a short human-readable summary of reason list."""
    if not reasons:
        return "No reasons stored"
    types = [r.get("type", "?") for r in reasons]
    primary = types[0] if types else "unknown"
    extras = len(types) - 1
    summary = f"{primary}"
    if extras > 0:
        summary += f" + {extras} more reason{'s' if extras > 1 else ''}"
    return summary


def _describe_position(scores: Dict[str, float]) -> str:
    """Generate a short descriptor for a track's emotional position."""
    energy = scores.get("energy", 0.5)
    valence = scores.get("valence", 0.5)
    tension = scores.get("tension", 0.5)

    parts = []
    if energy > 0.65:
        parts.append("energetic")
    elif energy < 0.35:
        parts.append("calm")

    if valence > 0.65:
        parts.append("euphoric")
    elif valence < 0.35:
        parts.append("melancholic")

    if tension > 0.65:
        parts.append("tense")
    elif tension < 0.35:
        parts.append("resolved")

    return "/".join(parts) if parts else "neutral"


def _top_aligned_dims(
    track_scores: Dict[str, float],
    taste: Dict[str, float],
    n: int = 2,
) -> List[str]:
    """Return the N dimensions with highest alignment between track and taste."""
    alignments = []
    for dim in _DIMENSIONS:
        if dim in taste and taste[dim] is not None:
            dist = abs(track_scores.get(dim, 0.5) - float(taste[dim]))
            alignments.append((dim, 1.0 - dist))
    alignments.sort(key=lambda x: x[1], reverse=True)
    return [d for d, _ in alignments[:n]]

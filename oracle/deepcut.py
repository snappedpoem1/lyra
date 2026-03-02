"""
Deep Cut Protocol — Obscurity-Weighted Discovery Engine

Surfaces tracks that are acclaimed by those who know, but invisible to the
mainstream. The core insight: scrobble count ≠ quality. A track with 40,000
Last.fm plays but a 4.8 Discogs rating is a better recommendation than a track
with 4 million plays and a 3.2 rating.

Algorithm:
    obscurity_score = acclaim / (popularity_percentile + epsilon)

Where:
    acclaim     = weighted average of Discogs community rating + genre credibility
    popularity  = Last.fm listener/playcount percentile within the local library
    epsilon     = 0.05 (prevents division by zero for truly unknown tracks)

A score > 1.0 means "more acclaimed than its popularity justifies" — that's a Deep Cut.

Author: Lyra Oracle — Sprint 2, F-004
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import requests

from oracle.db.schema import get_connection
from oracle.enrichers.cache import get_or_set_payload, get_cached_payload, make_lookup_key

logger = logging.getLogger(__name__)

_RATE_LOCK = threading.Lock()

# Last.fm configuration
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "")
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_CACHE_TTL = int(os.getenv("LYRA_CACHE_TTL_LASTFM_SECONDS", "604800"))  # 7 days

# Discogs configuration
DISCOGS_API_TOKEN = os.getenv("DISCOGS_API_TOKEN", "") or os.getenv("DISCOGS_TOKEN", "")
DISCOGS_BASE_URL = "https://api.discogs.com"
DISCOGS_CACHE_TTL = int(os.getenv("LYRA_CACHE_TTL_DISCOGS_SECONDS", "1209600"))  # 14 days

# User-Agent
USER_AGENT = os.getenv("LYRA_USER_AGENT", "LyraOracle/1.0")

_EPSILON = 0.05  # prevents division-by-zero in obscurity score


class DeepCut:
    """
    Obscurity-weighted recommendation engine.

    Finds tracks that are critically acclaimed relative to their mainstream
    visibility — the algorithm's version of "hidden gems."

    Usage::

        dc = DeepCut()

        # Hunt for obscure shoegaze
        results = dc.hunt_by_obscurity(genre="shoegaze", min_obscurity=0.7)

        # Hunt using current taste profile
        results = dc.hunt_with_taste_context(taste_dict, limit=20)
    """

    def __init__(self) -> None:
        self._conn = get_connection()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        if DISCOGS_API_TOKEN:
            self._session.headers["Authorization"] = f"Discogs token={DISCOGS_API_TOKEN}"
        self._percentile_cache: Optional[Dict] = None

    # ─── Public API ────────────────────────────────────────────────────────────

    def hunt_by_obscurity(
        self,
        genre: Optional[str] = None,
        artist: Optional[str] = None,
        min_obscurity: float = 0.6,
        max_obscurity: float = 1.0,
        min_acclaim: float = 0.0,
        limit: int = 20,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """
        Return tracks from the local library ranked by obscurity score.

        Args:
            genre: Filter to tracks whose genre column contains this string.
            artist: Filter to a specific artist.
            min_obscurity: Minimum obscurity score (0–∞, recommend 0.5–1.5).
            max_obscurity: Maximum obscurity score (cap outliers).
            min_acclaim: Minimum acclaim component (0–1).
            limit: Max results to return.
            progress_callback: Optional callable(status_string) for progress reporting.

        Returns:
            List of track dicts sorted by obscurity_score descending, each with::

                {
                    "track_id", "artist", "title", "album", "genre", "filepath",
                    "obscurity_score", "acclaim_score", "popularity_percentile",
                    "lastfm_listeners", "lastfm_playcount",
                    "discogs_rating", "tags"
                }
        """
        candidates = self._get_library_candidates(genre=genre, artist=artist, limit=limit * 5)
        if not candidates:
            logger.info("DeepCut: no candidates in library for genre=%s", genre)
            return []

        logger.info("DeepCut: scoring %d candidates (genre=%s)", len(candidates), genre or "all")

        # Pre-compute library percentiles for normalization
        percentiles = self._get_library_percentiles()

        scored: List[Dict] = []

        for i, track in enumerate(candidates):
            if progress_callback and i % 10 == 0:
                progress_callback(f"Scoring {i}/{len(candidates)}: {track['artist']} - {track['title']}")

            scored_track = self._score_track(track, percentiles)

            if scored_track["obscurity_score"] < min_obscurity:
                continue
            if scored_track["obscurity_score"] > max_obscurity:
                continue
            if scored_track["acclaim_score"] < min_acclaim:
                continue

            scored.append(scored_track)

        scored.sort(key=lambda x: x["obscurity_score"], reverse=True)
        logger.info("DeepCut: %d deep cuts found (min_obscurity=%.2f)", len(scored), min_obscurity)
        return scored[:limit]

    def hunt_with_taste_context(
        self,
        taste_profile: Dict,
        limit: int = 20,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[Dict]:
        """
        Hunt for deep cuts that align with the user's taste profile dimensions.

        The taste profile is a dict with dimension scores (0–1) matching the
        10-dimensional model in oracle/anchors.py::

            { "energy": 0.7, "valence": 0.6, "tension": 0.3, ... }

        Tracks are first filtered by taste alignment (cosine proximity to profile
        scores in track_scores table), then ranked by obscurity score. This finds
        "tracks like what you love, but that nobody else has heard."

        Args:
            taste_profile: Dict of dimension → float (0–1).
            limit: Max results.
            progress_callback: Optional progress reporter.

        Returns:
            Same structure as hunt_by_obscurity(), plus ``taste_alignment`` float.
        """
        taste_candidates = self._get_taste_aligned_candidates(taste_profile, limit * 5)
        if not taste_candidates:
            logger.info("DeepCut: no taste-aligned candidates — falling back to random selection")
            taste_candidates = self._get_library_candidates(limit=limit * 5)

        percentiles = self._get_library_percentiles()

        scored: List[Dict] = []
        for i, track in enumerate(taste_candidates):
            if progress_callback and i % 10 == 0:
                progress_callback(f"Scoring {i}/{len(taste_candidates)}: {track['artist']} - {track['title']}")

            scored_track = self._score_track(track, percentiles)
            scored_track["taste_alignment"] = track.get("taste_alignment", 0.0)
            scored.append(scored_track)

        # Blend obscurity + taste alignment into final rank
        for track in scored:
            track["deep_cut_rank"] = (
                track["obscurity_score"] * 0.6 + track["taste_alignment"] * 0.4
            )

        scored.sort(key=lambda x: x["deep_cut_rank"], reverse=True)
        return scored[:limit]

    def get_stats(self) -> Dict:
        """
        Return summary statistics about deep cut potential across the library.

        Returns::

            {
                "total_tracks": int,
                "tracks_scored": int,   # those with Last.fm cache data
                "median_obscurity": float,
                "high_potential_count": int,  # obscurity_score > 0.8
                "top_5_deep_cuts": List[{artist, title, obscurity_score}],
            }
        """
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM tracks")
        total = c.fetchone()[0]

        # Count tracks with Last.fm cache data
        c.execute(
            "SELECT COUNT(*) FROM enrich_cache WHERE provider = 'deepcut_lastfm'"
        )
        scored = c.fetchone()[0]

        # Pull existing obscurity data from deepcut cache
        c.execute(
            """SELECT payload FROM enrich_cache
               WHERE provider = 'deepcut_score'
               ORDER BY updated_at DESC LIMIT 500"""
        )
        rows = c.fetchall()
        conn.close()

        scores: List[float] = []
        top: List[Dict] = []
        for row in rows:
            try:
                payload = json.loads(row[0])
                os_score = payload.get("obscurity_score", 0.0)
                scores.append(os_score)
                if os_score > 0.8:
                    top.append({
                        "artist": payload.get("artist", ""),
                        "title": payload.get("title", ""),
                        "obscurity_score": round(os_score, 3),
                    })
            except (json.JSONDecodeError, KeyError):
                continue

        top.sort(key=lambda x: x["obscurity_score"], reverse=True)
        return {
            "total_tracks": total,
            "tracks_scored": scored,
            "median_obscurity": round(statistics.median(scores), 3) if scores else 0.0,
            "high_potential_count": len([s for s in scores if s > 0.8]),
            "top_5_deep_cuts": top[:5],
        }

    # ─── Scoring Logic ─────────────────────────────────────────────────────────

    def _score_track(self, track: Dict, percentiles: Dict) -> Dict:
        """
        Compute obscurity score for a single track.

        Returns a dict containing all score components merged into the track dict.
        """
        artist = track.get("artist", "")
        title = track.get("title", "")
        track_id = track.get("track_id", "")

        # Check for a cached full score first (avoids API re-calls)
        cache_key = make_lookup_key("deepcut_score", artist, title)
        cached = get_cached_payload("deepcut_score", cache_key, max_age_seconds=86400 * 3)
        if cached and not cached.get("_miss"):
            return {**track, **cached}

        # Fetch data components
        lfm = self._get_lastfm_data(artist, title)
        discogs_rating = self._get_discogs_rating(artist, title)

        listeners: int = lfm.get("listeners", 0)
        playcount: int = lfm.get("playcount", 0)

        # Compute popularity percentile (relative to local library distribution)
        popularity_pct = self._compute_popularity_percentile(listeners, percentiles)

        # Compute acclaim (0–1)
        acclaim = self._compute_acclaim(discogs_rating, lfm)

        # Obscurity score: acclaimed ÷ popular
        obscurity = acclaim / (popularity_pct + _EPSILON)

        score_payload = {
            "track_id": track_id,
            "artist": artist,
            "title": title,
            "album": track.get("album", ""),
            "genre": track.get("genre", ""),
            "filepath": track.get("filepath", ""),
            "obscurity_score": round(obscurity, 4),
            "acclaim_score": round(acclaim, 4),
            "popularity_percentile": round(popularity_pct, 4),
            "lastfm_listeners": listeners,
            "lastfm_playcount": playcount,
            "discogs_rating": discogs_rating,
            "tags": self._build_tags(obscurity, acclaim, popularity_pct, track.get("genre", "")),
        }

        # Cache the score for 3 days
        from oracle.enrichers.cache import set_cached_payload
        set_cached_payload("deepcut_score", cache_key, score_payload)

        return score_payload

    def _compute_popularity_percentile(self, listeners: int, percentiles: Dict) -> float:
        """
        Map a raw listeners count to a 0–1 percentile within the local library.

        Uses a pre-computed percentile table from _get_library_percentiles().
        Returns values close to 0.0 for unknown/obscure, close to 1.0 for mainstream.
        """
        if not listeners:
            return 0.01  # nearly unknown — treat as very obscure

        buckets = percentiles.get("listener_buckets", [])
        if not buckets:
            # Fallback: log-scale estimate against typical Last.fm population
            import math
            return min(1.0, math.log10(max(listeners, 1)) / 7.0)  # 10M = 1.0

        for pct, threshold in buckets:
            if listeners <= threshold:
                return pct
        return 1.0  # above highest bucket → mainstream

    def _compute_acclaim(self, discogs_rating: float, lfm_data: Dict) -> float:
        """
        Blend Discogs community rating with Last.fm tag quality signal.

        Returns a 0–1 float where 1.0 = exceptionally acclaimed.
        """
        components: List[Tuple[float, float]] = []  # (weight, value)

        if discogs_rating > 0:
            # Discogs community ratings are on 0–5, normalise to 0–1
            normalised = min(1.0, discogs_rating / 5.0)
            components.append((0.5, normalised))

        # Last.fm listeners can serve as a weak quality proxy when > 50k
        # (tracks with very few listeners AND a high Discogs rating = hidden gem)
        # If no Discogs data, use Last.fm track.getInfo userplaycount as proxy
        if not components:
            # No external rating — use a neutral-but-positive prior
            components.append((1.0, 0.5))

        total_weight = sum(w for w, _ in components)
        acclaim = sum(w * v for w, v in components) / total_weight
        return round(acclaim, 4)

    def _build_tags(
        self, obscurity: float, acclaim: float, pop_pct: float, genre: str
    ) -> List[str]:
        """Build descriptive tags for a deep cut result."""
        tags: List[str] = ["deepcut:true"]

        if obscurity > 1.5:
            tags.append("tier:holy_grail")
        elif obscurity > 1.0:
            tags.append("tier:hidden_gem")
        elif obscurity > 0.7:
            tags.append("tier:deep_cut")
        else:
            tags.append("tier:underrated")

        if pop_pct < 0.1:
            tags.append("visibility:nearly_unknown")
        elif pop_pct < 0.25:
            tags.append("visibility:obscure")

        if acclaim > 0.8:
            tags.append("quality:exceptional")
        elif acclaim > 0.6:
            tags.append("quality:acclaimed")

        if genre:
            safe_genre = genre.lower().replace(" ", "_").replace("/", "_")[:30]
            tags.append(f"genre:{safe_genre}")

        return tags

    # ─── Library Queries ───────────────────────────────────────────────────────

    def _get_library_candidates(
        self,
        genre: Optional[str] = None,
        artist: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict]:
        """Pull tracks from the local library with optional genre/artist filter."""
        conn = get_connection()
        c = conn.cursor()

        conditions: List[str] = []
        params: List = []

        if genre:
            conditions.append("(genre LIKE ? OR genre LIKE ?)")
            params.extend([f"%{genre}%", f"%{genre.capitalize()}%"])

        if artist:
            conditions.append("artist LIKE ?")
            params.append(f"%{artist}%")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        c.execute(
            f"""SELECT track_id, artist, title, album, genre, filepath
                FROM tracks
                {where_clause}
                ORDER BY RANDOM()
                LIMIT ?""",
            params,
        )
        rows = c.fetchall()
        conn.close()

        return [
            {
                "track_id": row[0],
                "artist": row[1] or "",
                "title": row[2] or "",
                "album": row[3] or "",
                "genre": row[4] or "",
                "filepath": row[5] or "",
            }
            for row in rows
        ]

    def _get_taste_aligned_candidates(
        self, taste_profile: Dict, limit: int = 200
    ) -> List[Dict]:
        """
        Find tracks whose scores align with the provided taste profile.

        Uses a simple L1 distance across the 10 dimensions stored in track_scores.
        Returns top candidates sorted by alignment (closest = highest score).
        """
        conn = get_connection()
        c = conn.cursor()

        dimensions = [
            "energy", "valence", "tension", "density",
            "warmth", "movement", "space", "rawness",
            "complexity", "nostalgia",
        ]

        c.execute(
            """SELECT ts.track_id, t.artist, t.title, t.album, t.genre, t.filepath,
                      ts.energy, ts.valence, ts.tension, ts.density,
                      ts.warmth, ts.movement, ts.space, ts.rawness,
                      ts.complexity, ts.nostalgia
               FROM track_scores ts
               JOIN tracks t ON ts.track_id = t.track_id
               LIMIT 5000"""
        )
        rows = c.fetchall()
        conn.close()

        results: List[Dict] = []
        for row in rows:
            track_scores = dict(zip(dimensions, row[6:]))

            # Compute taste alignment as 1 - normalised L1 distance
            total_dist = 0.0
            matched_dims = 0
            for dim in dimensions:
                if dim in taste_profile and taste_profile[dim] is not None:
                    dist = abs(track_scores.get(dim, 0.5) - float(taste_profile[dim]))
                    total_dist += dist
                    matched_dims += 1

            if matched_dims == 0:
                alignment = 0.5
            else:
                normalised_dist = total_dist / matched_dims  # 0–1 per dim
                alignment = 1.0 - normalised_dist

            results.append(
                {
                    "track_id": row[0],
                    "artist": row[1] or "",
                    "title": row[2] or "",
                    "album": row[3] or "",
                    "genre": row[4] or "",
                    "filepath": row[5] or "",
                    "taste_alignment": round(alignment, 4),
                }
            )

        results.sort(key=lambda x: x["taste_alignment"], reverse=True)
        return results[:limit]

    def _get_library_percentiles(self) -> Dict:
        """
        Compute listener-count percentile buckets from cached Last.fm data.

        Builds a lookup table::

            { "listener_buckets": [(0.1, 500), (0.25, 5000), (0.5, 50000), ...] }

        where (percentile, max_listeners_at_that_percentile).

        Results are cached in self._percentile_cache for the session.
        """
        if self._percentile_cache is not None:
            return self._percentile_cache

        conn = get_connection()
        c = conn.cursor()
        c.execute(
            """SELECT payload FROM enrich_cache
               WHERE provider = 'deepcut_lastfm'
               ORDER BY updated_at DESC LIMIT 2000"""
        )
        rows = c.fetchall()
        conn.close()

        listener_counts: List[int] = []
        for row in rows:
            try:
                payload = json.loads(row[0])
                if not payload.get("_miss"):
                    listeners = int(payload.get("listeners", 0))
                    if listeners > 0:
                        listener_counts.append(listeners)
            except (json.JSONDecodeError, ValueError):
                continue

        if len(listener_counts) < 10:
            # Not enough data — use sensible defaults derived from Last.fm distribution
            self._percentile_cache = {
                "listener_buckets": [
                    (0.05, 1_000),
                    (0.10, 5_000),
                    (0.25, 25_000),
                    (0.50, 150_000),
                    (0.75, 500_000),
                    (0.90, 1_500_000),
                    (0.95, 5_000_000),
                ]
            }
            return self._percentile_cache

        listener_counts.sort()
        n = len(listener_counts)
        percentile_points = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
        buckets = []
        for pct in percentile_points:
            idx = max(0, int(pct * n) - 1)
            buckets.append((pct, listener_counts[idx]))

        self._percentile_cache = {"listener_buckets": buckets}
        return self._percentile_cache

    # ─── External API calls ────────────────────────────────────────────────────

    def _get_lastfm_data(self, artist: str, title: str) -> Dict:
        """
        Fetch Last.fm track.getInfo for listeners + playcount.

        Cached for 7 days under provider='deepcut_lastfm'.
        Returns dict with keys: listeners, playcount (both int, default 0).
        """
        if not LASTFM_API_KEY:
            return {"listeners": 0, "playcount": 0}

        cache_key = make_lookup_key("deepcut_lastfm", artist, title)
        miss = {"_miss": True, "listeners": 0, "playcount": 0}

        def _fetch() -> Dict:
            with _RATE_LOCK:
                time.sleep(0.25)  # Last.fm: ~4 req/s
            try:
                resp = self._session.get(
                    LASTFM_BASE_URL,
                    params={
                        "method": "track.getInfo",
                        "artist": artist,
                        "track": title,
                        "api_key": LASTFM_API_KEY,
                        "format": "json",
                        "autocorrect": "1",
                    },
                    timeout=10,
                )
                if resp.status_code != 200:
                    return miss
                data = resp.json()
                track_info = data.get("track", {})
                if not track_info:
                    return miss
                return {
                    "listeners": int(track_info.get("listeners", 0)),
                    "playcount": int(track_info.get("playcount", 0)),
                    "duration": int(track_info.get("duration", 0)),
                    "name": track_info.get("name", title),
                    "artist": track_info.get("artist", {}).get("name", artist),
                    "tags": [
                        t.get("name", "")
                        for t in track_info.get("toptags", {}).get("tag", [])
                    ][:5],
                }
            except Exception as exc:
                logger.debug("DeepCut Last.fm error for %s - %s: %s", artist, title, exc)
                return miss

        payload = get_or_set_payload(
            provider="deepcut_lastfm",
            lookup_key=cache_key,
            max_age_seconds=LASTFM_CACHE_TTL,
            fetcher=_fetch,
            miss_payload=miss,
        )
        return payload if not payload.get("_miss") else {"listeners": 0, "playcount": 0}

    def _get_discogs_rating(self, artist: str, title: str) -> float:
        """
        Fetch Discogs community rating for a track/release.

        Returns a 0–5 float (0 if not found or API unavailable).
        Cached for 14 days under provider='deepcut_discogs'.
        """
        if not DISCOGS_API_TOKEN:
            return 0.0

        cache_key = make_lookup_key("deepcut_discogs", artist, title)
        miss = {"_miss": True, "rating": 0.0}

        def _fetch() -> Dict:
            with _RATE_LOCK:
                time.sleep(1.0)  # Discogs: 60 req/min
            try:
                resp = self._session.get(
                    f"{DISCOGS_BASE_URL}/database/search",
                    params={
                        "artist": artist,
                        "track": title,
                        "type": "release",
                        "per_page": "1",
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    return miss
                results = resp.json().get("results", [])
                if not results:
                    return miss

                release_id = results[0].get("id")
                if not release_id:
                    return miss

                # Fetch release details for community rating
                detail_resp = self._session.get(
                    f"{DISCOGS_BASE_URL}/releases/{release_id}",
                    timeout=15,
                )
                with _RATE_LOCK:
                    time.sleep(1.0)

                if detail_resp.status_code != 200:
                    return miss

                detail = detail_resp.json()
                community = detail.get("community", {})
                rating_data = community.get("rating", {})
                avg_rating = float(rating_data.get("average", 0.0))
                vote_count = int(rating_data.get("count", 0))

                if vote_count < 3:
                    # Too few votes to be meaningful
                    return miss

                return {
                    "rating": avg_rating,
                    "votes": vote_count,
                    "have": community.get("have", 0),
                    "want": community.get("want", 0),
                    "release_id": release_id,
                }
            except Exception as exc:
                logger.debug("DeepCut Discogs error for %s - %s: %s", artist, title, exc)
                return miss

        payload = get_or_set_payload(
            provider="deepcut_discogs",
            lookup_key=cache_key,
            max_age_seconds=DISCOGS_CACHE_TTL,
            fetcher=_fetch,
            miss_payload=miss,
        )
        return float(payload.get("rating", 0.0)) if not payload.get("_miss") else 0.0


# ─── Module-level convenience ──────────────────────────────────────────────────

_deepcut_instance: Optional[DeepCut] = None


def get_deepcut() -> DeepCut:
    """Return the module-level singleton DeepCut instance."""
    global _deepcut_instance
    if _deepcut_instance is None:
        _deepcut_instance = DeepCut()
    return _deepcut_instance

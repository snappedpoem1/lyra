"""
Lyra Oracle — Spotify Full Import Pipeline
============================================
Ingests everything: extended streaming history, liked songs, playlists,
top tracks, and audio features. Cross-references against local library
to generate a prioritized acquisition queue.

Usage:
    python spotify_import.py --all                    # Full import (history + library + queue)
    python spotify_import.py --history                # Extended streaming history only
    python spotify_import.py --library                # Liked songs + playlists + top tracks
    python spotify_import.py --queue                  # Generate acquisition queue from imported data
    python spotify_import.py --queue --min-plays 3    # Lower threshold for queue inclusion
    python spotify_import.py --features               # Fetch Spotify audio features for all imported tracks

Requires:
    pip install spotipy python-dotenv

Environment (.env):
    SPOTIFY_CLIENT_ID=your_client_id
    SPOTIFY_CLIENT_SECRET=your_client_secret
    LYRA_BASE_PATH=C:/MusicOracle        (default)
    LYRA_DB_PATH=lyra_registry.db        (relative to base, or absolute)
"""

import os
import sys
import json
import sqlite3
import hashlib
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Tuple

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

load_dotenv()

BASE_PATH = Path(os.getenv("LYRA_BASE_PATH", "C:/MusicOracle"))
DB_PATH = Path(os.getenv("LYRA_DB_PATH", str(BASE_PATH / "lyra_registry.db")))
# Prefer data/spotify/ (where files actually live), fall back to Spotify_Import/
_DATA_SPOTIFY = BASE_PATH / "data" / "spotify"
_LEGACY_IMPORT = BASE_PATH / "Spotify_Import"
SPOTIFY_IMPORT_DIR = _DATA_SPOTIFY if _DATA_SPOTIFY.exists() else _LEGACY_IMPORT
REDIRECT_URI = "http://127.0.0.1:42069/callback"

# Scopes needed for full library access
SCOPES = [
    "user-library-read",        # Liked songs
    "playlist-read-private",    # Private playlists
    "playlist-read-collaborative",
    "user-top-read",            # Top tracks/artists
    "user-read-recently-played",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lyra.spotify")


# ──────────────────────────────────────────────────────────────
# Database Setup
# ──────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Extended streaming history from Spotify data export
CREATE TABLE IF NOT EXISTS spotify_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT,
    track TEXT,
    album TEXT,
    played_at TEXT,
    ms_played INTEGER,
    spotify_track_uri TEXT,
    reason_start TEXT,
    reason_end TEXT,
    shuffle INTEGER,
    skipped INTEGER,
    platform TEXT,
    conn_country TEXT,
    ip_addr TEXT,
    episode_name TEXT,
    episode_show_name TEXT,
    imported_at TEXT DEFAULT (datetime('now'))
);

-- Live library data pulled via Spotify API
CREATE TABLE IF NOT EXISTS spotify_library (
    spotify_uri TEXT PRIMARY KEY,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    album TEXT,
    album_uri TEXT,
    artist_uri TEXT,
    duration_ms INTEGER,
    popularity INTEGER,
    explicit INTEGER,
    release_date TEXT,
    track_number INTEGER,
    disc_number INTEGER,
    isrc TEXT,
    preview_url TEXT,
    album_art_url TEXT,
    source TEXT DEFAULT 'liked',   -- liked | playlist | top_tracks
    playlist_name TEXT,            -- which playlist (if source=playlist)
    added_at TEXT,                 -- when user saved/added it
    imported_at TEXT DEFAULT (datetime('now'))
);

-- Spotify audio features (energy, valence, etc.) — bootstraps emotional scoring
CREATE TABLE IF NOT EXISTS spotify_features (
    spotify_uri TEXT PRIMARY KEY,
    danceability REAL,
    energy REAL,
    key INTEGER,
    loudness REAL,
    mode INTEGER,
    speechiness REAL,
    acousticness REAL,
    instrumentalness REAL,
    liveness REAL,
    valence REAL,
    tempo REAL,
    time_signature INTEGER,
    fetched_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(spotify_uri) REFERENCES spotify_library(spotify_uri)
);

-- Acquisition queue: tracks we want but don't have locally
CREATE TABLE IF NOT EXISTS acquisition_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    album TEXT,
    spotify_uri TEXT,
    priority_score REAL DEFAULT 0.0,
    play_count INTEGER DEFAULT 0,
    source TEXT,                    -- history | liked | playlist | top_tracks
    status TEXT DEFAULT 'pending',  -- pending | searching | downloading | complete | failed | skipped
    search_query TEXT,              -- pre-built query for Real-Debrid/Prowlarr
    added_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    matched_track_id TEXT,          -- links to tracks.track_id once acquired
    FOREIGN KEY(matched_track_id) REFERENCES tracks(track_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_history_artist_track ON spotify_history(artist, track);
CREATE INDEX IF NOT EXISTS idx_history_played_at ON spotify_history(played_at);
CREATE INDEX IF NOT EXISTS idx_history_uri ON spotify_history(spotify_track_uri);
CREATE INDEX IF NOT EXISTS idx_library_artist_title ON spotify_library(artist, title);
CREATE INDEX IF NOT EXISTS idx_library_source ON spotify_library(source);
CREATE INDEX IF NOT EXISTS idx_queue_status ON acquisition_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_priority ON acquisition_queue(priority_score DESC);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize database with WAL mode and create tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.info(f"Database ready: {db_path}")
    return conn


def get_spotify_client() -> spotipy.Spotify:
    """Authenticate and return Spotify client."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.error("Missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET in .env")
        sys.exit(1)

    cache_path = BASE_PATH / ".spotify_cache"
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=" ".join(SCOPES),
        cache_path=str(cache_path),
        open_browser=True,
    )

    sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=30)

    # Verify connection
    user = sp.current_user()
    logger.info(f"Authenticated as: {user['display_name']} ({user['id']})")
    return sp


# ──────────────────────────────────────────────────────────────
# 1. Extended Streaming History Import
# ──────────────────────────────────────────────────────────────

def find_history_files() -> List[Path]:
    """Locate extended streaming history JSON files."""
    search_dirs = [
        SPOTIFY_IMPORT_DIR,
        BASE_PATH / "data" / "spotify",
        BASE_PATH / "my_spotify_data",
        BASE_PATH / "Spotify Extended Streaming History",
        BASE_PATH,
    ]

    patterns = [
        "Streaming_History_Audio_*.json",
        "endsong_*.json",
    ]

    found = []
    for d in search_dirs:
        if not d.exists():
            continue
        for pattern in patterns:
            found.extend(sorted(d.glob(pattern)))

    # Deduplicate by resolved path
    seen = set()
    unique = []
    for f in found:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(f)

    return unique


def import_streaming_history(conn: sqlite3.Connection) -> Dict:
    """Import extended streaming history JSON files into database."""
    files = find_history_files()
    if not files:
        logger.warning(
            "No streaming history files found. Place Streaming_History_Audio_*.json "
            f"or endsong_*.json in: {SPOTIFY_IMPORT_DIR}"
        )
        return {"files": 0, "streams": 0, "skipped": 0, "errors": 0}

    logger.info(f"Found {len(files)} history file(s)")
    cursor = conn.cursor()

    total_streams = 0
    total_skipped = 0
    total_errors = 0

    for filepath in files:
        logger.info(f"  Processing: {filepath.name}")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"  Failed to parse {filepath.name}: {e}")
            total_errors += 1
            continue

        batch = []
        for entry in entries:
            # Handle both extended and standard history formats
            artist = (
                entry.get("master_metadata_album_artist_name")
                or entry.get("artistName")
                or ""
            ).strip()
            track = (
                entry.get("master_metadata_track_name")
                or entry.get("trackName")
                or ""
            ).strip()
            album = (
                entry.get("master_metadata_album_album_name")
                or entry.get("albumName")
                or ""
            ).strip()

            # Skip podcast episodes and empty entries
            if not artist and not track:
                episode = entry.get("episode_name") or entry.get("episode_show_name")
                if episode:
                    continue  # It's a podcast, skip silently
                total_skipped += 1
                continue

            # Parse timestamp
            played_at = (
                entry.get("ts")
                or entry.get("endTime")
                or entry.get("played_at")
                or ""
            )

            ms_played = entry.get("ms_played", entry.get("msPlayed", 0))
            uri = entry.get("spotify_track_uri", "")
            reason_start = entry.get("reason_start", "")
            reason_end = entry.get("reason_end", "")
            shuffle = 1 if entry.get("shuffle") else 0
            skipped = 1 if entry.get("skipped") else 0
            platform = entry.get("platform", "")
            conn_country = entry.get("conn_country", "")
            ip_addr = entry.get("ip_addr_decrypted", entry.get("ip_addr", ""))
            episode_name = entry.get("episode_name", "")
            episode_show = entry.get("episode_show_name", "")

            batch.append((
                artist, track, album, played_at, ms_played, uri,
                reason_start, reason_end, shuffle, skipped,
                platform, conn_country, ip_addr,
                episode_name, episode_show,
            ))

        if batch:
            cursor.executemany("""
                INSERT INTO spotify_history (
                    artist, track, album, played_at, ms_played, spotify_track_uri,
                    reason_start, reason_end, shuffle, skipped,
                    platform, conn_country, ip_addr,
                    episode_name, episode_show_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            total_streams += len(batch)

        logger.info(f"    → {len(batch):,} streams imported")

    conn.commit()

    stats = {
        "files": len(files),
        "streams": total_streams,
        "skipped": total_skipped,
        "errors": total_errors,
    }
    logger.info(
        f"History import complete: {total_streams:,} streams from {len(files)} files "
        f"({total_skipped} skipped, {total_errors} errors)"
    )
    return stats


# ──────────────────────────────────────────────────────────────
# 2. Live Library Pull (Liked Songs, Playlists, Top Tracks)
# ──────────────────────────────────────────────────────────────

def _extract_track_data(item: Dict, source: str, playlist_name: str = None) -> Optional[Dict]:
    """Extract standardized track data from various Spotify API response shapes."""
    # Handle the nested "track" wrapper (saved tracks / playlist tracks)
    track = item.get("track", item)
    if not track or track.get("is_local"):
        return None

    artists = track.get("artists", [])
    album = track.get("album", {})
    images = album.get("images", [])

    return {
        "spotify_uri": track.get("uri", ""),
        "artist": ", ".join(a["name"] for a in artists) if artists else "Unknown",
        "title": track.get("name", "Unknown"),
        "album": album.get("name", ""),
        "album_uri": album.get("uri", ""),
        "artist_uri": artists[0]["uri"] if artists else "",
        "duration_ms": track.get("duration_ms", 0),
        "popularity": track.get("popularity", 0),
        "explicit": 1 if track.get("explicit") else 0,
        "release_date": album.get("release_date", ""),
        "track_number": track.get("track_number", 0),
        "disc_number": track.get("disc_number", 0),
        "isrc": track.get("external_ids", {}).get("isrc", ""),
        "preview_url": track.get("preview_url", ""),
        "album_art_url": images[0]["url"] if images else "",
        "source": source,
        "playlist_name": playlist_name,
        "added_at": item.get("added_at", ""),
    }


def _upsert_library_track(cursor: sqlite3.Cursor, data: Dict):
    """Upsert a track into spotify_library (update source if already exists with higher priority)."""
    # Priority: liked > playlist > top_tracks (liked = you actively saved it)
    source_priority = {"liked": 3, "playlist": 2, "top_tracks": 1}

    cursor.execute("SELECT source FROM spotify_library WHERE spotify_uri = ?", (data["spotify_uri"],))
    existing = cursor.fetchone()

    if existing:
        existing_priority = source_priority.get(existing[0], 0)
        new_priority = source_priority.get(data["source"], 0)
        if new_priority > existing_priority:
            cursor.execute("""
                UPDATE spotify_library SET source = ?, playlist_name = ?, added_at = ?
                WHERE spotify_uri = ?
            """, (data["source"], data["playlist_name"], data["added_at"], data["spotify_uri"]))
    else:
        cursor.execute("""
            INSERT INTO spotify_library (
                spotify_uri, artist, title, album, album_uri, artist_uri,
                duration_ms, popularity, explicit, release_date,
                track_number, disc_number, isrc, preview_url, album_art_url,
                source, playlist_name, added_at
            ) VALUES (
                :spotify_uri, :artist, :title, :album, :album_uri, :artist_uri,
                :duration_ms, :popularity, :explicit, :release_date,
                :track_number, :disc_number, :isrc, :preview_url, :album_art_url,
                :source, :playlist_name, :added_at
            )
        """, data)


def import_liked_songs(sp: spotipy.Spotify, conn: sqlite3.Connection) -> int:
    """Pull all liked/saved songs."""
    logger.info("Importing liked songs...")
    cursor = conn.cursor()
    count = 0
    offset = 0
    limit = 50

    while True:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        items = results.get("items", [])
        if not items:
            break

        for item in items:
            data = _extract_track_data(item, source="liked")
            if data:
                _upsert_library_track(cursor, data)
                count += 1

        offset += limit
        if offset % 500 == 0:
            logger.info(f"  ...{offset} liked songs processed")
            conn.commit()

        if not results.get("next"):
            break

    conn.commit()
    logger.info(f"  → {count:,} liked songs imported")
    return count


def import_playlists(sp: spotipy.Spotify, conn: sqlite3.Connection) -> int:
    """Pull all tracks from user's playlists (owned + followed)."""
    logger.info("Importing playlists...")
    cursor = conn.cursor()
    total_tracks = 0
    offset = 0

    while True:
        playlists = sp.current_user_playlists(limit=50, offset=offset)
        items = playlists.get("items", [])
        if not items:
            break

        for playlist in items:
            name = playlist.get("name", "Unknown Playlist")
            playlist_id = playlist.get("id")
            owner = playlist.get("owner", {}).get("display_name", "")
            track_count = playlist.get("tracks", {}).get("total", 0)

            logger.info(f"  Playlist: {name} ({track_count} tracks, by {owner})")

            # Fetch all tracks from this playlist
            pl_offset = 0
            pl_count = 0
            while True:
                try:
                    tracks = sp.playlist_tracks(
                        playlist_id, limit=100, offset=pl_offset,
                        fields="items(added_at,track(uri,name,artists,album,duration_ms,"
                               "popularity,explicit,track_number,disc_number,external_ids,"
                               "preview_url,is_local)),next"
                    )
                except Exception as e:
                    logger.warning(f"    Error fetching {name} at offset {pl_offset}: {e}")
                    break

                for item in tracks.get("items", []):
                    data = _extract_track_data(item, source="playlist", playlist_name=name)
                    if data:
                        _upsert_library_track(cursor, data)
                        pl_count += 1

                pl_offset += 100
                if not tracks.get("next"):
                    break

            total_tracks += pl_count
            conn.commit()

        offset += 50
        if not playlists.get("next"):
            break

    logger.info(f"  → {total_tracks:,} playlist tracks imported")
    return total_tracks


def import_top_tracks(sp: spotipy.Spotify, conn: sqlite3.Connection) -> int:
    """Pull top tracks across all time ranges."""
    logger.info("Importing top tracks...")
    cursor = conn.cursor()
    count = 0

    for time_range in ["short_term", "medium_term", "long_term"]:
        results = sp.current_user_top_tracks(limit=50, time_range=time_range)
        for item in results.get("items", []):
            data = _extract_track_data(item, source="top_tracks")
            if data:
                _upsert_library_track(cursor, data)
                count += 1

    conn.commit()
    logger.info(f"  → {count:,} top tracks imported (across all time ranges)")
    return count


def import_full_library(sp: spotipy.Spotify, conn: sqlite3.Connection) -> Dict:
    """Run the complete library import."""
    stats = {}
    stats["liked"] = import_liked_songs(sp, conn)
    stats["playlists"] = import_playlists(sp, conn)
    stats["top_tracks"] = import_top_tracks(sp, conn)

    # Summary
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM spotify_library")
    stats["unique_tracks"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT artist) FROM spotify_library")
    stats["unique_artists"] = cursor.fetchone()[0]

    logger.info(
        f"\nLibrary import complete: {stats['unique_tracks']:,} unique tracks "
        f"from {stats['unique_artists']:,} artists"
    )
    return stats


# ──────────────────────────────────────────────────────────────
# 3. Audio Features (Bootstrap Emotional Scoring)
# ──────────────────────────────────────────────────────────────

def fetch_audio_features(sp: spotipy.Spotify, conn: sqlite3.Connection) -> int:
    """Fetch Spotify audio features for all library tracks. Bootstraps emotional scoring."""
    logger.info("Fetching audio features...")
    cursor = conn.cursor()

    # Get URIs that don't have features yet
    cursor.execute("""
        SELECT sl.spotify_uri
        FROM spotify_library sl
        LEFT JOIN spotify_features sf ON sl.spotify_uri = sf.spotify_uri
        WHERE sf.spotify_uri IS NULL
          AND sl.spotify_uri != ''
          AND sl.spotify_uri LIKE 'spotify:track:%'
    """)
    uris = [row[0] for row in cursor.fetchall()]

    if not uris:
        logger.info("  All tracks already have audio features")
        return 0

    logger.info(f"  Fetching features for {len(uris):,} tracks...")
    count = 0

    # Spotify API accepts up to 100 track IDs per request
    for i in range(0, len(uris), 100):
        batch_uris = uris[i : i + 100]
        # Extract track IDs from URIs
        track_ids = [uri.split(":")[-1] for uri in batch_uris]

        try:
            features_list = sp.audio_features(track_ids)
        except Exception as e:
            logger.warning(f"  Error fetching features batch at {i}: {e}")
            continue

        for uri, features in zip(batch_uris, features_list):
            if not features:
                continue
            cursor.execute("""
                INSERT OR REPLACE INTO spotify_features (
                    spotify_uri, danceability, energy, key, loudness, mode,
                    speechiness, acousticness, instrumentalness, liveness,
                    valence, tempo, time_signature
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uri,
                features.get("danceability"),
                features.get("energy"),
                features.get("key"),
                features.get("loudness"),
                features.get("mode"),
                features.get("speechiness"),
                features.get("acousticness"),
                features.get("instrumentalness"),
                features.get("liveness"),
                features.get("valence"),
                features.get("tempo"),
                features.get("time_signature"),
            ))
            count += 1

        if (i + 100) % 1000 == 0:
            logger.info(f"    ...{i + 100}/{len(uris)} processed")
            conn.commit()

    conn.commit()
    logger.info(f"  → {count:,} audio feature sets fetched")
    return count


# ──────────────────────────────────────────────────────────────
# 4. Acquisition Queue Generator
# ──────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Normalize text for fuzzy matching."""
    import re
    text = text.lower().strip()
    # Remove common suffixes that vary between sources
    text = re.sub(r"\s*\(feat\.?.*?\)", "", text)
    text = re.sub(r"\s*\[feat\.?.*?\]", "", text)
    text = re.sub(r"\s*ft\.?\s+.*$", "", text)
    text = re.sub(r"\s*-\s*(remaster(ed)?|deluxe|bonus|anniversary).*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^\w\s]", "", text)  # strip punctuation
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _check_local_ownership(cursor: sqlite3.Cursor, artist: str, title: str) -> bool:
    """Check if a track exists in the local library (tracks table)."""
    norm_artist = _normalize(artist)
    norm_title = _normalize(title)

    # Try exact normalized match first, then fuzzy
    cursor.execute("""
        SELECT COUNT(*) FROM tracks
        WHERE status = 'active'
        AND (
            (LOWER(artist) LIKE ? AND LOWER(title) LIKE ?)
        )
    """, (f"%{norm_artist}%", f"%{norm_title}%"))

    return cursor.fetchone()[0] > 0


def generate_acquisition_queue(
    conn: sqlite3.Connection,
    min_plays: int = 5,
    min_ms_per_play: int = 30000,
    max_queue_size: int = 2000,
    recency_weight: float = 0.3,
) -> Dict:
    """
    Build a prioritized acquisition queue by combining:
    - Streaming history (play count, total listen time, recency)
    - Library data (liked songs get a boost, top tracks even more)
    - What we already own locally

    Priority formula:
        score = (play_count * 2) + (liked_bonus * 15) + (top_bonus * 10) + (recency_score * recency_weight)
    """
    logger.info("Generating acquisition queue...")
    cursor = conn.cursor()

    # Clear previous pending queue entries (keep completed/downloading)
    cursor.execute("DELETE FROM acquisition_queue WHERE status = 'pending'")

    # ── Step 1: Aggregate from streaming history ──
    logger.info("  Analyzing streaming history...")
    cursor.execute("""
        SELECT artist, track, album, spotify_track_uri,
               COUNT(*) as play_count,
               SUM(ms_played) as total_ms,
               MAX(played_at) as last_played
        FROM spotify_history
        WHERE artist != '' AND track != ''
          AND ms_played >= ?
        GROUP BY LOWER(artist), LOWER(track)
        HAVING play_count >= ?
        ORDER BY play_count DESC
    """, (min_ms_per_play, min_plays))

    history_tracks = {}
    for row in cursor.fetchall():
        key = (_normalize(row[0]), _normalize(row[1]))
        history_tracks[key] = {
            "artist": row[0],
            "title": row[1],
            "album": row[2],
            "uri": row[3],
            "play_count": row[4],
            "total_ms": row[5],
            "last_played": row[6],
        }

    logger.info(f"    {len(history_tracks):,} unique tracks with {min_plays}+ plays")

    # ── Step 2: Add library tracks (liked/playlists/top) ──
    logger.info("  Cross-referencing library data...")
    cursor.execute("SELECT spotify_uri, artist, title, album, source, playlist_name FROM spotify_library")

    library_tracks = {}
    for row in cursor.fetchall():
        key = (_normalize(row[1]), _normalize(row[2]))
        library_tracks[key] = {
            "uri": row[0],
            "artist": row[1],
            "title": row[2],
            "album": row[3],
            "source": row[4],
            "playlist_name": row[5],
        }

    logger.info(f"    {len(library_tracks):,} unique library tracks")

    # ── Step 3: Merge and score ──
    logger.info("  Scoring and merging...")
    all_keys = set(history_tracks.keys()) | set(library_tracks.keys())

    # Find the most recent play timestamp for recency normalization
    all_timestamps = [
        h["last_played"] for h in history_tracks.values() if h.get("last_played")
    ]
    latest_ts = max(all_timestamps) if all_timestamps else datetime.now(timezone.utc).isoformat()

    scored = []
    for key in all_keys:
        hist = history_tracks.get(key, {})
        lib = library_tracks.get(key, {})

        artist = hist.get("artist") or lib.get("artist", "")
        title = hist.get("title") or lib.get("title", "")
        album = hist.get("album") or lib.get("album", "")
        uri = hist.get("uri") or lib.get("uri", "")
        source = lib.get("source", "history")
        playlist_name = lib.get("playlist_name")

        play_count = hist.get("play_count", 0)
        total_ms = hist.get("total_ms", 0)

        # Priority bonuses
        liked_bonus = 1 if source == "liked" else 0
        top_bonus = 1 if source == "top_tracks" else 0
        playlist_bonus = 0.5 if source == "playlist" else 0

        # Recency score (0-10): how recently was this played?
        recency_score = 0
        if hist.get("last_played"):
            try:
                last = datetime.fromisoformat(hist["last_played"].replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_ago = (now - last).days
                recency_score = max(0, 10 - (days_ago / 36.5))  # Linear decay over ~1 year
            except (ValueError, TypeError):
                pass

        # Combined score
        score = (
            (play_count * 2)
            + (liked_bonus * 15)
            + (top_bonus * 10)
            + (playlist_bonus * 5)
            + (recency_score * recency_weight)
            + (min(total_ms / 3_600_000, 10))  # Cap at 10 for total hours listened
        )

        scored.append({
            "artist": artist,
            "title": title,
            "album": album,
            "uri": uri,
            "source": source,
            "playlist_name": playlist_name,
            "play_count": play_count,
            "score": round(score, 2),
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # ── Step 4: Filter out tracks we already own ──
    logger.info("  Checking local ownership...")

    # Check if tracks table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'")
    has_tracks_table = cursor.fetchone() is not None

    queue = []
    owned_count = 0

    for track in scored:
        if has_tracks_table and _check_local_ownership(cursor, track["artist"], track["title"]):
            owned_count += 1
            continue

        queue.append(track)
        if len(queue) >= max_queue_size:
            break

    logger.info(f"    {owned_count:,} tracks already owned locally")
    logger.info(f"    {len(queue):,} tracks queued for acquisition")

    # ── Step 5: Insert into acquisition_queue ──
    for track in queue:
        search_query = f"{track['artist']} - {track['album']}" if track['album'] else f"{track['artist']} - {track['title']}"
        cursor.execute("""
            INSERT INTO acquisition_queue (
                artist, title, album, spotify_uri,
                priority_score, play_count, source, playlist_name, search_query
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            track["artist"], track["title"], track["album"], track["uri"],
            track["score"], track["play_count"], track["source"],
            track.get("playlist_name"), search_query,
        ))

    conn.commit()

    stats = {
        "total_candidates": len(all_keys),
        "already_owned": owned_count,
        "queued": len(queue),
        "top_artists": _top_artists_from_queue(queue, 15),
    }

    logger.info(f"\nAcquisition queue ready: {len(queue):,} tracks")
    logger.info("Top artists in queue:")
    for artist, count in stats["top_artists"]:
        logger.info(f"  {artist}: {count} tracks")

    return stats


def _top_artists_from_queue(queue: List[Dict], n: int) -> List[Tuple[str, int]]:
    """Get top N artists by track count in the queue."""
    counts = Counter(t["artist"] for t in queue)
    return counts.most_common(n)


# ──────────────────────────────────────────────────────────────
# 5. Reporting
# ──────────────────────────────────────────────────────────────

def print_summary(conn: sqlite3.Connection):
    """Print a comprehensive summary of all imported data."""
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("  LYRA ORACLE — SPOTIFY IMPORT SUMMARY")
    print("=" * 60)

    # Streaming History
    cursor.execute("SELECT COUNT(*) FROM spotify_history")
    history_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT artist || '|' || track) FROM spotify_history WHERE artist != ''")
    unique_history = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(played_at), MAX(played_at) FROM spotify_history")
    date_range = cursor.fetchone()

    print(f"\n  Streaming History")
    print(f"    Total streams:    {history_count:,}")
    print(f"    Unique tracks:    {unique_history:,}")
    if date_range[0]:
        print(f"    Date range:       {date_range[0][:10]} → {date_range[1][:10]}")

    # Total listening time
    cursor.execute("SELECT COALESCE(SUM(ms_played), 0) FROM spotify_history")
    total_ms = cursor.fetchone()[0]
    total_hours = total_ms / 3_600_000
    total_days = total_hours / 24
    print(f"    Total listening:  {total_hours:,.0f} hours ({total_days:.1f} days)")

    # Library
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spotify_library'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM spotify_library")
        lib_count = cursor.fetchone()[0]

        cursor.execute("SELECT source, COUNT(*) FROM spotify_library GROUP BY source")
        source_counts = dict(cursor.fetchall())

        cursor.execute("SELECT COUNT(DISTINCT artist) FROM spotify_library")
        lib_artists = cursor.fetchone()[0]

        print(f"\n  Library")
        print(f"    Total tracks:     {lib_count:,}")
        print(f"    Unique artists:   {lib_artists:,}")
        for source, count in sorted(source_counts.items()):
            print(f"    {source:16s}  {count:,}")

    # Audio Features
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spotify_features'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM spotify_features")
        feat_count = cursor.fetchone()[0]
        print(f"\n  Audio Features")
        print(f"    Tracks with data: {feat_count:,}")

        if feat_count > 0:
            cursor.execute("""
                SELECT AVG(energy), AVG(valence), AVG(danceability), AVG(tempo)
                FROM spotify_features
            """)
            avgs = cursor.fetchone()
            print(f"    Avg energy:       {avgs[0]:.3f}")
            print(f"    Avg valence:      {avgs[1]:.3f}")
            print(f"    Avg danceability: {avgs[2]:.3f}")
            print(f"    Avg tempo:        {avgs[3]:.1f} BPM")

    # Acquisition Queue
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='acquisition_queue'")
    if cursor.fetchone():
        cursor.execute("SELECT status, COUNT(*) FROM acquisition_queue GROUP BY status")
        queue_status = dict(cursor.fetchall())
        total_queue = sum(queue_status.values())

        print(f"\n  Acquisition Queue")
        print(f"    Total:            {total_queue:,}")
        for status, count in sorted(queue_status.items()):
            print(f"    {status:16s}  {count:,}")

        # Top 10 priority tracks
        cursor.execute("""
            SELECT artist, title, priority_score, play_count
            FROM acquisition_queue
            WHERE status = 'pending'
            ORDER BY priority_score DESC
            LIMIT 10
        """)
        top_queue = cursor.fetchall()
        if top_queue:
            print(f"\n  Top Priority Acquisitions:")
            for i, (artist, title, score, plays) in enumerate(top_queue, 1):
                print(f"    {i:2d}. {artist} — {title}")
                print(f"        Score: {score:.1f} | Plays: {plays}")

    # Local ownership
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM tracks WHERE status = 'active'")
        local_count = cursor.fetchone()[0]
        print(f"\n  Local Library")
        print(f"    Active tracks:    {local_count:,}")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spotify_library'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM spotify_library")
            lib_count = cursor.fetchone()[0]
            if lib_count > 0:
                coverage = (local_count / lib_count * 100)
                print(f"    Coverage:         {coverage:.1f}% of Spotify library")

    print("\n" + "=" * 60)


# ──────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Lyra Oracle — Spotify Import Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python spotify_import.py --all                 Full import pipeline
  python spotify_import.py --history             Import streaming history only
  python spotify_import.py --library             Pull liked songs + playlists + top tracks
  python spotify_import.py --queue --min-plays 3 Build acquisition queue (lower threshold)
  python spotify_import.py --features            Fetch audio features for scoring bootstrap
  python spotify_import.py --summary             Show import summary without importing
        """,
    )

    parser.add_argument("--all", action="store_true", help="Run full import pipeline")
    parser.add_argument("--history", action="store_true", help="Import extended streaming history")
    parser.add_argument("--library", action="store_true", help="Pull liked songs, playlists, top tracks via API")
    parser.add_argument("--queue", action="store_true", help="Generate acquisition queue")
    parser.add_argument("--features", action="store_true", help="Fetch Spotify audio features")
    parser.add_argument("--summary", action="store_true", help="Show import summary")
    parser.add_argument("--min-plays", type=int, default=5, help="Min play count for queue inclusion (default: 5)")
    parser.add_argument("--max-queue", type=int, default=2000, help="Max acquisition queue size (default: 2000)")
    parser.add_argument("--db", type=str, default=None, help="Override database path")

    args = parser.parse_args()

    # Default to --all if nothing specified
    if not any([args.all, args.history, args.library, args.queue, args.features, args.summary]):
        args.all = True

    db_path = Path(args.db) if args.db else DB_PATH
    conn = init_db(db_path)

    try:
        # ── Streaming History ──
        if args.all or args.history:
            print("\n━━━ Phase 1: Streaming History Import ━━━")
            history_stats = import_streaming_history(conn)

        # ── Live Library ──
        if args.all or args.library or args.features:
            print("\n━━━ Phase 2: Spotify Library Pull ━━━")
            sp = get_spotify_client()

            if args.all or args.library:
                lib_stats = import_full_library(sp, conn)

            # ── Audio Features ──
            if args.all or args.features:
                print("\n━━━ Phase 3: Audio Features ━━━")
                fetch_audio_features(sp, conn)

        # ── Acquisition Queue ──
        if args.all or args.queue:
            print("\n━━━ Phase 4: Acquisition Queue ━━━")
            queue_stats = generate_acquisition_queue(
                conn,
                min_plays=args.min_plays,
                max_queue_size=args.max_queue,
            )

        # ── Summary ──
        print_summary(conn)

    except KeyboardInterrupt:
        logger.info("\nInterrupted — all progress has been saved.")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

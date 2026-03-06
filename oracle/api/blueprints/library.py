"""Library blueprint — scan, index, validate, browse, stream, dossier."""

from __future__ import annotations

import subprocess
import traceback
import json
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_from_directory, stream_with_context

from oracle.api.helpers import (
    _fetch_library_tracks,
    _library_filter_state,
    _load_track,
    _track_row_to_dict,
)
from oracle.config import LIBRARY_BASE
from oracle.db.schema import get_connection
from oracle.validation import (
    sanitize_integer,
    validate_boolean,
    validate_confidence,
    validate_path,
)

bp = Blueprint("library", __name__)

DIMENSIONS: tuple[str, ...] = (
    "energy",
    "valence",
    "tension",
    "density",
    "warmth",
    "movement",
    "space",
    "rawness",
    "complexity",
    "nostalgia",
)

# Optional intelligence engines used by the dossier endpoint.
try:
    from oracle.architect import architect as _architect_engine
except Exception:
    _architect_engine = None  # type: ignore[assignment]

try:
    from oracle.lore import lore as _lore_engine
except Exception:
    _lore_engine = None  # type: ignore[assignment]

try:
    from oracle.dna import dna as _dna_engine
except Exception:
    _dna_engine = None  # type: ignore[assignment]

try:
    from oracle.agent import agent as _agent_engine
except Exception:
    _agent_engine = None  # type: ignore[assignment]


def _load_track_dimensions(track_id: str) -> dict[str, float | None]:
    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia
            FROM track_scores
            WHERE track_id = ?
            """,
            (track_id,),
        )
        row = cursor.fetchone()
        if not row:
            return {dimension: None for dimension in DIMENSIONS}
        return {
            DIMENSIONS[index]: (float(value) if value is not None else None)
            for index, value in enumerate(row)
        }
    finally:
        conn.close()


def _load_cached_genius_context(track_id: str) -> dict[str, object]:
    conn = get_connection(timeout=10.0)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT payload_json
            FROM enrich_cache
            WHERE provider = ? AND lookup_key = ?
            LIMIT 1
            """,
            ("genius", f"genius:{track_id}"),
        )
        row = cursor.fetchone()
        if not row:
            return {}
        payload_raw = row[0]
        if not isinstance(payload_raw, str) or not payload_raw.strip():
            return {}
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}

        description = str(payload.get("description") or "").strip()
        excerpt = description
        if len(excerpt) > 560:
            excerpt = excerpt[:560].rstrip() + "..."

        return {
            "lyrics_state": payload.get("lyrics_state"),
            "lyrics_excerpt": excerpt or None,
            "release_date": payload.get("release_date"),
            "annotation_count": payload.get("annotation_count"),
            "pageviews": payload.get("pageviews"),
            "url": payload.get("url"),
            "song_art_image_url": payload.get("song_art_image_url"),
            "provider": "genius",
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Routes — library management
# ---------------------------------------------------------------------------

@bp.route("/api/library/scan", methods=["POST"])
def api_scan():
    """Trigger library scan."""
    try:
        from oracle.scanner import scan_library

        data = request.get_json() or {}
        library_path = data.get("library") or str(LIBRARY_BASE)
        limit = data.get("limit", 0)
        results = scan_library(library_path, limit=limit)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/library/index", methods=["POST"])
def api_index():
    """Trigger library indexing (embed + auto-score)."""
    try:
        from oracle.indexer import index_library

        data = request.get_json() or {}
        library_path = data.get("library")
        limit = data.get("limit", 0)
        force_reindex = data.get("force_reindex", False)
        results = index_library(library_path, limit=limit, force_reindex=force_reindex)
        if isinstance(results, dict) and results.get("dependency_unavailable"):
            return jsonify(results), 503
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/library/validate", methods=["POST"])
def api_library_validate():
    """Validate and enrich track metadata using cached provider lookups."""
    try:
        from oracle.acquirers.validator import validate_and_fix_library

        data = request.get_json() or {}
        limit = sanitize_integer(data.get("limit", 0), default=0, min_val=0, max_val=500000)
        workers = sanitize_integer(data.get("workers", 0), default=0, min_val=0, max_val=64)
        confidence = data.get("confidence", 0.7)

        valid, error, apply_changes = validate_boolean(data.get("apply", True), "apply")
        if not valid:
            return jsonify({"error": error}), 400
        valid, error, only_unvalidated = validate_boolean(
            data.get("only_unvalidated", True), "only_unvalidated"
        )
        if not valid:
            return jsonify({"error": error}), 400
        valid, error, force_refresh = validate_boolean(data.get("force", False), "force")
        if not valid:
            return jsonify({"error": error}), 400
        valid, error, full_rescan_if_needed = validate_boolean(
            data.get("full_rescan_if_needed", True), "full_rescan_if_needed"
        )
        if not valid:
            return jsonify({"error": error}), 400

        if force_refresh:
            only_unvalidated = False

        valid_conf, conf_error, conf_value = validate_confidence(confidence)
        if not valid_conf:
            return jsonify({"error": conf_error}), 400

        results = validate_and_fix_library(
            limit=limit,
            apply=apply_changes,
            min_confidence=conf_value,
            workers=workers,
            only_unvalidated=only_unvalidated,
            full_rescan_if_needed=full_rescan_if_needed,
        )
        return jsonify({
            "status": "ok",
            "results": results,
            "config": {
                "limit": limit,
                "apply": apply_changes,
                "confidence": conf_value,
                "workers": workers,
                "only_unvalidated": only_unvalidated,
                "force": force_refresh,
                "full_rescan_if_needed": full_rescan_if_needed,
            },
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — library browsing
# ---------------------------------------------------------------------------

@bp.route("/api/library/tracks", methods=["GET"])
def api_tracks():
    """Get tracks with optional filtering and facets."""
    try:
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        query = (request.args.get("q") or "").strip()
        artist = (request.args.get("artist") or "").strip()
        album = (request.args.get("album") or "").strip()

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        where, params = _library_filter_state(query=query, artist=artist, album=album)

        total_row = cursor.execute(f"SELECT COUNT(*) FROM tracks {where}", params).fetchone()
        artist_rows = cursor.execute(
            f"""
            SELECT artist, COUNT(*)
            FROM tracks {where}
            GROUP BY artist ORDER BY artist COLLATE NOCASE ASC LIMIT 200
            """,
            params,
        ).fetchall()
        album_rows = cursor.execute(
            f"""
            SELECT COALESCE(album, ''), COUNT(*)
            FROM tracks {where}
            GROUP BY COALESCE(album, '')
            ORDER BY COALESCE(album, '') COLLATE NOCASE ASC LIMIT 200
            """,
            params,
        ).fetchall()
        conn.close()

        tracks = _fetch_library_tracks(query=query, artist=artist, album=album, limit=limit, offset=offset)
        return jsonify({
            "tracks": tracks,
            "count": len(tracks),
            "total": int(total_row[0] or 0),
            "offset": offset,
            "limit": limit,
            "query": query,
            "artist": artist or None,
            "album": album or None,
            "artists": [{"name": r[0] or "Unknown Artist", "count": int(r[1] or 0)} for r in artist_rows],
            "albums": [{"name": r[0] or "Singles / Unknown Album", "count": int(r[1] or 0)} for r in album_rows],
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/library/artists", methods=["GET"])
def api_library_artists():
    """Artist navigation rows for the library browser."""
    try:
        limit = request.args.get("limit", 200, type=int)
        query = (request.args.get("q") or "").strip()
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        where, params = _library_filter_state(query=query)
        rows = cursor.execute(
            f"""
            SELECT artist, COUNT(*) FROM tracks {where}
            GROUP BY artist ORDER BY artist COLLATE NOCASE ASC LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        conn.close()
        return jsonify({
            "artists": [{"name": r[0] or "Unknown Artist", "count": int(r[1] or 0)} for r in rows],
            "count": len(rows),
            "query": query,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/library/albums", methods=["GET"])
def api_library_albums():
    """Album navigation rows for the library browser."""
    try:
        limit = request.args.get("limit", 200, type=int)
        query = (request.args.get("q") or "").strip()
        artist = (request.args.get("artist") or "").strip()
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        where, params = _library_filter_state(query=query, artist=artist)
        rows = cursor.execute(
            f"""
            SELECT COALESCE(album, ''), COUNT(*) FROM tracks {where}
            GROUP BY COALESCE(album, '')
            ORDER BY COALESCE(album, '') COLLATE NOCASE ASC LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        conn.close()
        return jsonify({
            "albums": [{"name": r[0] or "Singles / Unknown Album", "count": int(r[1] or 0)} for r in rows],
            "count": len(rows),
            "query": query,
            "artist": artist or None,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/library/artists/<path:artist_name>", methods=["GET"])
def api_library_artist_detail(artist_name: str):
    """Single artist detail view for the library browser."""
    try:
        artist = artist_name.strip()
        if not artist:
            return jsonify({"error": "artist is required"}), 400
        tracks = _fetch_library_tracks(artist=artist, limit=500, offset=0)
        if not tracks:
            return jsonify({"error": "Artist not found"}), 404
        albums_map: dict = {}
        years = sorted({
            str(t.get("year") or "").strip()
            for t in tracks if str(t.get("year") or "").strip()
        })
        for t in tracks:
            album_name = t.get("album") or "Singles / Unknown Album"
            albums_map[album_name] = albums_map.get(album_name, 0) + 1
        return jsonify({
            "artist": artist,
            "track_count": len(tracks),
            "album_count": len(albums_map),
            "years": years,
            "albums": [
                {"name": name, "count": count}
                for name, count in sorted(albums_map.items(), key=lambda item: item[0].lower())
            ],
            "tracks": tracks[:120],
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/library/albums/<path:album_name>", methods=["GET"])
def api_library_album_detail(album_name: str):
    """Single album detail view for the library browser."""
    try:
        album = album_name.strip()
        artist = (request.args.get("artist") or "").strip()
        if not album:
            return jsonify({"error": "album is required"}), 400
        tracks = _fetch_library_tracks(artist=artist, album=album, limit=500, offset=0)
        if not tracks:
            return jsonify({"error": "Album not found"}), 404
        years = sorted({
            str(t.get("year") or "").strip()
            for t in tracks if str(t.get("year") or "").strip()
        })
        return jsonify({
            "artist": artist or tracks[0].get("artist") or "Unknown Artist",
            "album": album,
            "track_count": len(tracks),
            "years": years,
            "tracks": tracks[:120],
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Routes — streaming and dossier
# ---------------------------------------------------------------------------

# Formats browsers can play natively without transcoding.
_BROWSER_NATIVE = {".mp3", ".m4a", ".aac", ".ogg", ".opus"}

# ffmpeg default bitrate for AAC transcoding.
_TRANSCODE_BITRATE = "256k"


def _stream_transcoded(filepath: Path, bitrate: str = _TRANSCODE_BITRATE) -> Response:
    """Transcode filepath to frag-mp4/AAC via ffmpeg and stream the output.

    Uses ``frag_keyframe+empty_moov+skip_sidx`` so the browser can start
    playing before the file is fully written (no seekable container needed).
    Responds 503 if ffmpeg is not on PATH.
    """
    import shutil

    if not shutil.which("ffmpeg"):
        return jsonify({"error": "ffmpeg not found — cannot transcode FLAC"}), 503

    cmd = [
        "ffmpeg", "-y",
        "-i", str(filepath),
        "-c:a", "aac",
        "-b:a", bitrate,
        "-map_metadata", "0",
        "-movflags", "frag_keyframe+empty_moov+skip_sidx",
        "-f", "mp4",
        "pipe:1",
    ]

    def _generate():
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    return Response(
        stream_with_context(_generate()),
        mimetype="audio/mp4",
        headers={
            "Content-Disposition": f'inline; filename="{filepath.stem}.m4a"',
            "X-Transcoded-From": "flac",
            "Cache-Control": "no-cache",
            "Accept-Ranges": "none",
        },
    )


@bp.route("/api/stream/<track_id>", methods=["GET"])
def api_stream_track(track_id: str):
    """Stream audio file for browser playback.

    FLAC/WAV/WMA files are transcoded on-the-fly to fragmented mp4/AAC (256 kbps)
    so browsers can play them without plugins.  Pass ``?raw=1`` to skip
    transcoding and receive the original file (useful for foobar2000 or VLC).
    """
    try:
        conn = get_connection(timeout=5.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT filepath FROM tracks WHERE track_id = ? AND status = 'active'",
            (track_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "Track not found"}), 404
        filepath = Path(row[0])
        if not filepath.exists():
            return jsonify({"error": "File not found on disk"}), 404

        ext = filepath.suffix.lower()
        raw = request.args.get("raw", "").lower() in {"1", "true"}

        # Transcode non-browser-native files (FLAC, WAV, WMA, etc.) unless ?raw=1.
        if not raw and ext not in _BROWSER_NATIVE:
            return _stream_transcoded(filepath)

        MIME_MAP = {
            ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
            ".flac": "audio/flac", ".ogg": "audio/ogg", ".opus": "audio/opus",
            ".wav": "audio/wav", ".wma": "audio/x-ms-wma",
        }
        mime = MIME_MAP.get(ext, "audio/mpeg")
        return send_from_directory(
            str(filepath.parent),
            filepath.name,
            conditional=True,
            mimetype=mime,
        )
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/tracks/<track_id>/dossier", methods=["GET"])
def api_track_dossier(track_id: str):
    """Unified dossier: track metadata + structure + lineage + samples + fact."""
    try:
        track = _load_track(track_id)
        if not track:
            return jsonify({"error": "Track not found"}), 404

        structure = None
        if _architect_engine:
            try:
                structure = _architect_engine.get_structure(track_id)
            except Exception:
                pass

        connections = []
        if _lore_engine and track.get("artist"):
            try:
                connections = _lore_engine.get_artist_connections(track["artist"])
            except Exception:
                pass

        samples = []
        if _dna_engine:
            try:
                samples = _dna_engine.trace_samples(track_id)
            except Exception:
                pass

        fact = None
        if _agent_engine:
            try:
                fact = _agent_engine.fact_drop(track_id)
            except Exception:
                pass

        dimensions = _load_track_dimensions(track_id)
        lyrics = _load_cached_genius_context(track_id)

        return jsonify(
            {
                "track": track,
                "structure": structure,
                "lineage": connections,
                "samples": samples,
                "fact": fact,
                "dimensions": dimensions,
                "lyrics": lyrics,
                "provenance_notes": [
                    track.get("filepath") or "Track path unavailable",
                    "Bundled dossier view assembled from Lyra back-end services.",
                ],
                "acquisition_notes": [
                    "Playback and queue state are managed in the desktop client.",
                ],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

"""Enrichment blueprint — biographer, shrine, credits, constellation, graph."""

from __future__ import annotations

import json
import logging
import threading
import traceback

from flask import Blueprint, jsonify, request

from oracle.db.schema import get_connection
from oracle.validation import sanitize_integer

logger = logging.getLogger(__name__)

bp = Blueprint("enrich", __name__)


# ---------------------------------------------------------------------------
# Routes — Biographer
# ---------------------------------------------------------------------------

@bp.route("/api/enrich/biographer", methods=["POST"])
def api_enrich_biographer():
    """Enrich a single artist with biographical context."""
    data = request.get_json(silent=True) or {}
    artist_name = str(data.get("artist_name") or "").strip()
    if not artist_name:
        return jsonify({"error": "artist_name is required"}), 400
    mbid = str(data.get("mbid") or "").strip() or None
    force = bool(data.get("force", False))
    try:
        from oracle.enrichers.biographer import Biographer
        result = Biographer().enrich_artist(artist_name, mbid=mbid, force=force)
        if not result:
            return jsonify({"error": "no data found", "artist_name": artist_name}), 404
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/enrichment/biographer/<path:artist>", methods=["GET"])
def api_get_biographer_cached(artist: str):
    """Return cached biography for an artist, or trigger a fresh fetch."""
    artist_name = artist.strip()
    force = request.args.get("force", "0").strip() in {"1", "true", "yes"}
    try:
        from oracle.enrichers.biographer import Biographer
        result = Biographer().enrich_artist(artist_name, force=force)
        if not result:
            return jsonify({"error": "not found", "artist_name": artist_name}), 404
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/enrich/biographer/batch", methods=["POST"])
def api_enrich_biographer_batch():
    """Enrich all library artists with biographical context."""
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", 0))
    force = bool(data.get("force", False))
    try:
        from oracle.enrichers.biographer import Biographer
        stats = Biographer().enrich_all_library_artists(limit=limit, force=force)
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/enrich/biographer/stale", methods=["POST"])
def api_enrich_biographer_stale():
    """Re-enrich only artists whose cache entry is missing or past TTL."""
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", 0))
    ttl_days = data.get("ttl_days")
    ttl_seconds = int(float(ttl_days) * 86400) if ttl_days is not None else None
    try:
        from oracle.enrichers.biographer import Biographer
        stats = Biographer().enrich_stale_artists(limit=limit, ttl_seconds=ttl_seconds)
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Routes — Artist Shrine
# ---------------------------------------------------------------------------

@bp.route("/api/artist/shrine/<path:artist>", methods=["GET"])
def api_artist_shrine(artist: str):
    """Get comprehensive artist profile for Artist Shrine view."""
    artist_name = artist.strip()
    if not artist_name:
        return jsonify({"error": "artist required"}), 400
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*), COUNT(DISTINCT album) FROM tracks WHERE artist = ? AND status = 'active'",
            (artist_name,),
        )
        row = c.fetchone()
        track_count, album_count = (row[0] or 0, row[1] or 0) if row else (0, 0)
        c.execute(
            "SELECT DISTINCT album, year FROM tracks WHERE artist = ? AND status = 'active' ORDER BY year",
            (artist_name,),
        )
        albums = [{"album": r[0], "year": r[1]} for r in c.fetchall() if r[0]]
        c.execute(
            "SELECT target, type, weight FROM connections WHERE source = ? ORDER BY weight DESC LIMIT 20",
            (artist_name,),
        )
        connections = [{"target": r[0], "type": r[1], "weight": r[2]} for r in c.fetchall()]
        c.execute(
            "SELECT role, artist_name, COUNT(*) AS cnt FROM track_credits tc "
            "JOIN tracks t ON tc.track_id = t.track_id "
            "WHERE t.artist = ? GROUP BY role, tc.artist_name ORDER BY cnt DESC LIMIT 20",
            (artist_name,),
        )
        credits_rows = [{"role": r[0], "name": r[1], "count": r[2]} for r in c.fetchall()]
        conn.close()

        bio_data: dict = {}
        try:
            from oracle.enrichers.biographer import Biographer
            bio_data = Biographer().enrich_artist(artist_name) or {}
        except Exception:
            pass

        return jsonify({
            "artist": artist_name,
            "library_stats": {"track_count": track_count, "album_count": album_count, "albums": albums},
            "bio": bio_data.get("bio") or "",
            "bio_source": bio_data.get("bio_source") or "none",
            "images": bio_data.get("images") or {},
            "wiki_thumbnail": bio_data.get("wiki_thumbnail") or "",
            "formation_year": bio_data.get("formation_year"),
            "origin": bio_data.get("origin") or "",
            "members": bio_data.get("members") or [],
            "scene": bio_data.get("scene") or "",
            "genres": bio_data.get("genres") or [],
            "era": bio_data.get("era") or "",
            "artist_mbid": bio_data.get("artist_mbid") or "",
            "lastfm_listeners": bio_data.get("lastfm_listeners"),
            "lastfm_url": bio_data.get("lastfm_url") or "",
            "wiki_url": bio_data.get("wiki_url") or "",
            "social_links": bio_data.get("social_links") or {},
            "related_artists": connections,
            "credits": credits_rows,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Routes — Credits
# ---------------------------------------------------------------------------

@bp.route("/api/credits/<path:track_id>", methods=["GET"])
def api_credits_for_track(track_id: str):
    """Return all credits stored for a track."""
    try:
        from oracle.enrichers.credit_mapper import CreditMapper
        credits = CreditMapper().get_credits_for_track(track_id)
        return jsonify({"track_id": track_id, "credits": credits, "count": len(credits)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/credits/map", methods=["POST"])
def api_credits_map():
    """Map and persist credits for a single track."""
    body = request.get_json(force=True, silent=True) or {}
    track_id = (body.get("track_id") or "").strip()
    recording_mbid = (body.get("recording_mbid") or "").strip() or None
    artist = (body.get("artist") or "").strip() or None
    title = (body.get("title") or "").strip() or None
    album = (body.get("album") or "").strip() or None
    if not track_id:
        return jsonify({"error": "track_id required"}), 400
    if not recording_mbid and not (artist and title):
        return jsonify({"error": "recording_mbid or artist+title required"}), 400
    try:
        from oracle.enrichers.credit_mapper import map_credits_for_track
        credits = map_credits_for_track(
            track_id, recording_mbid=recording_mbid, artist=artist, title=title, album=album,
        )
        return jsonify({"track_id": track_id, "credits": credits, "count": len(credits)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/credits/map-batch", methods=["POST"])
def api_credits_map_batch():
    """Batch-map credits for all tracks with a musicbrainz_id. Runs in background."""
    body = request.get_json(force=True, silent=True) or {}
    limit = int(body.get("limit") or 200)
    only_missing = bool(body.get("only_missing", True))

    def _run() -> None:
        try:
            from oracle.enrichers.credit_mapper import CreditMapper
            result = CreditMapper().map_batch(limit=limit, only_missing=only_missing)
            logger.info("credits map-batch complete: %s", result)
        except Exception as exc:
            logger.error("credits map-batch error: %s", exc)

    threading.Thread(target=_run, daemon=True, name="credits-map-batch").start()
    return jsonify({"status": "started", "limit": limit, "only_missing": only_missing}), 202


@bp.route("/api/credits/summary", methods=["GET"])
def api_credits_summary():
    """Library-wide credit statistics."""
    try:
        from oracle.enrichers.credit_mapper import CreditMapper
        return jsonify(CreditMapper().get_credits_summary())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Routes — Constellation
# ---------------------------------------------------------------------------

@bp.route("/api/constellation", methods=["GET"])
def api_constellation():
    """Get artist connection graph for Constellation visualization."""
    genre_filter = (request.args.get("genre") or "").strip().lower()
    era_filter = (request.args.get("era") or "").strip().lower()
    type_filter = (request.args.get("type") or "").strip().lower()
    limit = sanitize_integer(request.args.get("limit", 200), default=200, min_val=1, max_val=2000)
    try:
        conn = get_connection()
        c = conn.cursor()

        params: list = []
        where_clauses: list = []
        if type_filter:
            where_clauses.append("lower(type) LIKE ?")
            params.append(f"%{type_filter}%")
        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        c.execute(
            f"SELECT source, target, type, weight FROM connections {where_sql} "
            f"ORDER BY weight DESC LIMIT ?",
            params + [limit * 2],
        )
        raw_edges = c.fetchall()

        if not raw_edges:
            conn.close()
            return jsonify({"nodes": [], "edges": [], "total_edges": 0})

        node_set: set = set()
        for src, tgt, *_ in raw_edges:
            node_set.add(src)
            node_set.add(tgt)

        c.execute("SELECT DISTINCT artist FROM tracks WHERE status = 'active'")
        in_library = {row[0] for row in c.fetchall()}

        from oracle.enrichers.cache import make_lookup_key
        node_list = sorted(node_set)[:limit]
        key_to_artist = {make_lookup_key("biographer", a.strip()): a for a in node_list}
        bio_by_artist: dict = {}
        if key_to_artist:
            placeholders = ",".join("?" * len(key_to_artist))
            c.execute(
                f"SELECT lookup_key, payload_json FROM enrich_cache "
                f"WHERE provider = 'biographer' AND lookup_key IN ({placeholders})",
                list(key_to_artist.keys()),
            )
            for lk, pj in c.fetchall():
                a_name = key_to_artist.get(lk)
                if a_name and pj:
                    try:
                        bio_by_artist[a_name] = json.loads(pj)
                    except Exception:
                        pass

        nodes = []
        for a_name in node_list:
            bio = bio_by_artist.get(a_name, {})
            if genre_filter and not any(genre_filter in g.lower() for g in (bio.get("genres") or [])):
                continue
            if era_filter and era_filter not in (bio.get("era") or "").lower():
                continue
            node: dict = {"id": a_name, "label": a_name, "inLibrary": a_name in in_library}
            if bio.get("genres"):
                node["genres"] = bio["genres"][:3]
            if bio.get("era"):
                node["era"] = bio["era"]
            if bio.get("origin"):
                node["origin"] = bio["origin"]
            if bio.get("lastfm_listeners"):
                node["listeners"] = bio["lastfm_listeners"]
            nodes.append(node)

        edges = [
            {"source": r[0], "target": r[1], "type": r[2] or "related", "weight": r[3] or 0.5}
            for r in raw_edges
        ]
        conn.close()
        return jsonify({"nodes": nodes, "edges": edges, "total_edges": len(edges), "total_nodes": len(nodes)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/constellation/filters", methods=["GET"])
def api_constellation_filters():
    """Return available filter options for Constellation view."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT DISTINCT type FROM connections WHERE type IS NOT NULL ORDER BY type")
        connection_types = [r[0] for r in c.fetchall()]
        conn.close()
        return jsonify({
            "connection_types": connection_types or [
                "member-of", "collaborated-with", "influenced", "samples", "toured-with"
            ],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Routes — Graph
# ---------------------------------------------------------------------------

@bp.route("/api/graph/build", methods=["POST"])
def api_graph_build():
    """Trigger relationship graph build (incremental or full)."""
    data = request.get_json(silent=True) or {}
    full = bool(data.get("full", False))
    depth = int(data.get("depth", 1))
    try:
        from oracle.graph_builder import GraphBuilder
        gb = GraphBuilder()
        if full:
            count = gb.build_full_graph(depth=depth)
            mode = "full"
        else:
            count = gb.build_incremental(depth=depth)
            mode = "incremental"
        stats = gb.get_stats()
        return jsonify({"ok": True, "mode": mode, "new_edges": count, "stats": stats})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route("/api/graph/stats", methods=["GET"])
def api_graph_stats():
    """Return graph builder statistics."""
    try:
        from oracle.graph_builder import GraphBuilder
        return jsonify(GraphBuilder().get_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

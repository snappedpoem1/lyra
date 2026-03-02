"""Lyra Oracle Flask API server."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import time
from typing import Dict, List
import json
import traceback
import sqlite3

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent


def _running_as_script() -> bool:
    try:
        return Path(sys.argv[0]).resolve() == Path(__file__).resolve()
    except Exception:
        return False


def _maybe_reexec_in_project_venv() -> None:
    if not _running_as_script():
        return
    if os.getenv("LYRA_SKIP_VENV_REEXEC", "").strip().lower() in {"1", "true", "yes"}:
        return
    if os.getenv("LYRA_VENV_REEXEC", "").strip() == "1":
        return

    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    ]
    venv_python = next((candidate for candidate in candidates if candidate.exists()), None)
    if not venv_python:
        return

    try:
        current_python = Path(sys.executable).resolve()
    except Exception:
        current_python = Path(sys.executable)

    try:
        if current_python.samefile(venv_python):
            return
    except Exception:
        if str(current_python).lower() == str(venv_python).lower():
            return

    env = os.environ.copy()
    env["LYRA_VENV_REEXEC"] = "1"
    print(f"[runtime] switching to project virtualenv: {venv_python}", flush=True)
    completed = subprocess.run(
        [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        env=env,
        cwd=str(PROJECT_ROOT),
    )
    raise SystemExit(completed.returncode)


_maybe_reexec_in_project_venv()
load_dotenv(override=False)
hf_home = str(PROJECT_ROOT / "hf_cache")
os.environ.setdefault("HF_HOME", hf_home)
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(hf_home) / "hub"))

from flask import Flask, request, jsonify, send_from_directory, Response, g
from flask_cors import CORS

from oracle.db.schema import get_connection, get_write_mode
from oracle.config import LIBRARY_BASE
from oracle.doctor import run_doctor
from oracle.search import search
from oracle.scanner import scan_library
from oracle.indexer import index_library
from oracle.vibes import generate_vibe, save_vibe, list_vibes, build_vibe, materialize_vibe, refresh_vibes, delete_vibe
from oracle.types import PlaylistRun
from oracle.curator import generate_plan, apply_plan
from oracle.classifier import classify_library
from oracle.acquirers.ytdlp import YTDLPAcquirer
from oracle.acquisition import process_queue
from oracle.download_processor import list_downloads
from oracle.acquirers.guarded_import import process_downloads
from oracle.validation import (
    validate_search_request,
    validate_vibe_save_request,
    validate_vibe_materialize_request,
    validate_name,
    validate_url,
    validate_path,
    validate_boolean,
    validate_confidence,
    sanitize_integer,
)
# Intelligence layer â€” wrapped in try/except so server starts even if subsystems fail
_import_warnings = []

try:
    from oracle.scout import scout as scout_engine
except Exception as _e:
    scout_engine = None
    _import_warnings.append(f"scout: {_e}")

try:
    from oracle.lore import lore as lore_engine
except Exception as _e:
    lore_engine = None
    _import_warnings.append(f"lore: {_e}")

try:
    from oracle.dna import dna as dna_engine
except Exception as _e:
    dna_engine = None
    _import_warnings.append(f"dna: {_e}")

try:
    from oracle.hunter import hunter as hunter_engine
except Exception as _e:
    hunter_engine = None
    _import_warnings.append(f"hunter: {_e}")

try:
    from oracle.architect import architect as architect_engine
except Exception as _e:
    architect_engine = None
    _import_warnings.append(f"architect: {_e}")

try:
    from oracle.radio import radio as radio_engine
except Exception as _e:
    radio_engine = None
    _import_warnings.append(f"radio: {_e}")

try:
    from oracle.agent import agent as agent_engine
except Exception as _e:
    agent_engine = None
    _import_warnings.append(f"agent: {_e}")

try:
    from oracle.llm import get_llm_status, LLMClient
except Exception as _e:
    LLMClient = None
    get_llm_status = lambda: {"status": "unavailable", "error": str(_e)}
    _import_warnings.append(f"llm: {_e}")

try:
    from oracle.safety import get_journal, get_controller, undo_last
except Exception as _e:
    get_journal = get_controller = undo_last = None
    _import_warnings.append(f"safety: {_e}")

try:
    from oracle.pipeline import get_pipeline
except Exception as _e:
    get_pipeline = None
    _import_warnings.append(f"pipeline: {_e}")

if _import_warnings:
    import logging as _logging
    _logger = _logging.getLogger("lyra_api")
    for w in _import_warnings:
        _logger.warning(f"Optional subsystem unavailable: {w}")
app = Flask(__name__)
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,null",
    ).split(",")
    if origin.strip()
]
CORS(app, resources={r"/api/*": {"origins": CORS_ALLOWED_ORIGINS or "*"}})

VERSION = "1.0.0"
API_TOKEN = os.getenv("LYRA_API_TOKEN", "").strip()


def _json_safe(value):
    """Convert non-JSON-native objects (e.g. Path) into JSON-safe primitives."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


def _playlist_run_to_dict(run: PlaylistRun) -> dict:
    """Convert PlaylistRun Pydantic model to a Flask-json-safe dict."""
    if hasattr(run, "model_dump"):
        payload = run.model_dump()
    else:
        payload = run.dict()
    return _json_safe(payload)


def _fallback_vibe_narrative(tracks: List[Dict[str, str]], arc_type: str) -> str:
    """Deterministic fallback narrative when LLM is unavailable."""
    if not tracks:
        return f"{arc_type.title()} arc with no tracks available."
    first = tracks[0]
    last = tracks[-1]
    return (
        f"{arc_type.title()} arc across {len(tracks)} tracks, beginning with "
        f"{first.get('artist', '?')} - {first.get('title', '?')} and resolving at "
        f"{last.get('artist', '?')} - {last.get('title', '?')}."
    )


def _feature_flags() -> dict:
    return {
        "agent": bool(agent_engine),
        "radio": bool(radio_engine),
        "dna": bool(dna_engine),
        "lore": bool(lore_engine),
        "architect": bool(architect_engine),
        "pipeline": bool(get_pipeline),
        "auth_required": bool(API_TOKEN),
    }


def _db_health() -> dict:
    try:
        conn = get_connection(timeout=5.0)
        cursor = conn.cursor()
        track_count = cursor.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        vibe_count = cursor.execute("SELECT COUNT(*) FROM vibe_profiles").fetchone()[0]
        conn.close()
        return {"ok": True, "track_count": int(track_count or 0), "vibe_count": int(vibe_count or 0)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _library_health() -> dict:
    try:
        base = Path(LIBRARY_BASE)
        return {
            "ok": base.exists(),
            "path": str(base),
            "exists": base.exists(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.before_request
def require_api_token():
    if not request.path.startswith("/api/"):
        return None
    if request.path == "/api/health":
        return None
    g.authenticated = not API_TOKEN
    if not API_TOKEN:
        return None
    auth_header = request.headers.get("Authorization", "").strip()
    expected = f"Bearer {API_TOKEN}"
    if auth_header != expected:
        return jsonify({"error": "Unauthorized", "status": 401}), 401
    g.authenticated = True
    return None


def _track_row_to_dict(row) -> dict:
    return {
        "track_id": row[0],
        "artist": row[1],
        "title": row[2],
        "album": row[3],
        "year": row[4],
        "version_type": row[5],
        "confidence": row[6],
        "duration": row[7],
        "filepath": row[8],
    }


def _load_track(track_id: str) -> dict | None:
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT track_id, artist, title, album, year, version_type, confidence, duration, filepath
        FROM tracks
        WHERE track_id = ?
        """,
        (track_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return _track_row_to_dict(row) if row else None


def _load_vibe_detail(name: str) -> dict | None:
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name, query_json, created_at, track_count
        FROM vibe_profiles
        WHERE name = ?
        """,
        (name,),
    )
    vibe_row = cursor.fetchone()
    if not vibe_row:
        conn.close()
        return None

    cursor.execute(
        """
        SELECT t.track_id, t.artist, t.title, t.album, t.year, t.version_type, t.confidence, t.duration, t.filepath
        FROM vibe_tracks vt
        JOIN tracks t ON vt.track_id = t.track_id
        WHERE vt.vibe_name = ?
        ORDER BY vt.position
        """,
        (name,),
    )
    track_rows = cursor.fetchall()
    cursor.execute(
        """
        SELECT name, query_json, created_at, track_count
        FROM vibe_profiles
        WHERE name != ?
        ORDER BY created_at DESC
        LIMIT 4
        """,
        (name,),
    )
    related_rows = cursor.fetchall()
    conn.close()

    query_data = json.loads(vibe_row[1]) if vibe_row[1] else {}
    tracks = [_track_row_to_dict(row) for row in track_rows]
    story_beats = [
        f"Lead thread seeded from: {query_data.get('query', 'saved vibe')}",
        f"Sequence runs {len(tracks)} tracks in saved order.",
        "Use Oracle mode to pivot without losing the thread.",
    ]
    arc = []
    for idx, _track in enumerate(tracks[:8], start=1):
        scale = max(1, len(tracks[:8]))
        energy = round(min(0.95, 0.3 + (idx / scale) * 0.45), 2)
        arc.append({"step": idx, "energy": energy, "valence": 0.52, "tension": round(0.38 + idx * 0.04, 2)})

    def _related(row) -> dict:
        qd = json.loads(row[1]) if row[1] else {}
        return {
            "id": row[0],
            "kind": "vibe",
            "title": row[0],
            "subtitle": qd.get("query", "Saved vibe"),
            "narrative": f"Saved listening thread for {qd.get('query', 'your library')}.",
            "trackCount": int(row[3] or 0),
            "freshnessLabel": "Saved vibe",
            "coverMosaic": [row[0][:1].upper() or "L"],
            "emotionalSignature": [],
            "lastTouchedLabel": "Saved",
        }

    return {
        "id": vibe_row[0],
        "kind": "vibe",
        "title": vibe_row[0],
        "subtitle": query_data.get("query", "Saved vibe"),
        "narrative": _fallback_vibe_narrative(tracks, "saved thread"),
        "trackCount": int(vibe_row[3] or len(tracks)),
        "freshnessLabel": "Saved vibe",
        "coverMosaic": [vibe_row[0][:1].upper() or "L"],
        "emotionalSignature": [],
        "lastTouchedLabel": "Saved",
        "query": query_data.get("query", ""),
        "tracks": tracks,
        "storyBeats": story_beats,
        "arc": arc,
        "relatedPlaylists": [_related(row) for row in related_rows],
        "oraclePivots": [],
        "createdAt": vibe_row[2],
    }


def _library_filter_state(query: str = "", artist: str = "", album: str = "") -> tuple[str, list]:
    clauses = []
    params: list = []
    if query:
        like = f"%{query}%"
        clauses.append("(artist LIKE ? OR title LIKE ? OR album LIKE ?)")
        params.extend([like, like, like])
    if artist:
        clauses.append("artist = ?")
        params.append(artist)
    if album:
        clauses.append("COALESCE(album, '') = ?")
        params.append("" if album == "Singles / Unknown Album" else album)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _fetch_library_tracks(query: str = "", artist: str = "", album: str = "", limit: int = 200, offset: int = 0) -> list[dict]:
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    where, params = _library_filter_state(query=query, artist=artist, album=album)
    cursor.execute(
        f"""
        SELECT track_id, artist, title, album, year, version_type, confidence, duration, filepath
        FROM tracks
        {where}
        ORDER BY artist COLLATE NOCASE ASC, album COLLATE NOCASE ASC, title COLLATE NOCASE ASC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            'track_id': row[0],
            'artist': row[1],
            'title': row[2],
            'album': row[3],
            'year': row[4],
            'version_type': row[5],
            'confidence': row[6],
            'duration': row[7],
            'filepath': row[8],
            'file_exists': bool(row[8] and Path(row[8]).exists()),
        }
        for row in rows
    ]


# ============================================================================
# HEALTH & STATUS
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify(_build_health_payload())


@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check alias for API clients."""
    return jsonify(_build_health_payload())


def _build_health_payload() -> dict:
    db = _db_health()
    library = _library_health()
    return {
        'status': 'ok',
        'ok': True,
        'service': 'lyra-oracle',
        'version': VERSION,
        'timestamp': time.time(),
        'profile': os.getenv("LYRA_PROFILE", "balanced"),
        'write_mode': get_write_mode(),
        'db': db,
        'library': library,
        'feature_flags': _feature_flags(),
        'auth': {'enabled': bool(API_TOKEN)},
        'cors': {'allowed_origins': CORS_ALLOWED_ORIGINS},
        'llm': get_llm_status()
    }


@app.route('/api/doctor', methods=['GET'])
def api_doctor():
    """Run doctor diagnostics and return structured results."""
    try:
        checks = run_doctor()
        return jsonify([
            {
                'name': check.name,
                'status': check.status,
                'details': check.details,
            }
            for check in checks
        ])
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/status', methods=['GET'])
def status():
    """Get library statistics."""
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    
    track_count = cursor.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    embedding_count = cursor.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    vibe_count = cursor.execute("SELECT COUNT(*) FROM vibe_profiles").fetchone()[0]
    queue_pending = cursor.execute("SELECT COUNT(*) FROM acquisition_queue WHERE status = 'pending'").fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'tracks': track_count,
        'embeddings': embedding_count,
        'vibes': vibe_count,
        'queue_pending': queue_pending,
        'write_mode': get_write_mode(),
        'llm': get_llm_status(),
    })


@app.route('/api/cache/stats', methods=['GET'])
def api_cache_stats():
    """Report provider-cache coverage and freshness from enrich_cache."""
    try:
        stale_seconds = sanitize_integer(request.args.get('stale_seconds', 1209600), default=1209600, min_val=60, max_val=31536000)
        provider = (request.args.get('provider') or '').strip()
        now = time.time()

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        where = ""
        params = []
        if provider:
            where = "WHERE provider = ?"
            params.append(provider)

        cursor.execute(
            f"""
            SELECT provider,
                   COUNT(*) AS total,
                   SUM(CASE WHEN fetched_at IS NULL THEN 1 ELSE 0 END) AS missing_ts,
                   MIN(fetched_at) AS min_fetched_at,
                   MAX(fetched_at) AS max_fetched_at
            FROM enrich_cache
            {where}
            GROUP BY provider
            ORDER BY total DESC
            """,
            params,
        )
        rows = cursor.fetchall()

        results = []
        for row in rows:
            p, total, missing_ts, min_ts, max_ts = row
            stale_count = 0
            if stale_seconds > 0:
                cursor.execute(
                    "SELECT COUNT(*) FROM enrich_cache WHERE provider = ? AND fetched_at IS NOT NULL AND fetched_at < ?",
                    (p, now - stale_seconds),
                )
                stale_count = int(cursor.fetchone()[0] or 0)

            results.append({
                'provider': p,
                'total': int(total or 0),
                'missing_timestamp': int(missing_ts or 0),
                'stale': stale_count,
                'min_fetched_at': min_ts,
                'max_fetched_at': max_ts,
            })

        conn.close()
        return jsonify({
            'providers': results,
            'count': len(results),
            'stale_seconds': stale_seconds,
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


def _rewrite_search_query_with_llm(query: str, n: int) -> dict:
    """Rewrite free-form query into CLAP-optimized text via local LLM."""
    fallback = {
        "query": query,
        "n": n,
        "used_llm": False,
        "llm": {"status": "unavailable"},
        "intent": "unknown",
        "rationale": "LLM rewrite unavailable; using raw query.",
    }

    if not LLMClient:
        return fallback

    try:
        client = LLMClient.from_env()
        status = client.check_available()
        llm_payload = status.as_dict()
        llm_payload["status"] = "ok" if status.ok else "unavailable"
        fallback["llm"] = llm_payload
        if not status.ok:
            return fallback

        result = client.chat(
            [{"role": "user", "content": query}],
            temperature=0.2,
            max_tokens=180,
            json_schema={
                "name": "search_rewrite",
                "schema": {
                    "type": "object",
                    "properties": {
                        "clap_query": {"type": "string"},
                        "n": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "intent": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["clap_query", "n", "intent", "rationale"],
                    "additionalProperties": False,
                },
            },
            system=(
                "You rewrite music search requests into compact CLAP-friendly audio descriptions. "
                "Focus on sonic traits (texture, tempo, instrumentation, energy, mood). "
                "Keep clap_query concise and retrieval-effective."
            ),
        )
        if not result.get("ok") or "data" not in result:
            fallback["rationale"] = f"LLM rewrite failed: {result.get('error', 'unknown')}"
            return fallback

        payload = result["data"]
        rewritten = (payload.get("clap_query") or "").strip() or query
        rewritten_n = sanitize_integer(payload.get("n", n), default=n, min_val=1, max_val=1000)
        return {
            "query": rewritten,
            "n": rewritten_n,
            "used_llm": rewritten != query or rewritten_n != n,
            "llm": llm_payload,
            "intent": (payload.get("intent") or "unknown").strip() or "unknown",
            "rationale": (payload.get("rationale") or "").strip(),
        }
    except Exception as exc:
        fallback["rationale"] = f"LLM rewrite exception: {exc}"
        return fallback


def _generate_vibe_from_prompt(prompt: str, n: int) -> dict:
    """Generate vibe metadata and CLAP query from a natural-language prompt."""
    prompt = prompt.strip()
    fallback_name = " ".join(prompt.split()[:4]).strip() or "Generated Vibe"
    fallback_name = fallback_name[:80]
    fallback = {
        "name": fallback_name,
        "query": prompt,
        "n": n,
        "narrative": "",
        "used_llm": False,
        "llm": {"status": "unavailable"},
    }

    if not LLMClient:
        return fallback

    try:
        client = LLMClient.from_env()
        status = client.check_available()
        llm_payload = status.as_dict()
        llm_payload["status"] = "ok" if status.ok else "unavailable"
        fallback["llm"] = llm_payload
        if not status.ok:
            return fallback

        result = client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.35,
            max_tokens=220,
            json_schema={
                "name": "vibe_generation",
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "query": {"type": "string"},
                        "n": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "narrative": {"type": "string"},
                    },
                    "required": ["name", "query", "n", "narrative"],
                    "additionalProperties": False,
                },
            },
            system=(
                "You build music vibe presets. Return a concise vibe name and a CLAP-friendly query "
                "that captures sound and mood (tempo, texture, instrumentation, energy)."
            ),
        )
        if not result.get("ok") or "data" not in result:
            return fallback

        payload = result["data"]
        name = (payload.get("name") or fallback_name).strip()[:80]
        query = (payload.get("query") or prompt).strip() or prompt
        count = sanitize_integer(payload.get("n", n), default=n, min_val=1, max_val=1000)
        narrative = (payload.get("narrative") or "").strip()
        return {
            "name": name,
            "query": query,
            "n": count,
            "narrative": narrative,
            "used_llm": True,
            "llm": llm_payload,
        }
    except Exception:
        return fallback


# ============================================================================
# SEARCH
# ============================================================================

@app.route('/api/search', methods=['POST'])
def api_search():
    """Semantic search endpoint."""
    try:
        data = request.get_json() or {}
        
        # Validate input
        valid, error, sanitized = validate_search_request(data)
        if not valid:
            return jsonify({'error': error}), 400

        raw_use_rewrite = data.get('rewrite_with_llm', data.get('natural_language', False))
        valid, error, use_rewrite = validate_boolean(raw_use_rewrite, "rewrite_with_llm")
        if not valid:
            return jsonify({'error': error}), 400

        query = sanitized['query']
        n = sanitized['n']
        rewrite_meta = {
            "query": query,
            "n": n,
            "used_llm": False,
            "intent": "unknown",
            "rationale": "",
            "llm": {"status": "not_requested"},
        }
        if use_rewrite:
            rewrite_meta = _rewrite_search_query_with_llm(query, n)
            query = rewrite_meta["query"]
            n = rewrite_meta["n"]

        results = search(query, n=n)
        return jsonify({
            'results': results,
            'count': len(results),
            'original_query': sanitized['query'],
            'query': query,
            'n': n,
            'rewrite': rewrite_meta,
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/search/rewrite', methods=['POST'])
def api_search_rewrite():
    """Rewrite a query with LLM for CLAP search, without running search."""
    try:
        data = request.get_json() or {}
        valid, error, sanitized = validate_search_request(data)
        if not valid:
            return jsonify({'error': error}), 400
        rewrite = _rewrite_search_query_with_llm(sanitized['query'], sanitized['n'])
        return jsonify({
            'original_query': sanitized['query'],
            'query': rewrite['query'],
            'n': rewrite['n'],
            'rewrite': rewrite,
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/search/hybrid', methods=['POST'])
def api_search_hybrid():
    """Hybrid search: semantic + metadata filters + dimensional ranges."""
    try:
        from oracle.search import hybrid_search

        data = request.get_json() or {}
        original_query = (data.get('query') or '').strip()
        query = original_query or None
        filters = data.get('filters') or {}
        dimension_ranges = data.get('dimension_ranges') or data.get('dimensions') or {}
        sort_by = data.get('sort_by') or data.get('sort') or 'relevance'
        top_k = sanitize_integer(data.get('top_k') or data.get('limit') or 20, default=20, min_val=1, max_val=1000)

        valid, error, rewrite_requested = validate_boolean(
            data.get('rewrite_with_llm', data.get('natural_language', False)),
            "rewrite_with_llm",
        )
        if not valid:
            return jsonify({'error': error}), 400

        rewrite_meta = None
        if query and rewrite_requested:
            rewrite_meta = _rewrite_search_query_with_llm(query, top_k)
            query = (rewrite_meta.get('query') or query).strip() or query
            top_k = sanitize_integer(rewrite_meta.get('n', top_k), default=top_k, min_val=1, max_val=1000)

        if not query and not filters:
            return jsonify({'error': 'query or filters required'}), 400

        results = hybrid_search(
            query=query,
            filters=filters,
            dimension_ranges=dimension_ranges,
            sort_by=sort_by,
            top_k=top_k,
        )
        response = {'results': results, 'count': len(results), 'query': query, 'top_k': top_k}
        if original_query:
            response['original_query'] = original_query
        if rewrite_meta:
            response['rewrite'] = rewrite_meta
        return jsonify(response)

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# LIBRARY
# ============================================================================

@app.route('/api/library/scan', methods=['POST'])
def api_scan():
    """Trigger library scan."""
    try:
        data = request.get_json() or {}
        library_path = data.get('library', r'A:\music\Active Music')
        limit = data.get('limit', 0)
        
        results = scan_library(library_path, limit=limit)
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/library/index', methods=['POST'])
def api_index():
    """Trigger library indexing."""
    try:
        data = request.get_json() or {}
        library_path = data.get('library')
        limit = data.get('limit', 0)
        force_reindex = data.get('force_reindex', False)
        
        results = index_library(library_path, limit=limit, force_reindex=force_reindex)
        if isinstance(results, dict) and results.get('dependency_unavailable'):
            return jsonify(results), 503
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/library/validate', methods=['POST'])
def api_library_validate():
    """Validate + enrich track metadata using cached provider lookups."""
    try:
        from oracle.acquirers.validator import validate_and_fix_library

        data = request.get_json() or {}
        limit = sanitize_integer(data.get('limit', 0), default=0, min_val=0, max_val=500000)
        workers = sanitize_integer(data.get('workers', 0), default=0, min_val=0, max_val=64)
        confidence = data.get('confidence', 0.7)
        valid, error, apply_changes = validate_boolean(data.get('apply', True), "apply")
        if not valid:
            return jsonify({'error': error}), 400
        valid, error, only_unvalidated = validate_boolean(
            data.get('only_unvalidated', True),
            "only_unvalidated",
        )
        if not valid:
            return jsonify({'error': error}), 400
        valid, error, force_refresh = validate_boolean(data.get('force', False), "force")
        if not valid:
            return jsonify({'error': error}), 400
        valid, error, full_rescan_if_needed = validate_boolean(
            data.get('full_rescan_if_needed', True),
            "full_rescan_if_needed",
        )
        if not valid:
            return jsonify({'error': error}), 400

        if force_refresh:
            only_unvalidated = False

        valid_conf, conf_error, conf_value = validate_confidence(confidence)
        if not valid_conf:
            return jsonify({'error': conf_error}), 400

        results = validate_and_fix_library(
            limit=limit,
            apply=apply_changes,
            min_confidence=conf_value,
            workers=workers,
            only_unvalidated=only_unvalidated,
            full_rescan_if_needed=full_rescan_if_needed,
        )
        return jsonify({
            'status': 'ok',
            'results': results,
            'config': {
                'limit': limit,
                'apply': apply_changes,
                'confidence': conf_value,
                'workers': workers,
                'only_unvalidated': only_unvalidated,
                'force': force_refresh,
                'full_rescan_if_needed': full_rescan_if_needed,
            },
        })

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/library/tracks', methods=['GET'])
def api_tracks():
    """Get list of tracks."""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        query = (request.args.get('q') or '').strip()
        artist = (request.args.get('artist') or '').strip()
        album = (request.args.get('album') or '').strip()
        
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()

        where, params = _library_filter_state(query=query, artist=artist, album=album)

        total_row = cursor.execute(
            f"SELECT COUNT(*) FROM tracks {where}",
            params,
        ).fetchone()

        artist_rows = cursor.execute(
            f"""
            SELECT artist, COUNT(*)
            FROM tracks
            {where}
            GROUP BY artist
            ORDER BY artist COLLATE NOCASE ASC
            LIMIT 200
            """,
            params,
        ).fetchall()

        album_rows = cursor.execute(
            f"""
            SELECT COALESCE(album, ''), COUNT(*)
            FROM tracks
            {where}
            GROUP BY COALESCE(album, '')
            ORDER BY COALESCE(album, '') COLLATE NOCASE ASC
            LIMIT 200
            """,
            params,
        ).fetchall()

        conn.close()
        tracks = _fetch_library_tracks(query=query, artist=artist, album=album, limit=limit, offset=offset)
        
        return jsonify({
            'tracks': tracks,
            'count': len(tracks),
            'total': int(total_row[0] or 0),
            'offset': offset,
            'limit': limit,
            'query': query,
            'artist': artist or None,
            'album': album or None,
            'artists': [
                {'name': row[0] or 'Unknown Artist', 'count': int(row[1] or 0)}
                for row in artist_rows
            ],
            'albums': [
                {'name': row[0] or 'Singles / Unknown Album', 'count': int(row[1] or 0)}
                for row in album_rows
            ],
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/library/artists', methods=['GET'])
def api_library_artists():
    """Get artist navigation rows for the library browser."""
    try:
        limit = request.args.get('limit', 200, type=int)
        query = (request.args.get('q') or '').strip()
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        where, params = _library_filter_state(query=query)
        rows = cursor.execute(
            f"""
            SELECT artist, COUNT(*)
            FROM tracks
            {where}
            GROUP BY artist
            ORDER BY artist COLLATE NOCASE ASC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        conn.close()
        return jsonify({
            'artists': [{'name': row[0] or 'Unknown Artist', 'count': int(row[1] or 0)} for row in rows],
            'count': len(rows),
            'query': query,
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/library/albums', methods=['GET'])
def api_library_albums():
    """Get album navigation rows for the library browser."""
    try:
        limit = request.args.get('limit', 200, type=int)
        query = (request.args.get('q') or '').strip()
        artist = (request.args.get('artist') or '').strip()
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        where, params = _library_filter_state(query=query, artist=artist)
        rows = cursor.execute(
            f"""
            SELECT COALESCE(album, ''), COUNT(*)
            FROM tracks
            {where}
            GROUP BY COALESCE(album, '')
            ORDER BY COALESCE(album, '') COLLATE NOCASE ASC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        conn.close()
        return jsonify({
            'albums': [{'name': row[0] or 'Singles / Unknown Album', 'count': int(row[1] or 0)} for row in rows],
            'count': len(rows),
            'query': query,
            'artist': artist or None,
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/library/artists/<path:artist_name>', methods=['GET'])
def api_library_artist_detail(artist_name: str):
    """Get a single artist detail view for the library browser."""
    try:
        artist = artist_name.strip()
        if not artist:
            return jsonify({'error': 'artist is required'}), 400
        tracks = _fetch_library_tracks(artist=artist, limit=500, offset=0)
        if not tracks:
            return jsonify({'error': 'Artist not found'}), 404
        albums_map: dict[str, int] = {}
        years = sorted({str(track.get('year') or '').strip() for track in tracks if str(track.get('year') or '').strip()})
        for track in tracks:
            album_name = track.get('album') or 'Singles / Unknown Album'
            albums_map[album_name] = albums_map.get(album_name, 0) + 1
        return jsonify({
            'artist': artist,
            'track_count': len(tracks),
            'album_count': len(albums_map),
            'years': years,
            'albums': [{'name': name, 'count': count} for name, count in sorted(albums_map.items(), key=lambda item: item[0].lower())],
            'tracks': tracks[:120],
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/library/albums/<path:album_name>', methods=['GET'])
def api_library_album_detail(album_name: str):
    """Get a single album detail view for the library browser."""
    try:
        album = album_name.strip()
        artist = (request.args.get('artist') or '').strip()
        if not album:
            return jsonify({'error': 'album is required'}), 400
        tracks = _fetch_library_tracks(artist=artist, album=album, limit=500, offset=0)
        if not tracks:
            return jsonify({'error': 'Album not found'}), 404
        years = sorted({str(track.get('year') or '').strip() for track in tracks if str(track.get('year') or '').strip()})
        return jsonify({
            'artist': artist or tracks[0].get('artist') or 'Unknown Artist',
            'album': album,
            'track_count': len(tracks),
            'years': years,
            'tracks': tracks[:120],
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# VIBES
# ============================================================================

@app.route('/api/vibes', methods=['GET'])
def api_vibes_list():
    """List all vibes."""
    try:
        vibes = list_vibes()
        return jsonify({'vibes': vibes, 'count': len(vibes)})
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/playlists/<playlist_id>', methods=['GET'])
def api_playlist_detail(playlist_id: str):
    """Return canonical playlist/listening-thread detail."""
    try:
        detail = _load_vibe_detail(playlist_id)
        if not detail:
            return jsonify({'error': 'Playlist not found'}), 404
        return jsonify(detail)
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/playlists/<int:run_id>/explain', methods=['GET'])
def api_playlist_explain(run_id: int):
    """
    Return structured reasons for every track in a playlist run (F-007).

    Response::

        {
            "run_id": int,
            "track_count": int,
            "tracks": [
                {
                    "rank": int,
                    "track_path": str,
                    "score": float,
                    "artist": str, "title": str, "album": str,
                    "reasons": [{"type": str, "score": float, "text": str}, ...],
                    "reasons_summary": str
                }, ...
            ]
        }
    """
    try:
        from oracle.explain import ReasonBuilder
        rb = ReasonBuilder()
        result = rb.explain_run(run_id)
        if result['track_count'] == 0:
            return jsonify({'error': f'No tracks found for run_id {run_id}'}), 404
        return jsonify(result)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@app.route('/api/vibes/save', methods=['POST'])
def api_vibes_save():
    """Create a new vibe."""
    try:
        data = request.get_json() or {}
        
        # Validate input
        valid, error, sanitized = validate_vibe_save_request(data)
        if not valid:
            return jsonify({'error': error}), 400
        
        result = save_vibe(sanitized['name'], sanitized['query'], n=sanitized['n'])
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/vibes/generate', methods=['POST'])
def api_vibes_generate():
    """Generate vibe query/name from natural-language prompt, optionally save."""
    try:
        data = request.get_json() or {}
        prompt = (data.get('prompt') or data.get('query') or '').strip()
        if not prompt:
            return jsonify({'error': 'prompt is required'}), 400

        n = sanitize_integer(data.get('n', 200), default=200, min_val=1, max_val=1000)
        valid, error, save_generated = validate_boolean(data.get('save', False), "save")
        if not valid:
            return jsonify({'error': error}), 400

        generated = _generate_vibe_from_prompt(prompt, n)
        candidate_name = generated.get('name', '').strip() or "Generated Vibe"
        if save_generated:
            valid_name, _name_error = validate_name(candidate_name, "Vibe name")
            if not valid_name:
                candidate_name = " ".join(prompt.split()[:4]).strip() or "Generated Vibe"
                candidate_name = candidate_name.replace("/", " ").replace("\\", " ").replace(":", " ")
                candidate_name = candidate_name[:80]

        run = generate_vibe(
            generated['query'],
            n=generated['n'],
            vibe_name=candidate_name if save_generated else None,
        )

        response = {
            'meta': {
                'prompt': prompt,
                'generated': generated,
                'save_requested': save_generated,
                'vibe_name': candidate_name if save_generated else None,
            },
            'run': _playlist_run_to_dict(run),
        }

        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/vibes/create', methods=['POST'])
def api_vibes_create():
    """One-shot vibe create from natural-language prompt with optional build/materialize."""
    try:
        data = request.get_json() or {}
        prompt = (data.get('prompt') or data.get('query') or '').strip()
        if not prompt:
            return jsonify({'error': 'prompt is required'}), 400

        provided_name = (data.get('name') or '').strip()
        n = sanitize_integer(data.get('n', 200), default=200, min_val=1, max_val=1000)

        valid, error, do_build = validate_boolean(data.get('build', False), "build")
        if not valid:
            return jsonify({'error': error}), 400
        valid, error, do_materialize = validate_boolean(data.get('materialize', False), "materialize")
        if not valid:
            return jsonify({'error': error}), 400

        mode = (data.get('mode') or 'hardlink').strip().lower()
        if mode not in ('hardlink', 'symlink', 'shortcut'):
            return jsonify({'error': "Invalid mode. Must be one of: hardlink, symlink, shortcut"}), 400

        generated = _generate_vibe_from_prompt(prompt, n)
        vibe_name = provided_name or (generated.get('name') or '').strip() or "Generated Vibe"

        valid_name, _ = validate_name(vibe_name, "Vibe name")
        if not valid_name:
            vibe_name = " ".join(prompt.split()[:4]).strip() or "Generated Vibe"
            vibe_name = vibe_name.replace("/", " ").replace("\\", " ").replace(":", " ")
            vibe_name = vibe_name[:80]

        save_result = save_vibe(vibe_name, generated['query'], n=generated['n'])
        if 'error' in save_result:
            return jsonify({'prompt': prompt, 'generated': generated, 'save': save_result}), 400

        response = {
            'prompt': prompt,
            'name': vibe_name,
            'generated': generated,
            'save': save_result,
        }

        if do_build:
            build_result = build_vibe(vibe_name)
            response['build'] = build_result
            if 'error' in build_result:
                return jsonify(response), 400

        if do_materialize:
            materialize_result = materialize_vibe(vibe_name, mode=mode)
            response['materialize'] = materialize_result
            if 'error' in materialize_result:
                return jsonify(response), 400

        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/vibes/narrate', methods=['POST'])
def api_vibes_narrate():
    """Generate an LLM narrative for a vibe's current ordered tracks."""
    try:
        if not LLMClient:
            return jsonify({'error': 'LLM client unavailable'}), 503

        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400

        arc_type = (data.get('arc_type') or 'journey').strip() or 'journey'
        limit = sanitize_integer(data.get('limit', 20), default=20, min_val=1, max_val=50)

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT t.artist, t.title
            FROM vibe_tracks vt
            JOIN tracks t ON vt.track_id = t.track_id
            WHERE vt.vibe_name = ?
            ORDER BY vt.position
            LIMIT ?
            """,
            (name, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return jsonify({'error': f'No tracks found for vibe "{name}"'}), 404

        tracks = [{"artist": row[0] or "", "title": row[1] or ""} for row in rows]
        client = LLMClient.from_env()
        llm_status = client.check_available()
        llm_payload = llm_status.as_dict()
        llm_payload["status"] = "ok" if llm_status.ok else "unavailable"
        if not llm_status.ok:
            narrative = _fallback_vibe_narrative(tracks, arc_type)
            return jsonify({
                'name': name,
                'arc_type': arc_type,
                'track_count': len(tracks),
                'narrative': narrative,
                'llm': llm_payload,
                'fallback': True,
            })

        narrative = client.narrate_playlist(tracks, arc_type=arc_type)
        return jsonify({
            'name': name,
            'arc_type': arc_type,
            'track_count': len(tracks),
            'narrative': narrative,
            'llm': llm_payload,
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/vibes/build', methods=['POST'])
def api_vibes_build():
    """Build M3U8 for a vibe."""
    try:
        data = request.get_json()
        name = data.get('name', '')
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        
        result = build_vibe(name)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/vibes/materialize', methods=['POST'])
def api_vibes_materialize():
    """Materialize a vibe as folder."""
    try:
        data = request.get_json() or {}
        
        # Validate input
        valid, error, sanitized = validate_vibe_materialize_request(data)
        if not valid:
            return jsonify({'error': error}), 400
        
        result = materialize_vibe(sanitized['name'], mode=sanitized['mode'])
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/vibes/refresh', methods=['POST'])
def api_vibes_refresh():
    """Refresh vibe(s)."""
    try:
        data = request.get_json() or {}
        name = data.get('name')
        
        result = refresh_vibes(name)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/vibes/delete', methods=['POST'])
def api_vibes_delete():
    """Delete a vibe."""
    try:
        data = request.get_json()
        name = data.get('name', '')
        delete_folder = data.get('delete_folder', False)
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        
        result = delete_vibe(name, delete_materialized=delete_folder)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# CURATION
# ============================================================================

@app.route('/api/curate/classify', methods=['POST'])
def api_curate_classify():
    """Classify all tracks."""
    try:
        data = request.get_json() or {}
        limit = sanitize_integer(data.get('limit', 0), default=0, min_val=0, max_val=500000)
        raw_use_llm = data.get('use_llm', False)
        valid, error, use_llm = validate_boolean(raw_use_llm, "use_llm")
        if not valid:
            return jsonify({'error': error}), 400

        results = classify_library(limit=limit, use_llm=use_llm)
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/curate/plan', methods=['POST'])
def api_curate_plan():
    """Generate curation plan."""
    try:
        data = request.get_json() or {}
        preset = data.get('preset', 'artist_album')
        classify_first = data.get('classify_first', False)
        limit = data.get('limit', 0)
        
        result = generate_plan(
            preset=preset,
            classify_first=classify_first,
            limit=limit,
            output_dir='Reports'
        )
        
        return jsonify({'result': result})
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/curate/apply', methods=['POST'])
def api_curate_apply():
    """Apply curation plan."""
    try:
        data = request.get_json()
        plan_path = data.get('plan_path', '')
        confidence_min = data.get('confidence_min', 0.5)
        dry_run = data.get('dry_run', True)
        
        if not plan_path:
            return jsonify({'error': 'Plan path is required'}), 400
        
        result = apply_plan(
            plan_path=plan_path,
            confidence_min=confidence_min,
            dry_run=dry_run
        )
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# ACQUISITION
# ============================================================================

@app.route('/api/acquire/youtube', methods=['POST'])
def api_acquire_youtube():
    """Download from YouTube."""
    try:
        data = request.get_json() or {}
        url = data.get('url', '')
        
        # Validate URL
        valid, error = validate_url(url)
        if not valid:
            return jsonify({'error': error}), 400
        
        acquirer = YTDLPAcquirer()
        result = acquirer.download(url.strip())

        return jsonify({'result': _json_safe(result or 'Download failed')})
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/acquire/queue', methods=['GET'])
def api_acquire_queue():
    """Get acquisition queue."""
    try:
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT id, url, source, status, added_at, error
            FROM acquisition_queue
            ORDER BY added_at DESC
            LIMIT 50
            """
        )
        rows = cursor.fetchall()
        conn.close()
        
        queue = []
        for row in rows:
            queue.append({
                'id': row[0],
                'url': row[1],
                'source': row[2],
                'status': row[3],
                'added_at': row[4],
                'error': row[5]
            })
        
        return jsonify({'queue': queue, 'count': len(queue)})
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/acquire/process', methods=['POST'])
def api_acquire_process():
    """Process acquisition queue."""
    try:
        data = request.get_json(silent=True) or {}
        limit = sanitize_integer(data.get('limit', 0), default=0, min_val=0, max_val=1000)
        results = process_queue(limit=limit)
        return jsonify(results)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return jsonify({'error': 'database is locked; retry shortly'}), 503
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/remixes/search', methods=['POST'])
def api_remixes_search():
    """Find and view remix tracks for artist/album/track scopes."""
    try:
        from oracle.search import find_remixes

        data = request.get_json() or {}
        artist = (data.get('artist') or '').strip()
        album = (data.get('album') or '').strip()
        track = (data.get('track') or '').strip()
        n = sanitize_integer(data.get('n', 100), default=100, min_val=1, max_val=1000)
        sort_by = (data.get('sort_by') or 'recent').strip().lower()

        valid, error, include_candidates = validate_boolean(
            data.get('include_candidates', True),
            "include_candidates",
        )
        if not valid:
            return jsonify({'error': error}), 400

        if not artist and not album and not track:
            return jsonify({'error': 'artist, album, or track is required'}), 400

        results = find_remixes(
            artist=artist or None,
            album=album or None,
            track=track or None,
            n=n,
            include_candidates=include_candidates,
            sort_by=sort_by,
        )
        strict_count = sum(1 for r in results if r.get('is_strict_remix'))
        candidate_count = len(results) - strict_count

        return jsonify({
            'filters': {
                'artist': artist,
                'album': album,
                'track': track,
                'n': n,
                'include_candidates': include_candidates,
                'sort_by': sort_by,
            },
            'count': len(results),
            'summary': {
                'strict_remix': strict_count,
                'candidate': candidate_count,
            },
            'results': results,
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Batch Acquisition (parallel fast_batch with SSE progress)
# ---------------------------------------------------------------------------
import threading
import queue as _queue
import time as _time
import uuid as _uuid

_batch_jobs: Dict[str, dict] = {}   # job_id â†’ {status, progress, results, ...}
_batch_queues: Dict[str, _queue.Queue] = {}  # job_id â†’ SSE event queue


def _run_batch_job(job_id: str, queries: List[str], workers: int, run_pipeline: bool):
    """Background thread that runs fast_batch and pushes SSE events."""
    from oracle.fast_batch import _download_one, FAST_SLEEP_MIN, FAST_SLEEP_MAX
    from oracle.config import load_config
    from concurrent.futures import ThreadPoolExecutor, as_completed

    eq = _batch_queues[job_id]
    job = _batch_jobs[job_id]

    cfg = load_config()
    cfg.sleep_min = FAST_SLEEP_MIN
    cfg.sleep_max = FAST_SLEEP_MAX
    db_path = Path(os.getenv("LYRA_DB_PATH", "lyra_registry.db"))

    total = len(queries)
    job["total"] = total
    eq.put({"event": "start", "total": total, "workers": workers})

    # Phase 1: Downloads
    ok = 0
    fail = 0
    results = []
    t0 = _time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_download_one, q.strip(), cfg, db_path, i, total): (i, q)
            for i, q in enumerate(queries, 1)
            if q.strip()
        }
        for future in as_completed(futures):
            idx, query = futures[future]
            r = future.result()
            results.append(r)
            if r["success"]:
                ok += 1
                eq.put({"event": "downloaded", "idx": idx, "query": query,
                        "artist": r.get("artist", ""), "title": r.get("title", ""),
                        "elapsed": round(r.get("elapsed", 0), 1), "ok": ok, "fail": fail, "total": total})
            else:
                fail += 1
                eq.put({"event": "failed", "idx": idx, "query": query,
                        "error": r.get("error", ""), "ok": ok, "fail": fail, "total": total})

    dl_time = round(_time.perf_counter() - t0, 1)
    eq.put({"event": "downloads_done", "ok": ok, "fail": fail, "time": dl_time})
    job["download_results"] = results

    # Phase 2: Pipeline
    if run_pipeline and ok > 0:
        downloads_path = str(cfg.download_dir.resolve())

        eq.put({"event": "pipeline", "stage": "scan"})
        t1 = _time.perf_counter()
        from oracle.scanner import scan_library as _scan
        scan_r = _scan(downloads_path)
        scan_time = round(_time.perf_counter() - t1, 2)
        eq.put({"event": "pipeline_done", "stage": "scan", "result": scan_r, "time": scan_time})

        eq.put({"event": "pipeline", "stage": "index"})
        t1 = _time.perf_counter()
        from oracle.indexer import index_library as _index
        idx_r = _index(library_path=downloads_path)
        idx_time = round(_time.perf_counter() - t1, 2)
        eq.put({"event": "pipeline_done", "stage": "index", "result": idx_r, "time": idx_time})

        eq.put({"event": "pipeline", "stage": "score"})
        t1 = _time.perf_counter()
        from oracle.scorer import score_all as _score
        score_r = _score(force=False)
        score_time = round(_time.perf_counter() - t1, 2)
        eq.put({"event": "pipeline_done", "stage": "score", "result": score_r, "time": score_time})

    total_time = round(_time.perf_counter() - t0, 1)
    job["status"] = "complete"
    job["ok"] = ok
    job["fail"] = fail
    job["total_time"] = total_time
    eq.put({"event": "complete", "ok": ok, "fail": fail, "total_time": total_time})
    eq.put(None)  # sentinel


@app.route('/api/acquire/batch', methods=['POST'])
def api_acquire_batch():
    """Start a parallel batch download job. Returns job_id for SSE streaming."""
    try:
        data = request.get_json() or {}
        raw = data.get('queries', '')
        workers = min(int(data.get('workers', 4)), 8)
        run_pipeline = data.get('pipeline', True)

        if isinstance(raw, str):
            queries = [q.strip() for q in raw.splitlines() if q.strip() and not q.strip().startswith('#')]
        elif isinstance(raw, list):
            queries = [q.strip() for q in raw if q.strip()]
        else:
            return jsonify({'error': 'queries must be string or list'}), 400

        if not queries:
            return jsonify({'error': 'No queries provided'}), 400
        if len(queries) > 200:
            return jsonify({'error': f'Max 200 queries per batch, got {len(queries)}'}), 400

        job_id = _uuid.uuid4().hex[:12]
        _batch_jobs[job_id] = {"status": "running", "total": len(queries)}
        _batch_queues[job_id] = _queue.Queue()

        t = threading.Thread(target=_run_batch_job, args=(job_id, queries, workers, run_pipeline), daemon=True)
        t.start()

        return jsonify({'job_id': job_id, 'total': len(queries), 'workers': workers})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/acquire/batch/<job_id>/stream')
def api_acquire_batch_stream(job_id):
    """SSE stream for batch job progress."""
    if job_id not in _batch_queues:
        return jsonify({'error': 'Job not found'}), 404

    def generate():
        eq = _batch_queues[job_id]
        while True:
            try:
                msg = eq.get(timeout=120)
                if msg is None:
                    yield f"data: {json.dumps({'event': 'done'})}\n\n"
                    break
                yield f"data: {json.dumps(msg)}\n\n"
            except _queue.Empty:
                yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/acquire/batch/<job_id>/status')
def api_acquire_batch_status(job_id):
    """Get batch job status (polling fallback)."""
    job = _batch_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@app.route('/api/downloads', methods=['GET'])
def api_downloads_list():
    """List downloads."""
    try:
        show_metadata = request.args.get('metadata', 'false').lower() == 'true'
        downloads = list_downloads(show_metadata=show_metadata)
        return jsonify({'downloads': downloads, 'count': len(downloads)})
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/downloads/organize', methods=['POST'])
def api_downloads_organize():
    """Organize downloads into library."""
    try:
        data = request.get_json() or {}
        library = data.get('library', r'A:\music\Active Music')
        clean_names = data.get('clean_names', True)
        dry_run = data.get('dry_run', False)
        scan_after = data.get('scan_after', True)
        
        results = process_downloads(
            target_library=library,
            clean_names=clean_names,
            dry_run=dry_run,
            scan_after=scan_after
        )
        
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/spotify/missing', methods=['GET'])
def api_spotify_missing():
    """Find Spotify favorites not in local library â€” acquisition candidates."""
    try:
        min_plays = sanitize_integer(request.args.get('min_plays', 5), default=5, min_val=0, max_val=1000000)
        limit = sanitize_integer(request.args.get('limit', 100), default=100, min_val=1, max_val=1000)

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT artist, title, album, spotify_uri, source, play_count, priority_score, status, added_at
            FROM acquisition_queue
            WHERE source IN ('history', 'liked', 'playlist', 'top_tracks')
              AND status = 'pending'
              AND COALESCE(play_count, 0) >= ?
            ORDER BY COALESCE(priority_score, 0.0) DESC, COALESCE(play_count, 0) DESC, added_at DESC
            LIMIT ?
            """,
            (min_plays, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        missing = [
            {
                'artist': row[0],
                'title': row[1],
                'album': row[2],
                'spotify_uri': row[3],
                'source': row[4],
                'play_count': row[5],
                'priority_score': row[6],
                'status': row[7],
                'added_at': row[8],
            }
            for row in rows
        ]
        return jsonify({
            'ok': True,
            'missing': missing,
            'count': len(missing),
            'min_plays': min_plays
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/spotify/stats', methods=['GET'])
def api_spotify_stats():
    """Get Spotify import statistics."""
    try:
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        stats = {}

        for table in ('spotify_history', 'spotify_library', 'spotify_features'):
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name = ?", (table,))
            exists = cursor.fetchone()[0] > 0
            if exists:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[f"{table}_count"] = int(cursor.fetchone()[0])
            else:
                stats[f"{table}_count"] = 0

        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
            FROM acquisition_queue
            WHERE source IN ('history', 'liked', 'playlist', 'top_tracks')
            """
        )
        pending, completed, failed = cursor.fetchone()
        stats['queue_pending'] = int(pending or 0)
        stats['queue_completed'] = int(completed or 0)
        stats['queue_failed'] = int(failed or 0)

        top_artists = []
        cursor.execute(
            """
            SELECT artist, COUNT(*) AS play_count, SUM(COALESCE(ms_played, 0)) AS total_ms
            FROM spotify_history
            WHERE artist IS NOT NULL AND trim(artist) != ''
            GROUP BY artist
            ORDER BY play_count DESC, total_ms DESC
            LIMIT 25
            """
        )
        for artist, play_count, total_ms in cursor.fetchall():
            top_artists.append({
                'name': artist,
                'score': int(play_count or 0),
                'plays': int(play_count or 0),
                'total_ms': int(total_ms or 0),
            })

        conn.close()
        stats['top_artists'] = top_artists
        return jsonify({'ok': True, **stats})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ============================================================================
# INTELLIGENCE LAYER (SCOUT / LORE / DNA)
# ============================================================================

@app.route('/api/scout/cross-genre', methods=['POST'])
def api_scout_cross_genre():
    """Cross-genre hunt using Discogs + bridge artists."""
    try:
        if not scout_engine:
            return jsonify({'error': 'Scout engine not available Ã¢â‚¬â€ check server logs'}), 503

        data = request.get_json() or {}
        source_genre = (data.get('source_genre') or '').strip()
        target_genre = (data.get('target_genre') or '').strip()
        limit = int(data.get('limit', 20))
        prefer_remixes = bool(data.get('prefer_remixes', True))

        if not source_genre or not target_genre:
            return jsonify({'error': 'source_genre and target_genre are required'}), 400

        results = scout_engine.cross_genre_hunt(source_genre, target_genre, limit, prefer_remixes)
        return jsonify({'results': results, 'count': len(results)})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/lore/trace', methods=['POST'])
def api_lore_trace():
    """Trace artist lineage and store connections."""
    try:
        if not lore_engine:
            return jsonify({'error': 'Lore engine not available â€” check server logs'}), 503

        data = request.get_json() or {}
        artist = (data.get('artist') or '').strip()
        depth = int(data.get('depth', 2))

        if not artist:
            return jsonify({'error': 'artist is required'}), 400

        results = lore_engine.trace_lineage(artist, depth=depth)
        return jsonify(results)

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/lore/connections', methods=['GET'])
def api_lore_connections():
    """Get stored connections for an artist."""
    try:
        if not lore_engine:
            return jsonify({'error': 'Lore engine not available â€” check server logs'}), 503

        artist = (request.args.get('artist') or '').strip()
        if not artist:
            return jsonify({'error': 'artist is required'}), 400

        connections = lore_engine.get_artist_connections(artist)
        return jsonify({'artist': artist, 'connections': connections, 'count': len(connections)})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/dna/trace', methods=['GET'])
def api_dna_trace():
    """Trace samples for a track."""
    try:
        if not dna_engine:
            return jsonify({'error': 'DNA engine not available Ã¢â‚¬â€ check server logs'}), 503

        track_id = (request.args.get('track_id') or '').strip()
        if not track_id:
            return jsonify({'error': 'track_id is required'}), 400

        samples = dna_engine.trace_samples(track_id)
        return jsonify({'track_id': track_id, 'samples': samples, 'count': len(samples)})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/dna/pivot', methods=['GET'])
def api_dna_pivot():
    """Pivot to original sample source if available."""
    try:
        if not dna_engine:
            return jsonify({'error': 'DNA engine not available Ã¢â‚¬â€ check server logs'}), 503

        track_id = (request.args.get('track_id') or '').strip()
        if not track_id:
            return jsonify({'error': 'track_id is required'}), 400

        result = dna_engine.pivot_to_original(track_id)
        return jsonify({'result': result})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# HUNTER (ACQUISITION)
# ============================================================================

@app.route('/api/hunter/hunt', methods=['POST'])
def api_hunter_hunt():
    """Hunt for a release via Prowlarr + Real-Debrid cache."""
    try:
        if not hunter_engine:
            return jsonify({'error': 'Hunter engine not available Ã¢â‚¬â€ check server logs'}), 503

        data = request.get_json() or {}
        query = (data.get('query') or '').strip()
        prefer_cached = bool(data.get('prefer_cached', True))
        quality_preference = (data.get('quality_preference') or 'FLAC').strip()

        if not query:
            return jsonify({'error': 'query is required'}), 400

        results = hunter_engine.hunt(query, prefer_cached=prefer_cached, quality_preference=quality_preference)
        return jsonify({'results': results, 'count': len(results)})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/hunter/acquire', methods=['POST'])
def api_hunter_acquire():
    """Acquire a target from hunter results."""
    try:
        if not hunter_engine:
            return jsonify({'error': 'Hunter engine not available Ã¢â‚¬â€ check server logs'}), 503

        data = request.get_json() or {}
        target = data.get('target') or {}
        if not target:
            return jsonify({'error': 'target is required'}), 400

        result = hunter_engine.acquire(target)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# ARCHITECT (ANALYSIS)
# ============================================================================

@app.route('/api/architect/analyze', methods=['POST'])
def api_architect_analyze():
    """Analyze track structure and store results."""
    try:
        if not architect_engine:
            return jsonify({'error': 'Architect engine not available Ã¢â‚¬â€ check server logs'}), 503

        data = request.get_json() or {}
        track_id = (data.get('track_id') or '').strip()
        file_path = (data.get('file_path') or '').strip()

        if not track_id or not file_path:
            return jsonify({'error': 'track_id and file_path are required'}), 400

        valid_path, error = validate_path(file_path, must_exist=True)
        if not valid_path:
            return jsonify({'error': error}), 400

        base_path = Path(LIBRARY_BASE).resolve()
        target_path = Path(file_path).resolve()
        if base_path not in target_path.parents and target_path != base_path:
            return jsonify({'error': 'file_path must be within library base'}), 400

        result = architect_engine.analyze_structure(track_id, file_path)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/structure/<track_id>', methods=['GET'])
def api_architect_structure(track_id: str):
    """Get stored structure analysis for a track."""
    try:
        if not architect_engine:
            return jsonify({'error': 'Architect engine not available Ã¢â‚¬â€ check server logs'}), 503

        result = architect_engine.get_structure(track_id)
        return jsonify({'track_id': track_id, 'structure': result})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# RADIO (PLAYBACK)
# ============================================================================

@app.route('/api/radio/chaos', methods=['POST'])
def api_radio_chaos():
    """Get chaos mode recommendations."""
    try:
        if not radio_engine:
            return jsonify({'error': 'Radio engine not available â€” check server logs'}), 503

        data = request.get_json() or {}
        track_id = (data.get('track_id') or '').strip() or None
        count = int(data.get('count', 1))

        results = radio_engine.get_chaos_track(track_id, count=count)
        return jsonify({'results': results, 'count': len(results)})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/radio/flow', methods=['POST'])
def api_radio_flow():
    """Get flow mode recommendations."""
    try:
        if not radio_engine:
            return jsonify({'error': 'Radio engine not available â€” check server logs'}), 503

        data = request.get_json() or {}
        track_id = (data.get('track_id') or data.get('seed_track') or '').strip()
        count = int(data.get('count', 1))

        if not track_id:
            conn = get_connection(timeout=5.0)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT track_id FROM tracks WHERE status = 'active' ORDER BY COALESCE(updated_at, created_at, added_at, 0) DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                track_id = row[0]
            else:
                return jsonify({'error': 'track_id is required for flow mode when no active library track is available'}), 400

        results = radio_engine.get_flow_track(track_id, count=count)
        return jsonify({'results': results, 'count': len(results)})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/radio/discovery', methods=['GET'])
def api_radio_discovery():
    """Get discovery mode recommendations."""
    try:
        if not radio_engine:
            return jsonify({'error': 'Radio engine not available â€” check server logs'}), 503

        count = request.args.get('count', 1, type=int)
        results = radio_engine.get_discovery_track(count=count)
        return jsonify({'results': results, 'count': len(results)})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/radio/queue', methods=['POST'])
def api_radio_queue():
    """Build a full radio queue."""
    try:
        if not radio_engine:
            return jsonify({'error': 'Radio engine not available'}), 503

        data = request.get_json() or {}
        mode = (data.get('mode') or 'chaos').strip()
        seed_track = (data.get('seed_track') or '').strip() or None
        length = int(data.get('length', 20))

        queue = radio_engine.build_queue(mode=mode, seed_track=seed_track, length=length)
        return jsonify({'queue': queue, 'count': len(queue), 'mode': mode})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/playback/record', methods=['POST'])
def api_playback_record():
    """Record playback event for taste learning."""
    try:
        if not radio_engine:
            return jsonify({'error': 'Radio engine not available; check server logs'}), 503

        data = request.get_json() or {}
        track_id = (data.get('track_id') or '').strip()
        context = (data.get('context') or 'manual').strip()
        skipped = bool(data.get('skipped', False))
        rating = data.get('rating')

        if not track_id:
            return jsonify({'error': 'track_id is required'}), 400
        try:
            completion_rate = float(data.get('completion_rate', 1.0))
        except (TypeError, ValueError):
            return jsonify({'error': 'completion_rate must be a number'}), 400
        if completion_rate < 0.0 or completion_rate > 1.0:
            return jsonify({'error': 'completion_rate must be between 0.0 and 1.0'}), 400
        if rating is not None:
            try:
                rating = int(rating)
            except (TypeError, ValueError):
                return jsonify({'error': 'rating must be an integer from 1 to 5'}), 400
            if rating < 1 or rating > 5:
                return jsonify({'error': 'rating must be an integer from 1 to 5'}), 400

        try:
            radio_engine.record_playback(
                track_id=track_id,
                context=context,
                skipped=skipped,
                completion_rate=completion_rate,
                rating=rating
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        return jsonify({'status': 'ok'})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# TASTE PROFILE
# ============================================================================

@app.route('/api/taste/profile', methods=['GET'])
def api_taste_profile():
    """Return the user's current taste profile with library context.

    Always returns a meaningful response — if no playback has been recorded
    yet, dimensions are derived from library averages (cold-start mode).

    Response includes:
        dimensions        — all 10 dimensional values (-1..1)
        confidence        — per-dimension confidence (0..1)
        source            — 'learned' | 'library' | 'default'
        genre_affinity    — top genres
        era_distribution  — decade → track count
        top_artists       — top 10 library artists
        total_signals     — playback events recorded
        library_stats     — track/scored counts
        is_cold_start     — True when mostly derived from library, not playback
    """
    try:
        from oracle.taste import get_taste_profile
        return jsonify(get_taste_profile())
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@app.route('/api/taste/seed', methods=['POST'])
def api_taste_seed():
    """Seed taste profile from library averages (cold-start bootstrap).

    Safe to call repeatedly — only overwrites dimensions that haven't been
    meaningfully updated by real playback (confidence < 0.3).

    Request body (optional)::

        { "overwrite": false }

    Set ``overwrite=true`` to reset all dimensions to library averages.
    """
    try:
        from oracle.taste import seed_taste_from_library
        data = request.get_json(silent=True) or {}
        overwrite = bool(data.get('overwrite', False))
        result = seed_taste_from_library(overwrite_existing=overwrite)
        return jsonify({'ok': True, 'result': result})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


# ============================================================================
# AGENT (LYRA)
# ============================================================================

@app.route('/api/agent/query', methods=['POST'])
def api_agent_query():
    """Query Lyra agent for orchestration."""
    try:
        if not agent_engine:
            return jsonify({'error': 'Agent engine not available'}), 503

        data = request.get_json() or {}
        text = (data.get('text') or data.get('query') or '').strip()
        context = data.get('context') or {}
        valid, error, execute = validate_boolean(data.get('execute', False), "execute")
        if not valid:
            return jsonify({'error': error}), 400

        if not text:
            return jsonify({'error': 'text is required'}), 400

        if execute:
            result = agent_engine.query(text, context=context)
        else:
            result = agent_engine.run_agent(text, context=context)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/agent/fact-drop', methods=['GET'])
def api_agent_fact_drop():
    """Get a fact drop for a track."""
    try:
        if not agent_engine:
            return jsonify({'error': 'Agent engine not available'}), 503

        track_id = (request.args.get('track_id') or '').strip()
        if not track_id:
            return jsonify({'error': 'track_id is required'}), 400

        fact = agent_engine.fact_drop(track_id)
        return jsonify({'track_id': track_id, 'fact': fact})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/agent/suggest', methods=['GET'])
def api_agent_suggest():
    """Get proactive next-action suggestion from Lyra agent."""
    try:
        if not agent_engine:
            return jsonify({'error': 'Agent engine not available'}), 503

        context = {}
        track_id = (request.args.get('track_id') or '').strip()
        if track_id:
            context['current_track'] = track_id

        result = agent_engine.suggest_next_action(context)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# SAFETY & OPERATIONS
# ============================================================================

@app.route('/api/journal', methods=['GET'])
def api_journal():
    """Get operation history from journal."""
    try:
        n = int(request.args.get('n', 10))
        journal = get_journal()
        transactions = journal.read_last(n)
        
        return jsonify({
            'count': len(transactions),
            'transactions': [txn.to_dict() for txn in transactions]
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/undo', methods=['POST'])
def api_undo():
    """Undo last N file operations."""
    try:
        data = request.get_json() or {}
        n = int(data.get('n', 1))
        
        undone = undo_last(n)
        
        return jsonify({
            'success': True,
            'undone_count': len(undone),
            'transactions': [txn.to_dict() for txn in undone]
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# ACQUISITION PIPELINE
# ============================================================================

@app.route('/api/pipeline/start', methods=['POST'])
def api_pipeline_start():
    """Start acquisition pipeline."""
    try:
        if not get_pipeline:
            return jsonify({'error': 'Pipeline engine not available Ã¢â‚¬â€ check server logs'}), 503

        data = request.get_json() or {}
        query = (data.get('query') or '').strip()
        
        if not query:
            return jsonify({'error': 'query is required'}), 400
        
        pipeline = get_pipeline()
        job_id = pipeline.create_job(query)
        job = pipeline.get_job(job_id)
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'job': job
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/pipeline/status/<job_id>', methods=['GET'])
def api_pipeline_status(job_id: str):
    """Get pipeline job status."""
    try:
        if not get_pipeline:
            return jsonify({'error': 'Pipeline engine not available Ã¢â‚¬â€ check server logs'}), 503

        pipeline = get_pipeline()
        job = pipeline.get_job(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify({
            'success': True,
            'job': job
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/pipeline/run/<job_id>', methods=['POST'])
def api_pipeline_run(job_id: str):
    """Execute pipeline for a job."""
    try:
        from oracle.pipeline import run_pipeline
        job = run_pipeline(job_id)
        
        return jsonify({
            'success': True,
            'job': job
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/pipeline/jobs', methods=['GET'])
def api_pipeline_jobs():
    """List recent pipeline jobs."""
    try:
        if not get_pipeline:
            return jsonify({'error': 'Pipeline engine not available Ã¢â‚¬â€ check server logs'}), 503

        limit = int(request.args.get('limit', 20))
        pipeline = get_pipeline()
        jobs = pipeline.list_jobs(limit)
        
        return jsonify({
            'success': True,
            'count': len(jobs),
            'jobs': jobs
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# STREAMING
# ============================================================================

@app.route('/api/stream/<track_id>', methods=['GET'])
def api_stream_track(track_id: str):
    """Stream audio file with Range support."""
    try:
        conn = get_connection(timeout=5.0)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT filepath FROM tracks WHERE track_id = ? AND status = 'active'",
            (track_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Track not found'}), 404
        
        filepath = Path(row[0])
        if not filepath.exists():
            return jsonify({'error': 'File not found on disk'}), 404

        MIME_MAP = {
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.aac': 'audio/aac',
            '.flac': 'audio/flac',
            '.ogg': 'audio/ogg',
            '.opus': 'audio/opus',
            '.wav': 'audio/wav',
            '.wma': 'audio/x-ms-wma',
        }
        mime = MIME_MAP.get(filepath.suffix.lower(), 'audio/mpeg')

        return send_from_directory(
            str(filepath.parent),
            filepath.name,
            conditional=True,
            mimetype=mime
        )
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/tracks/<track_id>/dossier', methods=['GET'])
def api_track_dossier(track_id: str):
    """Unified dossier endpoint for a track."""
    try:
        track = _load_track(track_id)
        if not track:
            return jsonify({'error': 'Track not found'}), 404

        structure = None
        if architect_engine:
            try:
                structure = architect_engine.get_structure(track_id)
            except Exception:
                structure = None

        connections = []
        if lore_engine and track.get('artist'):
            try:
                connections = lore_engine.get_artist_connections(track['artist'])
            except Exception:
                connections = []

        samples = []
        if dna_engine:
            try:
                samples = dna_engine.trace_samples(track_id)
            except Exception:
                samples = []

        fact = None
        if agent_engine:
            try:
                fact = agent_engine.fact_drop(track_id)
            except Exception:
                fact = None

        return jsonify({
            'track': track,
            'structure': structure,
            'lineage': connections,
            'samples': samples,
            'fact': fact,
            'provenance_notes': [
                track.get('filepath') or 'Track path unavailable',
                'Bundled dossier view assembled from Lyra back-end services.',
            ],
            'acquisition_notes': [
                'Playback and queue state are managed in the desktop client.',
            ],
        })
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# SPRINT 1: BIOGRAPHER, CONSTELLATION, ARTIST SHRINE
# ============================================================================


@app.route('/api/enrich/biographer', methods=['POST'])
def api_enrich_biographer():
    """Enrich a single artist with biographical context.

    Request body::

        { "artist_name": "Radiohead", "mbid": "optional-mbid", "force": false }

    Returns full biography dict from Biographer module.
    """
    data = request.get_json(silent=True) or {}
    artist_name = str(data.get("artist_name") or "").strip()
    if not artist_name:
        return jsonify({"error": "artist_name is required"}), 400

    mbid = str(data.get("mbid") or "").strip() or None
    force = bool(data.get("force", False))

    try:
        from oracle.enrichers.biographer import Biographer
        bio = Biographer()
        result = bio.enrich_artist(artist_name, mbid=mbid, force=force)
        if not result:
            return jsonify({"error": "no data found", "artist_name": artist_name}), 404
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/enrichment/biographer/<path:artist>', methods=['GET'])
def api_get_biographer_cached(artist: str):
    """Return cached biography for an artist, or trigger a fresh fetch.

    Query params:
        force=1  — bypass cache and re-fetch
    """
    artist_name = artist.strip()
    force = request.args.get("force", "0").strip() in {"1", "true", "yes"}

    try:
        from oracle.enrichers.biographer import Biographer
        bio = Biographer()
        result = bio.enrich_artist(artist_name, force=force)
        if not result:
            return jsonify({"error": "not found", "artist_name": artist_name}), 404
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/enrich/biographer/batch', methods=['POST'])
def api_enrich_biographer_batch():
    """Enrich all library artists with biographical context.

    Request body (optional)::

        { "limit": 50, "force": false }

    Returns processing stats dict.
    """
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", 0))
    force = bool(data.get("force", False))

    try:
        from oracle.enrichers.biographer import Biographer
        bio = Biographer()
        stats = bio.enrich_all_library_artists(limit=limit, force=force)
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/enrich/biographer/stale', methods=['POST'])
def api_enrich_biographer_stale():
    """Re-enrich only artists whose cache entry is missing or past the TTL.

    Use this instead of /batch for routine refreshes — it never re-fetches
    artists that were enriched recently, so it's cheap when most data is fresh.

    Request body (optional)::

        { "limit": 0, "ttl_days": 30 }

    ``ttl_days`` overrides the default 30-day window.  Set to 0 to re-enrich
    everything that is missing (never refetches fresh entries).

    Returns::

        {
          "ok": true,
          "stats": {
            "processed": 12,
            "skipped": 340,   // already fresh
            "failed": 0,
            "total_library": 352,
            "total_stale": 12
          }
        }
    """
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", 0))
    ttl_days = data.get("ttl_days")
    ttl_seconds = int(float(ttl_days) * 86400) if ttl_days is not None else None

    try:
        from oracle.enrichers.biographer import Biographer
        bio = Biographer()
        stats = bio.enrich_stale_artists(limit=limit, ttl_seconds=ttl_seconds)
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/artist/shrine/<path:artist>', methods=['GET'])
def api_artist_shrine(artist: str):
    """Get comprehensive artist profile for Artist Shrine view.

    Combines: biography, images, library stats, and relationship data.
    """
    artist_name = artist.strip()
    if not artist_name:
        return jsonify({"error": "artist required"}), 400

    try:
        conn = get_connection()
        c = conn.cursor()

        # Library stats
        c.execute(
            "SELECT COUNT(*), COUNT(DISTINCT album) FROM tracks WHERE artist = ? AND status = 'active'",
            (artist_name,),
        )
        row = c.fetchone()
        track_count = row[0] if row else 0
        album_count = row[1] if row else 0

        c.execute(
            "SELECT DISTINCT album, year FROM tracks WHERE artist = ? AND status = 'active' ORDER BY year",
            (artist_name,),
        )
        albums = [{"album": r[0], "year": r[1]} for r in c.fetchall() if r[0]]

        # Connections
        c.execute(
            "SELECT target, type, weight FROM connections WHERE source = ? ORDER BY weight DESC LIMIT 20",
            (artist_name,),
        )
        connections = [{"target": r[0], "type": r[1], "weight": r[2]} for r in c.fetchall()]

        # Credits (producers etc.)
        c.execute(
            "SELECT role, artist_name, COUNT(*) as cnt FROM track_credits tc "
            "JOIN tracks t ON tc.track_id = t.track_id "
            "WHERE t.artist = ? GROUP BY role, tc.artist_name ORDER BY cnt DESC LIMIT 20",
            (artist_name,),
        )
        credits_rows = [{"role": r[0], "name": r[1], "count": r[2]} for r in c.fetchall()]

        conn.close()

        # Biography (lazy fetch + cached)
        bio_data = {}
        try:
            from oracle.enrichers.biographer import Biographer
            bio = Biographer()
            bio_data = bio.enrich_artist(artist_name) or {}
        except Exception:
            pass

        return jsonify({
            "artist": artist_name,
            "library_stats": {
                "track_count": track_count,
                "album_count": album_count,
                "albums": albums,
            },
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


@app.route('/api/constellation', methods=['GET'])
def api_constellation():
    """Get artist connection graph for Constellation visualization.

    Query params:
        genre  — filter by genre tag (partial match)
        era    — filter by artist era substring
        type   — filter by connection type (e.g., 'member-of', 'collaborated-with')
        limit  — max nodes to return (default 200)
    """
    genre_filter = (request.args.get("genre") or "").strip().lower()
    era_filter = (request.args.get("era") or "").strip().lower()
    type_filter = (request.args.get("type") or "").strip().lower()
    limit = int(request.args.get("limit") or 200)

    try:
        conn = get_connection()
        c = conn.cursor()

        # Build edges from connections table
        params = []
        where_clauses = []
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

        # Build node set from edges
        node_set = set()
        for src, tgt, *_ in raw_edges:
            node_set.add(src)
            node_set.add(tgt)

        # Fetch in-library artists for styling
        c.execute("SELECT DISTINCT artist FROM tracks WHERE status = 'active'")
        in_library = {row[0] for row in c.fetchall()}

        # Batch-fetch biographer cache for all nodes in one query.
        # Compute lookup keys in Python (sha1 is not available in SQLite).
        from oracle.enrichers.cache import make_lookup_key
        import json as _json
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
                artist_name = key_to_artist.get(lk)
                if artist_name and pj:
                    try:
                        bio_by_artist[artist_name] = _json.loads(pj)
                    except Exception:
                        pass

        nodes = []
        for artist in node_list:
            bio = bio_by_artist.get(artist, {})
            node: dict = {
                "id": artist,
                "label": artist,
                "inLibrary": artist in in_library,
            }
            if bio.get("genres"):
                node["genres"] = bio["genres"][:3]
            if bio.get("era"):
                node["era"] = bio["era"]
            if bio.get("origin"):
                node["origin"] = bio["origin"]
            if bio.get("lastfm_listeners"):
                node["listeners"] = bio["lastfm_listeners"]
            nodes.append(node)

            # Apply genre / era filters (post-fetch, since data lives in JSON)
            if genre_filter and not any(
                genre_filter in g.lower() for g in (bio.get("genres") or [])
            ):
                nodes.pop()
                continue
            if era_filter and era_filter not in (bio.get("era") or "").lower():
                nodes.pop()
                continue

        edges = [
            {"source": r[0], "target": r[1], "type": r[2] or "related", "weight": r[3] or 0.5}
            for r in raw_edges
        ]

        conn.close()
        return jsonify({
            "nodes": nodes,
            "edges": edges,
            "total_edges": len(edges),
            "total_nodes": len(nodes),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/constellation/filters', methods=['GET'])
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


@app.route('/api/graph/build', methods=['POST'])
def api_graph_build():
    """Trigger relationship graph build.

    Request body::

        { "full": false, "depth": 1 }

    full=false (default) runs incremental build (new artists only).
    full=true runs full rebuild (all artists — slow).
    """
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


@app.route('/api/graph/stats', methods=['GET'])
def api_graph_stats():
    """Return graph builder statistics."""
    try:
        from oracle.graph_builder import GraphBuilder
        gb = GraphBuilder()
        return jsonify(gb.get_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ============================================================================
# SPRINT 2 -- DEEP CUT PROTOCOL (F-004)
# ============================================================================


@app.route('/api/deep-cut/hunt', methods=['POST'])
def api_deep_cut_hunt():
    """
    Hunt for acclaimed-but-obscure tracks in the local library.

    Request body (JSON)::

        {
            "genre": "shoegaze",          // optional genre filter
            "artist": "Slowdive",         // optional artist filter
            "min_obscurity": 0.6,         // 0.0–2.0, default 0.6
            "max_obscurity": 10.0,        // upper cap, default 10.0
            "min_acclaim": 0.0,           // 0.0–1.0, default 0.0
            "limit": 20                   // max results, default 20
        }

    Response::

        {
            "count": int,
            "results": [
                {
                    "track_id", "artist", "title", "album", "genre",
                    "obscurity_score", "acclaim_score", "popularity_percentile",
                    "lastfm_listeners", "discogs_rating", "tags"
                }, ...
            ]
        }
    """
    try:
        from oracle.deepcut import DeepCut
        body = request.get_json(silent=True) or {}
        dc = DeepCut()
        results = dc.hunt_by_obscurity(
            genre=body.get("genre"),
            artist=body.get("artist"),
            min_obscurity=float(body.get("min_obscurity", 0.6)),
            max_obscurity=float(body.get("max_obscurity", 10.0)),
            min_acclaim=float(body.get("min_acclaim", 0.0)),
            limit=int(body.get("limit", 20)),
        )
        return jsonify({"count": len(results), "results": results})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/deep-cut/stats', methods=['GET'])
def api_deep_cut_stats():
    """Return deep cut potential statistics for the library."""
    try:
        from oracle.deepcut import DeepCut
        dc = DeepCut()
        return jsonify(dc.get_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/deep-cut/taste', methods=['POST'])
def api_deep_cut_taste():
    """
    Hunt for deep cuts that align with a provided taste profile.

    Request body::

        {
            "taste_profile": {
                "energy": 0.7, "valence": 0.6, "tension": 0.3,
                "density": 0.4, "warmth": 0.8, "movement": 0.5,
                "space": 0.6, "rawness": 0.4, "complexity": 0.5,
                "nostalgia": 0.7
            },
            "limit": 20
        }

    Returns tracks sorted by a blended rank (obscurity * 0.6 + taste_alignment * 0.4).
    """
    try:
        from oracle.deepcut import DeepCut
        body = request.get_json(silent=True) or {}
        taste = body.get("taste_profile", {})
        if not taste:
            return jsonify({"error": "taste_profile is required"}), 400
        dc = DeepCut()
        results = dc.hunt_with_taste_context(
            taste_profile=taste,
            limit=int(body.get("limit", 20)),
        )
        return jsonify({"count": len(results), "results": results})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ============================================================================
# SPRINT 2 -- PLAYLUST 4-ACT ARC GENERATOR (F-008)
# ============================================================================


@app.route('/api/playlust/generate', methods=['POST'])
def api_playlust_generate():
    """
    Generate a 4-act Playlust emotional arc playlist (F-008 — FLAGSHIP).

    Request body::

        {
            "mood": "volcanic shoegaze fever dream",
            "duration_minutes": 60,
            "name": "Late Night Ritual",
            "use_deepcut": true,
            "taste_profile": {
                "energy": 0.7, "valence": 0.5, ...
            }
        }

    Response::

        {
            "run_uuid": str,
            "track_count": int,
            "narrative": str,
            "acts": [
                {
                    "act": str, "label": str,
                    "tracks": [{"rank", "artist", "title", "score", "reasons"}, ...]
                }, ...
            ],
            "tracks": [{"rank", "artist", "title", "score", "reasons"}, ...]
        }
    """
    try:
        from oracle.playlust import Playlust
        body = request.get_json(silent=True) or {}

        pl = Playlust()
        run = pl.generate(
            mood=body.get("mood"),
            duration_minutes=int(body.get("duration_minutes", 60)),
            name=body.get("name"),
            taste_context=body.get("taste_profile"),
            use_deepcut=bool(body.get("use_deepcut", True)),
        )

        # Serialise run
        tracks = [
            {
                "rank": t.rank,
                "path": t.path,
                "artist": t.artist,
                "title": t.title,
                "score": t.global_score,
                "reasons": [r.dict() for r in t.reasons],
            }
            for t in run.tracks
        ]

        # Group into acts for the response
        acts_map: dict = {}
        for t in tracks:
            act_reason = next((r for r in t["reasons"] if r["type"].startswith("act:")), None)
            act_key = act_reason["type"].replace("act:", "") if act_reason else "unknown"
            acts_map.setdefault(act_key, []).append(t)

        act_order = ["aggressive", "seductive", "breakdown", "sublime"]
        acts_out = [
            {"act": a, "tracks": acts_map.get(a, [])}
            for a in act_order
        ]

        return jsonify({
            "run_uuid": run.uuid,
            "track_count": len(tracks),
            "narrative": run.prompt,
            "acts": acts_out,
            "tracks": tracks,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/playlust/acts', methods=['GET'])
def api_playlust_acts():
    """Return the four act definitions and their target dimensional profiles."""
    try:
        from oracle.playlust import Playlust
        pl = Playlust()
        return jsonify({"acts": pl.get_act_definitions()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ============================================================================
# SPRINT 2 -- PLAYFAUX BEEFWEB BRIDGE STATUS (F-013)
# ============================================================================


@app.route('/api/listen/status', methods=['GET'])
def api_listen_status():
    """
    Check BeefWeb connectivity and return current playback state.

    Response::

        {
            "connected": bool,
            "now_playing": {
                "artist": str, "title": str, "album": str,
                "position": float, "duration": float, "state": str
            } | null
        }
    """
    try:
        from oracle.integrations.beefweb_bridge import BeefWebBridge
        import os as _os
        host = _os.getenv("BEEFWEB_HOST", "localhost")
        port = int(_os.getenv("BEEFWEB_PORT", "8880"))
        bridge = BeefWebBridge(host=host, port=port)
        connected = bridge.check_connection()
        now_playing = bridge.get_current_track() if connected else None
        return jsonify({
            "connected": connected,
            "now_playing": now_playing,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/listen/now-playing', methods=['GET'])
def api_listen_now_playing():
    """Return only the currently playing track info (lightweight poll endpoint)."""
    try:
        from oracle.integrations.beefweb_bridge import BeefWebBridge
        import os as _os
        host = _os.getenv("BEEFWEB_HOST", "localhost")
        port = int(_os.getenv("BEEFWEB_PORT", "8880"))
        bridge = BeefWebBridge(host=host, port=port)
        track = bridge.get_current_track()
        if not track or track.get("state") == "stopped":
            return jsonify({"state": "stopped", "track": None})
        return jsonify({"state": track["state"], "track": track})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ============================================================================
# ROOT ROUTE
# ============================================================================


@app.route('/')
def index():
    """API root."""
    return jsonify({
        'service': 'lyra-oracle',
        'status': 'ok',
        'version': VERSION,
        'message': 'UI removed; use API endpoints under /api/*'
    })


# ============================================================================
# MAIN
# ============================================================================

def _schedule_startup_jobs() -> None:
    """Kick off lightweight background jobs when the server boots.

    Checks for empty/sparse tables and fills them without blocking startup:
      - Taste profile: seed from library scores if never had real playback
      - Artist graph: run incremental build if connections table is empty
      - Biographer: enrich up to 50 new/stale artists if cache is empty
    """
    import threading

    def _run():
        import time as _time
        _time.sleep(3)  # let Flask settle before hitting SQLite
        try:
            from oracle.db.schema import get_connection as _gc
            _conn = _gc()
            _c = _conn.cursor()

            # 1. Taste seed
            _c.execute("SELECT COUNT(*) FROM playback_history")
            playback_count = _c.fetchone()[0] or 0
            _c.execute("SELECT COUNT(*) FROM track_scores WHERE energy IS NOT NULL")
            scored_count = _c.fetchone()[0] or 0
            _c.execute("SELECT MAX(confidence) FROM taste_profile")
            max_conf = _c.fetchone()[0] or 0

            if scored_count > 0 and (playback_count == 0 or float(max_conf) < 0.5):
                _conn.close()
                try:
                    from oracle.taste import seed_taste_from_library
                    res = seed_taste_from_library()
                    print(f"[startup] Taste seeded from library: {len(res.get('seeded', []))} dimensions")
                except Exception as _e:
                    print(f"[startup] Taste seed error: {_e}")
            else:
                _conn.close()

            # 2. Artist graph (incremental)
            _conn2 = _gc()
            _c2 = _conn2.cursor()
            _c2.execute("SELECT COUNT(*) FROM connections")
            conn_count = _c2.fetchone()[0] or 0
            _conn2.close()

            if conn_count == 0:
                print("[startup] connections=0 — scheduling incremental graph build...")
                try:
                    from oracle.graph_builder import GraphBuilder
                    added = GraphBuilder().build_incremental()
                    print(f"[startup] Graph build complete: {added} edges added")
                except Exception as _e:
                    print(f"[startup] Graph build error: {_e}")

            # 3. Biographer (first 50 stale artists)
            _conn3 = _gc()
            _c3 = _conn3.cursor()
            _c3.execute("SELECT COUNT(*) FROM enrich_cache WHERE provider='biographer'")
            bio_count = _c3.fetchone()[0] or 0
            _conn3.close()

            if bio_count < 10:
                print(f"[startup] biographer_cache={bio_count} — enriching first 50 artists...")
                try:
                    from oracle.enrichers.biographer import Biographer
                    stats = Biographer().enrich_stale_artists(limit=50)
                    print(f"[startup] Biographer: {stats['processed']} enriched, {stats['failed']} failed")
                except Exception as _e:
                    print(f"[startup] Biographer error: {_e}")

        except Exception as _outer:
            print(f"[startup] auto-init error: {_outer}")

    t = threading.Thread(target=_run, name="lyra-startup-init", daemon=True)
    t.start()


def main():
    """Start Flask server."""
    if os.getenv("LYRA_BOOTSTRAP", "1").strip().lower() not in {"0", "false", "no"}:
        try:
            from oracle.bootstrap import bootstrap_runtime
            result = bootstrap_runtime(timeout_seconds=int(os.getenv("LYRA_BOOTSTRAP_TIMEOUT", "40")))
            docker = result.get("docker", {})
            llm = result.get("llm", {})
            print(f"[bootstrap] docker: {'ready' if docker.get('ready') else 'not ready'}")
            if docker.get("error"):
                print(f"[bootstrap] docker detail: {docker.get('error')}")
            print(f"[bootstrap] lm studio: {'ready' if llm.get('ready') else 'not ready'}")
            if llm.get("error"):
                print(f"[bootstrap] lm detail: {llm.get('error')}")
        except Exception as exc:
            print(f"[bootstrap] warning: {exc}")

    print("\n" + "="*60)
    print("LYRA ORACLE API SERVER")
    print("="*60)
    print(f"Version: {VERSION}")
    print(f"Write Mode: {get_write_mode()}")
    print(f"\nStarting server at http://localhost:5000")
    print("="*60 + "\n")

    # --- Background auto-init: seed sparse data on first run ---
    _schedule_startup_jobs()
    
    debug_value = os.getenv("LYRA_DEBUG", "").strip().lower()
    if not debug_value:
        debug_value = os.getenv("FLASK_DEBUG", "").strip().lower()
    debug_enabled = debug_value in {"1", "true", "yes"}

    app.run(host='0.0.0.0', port=5000, debug=debug_enabled)


if __name__ == '__main__':
    main()

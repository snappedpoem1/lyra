"""Lyra Oracle Flask API server."""

from __future__ import annotations

from pathlib import Path
import os
from typing import Dict, List
import json
import traceback

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv(override=True)

PROJECT_ROOT = Path(__file__).resolve().parent
hf_home = str(PROJECT_ROOT / "hf_cache")
os.environ.setdefault("HF_HOME", hf_home)
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(hf_home) / "hub"))

from oracle.db.schema import get_connection, get_write_mode
from oracle.config import LIBRARY_BASE
from oracle.search import search
from oracle.scanner import scan_library
from oracle.indexer import index_library
from oracle.vibes import save_vibe, list_vibes, build_vibe, materialize_vibe, refresh_vibes, delete_vibe
from oracle.curator import generate_plan, apply_plan
from oracle.classifier import classify_library
from oracle.acquirers.ytdlp import YTDLPAcquirer
from oracle.acquisition import enqueue_url, process_queue
from oracle.download_processor import list_downloads, process_downloads
from oracle.validation import (
    validate_search_request,
    validate_vibe_save_request,
    validate_vibe_materialize_request,
    validate_name,
    validate_url,
    validate_path,
    validate_count,
    validate_boolean,
    validate_confidence,
    sanitize_integer,
)
# Intelligence layer — wrapped in try/except so server starts even if subsystems fail
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
    from oracle.llm import get_llm_status
except Exception as _e:
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
CORS(app)

VERSION = "1.0.0"


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
    return {
        'status': 'ok',
        'ok': True,
        'service': 'lyra-oracle',
        'version': VERSION,
        'write_mode': get_write_mode(),
        'llm': get_llm_status()
    }


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
        'write_mode': get_write_mode()
    })


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
        
        results = search(sanitized['query'], n=sanitized['n'])
        return jsonify({'results': results, 'count': len(results)})
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/search/hybrid', methods=['POST'])
def api_search_hybrid():
    """Hybrid search: semantic + metadata filters + dimensional ranges."""
    try:
        from oracle.search import hybrid_search

        data = request.get_json() or {}
        query = (data.get('query') or '').strip() or None
        filters = data.get('filters') or {}
        dimension_ranges = data.get('dimension_ranges') or data.get('dimensions') or {}
        sort_by = data.get('sort_by') or data.get('sort') or 'relevance'
        top_k = int(data.get('top_k') or data.get('limit') or 20)

        if not query and not filters:
            return jsonify({'error': 'query or filters required'}), 400

        results = hybrid_search(
            query=query,
            filters=filters,
            dimension_ranges=dimension_ranges,
            sort_by=sort_by,
            top_k=top_k,
        )
        return jsonify({'results': results, 'count': len(results)})

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
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/library/tracks', methods=['GET'])
def api_tracks():
    """Get list of tracks."""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT track_id, artist, title, album, year, version_type, confidence
            FROM tracks
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        rows = cursor.fetchall()
        conn.close()
        
        tracks = []
        for row in rows:
            tracks.append({
                'track_id': row[0],
                'artist': row[1],
                'title': row[2],
                'album': row[3],
                'year': row[4],
                'version_type': row[5],
                'confidence': row[6]
            })
        
        return jsonify({'tracks': tracks, 'count': len(tracks)})
    
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
        limit = data.get('limit', 0)
        
        results = classify_library(limit=limit)
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
        
        return jsonify({'result': result or 'Download failed'})
    
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
        results = process_queue()
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ---------------------------------------------------------------------------
# Batch Acquisition (parallel fast_batch with SSE progress)
# ---------------------------------------------------------------------------
import threading
import queue as _queue
import time as _time
import uuid as _uuid

_batch_jobs: Dict[str, dict] = {}   # job_id → {status, progress, results, ...}
_batch_queues: Dict[str, _queue.Queue] = {}  # job_id → SSE event queue


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
    """Find Spotify favorites not in local library — acquisition candidates."""
    try:
        from oracle.spotify_import import SpotifyImporter
        from pathlib import Path
        min_plays = int(request.args.get('min_plays', 5))
        limit = int(request.args.get('limit', 100))
        importer = SpotifyImporter(
            db_path=Path(os.getenv("LYRA_DB_PATH", "lyra_registry.db")),
            data_dir=Path("data/spotify")
        )
        missing = importer.find_missing_tracks(min_plays=min_plays, limit=limit)
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
        from oracle.spotify_import import SpotifyImporter
        from pathlib import Path
        importer = SpotifyImporter(
            db_path=Path(os.getenv("LYRA_DB_PATH", "lyra_registry.db")),
            data_dir=Path("data/spotify")
        )
        stats = importer.get_stats()
        top_artists = importer.get_top_artists(limit=25)
        stats['top_artists'] = [
            {'name': r[0], 'score': r[1], 'plays': r[2], 'total_ms': r[3]}
            for r in top_artists
        ]
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
            return jsonify({'error': 'Lore engine not available — check server logs'}), 503

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
            return jsonify({'error': 'Lore engine not available — check server logs'}), 503

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
            return jsonify({'error': 'Radio engine not available — check server logs'}), 503

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
            return jsonify({'error': 'Radio engine not available — check server logs'}), 503

        data = request.get_json() or {}
        track_id = (data.get('track_id') or '').strip()
        count = int(data.get('count', 1))

        if not track_id:
            return jsonify({'error': 'track_id is required'}), 400

        results = radio_engine.get_flow_track(track_id, count=count)
        return jsonify({'results': results, 'count': len(results)})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/radio/discovery', methods=['GET'])
def api_radio_discovery():
    """Get discovery mode recommendations."""
    try:
        if not radio_engine:
            return jsonify({'error': 'Radio engine not available — check server logs'}), 503

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
        data = request.get_json() or {}
        track_id = (data.get('track_id') or '').strip()
        context = (data.get('context') or 'manual').strip()
        skipped = bool(data.get('skipped', False))
        completion_rate = float(data.get('completion_rate', 1.0))
        rating = data.get('rating')

        if not track_id:
            return jsonify({'error': 'track_id is required'}), 400

        radio_engine.record_playback(
            track_id=track_id,
            context=context,
            skipped=skipped,
            completion_rate=completion_rate,
            rating=rating
        )
        return jsonify({'status': 'ok'})

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


# ============================================================================
# AGENT (LYRA)
# ============================================================================

@app.route('/api/agent/query', methods=['POST'])
def api_agent_query():
    """Query Lyra agent for orchestration."""
    try:
        data = request.get_json() or {}
        text = (data.get('text') or '').strip()
        context = data.get('context') or {}

        if not text:
            return jsonify({'error': 'text is required'}), 400

        result = agent_engine.run_agent(text, context=context)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/agent/fact-drop', methods=['GET'])
def api_agent_fact_drop():
    """Get a fact drop for a track."""
    try:
        track_id = (request.args.get('track_id') or '').strip()
        if not track_id:
            return jsonify({'error': 'track_id is required'}), 400

        fact = agent_engine.fact_drop(track_id)
        return jsonify({'track_id': track_id, 'fact': fact})

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
    
    debug_value = os.getenv("LYRA_DEBUG", "").strip().lower()
    if not debug_value:
        debug_value = os.getenv("FLASK_DEBUG", "").strip().lower()
    debug_enabled = debug_value in {"1", "true", "yes"}

    app.run(host='0.0.0.0', port=5000, debug=debug_enabled)


if __name__ == '__main__':
    main()

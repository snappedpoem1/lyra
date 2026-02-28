"""Unified CLI for Lyra Oracle."""

from __future__ import annotations

import asyncio
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from oracle.config import LIBRARY_BASE
from oracle.db.schema import migrate, get_write_mode


def _print_json_safe(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=True, default=str)
    print(text)


def main() -> None:
    # Ensure UTF-8 output on Windows (avoids UnicodeEncodeError with emoji/special chars)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    load_dotenv(override=True)

    parser = argparse.ArgumentParser(prog="oracle", description="Lyra Oracle CLI")
    subparsers = parser.add_subparsers(dest="command")

    db_parser = subparsers.add_parser("db", help="Database operations")
    db_sub = db_parser.add_subparsers(dest="db_command")
    db_sub.add_parser("migrate", help="Create or update database schema")

    subparsers.add_parser("doctor", help="Run system diagnostics")
    subparsers.add_parser("audit", help="Run database audit â€” row counts and health check")
    subparsers.add_parser("status", help="Quick status check â€” row counts and system state")

    ops_parser = subparsers.add_parser("ops", help="Operational run sequence + markdown report")
    ops_sub = ops_parser.add_subparsers(dest="ops_command")
    ops_iterate = ops_sub.add_parser("iterate", help="Run best-order ops cycle and write a report")
    ops_iterate.add_argument("--no-bootstrap", action="store_true", help="Skip Docker/LM Studio bootstrap")
    ops_iterate.add_argument("--apply-validation", action="store_true", help="Apply validation metadata fixes")
    ops_iterate.add_argument("--validation-limit", type=int, default=0, help="Limit tracks during validation")
    ops_iterate.add_argument("--validation-workers", type=int, default=0, help="Validation workers (0=auto)")
    ops_iterate.add_argument("--validation-confidence", type=float, default=0.7, help="Validation confidence threshold")
    ops_iterate.add_argument("--drain-limit", type=int, default=0, help="Canary drain size (0=skip)")
    ops_iterate.add_argument("--watch-once", action="store_true", help="Run one ingest watcher sweep after drain")
    ops_iterate.add_argument("--report", help="Markdown report output path")

    scan_parser = subparsers.add_parser("scan", help="Scan a library for tracks")
    scan_parser.add_argument(
        "--library",
        required=True,
        help="Library path (use a real path, e.g. A:\\music\\Active Music; avoid placeholder examples)",
    )
    scan_parser.add_argument("--limit", type=int, default=0, help="Limit files")

    index_parser = subparsers.add_parser("index", help="Index embeddings")
    index_parser.add_argument("--library", help="Library path scope")
    index_parser.add_argument("--limit", type=int, default=0, help="Limit tracks")
    index_parser.add_argument("--force-reindex", action="store_true", help="Force reindex")
    index_parser.add_argument("--no-score", action="store_true", help="Skip auto-scoring after indexing")
    index_parser.add_argument("--workers", type=int, default=0, help="Index workers (0=auto by profile)")
    index_parser.add_argument("--embed-batch", type=int, default=0, help="Embedding batch size (0=auto by profile)")

    search_parser = subparsers.add_parser("search", help="Semantic search")
    search_parser.add_argument("--query", required=True, help="Search query")
    search_parser.add_argument("--n", type=int, default=10, help="Number of results")
    search_parser.add_argument(
        "--nl", action="store_true",
        help="Natural language mode: LM Studio rewrites query for better CLAP matching"
    )

    pipeline_parser = subparsers.add_parser("pipeline", help="Scan + index + score pipeline")
    pipeline_parser.add_argument("--library", required=True, help="Library path")
    pipeline_parser.add_argument("--limit", type=int, default=0, help="Limit tracks")
    pipeline_parser.add_argument("--force-reindex", action="store_true", help="Force reindex")
    pipeline_parser.add_argument("--no-score", action="store_true", help="Skip auto-scoring")

    hunt_parser = subparsers.add_parser("hunt", help="Compatibility hunt command routed to converged pipeline")
    hunt_parser.add_argument("query", nargs="+", help='Query text, e.g. "Artist - Title"')

    acquire_parser = subparsers.add_parser("acquire", help="Acquire media")
    acquire_sub = acquire_parser.add_subparsers(dest="acquire_command")
    acquire_youtube = acquire_sub.add_parser("youtube", help="Download from YouTube")
    acquire_youtube.add_argument("--url", required=True, help="Video URL")
    acquire_search = acquire_sub.add_parser("search", help="Search via Prowlarr")
    acquire_search.add_argument("--query", required=True, help="Search query")
    acquire_search.add_argument("--source", default="prowlarr", help="Source (prowlarr)")
    acquire_search.add_argument("--limit", type=int, default=5, help="Limit results")
    acquire_lyra = acquire_sub.add_parser("lyra", help="Run Lyra Protocol swarm acquisition")
    acquire_lyra.add_argument("--artist", required=True, help="Artist name")
    acquire_lyra.add_argument("--title", required=True, help="Track title")
    acquire_waterfall = acquire_sub.add_parser("waterfall", help="Run full acquisition waterfall (T1-T4)")
    acquire_waterfall.add_argument("--artist", required=True, help="Artist name")
    acquire_waterfall.add_argument("--title", required=True, help="Track title")
    acquire_waterfall.add_argument("--album", help="Album name (helps T1 search)")
    acquire_waterfall.add_argument("--max-tier", type=int, default=4, help="Stop after tier N (1-4)")

    enrich_parser = subparsers.add_parser("enrich", help="Enrich track metadata")
    enrich_parser.add_argument("--track-id", required=True, help="Track ID to enrich")
    enrich_parser.add_argument("--providers", default="musicbrainz,acoustid,discogs", help="Comma list")

    curate_parser = subparsers.add_parser("curate", help="Curation operations")
    curate_sub = curate_parser.add_subparsers(dest="curate_command")
    
    curate_classify = curate_sub.add_parser("classify", help="Classify all tracks")
    curate_classify.add_argument("--limit", type=int, default=0, help="Limit tracks")
    curate_classify.add_argument(
        "--llm", action="store_true",
        help="Use LM Studio as a second pass for regex-ambiguous tracks (requires LM Studio running)"
    )
    
    curate_plan = curate_sub.add_parser("plan", help="Generate curation plan")
    curate_plan.add_argument("--preset", default="artist_album", help="Organization preset")
    curate_plan.add_argument("--limit", type=int, default=0, help="Limit tracks")
    curate_plan.add_argument("--out", default="Reports", help="Output directory")
    curate_plan.add_argument("--classify-first", action="store_true", help="Run classifier first")
    
    curate_apply = curate_sub.add_parser("apply", help="Apply curation plan")
    curate_apply.add_argument("--plan", required=True, help="Plan JSON file path")
    curate_apply.add_argument("--confidence-min", type=float, default=0.5, help="Min confidence")
    curate_apply.add_argument("--dry-run", action="store_true", help="Don't actually move files")
    
    curate_undo = curate_sub.add_parser("undo", help="Undo plan")
    curate_undo.add_argument("--journal", required=True, help="Journal JSON file path")
    curate_undo.add_argument("--dry-run", action="store_true", help="Don't actually move files")

    downloads_parser = subparsers.add_parser("downloads", help="Manage downloads folder")
    downloads_sub = downloads_parser.add_subparsers(dest="downloads_command")
    
    downloads_list = downloads_sub.add_parser("list", help="List downloads")
    downloads_list.add_argument("--show-metadata", action="store_true", help="Show metadata preview")
    
    downloads_clean = downloads_sub.add_parser("clean", help="Clean filenames in downloads")
    downloads_clean.add_argument("--dry-run", action="store_true", help="Preview only")
    
    downloads_organize = downloads_sub.add_parser("organize", help="Organize downloads into library")
    downloads_organize.add_argument("--library", default=str(LIBRARY_BASE), help="Library path")
    downloads_organize.add_argument("--no-clean", action="store_true", help="Don't clean names")
    downloads_organize.add_argument("--no-scan", action="store_true", help="Don't scan after")
    downloads_organize.add_argument("--dry-run", action="store_true", help="Preview only")

    vibe_parser = subparsers.add_parser("vibe", help="Vibe playlist management")
    vibe_sub = vibe_parser.add_subparsers(dest="vibe_command")
    
    vibe_save = vibe_sub.add_parser("save", help="Save a vibe from semantic search")
    vibe_save.add_argument("--name", required=True, help="Vibe name")
    vibe_save.add_argument("--query", required=True, help="Semantic search query")
    vibe_save.add_argument("--n", type=int, default=200, help="Number of tracks")
    
    vibe_sub.add_parser("list", help="List all vibes")
    
    vibe_build = vibe_sub.add_parser("build", help="Build M3U8 playlist for vibe")
    vibe_build.add_argument("--name", required=True, help="Vibe name")
    
    vibe_materialize = vibe_sub.add_parser("materialize", help="Materialize vibe as folder")
    vibe_materialize.add_argument("--name", required=True, help="Vibe name")
    vibe_materialize.add_argument("--mode", default="hardlink", choices=["hardlink", "symlink", "shortcut"], help="Link mode")
    
    vibe_refresh = vibe_sub.add_parser("refresh", help="Refresh vibe(s)")
    vibe_refresh.add_argument("--name", help="Specific vibe name (all if omitted)")
    vibe_refresh.add_argument("--all", action="store_true", help="Refresh all vibes")
    
    vibe_delete = vibe_sub.add_parser("delete", help="Delete a vibe")
    vibe_delete.add_argument("--name", required=True, help="Vibe name")
    vibe_delete.add_argument("--delete-folder", action="store_true", help="Also delete materialized folder")

    serve_parser = subparsers.add_parser("serve", help="Start Flask API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host address")
    serve_parser.add_argument("--port", type=int, default=5000, help="Port number")
    serve_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    serve_parser.add_argument("--no-bootstrap", action="store_true", help="Skip Docker/LM Studio startup bootstrap")
    serve_parser.add_argument("--bootstrap-timeout", type=int, default=40, help="Bootstrap timeout seconds")

    score_parser = subparsers.add_parser('score', help='Score library tracks on 10 emotional dimensions')
    score_parser.add_argument('--all', action='store_true', help='Score all active tracks')
    score_parser.add_argument('--limit', type=int, default=0, help='Limit tracks to score (0=all)')
    score_parser.add_argument('--force', action='store_true', help='Rescore already-scored tracks')
    score_parser.add_argument('--workers', type=int, default=0, help='Score worker threads (0=auto by profile)')

    # Library maintenance commands
    normalize_parser = subparsers.add_parser('normalize', help='Normalize artist/title metadata across library')
    normalize_parser.add_argument('--apply', action='store_true', help='Apply changes (default: preview only)')

    validate_parser = subparsers.add_parser('validate', help='Validate library against Discogs/MusicBrainz')
    validate_parser.add_argument('--limit', type=int, default=0, help='Limit tracks to validate')
    validate_parser.add_argument('--apply', action='store_true', help='Apply fixes')
    validate_parser.add_argument('--workers', type=int, default=0, help='Validation worker threads (0=auto)')
    validate_parser.add_argument('--confidence', type=float, default=0.7, help='Min validation confidence (0-1)')
    validate_parser.add_argument('--full-scan', action='store_true', help='Force full validation scan, including already white-gloved tracks')

    enrich_all_parser = subparsers.add_parser('enrich-all', help='Enrich all tracks with genre/metadata from Last.fm')
    enrich_all_parser.add_argument('--limit', type=int, default=0, help='Limit tracks')

    # Smart acquisition
    smart_acquire_parser = subparsers.add_parser('smart-acquire', help='Smart acquisition with validation')
    smart_acquire_parser.add_argument('--artist', help='Artist name')
    smart_acquire_parser.add_argument('--title', help='Track title')
    smart_acquire_parser.add_argument('--album', help='Album name')
    smart_acquire_parser.add_argument('--queue', action='store_true', help='Process acquisition queue')
    smart_acquire_parser.add_argument('--limit', type=int, default=10, help='Queue limit')
    smart_acquire_parser.add_argument('--no-validate', action='store_true', help='Skip validation')

    # Guard commands
    guard_parser = subparsers.add_parser('guard', help='Acquisition guard operations')
    guard_sub = guard_parser.add_subparsers(dest='guard_command')
    
    guard_test = guard_sub.add_parser('test', help='Test if track would be allowed')
    guard_test.add_argument('--artist', required=True, help='Artist name')
    guard_test.add_argument('--title', required=True, help='Track title')
    
    guard_scan = guard_sub.add_parser('scan', help='Scan folder for junk')
    guard_scan.add_argument('--folder', default='downloads', help='Folder to scan')
    
    guard_import = guard_sub.add_parser('import', help='Import downloads with guard protection')
    guard_import.add_argument('--downloads', default='downloads', help='Downloads folder')
    guard_import.add_argument('--library', help='Library folder (default: LIBRARY_BASE)')
    guard_import.add_argument('--dry-run', action='store_true', help='Preview only')
    guard_import.add_argument('--delete-rejected', action='store_true', help='Delete rejected files')
    
    guard_audit = guard_sub.add_parser('audit', help='Audit library for junk')
    guard_audit.add_argument('--library', help='Library folder')
    
    guard_quarantine = guard_sub.add_parser('quarantine', help='Quarantine junk from library')
    guard_quarantine.add_argument('--library', help='Library folder')
    guard_quarantine.add_argument('--dry-run', action='store_true', help='Preview only')

    # Prowlarr helpers
    prowlarr_parser = subparsers.add_parser("prowlarr", help="Prowlarr setup helpers")
    prowlarr_sub = prowlarr_parser.add_subparsers(dest="prowlarr_command")
    prowlarr_rutracker = prowlarr_sub.add_parser("setup-rutracker", help="Create or update RuTracker indexer credentials")
    prowlarr_rutracker.add_argument("--username", required=True, help="RuTracker username")
    prowlarr_rutracker.add_argument("--password", required=True, help="RuTracker password")

    # Catalog-first acquisition (MusicBrainz-verified discography)
    catalog_parser = subparsers.add_parser('catalog', help='Verified catalog acquisition from MusicBrainz')
    catalog_sub = catalog_parser.add_subparsers(dest='catalog_command')

    catalog_lookup = catalog_sub.add_parser('lookup', help='Look up artist discography')
    catalog_lookup.add_argument('artist', help='Artist name')
    catalog_lookup.add_argument('--types', default='album,ep', help='Release types: album,ep,single')

    catalog_acquire = catalog_sub.add_parser('acquire', help='Acquire verified catalog via Real-Debrid')
    catalog_acquire.add_argument('artist', help='Artist name')
    catalog_acquire.add_argument('--types', default='album,ep', help='Release types: album,ep,single')
    catalog_acquire.add_argument('--limit', type=int, default=0, help='Limit number of releases to acquire')
    catalog_acquire.add_argument('--dry-run', action='store_true', help='Show plan without downloading')
    catalog_acquire.add_argument('--max-gb', type=float, default=5.0, help='Max torrent size in GB (default: 5)')
    catalog_acquire.add_argument('--download-wait', type=int, default=120, help='Max seconds to wait for RD download completion')
    catalog_acquire.add_argument('--select-wait', type=int, default=15, help='Max seconds to wait for RD file selection state')
    catalog_acquire.add_argument('--poll-interval', type=int, default=3, help='Seconds between RD status polls')
    catalog_acquire.add_argument('--no-replace', action='store_true', help='Do not replace existing tracks with HQ full-album files')

    catalog_status_cmd = catalog_sub.add_parser('status', help='Show catalog acquisition status')
    catalog_status_cmd.add_argument('--artist', help='Filter by artist')

    # Ingest watcher
    watch_parser = subparsers.add_parser("watch", help="Watch downloads/ and auto-ingest new audio files")
    watch_parser.add_argument("--once", action="store_true", help="Process existing files and exit")

    import_parser = subparsers.add_parser(
        "import", help="Import audio files via beets (auto-tag + organize + scan)"
    )
    import_parser.add_argument(
        "--source", default="staging",
        help="Source: 'staging', 'downloads', or an absolute path (default: staging)",
    )
    import_parser.add_argument("--dry-run", action="store_true", help="Preview without moving files")
    import_parser.add_argument("--no-autotag", action="store_true", help="Skip MusicBrainz lookup")
    import_parser.add_argument("--singletons", action="store_true", help="Import as non-album tracks")
    import_parser.add_argument("--copy", action="store_true", help="Copy instead of move")

    # Playback signal â€” log plays/skips for taste learning without the server
    played_parser = subparsers.add_parser(
        "played", help="Log a playback signal for taste learning"
    )
    played_parser.add_argument("--artist", required=True, help="Track artist")
    played_parser.add_argument("--title", required=True, help="Track title")
    played_parser.add_argument("--skipped", action="store_true", help="Track was skipped (negative signal)")
    played_parser.add_argument("--weight", type=float, default=1.0, help="Signal weight (default 1.0)")

    # Queue drain
    drain_parser = subparsers.add_parser("drain", help="Drain acquisition queue via guarded waterfall (T1-T4)")
    drain_parser.add_argument("--limit", type=int, default=10, help="Number of tracks to acquire")
    drain_parser.add_argument("--artist", help="Filter by artist")
    drain_parser.add_argument("--max-tier", type=int, default=4, help="Max acquisition tier (1=Qobuz, 2=Slskd, 3=RD, 4=SpotDL)")
    drain_parser.add_argument("--workers", type=int, default=0, help="Parallel download workers (0=auto)")
    drain_parser.add_argument("--max-retries", type=int, default=3, help="Mark failed after N attempts")
    drain_parser.add_argument("--no-ingest", action="store_true", help="Skip auto-ingest after download (run 'oracle watch --once' manually)")

    perf_parser = subparsers.add_parser("perf", help="Performance profile and runtime pause controls")
    perf_sub = perf_parser.add_subparsers(dest="perf_command")
    perf_sub.add_parser("status", help="Show current performance profile and pause state")
    perf_profile = perf_sub.add_parser("profile", help="Set performance profile")
    perf_profile.add_argument("name", choices=["balanced", "performance", "quiet"], help="Profile name")
    perf_pause = perf_sub.add_parser("pause", help="Pause heavy workers")
    perf_pause.add_argument("--reason", default="", help="Optional pause reason")
    perf_sub.add_parser("resume", help="Resume paused workers")

    args = parser.parse_args()

    if args.command == "db" and args.db_command == "migrate":
        migrate()
        return

    if args.command == "doctor":
        from oracle.doctor import run_doctor, _render
        sys.exit(_render(run_doctor()))

    if args.command == "audit":
        from oracle.audit import run_audit
        run_audit()
        return

    if args.command == "ops" and args.ops_command == "iterate":
        from oracle.ops import run_iteration

        payload = run_iteration(
            bootstrap=not bool(args.no_bootstrap),
            validate_apply=bool(args.apply_validation),
            validate_limit=int(args.validation_limit or 0),
            validate_workers=int(args.validation_workers or 0),
            validate_confidence=float(args.validation_confidence or 0.7),
            drain_limit=int(args.drain_limit or 0),
            watch_once=bool(args.watch_once),
            report_path=args.report,
        )
        print(f"Ops iteration complete. Report: {payload.get('report_path')}")
        missing = payload.get("missing_pieces") or []
        if missing:
            print("Missing pieces detected:")
            for item in missing:
                print(f"  - {item}")
        return

    if args.command == "status":
        from oracle.db.schema import get_connection
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        
        print("\n" + "="*60)
        print("LYRA ORACLE STATUS")
        print("="*60)
        print(f"Write Mode: {get_write_mode()}")
        try:
            from oracle.runtime_state import get_profile, is_paused
            paused, _ = is_paused()
            print(f"Profile: {get_profile()} | Paused: {'yes' if paused else 'no'}")
        except Exception:
            pass
        print()
        
        # Row counts
        count_queries = [
            ("SELECT COUNT(*) FROM tracks", "Tracks (total)"),
            ("SELECT COUNT(*) FROM tracks WHERE status = 'active'", "Tracks (active)"),
            ("SELECT COUNT(*) FROM embeddings", "Embeddings"),
            ("SELECT COUNT(*) FROM track_scores", "Scored tracks"),
            ("SELECT COUNT(*) FROM vibe_profiles", "Vibes"),
            ("SELECT COUNT(*) FROM acquisition_queue WHERE status = 'pending'", "Queue (pending)"),
            ("SELECT COUNT(*) FROM spotify_history", "Spotify history"),
            ("SELECT COUNT(*) FROM spotify_library", "Spotify library"),
            ("SELECT COUNT(*) FROM playback_history", "Playback events"),
        ]
        
        print("Database:")
        for sql, label in count_queries:
            try:
                cursor.execute(sql)
                count = cursor.fetchone()[0]
                print(f"   {label}: {count:,}")
            except Exception:
                print(f"   {label}: (table missing)")
        
        # Tier availability
        print("\nAcquisition Tiers:")
        try:
            from oracle.acquirers.waterfall import get_tier_status
            tiers = get_tier_status()
            for tier, info in tiers.items():
                avail = "[OK]" if info.get("available") else "[--]"
                print(f"   {avail} {tier}")
        except Exception as e:
            print(f"   (could not check: {e})")

        # Docker / external service health
        print("\nServices:")
        _svc_checks = [
            ("Docker",       "docker", ["docker", "ps"], None),
            ("Prowlarr",     "http", "http://localhost:9696/health", None),
            ("rdtclient",    "http", "http://localhost:6500", None),
            ("slskd",        "http", "http://localhost:5030/api/v0/application", None),
            ("LM Studio",    "http", "http://127.0.0.1:1234/v1/models", None),
        ]
        import subprocess
        import urllib.request
        import urllib.error
        for svc_name, kind, target, _ in _svc_checks:
            try:
                if kind == "docker":
                    r = subprocess.run(target, capture_output=True, timeout=3)
                    icon = "[OK]" if r.returncode == 0 else "[--]"
                    label = "daemon running" if r.returncode == 0 else "daemon not running"
                else:
                    try:
                        req = urllib.request.urlopen(target, timeout=3)
                        icon = "[OK]"
                        label = f"HTTP {req.status}"
                    except urllib.error.HTTPError as he:
                        # 4xx means service is up but needs auth â€” still live
                        if he.code < 500:
                            icon = "[OK]"
                            label = f"HTTP {he.code} (live)"
                        else:
                            icon = "[--]"
                            label = f"HTTP {he.code}"
            except Exception:
                icon = "[--]"
                label = "offline"
            print(f"   {icon} {svc_name}: {label}")

        conn.close()
        print("=" * 60 + "\n")
        return

    if args.command == "perf":
        from oracle.runtime_state import get_profile, is_paused, pause, resume, set_profile
        from oracle.perf import auto_workers, cpu_count

        if args.perf_command == "profile":
            profile = set_profile(args.name)
            print(f"Performance profile set to: {profile}")
            print(
                f"Auto workers -> network: {auto_workers('network')}, "
                f"io: {auto_workers('io')}, cpu: {auto_workers('cpu')}"
            )
            return

        if args.perf_command == "pause":
            pause(args.reason)
            print("Workers paused.")
            return

        if args.perf_command == "resume":
            resume()
            print("Workers resumed.")
            return

        paused, reason = is_paused()
        print(f"CPU cores: {cpu_count()}")
        print(f"Profile: {get_profile()}")
        print(
            f"Auto workers -> network: {auto_workers('network')}, "
            f"io: {auto_workers('io')}, cpu: {auto_workers('cpu')}"
        )
        if paused:
            if reason:
                print(f"Pause: ON ({reason})")
            else:
                print("Pause: ON")
        else:
            print("Pause: OFF")
        return

    if args.command == "scan":
        from oracle.scanner import scan_library
        results = scan_library(args.library, limit=args.limit)
        print(results)
        return

    if args.command == "index":
        from oracle.indexer import index_library
        results = index_library(
            args.library,
            limit=args.limit,
            force_reindex=args.force_reindex,
            auto_score=not getattr(args, 'no_score', False),
            workers=int(getattr(args, "workers", 0) or 0),
            embed_batch=int(getattr(args, "embed_batch", 0) or 0),
        )
        print(results)
        return

    if args.command == "search":
        from oracle.search import search

        query = args.query
        if args.nl:
            # LLM rewrites the natural language query into CLAP-optimized audio description
            try:
                from oracle.llm import LLMClient
                _llm = LLMClient.from_env()
                result = _llm.chat(
                    [{"role": "user", "content": args.query}],
                    temperature=0.2,
                    max_tokens=100,
                    json_schema={
                        "name": "search_rewrite",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "clap_query": {
                                    "type": "string",
                                    "description": "Rewritten as an audio description for embedding"
                                },
                                "n": {"type": "integer", "minimum": 1, "maximum": 50},
                            },
                            "required": ["clap_query", "n"],
                            "additionalProperties": False,
                        },
                    },
                    system=(
                        "You rewrite music search queries into audio descriptions optimized "
                        "for CLAP audio embeddings. Focus on sonic qualities: tempo, texture, "
                        "mood, instrumentation, energy. The 10 emotional dimensions are: "
                        "energy, valence, tension, density, warmth, movement, space, "
                        "rawness, complexity, nostalgia. Keep clap_query under 20 words. "
                        "Set n to the number of results the user seems to want (default 10)."
                    ),
                )
                if result.get("ok") and "data" in result:
                    rewritten = result["data"].get("clap_query", query)
                    suggested_n = result["data"].get("n", args.n)
                    print(f"[NL] '{args.query}'")
                    print(f"  -> '{rewritten}'")
                    query = rewritten
                    if suggested_n != args.n:
                        args.n = suggested_n
            except Exception as exc:
                print(f"[NL] LLM rewrite failed ({exc}), using raw query")

        results = search(query, n=args.n)
        for item in results:
            print(
                f"{item.get('rank')}. {item.get('artist', '')} - {item.get('title', '')}"
                f" | {item.get('album', '')} | {item.get('year', '')} | {item.get('path', '')}"
            )
        return

    if args.command == "pipeline":
        if get_write_mode() != "apply_allowed":
            print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to run pipeline.")
            return
        from oracle.scanner import scan_library
        from oracle.indexer import index_library
        
        print("\n" + "="*60)
        print("LYRA PIPELINE: Scan â†’ Index â†’ Score")
        print("="*60 + "\n")
        
        print("[1/2] Scanning library...")
        scan_results = scan_library(args.library, limit=args.limit)
        print(f"  Scanned: {scan_results}")
        
        print("\n[2/2] Indexing + scoring...")
        index_results = index_library(
            args.library,
            limit=args.limit,
            force_reindex=args.force_reindex,
            auto_score=not getattr(args, 'no_score', False),
        )
        print(f"  Indexed: {index_results.get('indexed', 0)}")
        print(f"  Scored: {index_results.get('scored', 0)}")
        print(f"  Failed: {index_results.get('failed', 0)}")
        print("\n" + "="*60)
        print("Pipeline complete!")
        print("="*60 + "\n")
        return

    if args.command == "hunt":
        if get_write_mode() != "apply_allowed":
            print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to hunt.")
            return
        from oracle.acquirers.smart_pipeline import SmartAcquisition, AcquisitionRequest
        import logging as _logging
        _logging.basicConfig(level=_logging.INFO, format="%(message)s")
        query = " ".join(args.query).strip()
        if " - " in query:
            _artist, _title = query.split(" - ", 1)
        else:
            _artist, _title = "Unknown Artist", query
        _hunt_pipeline = SmartAcquisition(library_path=LIBRARY_BASE, require_validation=True)
        try:
            _hunt_result = _hunt_pipeline.acquire(AcquisitionRequest(
                artist=_artist.strip(), title=_title.strip(), source="hunt"
            ))
            if _hunt_result.success:
                print(f"Acquired: {_hunt_result.filepath}")
                if getattr(_hunt_result, "quality", None):
                    print(f"  Quality: {_hunt_result.quality}")
                if getattr(_hunt_result, "tier_used", None):
                    print(f"  Tier: {_hunt_result.tier_used}")
            else:
                print(f"Failed: {_hunt_result.rejection_reason}")
        finally:
            if hasattr(_hunt_pipeline, "close"):
                _hunt_pipeline.close()
        return

    if args.command == "acquire" and args.acquire_command == "youtube":
        if get_write_mode() != "apply_allowed":
            print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to acquire.")
            return
        from oracle.acquirers.ytdlp import YTDLPAcquirer
        acquirer = YTDLPAcquirer()
        result = acquirer.download(args.url)
        print(result if result else "Download failed")
        return

    if args.command == "acquire" and args.acquire_command == "search":
        from oracle.acquirers.prowlarr_rd import search_prowlarr
        from oracle.acquisition import enqueue_url
        if args.source != "prowlarr":
            print(f"Unsupported source: {args.source}")
            return
        results = search_prowlarr(args.query, limit=args.limit)
        for item in results:
            title = item.get("title") or item.get("guid") or "Unknown"
            link = (
                item.get("magnetUrl")
                or item.get("downloadUrl")
                or item.get("link")
                or item.get("guid")
            )
            print(f"{title} -> {link}")
            if link:
                enqueue_url(link, "prowlarr")
        return

    if args.command == "acquire" and args.acquire_command == "lyra":
        if get_write_mode() != "apply_allowed":
            print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to acquire.")
            return
        from oracle.lyra_protocol import run_lyra_protocol

        result = asyncio.run(run_lyra_protocol(args.artist, args.title))
        status = result.get("status", "unknown")
        route = result.get("route", "-")
        print(f"Lyra Protocol status: {status} | route: {route}")
        if "error" in result:
            print(f"Error: {result['error']}")
        attempted = result.get("attempted_queries") or []
        if status == "no_results" and attempted:
            print("Attempted queries:")
            for q in attempted:
                print(f"  - {q}")
        winner = result.get("winner")
        if winner:
            print(
                f"Winner: {winner.source} | score={winner.integrity_score} | id={winner.identifier}"
            )
        return

    if args.command == "acquire" and args.acquire_command == "waterfall":
        if get_write_mode() != "apply_allowed":
            print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to acquire.")
            return
        from oracle.acquirers.waterfall import acquire
        import logging
        logging.basicConfig(level=logging.INFO, format="%(message)s")

        result = acquire(
            artist=args.artist,
            title=args.title,
            album=getattr(args, 'album', None),
            max_tier=getattr(args, 'max_tier', 4),
        )
        print(f"\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Tier: {result.tier}")
        print(f"  Source: {result.source}")
        if result.path:
            print(f"  Path: {result.path}")
        if result.error:
            print(f"  Error: {result.error}")
        print(f"  Elapsed: {result.elapsed:.1f}s")
        return

    if args.command == "enrich":
        from oracle.enrichers.unified import enrich_track
        providers = [p.strip() for p in args.providers.split(",") if p.strip()]
        results = enrich_track(args.track_id, providers=providers)
        _print_json_safe(results)
        return

    if args.command == "curate" and args.curate_command == "classify":
        from oracle.classifier import classify_library
        if args.llm:
            print("[classify] LLM second pass enabled â€” LM Studio must be running.")
        results = classify_library(limit=args.limit, use_llm=args.llm)
        print(f"\nClassification Summary ({results['total']} tracks):")
        for k, v in results.items():
            if k not in ("total",) and v > 0:
                print(f"  {k}: {v}")
        return

    if args.command == "curate" and args.curate_command == "plan":
        from oracle.curator import generate_plan
        generate_plan(
            preset=args.preset,
            classify_first=args.classify_first,
            limit=args.limit,
            output_dir=args.out
        )
        return

    if args.command == "curate" and args.curate_command == "apply":
        from oracle.curator import apply_plan
        results = apply_plan(
            plan_path=args.plan,
            confidence_min=args.confidence_min,
            dry_run=args.dry_run
        )
        if "error" in results:
            print(f"ERROR: {results['error']}")
        return

    if args.command == "curate" and args.curate_command == "undo":
        from oracle.curator import undo_plan
        results = undo_plan(
            journal_path=args.journal,
            dry_run=args.dry_run
        )
        if "error" in results:
            print(f"ERROR: {results['error']}")
        return

    if args.command == "downloads" and args.downloads_command == "list":
        from oracle.download_processor import list_downloads
        downloads = list_downloads(show_metadata=args.show_metadata)
        if not downloads:
            print("No downloads found.")
            return
        print(f"\nFound {len(downloads)} downloads:\n")
        for idx, dl in enumerate(downloads, 1):
            print(f"{idx}. {dl['name']}")
            print(f"   Folder: {dl['folder']} | Size: {dl['size_mb']:.2f} MB")
            if args.show_metadata and 'metadata_clean' in dl:
                meta = dl['metadata_clean']
                print(f"   Metadata: {meta.get('artist', '?')} - {meta.get('title', '?')}")
                if meta.get('album'):
                    print(f"   Album: {meta['album']}")
        return

    if args.command == "downloads" and args.downloads_command == "clean":
        from oracle.download_processor import find_new_downloads, clean_filename_inplace
        files = find_new_downloads()
        if not files:
            print("No downloads found.")
            return
        
        cleaned_count = 0
        for file_path in files:
            new_path, was_renamed = clean_filename_inplace(file_path, dry_run=args.dry_run)
            if was_renamed:
                cleaned_count += 1
                action = "Would rename" if args.dry_run else "Renamed"
                print(f"{action}: {file_path.name}")
                print(f"       â†’ {new_path.name}")
        
        if cleaned_count == 0:
            print("All filenames are already clean.")
        else:
            action = "would be" if args.dry_run else "were"
            print(f"\n{cleaned_count}/{len(files)} files {action} renamed.")
        return

    if args.command == "downloads" and args.downloads_command == "organize":
        print("NOTE: 'oracle downloads organize' is deprecated. Use 'oracle import' instead.")
        print("Redirecting to beets import...")
        import logging as _logging
        _logging.basicConfig(level=_logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        from oracle.integrations.beets_import import beets_import_and_ingest
        from oracle.config import DOWNLOADS_FOLDER
        result = beets_import_and_ingest(
            Path(DOWNLOADS_FOLDER),
            dry_run=args.dry_run,
        )
        print(f"Beets import: {result.get('imported', 0)} imported, "
              f"{result.get('quarantined', 0)} quarantined, "
              f"{result.get('errors', 0)} errors")
        return

    if args.command == "vibe" and args.vibe_command == "save":
        from oracle.vibes import save_vibe
        result = save_vibe(args.name, args.query, n=args.n)
        if 'error' in result:
            print(f"ERROR: {result['error']}")
            return
        print(f"\nâœ“ Vibe saved: {result['name']}")
        print(f"  Query: {result['query']}")
        print(f"  Tracks: {result['track_count']}")
        return

    if args.command == "vibe" and args.vibe_command == "list":
        from oracle.vibes import list_vibes
        vibes = list_vibes()
        if not vibes:
            print("No vibes saved yet.")
            return
        print(f"\nSaved Vibes ({len(vibes)}):\n")
        for vibe in vibes:
            print(f"â€¢ {vibe['name']}")
            print(f"  Query: {vibe['query']}")
            print(f"  Tracks: {vibe['track_count']}")
            import datetime
            created = datetime.datetime.fromtimestamp(vibe['created_at']).strftime('%Y-%m-%d %H:%M')
            print(f"  Created: {created}\n")
        return

    if args.command == "vibe" and args.vibe_command == "build":
        from oracle.vibes import build_vibe
        result = build_vibe(args.name)
        if 'error' in result:
            print(f"ERROR: {result['error']}")
            return
        print(f"\nâœ“ M3U8 playlist built: {result['m3u8_path']}")
        print(f"  Tracks: {result['track_count']}")
        return

    if args.command == "vibe" and args.vibe_command == "materialize":
        from oracle.vibes import materialize_vibe
        result = materialize_vibe(args.name, mode=args.mode)
        if 'error' in result:
            print(f"ERROR: {result['error']}")
            return
        print(f"\nâœ“ Vibe materialized: {result['folder']}")
        print(f"  Mode: {result['mode']}")
        stats = result['stats']
        print(f"  Created: {stats['created']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Missing: {stats['missing']}")
        print(f"  Errors: {stats['errors']}")
        return

    if args.command == "vibe" and args.vibe_command == "refresh":
        from oracle.vibes import refresh_vibes
        vibe_name = args.name if not args.all else None
        result = refresh_vibes(vibe_name)
        if 'error' in result:
            print(f"ERROR: {result['error']}")
            return
        print(f"\nâœ“ Refreshed {result['refreshed']} vibe(s)")
        for item in result['results']:
            print(f"\nâ€¢ {item['name']}")
            if 'error' in item['result']:
                print(f"  âœ— {item['result']['error']}")
            else:
                print(f"  âœ“ {item['result']['track_count']} tracks")
        return

    if args.command == "vibe" and args.vibe_command == "delete":
        from oracle.vibes import delete_vibe
        result = delete_vibe(args.name, delete_materialized=args.delete_folder)
        if 'error' in result:
            print(f"ERROR: {result['error']}")
            return
        print(f"\nâœ“ Vibe deleted: {result['name']}")
        if result.get('deleted_materialized'):
            print(f"  Folder also deleted")
        return

    if args.command == "serve":
        if not getattr(args, "no_bootstrap", False):
            try:
                from oracle.bootstrap import bootstrap_runtime
                result = bootstrap_runtime(timeout_seconds=int(getattr(args, "bootstrap_timeout", 40)))
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

        from lyra_api import app
        print("\n" + "="*60)
        print("LYRA ORACLE API SERVER")
        print("="*60)
        print(f"Host: {args.host}")
        print(f"Port: {args.port}")
        print(f"Debug: {args.debug}")
        print(f"Write Mode: {get_write_mode()}")
        print(f"\nStarting server at http://{args.host}:{args.port}")
        print("="*60 + "\n")
        app.run(host=args.host, port=args.port, debug=args.debug)
        return

    if args.command == "score":
        import json as _json
        from oracle.scorer import score_all
        result = score_all(
            limit=args.limit,
            force=args.force,
            workers=int(getattr(args, "workers", 0) or 0),
        )
        print(_json.dumps(result, indent=2))
        return

    if args.command == "normalize":
        from oracle.normalizer import normalize_library
        normalize_library(apply=args.apply)
        return

    if args.command == "validate":
        from oracle.acquirers.validator import validate_and_fix_library
        validate_and_fix_library(
            limit=int(args.limit or 0),
            apply=bool(args.apply),
            min_confidence=float(args.confidence or 0.7),
            workers=int(args.workers or 0),
            only_unvalidated=not bool(args.full_scan),
            full_rescan_if_needed=True,
        )
        return

    if args.command == "prowlarr" and args.prowlarr_command == "setup-rutracker":
        from oracle.acquirers.prowlarr_setup import ensure_rutracker_indexer

        result = ensure_rutracker_indexer(
            username=args.username,
            password=args.password,
            enable=True,
        )
        if result.get("ok"):
            action = result.get("action", "updated")
            indexer_id = result.get("id", "?")
            print(f"RuTracker indexer {action} (id={indexer_id}).")
            if result.get("test_ok"):
                print("Connection test: OK")
            else:
                print(f"Connection test: {result.get('test_message', 'unknown')}")
            return
        print(f"RuTracker setup failed: {result.get('error', 'unknown error')}")
        return

    if args.command == "enrich-all":
        import subprocess
        subprocess.run([sys.executable, "enrich_genres.py"], cwd=".")
        return

    if args.command == "smart-acquire":
        if get_write_mode() != "apply_allowed":
            print("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed to acquire.")
            return
        
        from pathlib import Path
        from oracle.acquirers.smart_pipeline import SmartAcquisition, AcquisitionRequest
        import logging
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        
        library = str(LIBRARY_BASE)
        pipeline = SmartAcquisition(
            library_path=Path(library),
            require_validation=not args.no_validate,
        )
        
        if args.queue:
            results = pipeline.process_queue(limit=args.limit)
            print(f"\n=== Processed {len(results)} items ===")
            summary = getattr(pipeline, "last_queue_summary", {})
            success = summary.get("succeeded", sum(1 for r in results if r.success))
            print(f"Success: {success}/{len(results)}")
            print(
                "Queue summary: "
                f"failed={summary.get('failed', 0)} "
                f"retried={summary.get('retried', 0)} "
                f"rejected={summary.get('rejected', 0)}"
            )
        elif args.artist and args.title:
            request = AcquisitionRequest(
                artist=args.artist,
                title=args.title,
                album=args.album,
            )
            result = pipeline.acquire(request)
            
            if result.success:
                print(f"\nâœ“ Acquired: {result.filepath}")
                print(f"  Artist: {result.canonical_artist}")
                print(f"  Title: {result.canonical_title}")
                print(f"  Quality: {result.quality}")
                print(f"  Tier: {result.tier_used}")
            else:
                print(f"\nâœ— Failed: {result.rejection_reason}")
        else:
            print("Usage: oracle smart-acquire --artist X --title Y")
            print("   or: oracle smart-acquire --queue --limit 10")
        return

    if args.command == "guard" and args.guard_command == "test":
        from oracle.acquirers.guard import guard_acquisition
        
        result = guard_acquisition(args.artist, args.title)
        
        print(f"\n{'='*60}")
        print(f"GUARD TEST: {args.artist} - {args.title}")
        print(f"{'='*60}")
        
        if result.allowed:
            print(f"\nâœ… ALLOWED")
            print(f"  Confidence: {result.confidence:.0%}")
            print(f"  Canonical: {result.artist} - {result.title}")
            if result.validated_by:
                print(f"  Validated by: {result.validated_by}")
            if result.warnings:
                print(f"  Warnings:")
                for w in result.warnings:
                    print(f"    âš ï¸ {w}")
        else:
            print(f"\nâŒ REJECTED")
            print(f"  Reason: {result.rejection_reason}")
            print(f"  Category: {result.rejection_category}")
        return

    if args.command == "guard" and args.guard_command == "scan":
        from pathlib import Path
        from oracle.acquirers.guarded_import import scan_folder
        
        folder = Path(args.folder)
        if not folder.exists():
            print(f"Folder not found: {folder}")
            return
        
        results = scan_folder(folder)
        allowed = [r for r in results if r[1].allowed]
        rejected = [r for r in results if not r[1].allowed]
        
        print(f"\n{'='*60}")
        print(f"GUARD SCAN: {folder}")
        print(f"{'='*60}")
        print(f"\nTotal: {len(results)}")
        print(f"Allowed: {len(allowed)}")
        print(f"Rejected: {len(rejected)}")
        
        if rejected:
            print(f"\nâŒ REJECTED:")
            for filepath, result in rejected:
                print(f"  â€¢ {filepath.name[:50]}")
                print(f"    {result.rejection_reason}")
        return

    if args.command == "guard" and args.guard_command == "import":
        from pathlib import Path
        from oracle.acquirers.guarded_import import process_downloads
        
        downloads = Path(args.downloads)
        library = Path(args.library or str(LIBRARY_BASE))
        
        summary = process_downloads(
            downloads,
            library,
            dry_run=args.dry_run,
            delete_rejected=args.delete_rejected,
        )
        
        print(f"\n{'='*60}")
        print(f"GUARDED IMPORT")
        print(f"{'='*60}")
        print(f"Total: {summary.get('total', 0)}")
        print(f"Imported: {summary.get('imported', 0)}")
        print(f"Rejected: {summary.get('rejected', 0)}")
        print(f"Low confidence: {summary.get('low_confidence', 0)}")
        print(f"Errors: {summary.get('errors', 0)}")
        
        if args.dry_run:
            print("\n(DRY RUN - no changes made)")
        return

    if args.command == "guard" and args.guard_command == "audit":
        from pathlib import Path
        from oracle.acquirers.guarded_import import audit_library
        
        library = Path(args.library or str(LIBRARY_BASE))
        audit = audit_library(library)
        
        print(f"\n{'='*60}")
        print(f"LIBRARY AUDIT: {library}")
        print(f"{'='*60}")
        print(f"Total: {audit['total']}")
        print(f"Clean: {audit['clean']}")
        print(f"Junk: {audit['junk']}")
        
        if audit["junk_files"]:
            print(f"\nâŒ JUNK FILES:")
            for item in audit["junk_files"][:20]:
                filepath = Path(item["file"])
                print(f"  â€¢ {filepath.name[:50]}")
                print(f"    {item['reason']}")
            if len(audit["junk_files"]) > 20:
                print(f"  ... and {len(audit['junk_files']) - 20} more")
        return

    if args.command == "guard" and args.guard_command == "quarantine":
        from pathlib import Path
        from oracle.acquirers.guarded_import import quarantine_junk
        
        library = Path(args.library or str(LIBRARY_BASE))
        result = quarantine_junk(library, dry_run=args.dry_run)
        
        print(f"\n{'='*60}")
        print(f"QUARANTINE RESULTS")
        print(f"{'='*60}")
        
        if result.get("dry_run"):
            print(f"Would quarantine: {result.get('would_quarantine', 0)} files")
            print("\n(DRY RUN - run without --dry-run to execute)")
        else:
            print(f"Quarantined: {result.get('quarantined', 0)}")
            print(f"Errors: {result.get('errors', 0)}")
        return

    if args.command == "played":
        from oracle.db.schema import get_connection
        from oracle.taste import update_taste_from_playback
        import time as _time

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT track_id FROM tracks WHERE LOWER(artist) LIKE LOWER(?) AND LOWER(title) LIKE LOWER(?)",
            (f"%{args.artist}%", f"%{args.title}%"),
        )
        row = cur.fetchone()
        if not row:
            print(f"[played] No track found matching: {args.artist} - {args.title}")
            conn.close()
            return
        track_id = row[0]

        # Write to playback_history
        try:
            conn.execute(
                """INSERT INTO playback_history (track_id, ts, context, skipped, completion_rate)
                   VALUES (?, ?, 'cli', ?, ?)""",
                (track_id, _time.time(), 1 if args.skipped else 0,
                 0.1 if args.skipped else 1.0),
            )
            conn.commit()
        except Exception as exc:
            print(f"[played] Warning: could not write playback_history: {exc}")
        conn.close()

        # Update taste profile
        result = update_taste_from_playback(
            track_id, positive=not args.skipped, weight=args.weight
        )
        signal = "SKIP" if args.skipped else "PLAY"
        print(f"[played] {signal}: {args.artist} - {args.title}")
        print(f"         track_id={track_id}")
        print(f"         taste updated: {result}")
        return

    if args.command == "catalog":
        import logging as _logging
        _logging.basicConfig(
            level=_logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        from oracle.catalog import (
            catalog_acquire_artist,
            catalog_lookup,
            display_acquire_results,
            display_lookup,
        )

        if args.catalog_command == "lookup":
            types = args.types.split(",")
            data = catalog_lookup(args.artist, types=types)
            display_lookup(data)
            return

        if args.catalog_command == "acquire":
            types = args.types.split(",")
            data = catalog_acquire_artist(
                args.artist,
                types=types,
                dry_run=args.dry_run,
                limit=args.limit,
                max_torrent_gb=args.max_gb,
                download_wait=args.download_wait,
                file_select_wait=args.select_wait,
                poll_interval=args.poll_interval,
                replace_with_hq_album=not args.no_replace,
            )
            display_acquire_results(data)
            return

        if args.catalog_command == "status":
            conn = get_connection()
            query = "SELECT artist_name, title, release_type, year, track_count, status, error FROM catalog_releases"
            params: list = []
            if args.artist:
                query += " WHERE artist_name LIKE ?"
                params.append(f"%{args.artist}%")
            query += " ORDER BY year"
            rows = conn.execute(query, params).fetchall()
            conn.close()
            if not rows:
                print("No catalog entries found.")
                return
            print(f"\n{'Artist':<25s} {'Year':<6s} {'Type':<8s} {'Tracks':<8s} {'Status':<10s} Title")
            print("-" * 90)
            for r in rows:
                print(f"{(r[0] or '')[:24]:<25s} {str(r[3] or '?'):<6s} {(r[2] or ''):<8s} {str(r[4] or '?'):<8s} {(r[5] or ''):<10s} {r[1]}")
                if r[6]:
                    print(f"{'':>25s} Error: {r[6][:60]}")
            return

        print("Usage: oracle catalog {lookup|acquire|status}")
        return

    if args.command == "watch":
        import logging as _logging
        _logging.basicConfig(level=_logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        from oracle.ingest_watcher import run_watcher
        run_watcher(once=args.once)
        return

    if args.command == "import":
        import logging as _logging
        from pathlib import Path as _Path
        _logging.basicConfig(level=_logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        from oracle.integrations.beets_import import beets_import_and_ingest
        from oracle.config import STAGING_FOLDER, DOWNLOADS_FOLDER
        source_map = {
            "staging": STAGING_FOLDER,
            "downloads": DOWNLOADS_FOLDER,
        }
        source = source_map.get(args.source, _Path(args.source))
        result = beets_import_and_ingest(
            source,
            dry_run=getattr(args, "dry_run", False),
            no_autotag=getattr(args, "no_autotag", False),
            singleton=getattr(args, "singletons", False),
            move=not getattr(args, "copy", False),
        )
        print(f"Beets import: {result.get('imported', 0)} imported, "
              f"{result.get('quarantined', 0)} quarantined, "
              f"{result.get('errors', 0)} errors")
        if result.get("scan"):
            print(f"Scan: {result['scan']}")
        if result.get("index"):
            print(f"Index: {result['index']}")
        return

    if args.command == "drain":
        import logging as _logging
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from pathlib import Path as _Path
        from oracle.runtime_state import wait_if_paused
        _logging.basicConfig(level=_logging.INFO, format="%(message)s")
        from oracle.db.schema import get_connection
        from oracle.acquirers.waterfall import acquire

        conn = get_connection()
        cur = conn.cursor()
        q = (
            "SELECT id, artist, title, album, spotify_uri, COALESCE(retry_count, 0) "
            "FROM acquisition_queue "
            "WHERE status = 'pending' AND artist != '' AND title != '' "
            "AND artist IS NOT NULL AND title IS NOT NULL"
        )
        params: list = []
        if args.artist:
            q += " AND artist LIKE ?"
            params.append(f"%{args.artist}%")
        q += " ORDER BY COALESCE(priority_score, 0) DESC, datetime(added_at) ASC, id ASC"
        if args.limit:
            q += " LIMIT ?"
            params.append(args.limit)
        cur.execute(q, params)
        items = cur.fetchall()
        conn.close()

        if int(args.workers) <= 0:
            from oracle.perf import auto_workers
            workers = auto_workers("network")
        else:
            workers = int(args.workers)
        workers = max(1, min(workers, 32))
        print(f"\nDraining {len(items)} track(s) from queue (max tier: T{args.max_tier}, workers: {workers})...")

        downloaded_count = 0
        failed_count = 0
        retried_count = 0
        hard_failed_count = 0
        lock = threading.Lock()

        def _drain_one(item):
            wait_if_paused("drain")
            queue_id, artist, title, album, spotify_uri, retry_count = item
            result = acquire(artist, title, album=album, spotify_uri=spotify_uri, max_tier=args.max_tier)
            file_ready = bool(result.path) and _Path(result.path).exists()

            new_state = "failed"
            if result.success and file_ready:
                # Download succeeded; watcher marks final completion after post-flight ingest.
                try:
                    wconn = get_connection()
                    wconn.execute(
                        "UPDATE acquisition_queue SET status='downloaded', completed_at=NULL, error=NULL WHERE id=?",
                        (queue_id,),
                    )
                    wconn.commit()
                    wconn.close()
                    new_state = "downloaded"
                except Exception as exc:
                    new_state = "failed"
                    result.error = f"DB update failed: {exc}"
            else:
                # Partial/failed attempt: retry until max_retries, then hard fail.
                next_retry = int(retry_count or 0) + 1
                retryable_error = result.error or "acquisition did not yield a local file"
                target_status = "pending" if next_retry < args.max_retries else "failed"
                try:
                    wconn = get_connection()
                    wconn.execute(
                        "UPDATE acquisition_queue SET status=?, retry_count=?, error=? WHERE id=?",
                        (target_status, next_retry, retryable_error, queue_id),
                    )
                    wconn.commit()
                    wconn.close()
                    new_state = "retried" if target_status == "pending" else "failed"
                except Exception as exc:
                    new_state = "failed"
                    result.error = f"{retryable_error}; DB update failed: {exc}"

            return artist, title, result, new_state

        if workers == 1:
            for item in items:
                _, artist, title, album, spotify_uri, _ = item
                print(f"\n  {artist} - {title}")
                _, _, result, state = _drain_one(item)
                if state == "downloaded":
                    print(f"    [OK] T{result.tier} ({result.source}) â€” {result.elapsed:.1f}s")
                    if result.path:
                        print(f"         {result.path}")
                    downloaded_count += 1
                else:
                    if state == "retried":
                        print(f"    [~~] RETRY QUEUED: {result.error}")
                        retried_count += 1
                    else:
                        print(f"    [--] FAILED: {result.error}")
                        hard_failed_count += 1
                    failed_count += 1
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_drain_one, item): item for item in items}
                for future in as_completed(futures):
                    artist, title, result, state = future.result()
                    with lock:
                        if state == "downloaded":
                            print(f"  [OK] {artist} - {title} | T{result.tier} ({result.source}) {result.elapsed:.1f}s")
                            downloaded_count += 1
                        else:
                            if state == "retried":
                                print(f"  [~~] {artist} - {title} | retry queued | {result.error}")
                                retried_count += 1
                            else:
                                print(f"  [--] {artist} - {title} | {result.error}")
                                hard_failed_count += 1
                            failed_count += 1

        print(f"\nDone. {downloaded_count} downloaded, {failed_count} failed.")
        if retried_count or hard_failed_count:
            print(f"Retries queued: {retried_count} | Hard failed: {hard_failed_count}")
        if downloaded_count and not getattr(args, "no_ingest", False):
            print("\n-- Ingesting downloads (embed + score)... --")
            try:
                from oracle.ingest_watcher import run_watcher
                run_watcher(once=True)
            except Exception as _exc:
                print(f"[WARN] Auto-ingest failed: {_exc}")
                print("       Run 'oracle watch --once' to retry.")
        elif downloaded_count:
            print("Run 'oracle watch --once' to ingest and mark queue items completed.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()

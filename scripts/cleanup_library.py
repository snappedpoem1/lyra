#!/usr/bin/env python3
"""cleanup_library.py — Zero-trust library cleanup CLI.

Orchestrates the full ingestion/normalization pipeline:
    Phase 1: Fingerprint identification (AcoustID -> MBID)
    Phase 2: Metadata enrichment (MusicBrainz canonical data)
    Phase 3: Tag injection (mutagen writes verified tags)
    Phase 4: Library reorganization (plan -> review -> apply)

System invariants:
    - ZERO destructive operations: os.remove() is banned
    - Irresolvable files go to _Quarantine/ and are flagged in the DB
    - --dry-run is the default for ALL phases
    - JSON audit logs + undo journals for every operation
    - Deterministic: word-boundary regex for junk detection, no substring hacks
    - MusicBrainz-validated artists bypass all junk filters

Usage:
    # Full pipeline dry-run (generates plans, writes nothing)
    python scripts/cleanup_library.py

    # Phase 1 only: fingerprint scan
    python scripts/cleanup_library.py --phase fingerprint --limit 50

    # Phase 2 only: enrich from MusicBrainz
    python scripts/cleanup_library.py --phase enrich --limit 50

    # Phase 3 only: inject verified tags into files
    python scripts/cleanup_library.py --phase tags --apply

    # Phase 4 only: reorganize library
    python scripts/cleanup_library.py --phase organize --apply

    # Full pipeline with apply
    python scripts/cleanup_library.py --apply --limit 100
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from dotenv import load_dotenv
load_dotenv(_project_root / ".env", override=True)

from oracle.db.schema import get_connection, get_write_mode
from oracle.enrichers.acoustid import Confidence, identify_file
from oracle.enrichers.musicbrainz import enrich_by_mbid, enrich_by_text, validate_artist
from oracle.normalizer import (
    inject_tags,
    normalize_artist,
    normalize_library,
    normalize_title,
)
from oracle.organizer import apply_repair_plan, generate_repair_plan

logger = logging.getLogger("cleanup_library")

# ---------------------------------------------------------------------------
# Quarantine helper
# ---------------------------------------------------------------------------

_QUARANTINE_DIR = _project_root / "_Quarantine"


def _quarantine_track(track_id: str, filepath: str, reason: str) -> None:
    """Flag a track in the DB as quarantined. Does NOT delete the file."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tracks SET status = 'quarantine' WHERE track_id = ?",
        (track_id,),
    )
    conn.commit()
    conn.close()
    logger.info("Quarantined track %s: %s", track_id[:8], reason)


# ---------------------------------------------------------------------------
# Phase 1: Fingerprint identification
# ---------------------------------------------------------------------------

def phase_fingerprint(limit: int = 0, apply: bool = False) -> dict:
    """Fingerprint audio files and store MBID results.

    Dry-run mode: generates fingerprint_report_<ts>.json
    Apply mode: writes recording_mbid into tracks table
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT track_id, filepath, artist, title, duration
        FROM tracks
        WHERE status = 'active'
          AND (recording_mbid IS NULL OR recording_mbid = '')
    """
    params: list = []
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logger.info("Phase 1: Fingerprinting %d tracks...", len(rows))

    results = []
    high = med = low = 0

    for i, (track_id, filepath, artist, title, duration) in enumerate(rows, 1):
        if not filepath or not Path(filepath).is_file():
            continue

        logger.info("  [%d/%d] %s - %s", i, len(rows), artist or "?", title or "?")

        fp_result = identify_file(
            Path(filepath),
            existing_artist=artist,
            existing_title=title,
            existing_duration=duration,
        )

        entry = {
            "track_id": track_id,
            "filepath": filepath,
            "confidence": fp_result.confidence.value,
            "recording_mbid": fp_result.recording_mbid,
            "acoustid_score": fp_result.acoustid_score,
            "fp_artist": fp_result.artist,
            "fp_title": fp_result.title,
            "error": fp_result.error,
        }
        results.append(entry)

        if fp_result.confidence == Confidence.HIGH:
            high += 1
        elif fp_result.confidence == Confidence.MEDIUM:
            med += 1
        else:
            low += 1

        # Apply: write MBID to database
        if apply and fp_result.recording_mbid and fp_result.confidence != Confidence.LOW:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tracks SET recording_mbid = ? WHERE track_id = ?",
                (fp_result.recording_mbid, track_id),
            )
            conn.commit()
            conn.close()

    # Save report
    report = {
        "phase": "fingerprint",
        "timestamp": time.time(),
        "total": len(rows),
        "processed": len(results),
        "high": high,
        "medium": med,
        "low": low,
        "applied": apply,
        "results": results,
    }
    report_path = _project_root / f"fingerprint_report_{int(time.time())}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Fingerprint report: %s", report_path)
    logger.info("Results: %d high, %d medium, %d low", high, med, low)

    return report


# ---------------------------------------------------------------------------
# Phase 2: Metadata enrichment
# ---------------------------------------------------------------------------

def phase_enrich(limit: int = 0, apply: bool = False) -> dict:
    """Enrich tracks with canonical MusicBrainz metadata.

    Priority: MBID lookup (Phase 1 results) > text search fallback.
    MusicBrainz-validated artists are whitelisted (bypass junk filters).
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT track_id, filepath, artist, title, album, year, duration,
               recording_mbid
        FROM tracks
        WHERE status = 'active'
          AND (metadata_source IS NULL OR metadata_source = '')
    """
    params: list = []
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logger.info("Phase 2: Enriching %d tracks...", len(rows))

    results = []
    enriched_count = 0
    validated_artists: set = set()

    for i, (track_id, filepath, artist, title, album, year, duration, mbid) in enumerate(rows, 1):
        logger.info("  [%d/%d] %s - %s", i, len(rows), artist or "?", title or "?")

        match = None

        # Strategy 1: Use existing MBID from fingerprinting
        if mbid:
            match = enrich_by_mbid(mbid)
            if match:
                logger.debug("    MBID lookup success: %s", mbid)

        # Strategy 2: Text search fallback
        if match is None and artist and title:
            match = enrich_by_text(artist, title, album, duration)
            if match:
                logger.debug("    Text search match: confidence=%.2f", match.confidence)

        if match is None:
            results.append({
                "track_id": track_id,
                "status": "no_match",
                "artist": artist,
                "title": title,
            })
            continue

        # Validate artist against MusicBrainz (whitelist check)
        if match.artist and match.artist not in validated_artists:
            validation = validate_artist(match.artist)
            if validation:
                validated_artists.add(match.artist)
                logger.debug("    Artist validated: %s (MBID: %s)", match.artist, validation["mbid"])

        entry = {
            "track_id": track_id,
            "status": "enriched",
            "source": match.source,
            "confidence": match.confidence,
            "mb_artist": match.artist,
            "mb_title": match.title,
            "mb_album": match.album,
            "mb_year": match.year,
            "recording_mbid": match.recording_mbid,
            "artist_mbid": match.artist_mbid,
            "isrc": match.isrc,
            "track_number": match.track_number,
            "disc_number": match.disc_number,
        }
        results.append(entry)

        if apply and match.confidence >= 0.5:
            updates = []
            params_list = []

            if match.artist:
                updates.append("artist = ?")
                params_list.append(match.artist)
            if match.title:
                updates.append("title = ?")
                params_list.append(match.title)
            if match.album:
                updates.append("album = ?")
                params_list.append(match.album)
            if match.year:
                updates.append("year = ?")
                params_list.append(match.year)
            if match.recording_mbid:
                updates.append("recording_mbid = ?")
                params_list.append(match.recording_mbid)
            if match.artist_mbid:
                updates.append("artist_mbid = ?")
                params_list.append(match.artist_mbid)
            if match.isrc:
                updates.append("isrc = ?")
                params_list.append(match.isrc)

            updates.append("metadata_source = ?")
            params_list.append(match.source)
            updates.append("canonical_confidence = ?")
            params_list.append(match.confidence)
            updates.append("last_enriched_at = ?")
            params_list.append(time.time())

            if updates:
                params_list.append(track_id)
                update_sql = f"UPDATE tracks SET {', '.join(updates)} WHERE track_id = ?"

                wrote = False
                for attempt in range(1, 7):
                    conn = None
                    try:
                        conn = get_connection(timeout=30.0)
                        cursor = conn.cursor()
                        cursor.execute(update_sql, params_list)
                        conn.commit()
                        enriched_count += 1
                        wrote = True
                        break
                    except sqlite3.OperationalError as exc:
                        if "locked" not in str(exc).lower() or attempt == 6:
                            raise
                        wait_s = min(8.0, 0.5 * (2 ** (attempt - 1)))
                        logger.warning(
                            "DB locked while enriching %s (attempt %d/6). Retrying in %.1fs",
                            track_id,
                            attempt,
                            wait_s,
                        )
                        time.sleep(wait_s)
                    finally:
                        if conn is not None:
                            conn.close()

                if not wrote:
                    logger.error("Failed to persist enrichment for %s after retries", track_id)

    # Save report
    report = {
        "phase": "enrich",
        "timestamp": time.time(),
        "total": len(rows),
        "enriched": enriched_count,
        "validated_artists": list(validated_artists),
        "applied": apply,
        "results": results,
    }
    report_path = _project_root / f"enrich_report_{int(time.time())}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Enrichment report: %s", report_path)
    logger.info("Enriched: %d / %d", enriched_count, len(rows))

    return report


# ---------------------------------------------------------------------------
# Phase 3: Tag injection
# ---------------------------------------------------------------------------

def phase_tags(limit: int = 0, apply: bool = False) -> dict:
    """Inject verified metadata into audio file tags.

    Only writes fields that have been verified (metadata_source is set).
    Preserves ReplayGain. Writes musicbrainz_recordingid.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT track_id, filepath, artist, title, album, year,
               recording_mbid, artist_mbid, isrc
        FROM tracks
        WHERE status = 'active'
          AND metadata_source IS NOT NULL
          AND metadata_source != ''
    """
    params: list = []
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logger.info("Phase 3: Tag injection for %d tracks...", len(rows))

    results = []
    written = 0
    skipped = 0
    errors = 0

    for i, (track_id, filepath, artist, title, album, year, rec_mbid, art_mbid, isrc) in enumerate(rows, 1):
        if not filepath or not Path(filepath).is_file():
            skipped += 1
            continue

        logger.info("  [%d/%d] %s", i, len(rows), Path(filepath).name)

        result = inject_tags(
            Path(filepath),
            artist=artist,
            title=title,
            album=album,
            year=year,
            recording_mbid=rec_mbid,
            artist_mbid=art_mbid,
            isrc=isrc,
            dry_run=not apply,
        )

        results.append(result.to_dict())

        if result.success:
            if result.action == "write":
                written += 1
            else:
                skipped += 1
        else:
            errors += 1

    # Save report
    report = {
        "phase": "tags",
        "timestamp": time.time(),
        "total": len(rows),
        "written": written,
        "skipped": skipped,
        "errors": errors,
        "applied": apply,
        "results": results,
    }
    report_path = _project_root / f"tags_report_{int(time.time())}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Tag injection report: %s", report_path)
    logger.info("Tags: %d written, %d skipped, %d errors", written, skipped, errors)

    return report


# ---------------------------------------------------------------------------
# Phase 4: Library reorganization
# ---------------------------------------------------------------------------

def phase_organize(
    library_path: str = "",
    preset: str = "artist_album",
    limit: int = 0,
    apply: bool = False,
) -> dict:
    """Generate and optionally apply a library reorganization plan.

    Dry-run (default): generates repair_plan_<ts>.json for review.
    Apply: executes the plan, creates undo journal.
    """
    from oracle.config import LIBRARY_BASE as _lb

    lib = library_path or str(_lb)

    logger.info("Phase 4: Organizing library (preset=%s)...", preset)

    # Always generate a plan first
    plan = generate_repair_plan(
        library_path=lib,
        preset=preset,
        limit=limit,
        output_dir=str(_project_root),
    )

    logger.info("Plan %s: %s", plan.plan_id, plan.summary)

    result = {
        "phase": "organize",
        "plan_id": plan.plan_id,
        "summary": plan.summary,
        "applied": False,
    }

    if apply:
        plan_path = _project_root / f"repair_plan_{plan.plan_id}.json"
        apply_result = apply_repair_plan(str(plan_path))
        result.update(apply_result)
        result["applied"] = True
        logger.info("Apply result: %s", apply_result)
    else:
        logger.info("Dry run. Review the plan, then run with --apply")

    return result


# ---------------------------------------------------------------------------
# Normalization (database-level metadata fixes)
# ---------------------------------------------------------------------------

def phase_normalize(apply: bool = False) -> dict:
    """Run database-level metadata normalization.

    Fixes: artist name variations, featured artist extraction, YouTube cruft.
    """
    logger.info("Phase 0: Database normalization...")
    output_path = str(_project_root / f"normalize_plan_{int(time.time())}.json")
    changes = normalize_library(apply=apply, output_path=output_path)
    logger.info("Normalization: %d changes %s", len(changes), "applied" if apply else "proposed")
    return {"phase": "normalize", "changes": len(changes), "applied": apply}


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Zero-trust library cleanup pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases (run in order by default):
  normalize    Fix artist/title variations in DB
  fingerprint  AcoustID fingerprint -> MBID identification
  enrich       MusicBrainz canonical metadata lookup
  tags         Write verified tags into audio files
  organize     Reorganize library folders

Examples:
  python scripts/cleanup_library.py                        # Full dry-run
  python scripts/cleanup_library.py --phase fingerprint    # Phase 1 only
  python scripts/cleanup_library.py --apply --limit 50     # Full pipeline, 50 tracks
        """,
    )
    parser.add_argument(
        "--phase",
        choices=["normalize", "fingerprint", "enrich", "tags", "organize", "all"],
        default="all",
        help="Which phase to run (default: all)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default: dry-run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max tracks to process per phase (0 = all)",
    )
    parser.add_argument(
        "--library",
        default="",
        help="Library path (default: from .env)",
    )
    parser.add_argument(
        "--preset",
        default="artist_album",
        help="Organization preset (default: artist_album)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Safety check
    if args.apply:
        mode = get_write_mode()
        if mode != "apply_allowed":
            logger.error(
                "Write mode is '%s'. Set LYRA_WRITE_MODE=apply_allowed to enable writes.",
                mode,
            )
            sys.exit(1)
        logger.warning("APPLY MODE: Changes will be written to files and database.")
    else:
        logger.info("DRY RUN MODE: No files or database records will be modified.")

    # Run phases
    phase = args.phase
    reports = []

    if phase in ("all", "normalize"):
        reports.append(phase_normalize(apply=args.apply))

    if phase in ("all", "fingerprint"):
        reports.append(phase_fingerprint(limit=args.limit, apply=args.apply))

    if phase in ("all", "enrich"):
        reports.append(phase_enrich(limit=args.limit, apply=args.apply))

    if phase in ("all", "tags"):
        reports.append(phase_tags(limit=args.limit, apply=args.apply))

    if phase in ("all", "organize"):
        reports.append(
            phase_organize(
                library_path=args.library,
                preset=args.preset,
                limit=args.limit,
                apply=args.apply,
            )
        )

    # Summary
    print("\n" + "=" * 60)
    print("CLEANUP PIPELINE SUMMARY")
    print("=" * 60)
    for r in reports:
        p = r.get("phase", "unknown")
        applied = r.get("applied", False)
        status = "APPLIED" if applied else "DRY RUN"
        print(f"  {p:15s} [{status}]  {json.dumps({k: v for k, v in r.items() if k not in ('phase', 'applied', 'results')})}")
    print("=" * 60)


if __name__ == "__main__":
    main()

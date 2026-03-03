"""scripts/flush_tracks_db.py — Surgical DB flush after Picard library rebuild.

Empties all file-path-dependent tables so a fresh ``oracle pipeline`` can
re-scan, re-embed, and re-score the library from scratch.

Preserved tables (never touched):
  spotify_history, spotify_library, spotify_features,
  acquisition_queue, vibe_profiles, taste_profile,
  enrich_cache, connections, catalog_releases

Tables that are cleared:
  tracks, embeddings, track_scores, playback_history, radio_queue,
  vibe_tracks, playlist_tracks, playlist_runs, curation_plans, errors,
  track_structure, sample_lineage, track_credits, llm_audit

Also deletes chroma_storage/ and creates a DB backup before doing anything.

Usage
-----
  # Dry run (default) — shows row counts, makes no changes:
  python scripts/flush_tracks_db.py

  # Execute flush (backs up DB first):
  python scripts/flush_tracks_db.py --apply
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from oracle.config import CHROMA_PATH
from oracle.db.schema import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "lyra_registry.db"
BACKUP_DIR   = PROJECT_ROOT / "backups"

# ---------------------------------------------------------------------------
# Tables — flush vs preserve
# ---------------------------------------------------------------------------

FLUSH_TABLES = [
    "track_credits",    # FK → tracks — clear first to satisfy any FK constraints
    "sample_lineage",
    "track_structure",
    "llm_audit",
    "curation_plans",
    "errors",
    "radio_queue",
    "playback_history",
    "playlist_tracks",
    "playlist_runs",
    "vibe_tracks",
    "track_scores",
    "embeddings",
    "tracks",           # Clear last — everything else references track_id
]

PRESERVE_TABLES = [
    "acquisition_queue",
    "spotify_history",
    "spotify_library",
    "spotify_features",
    "vibe_profiles",
    "taste_profile",
    "enrich_cache",
    "connections",
    "catalog_releases",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_counts(conn) -> dict[str, int]:
    c = conn.cursor()
    counts: dict[str, int] = {}
    for table in FLUSH_TABLES + PRESERVE_TABLES:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")   # noqa: S608
            counts[table] = c.fetchone()[0]
        except Exception:
            counts[table] = -1  # table doesn't exist yet
    return counts


def _backup_db() -> Path:
    """Copy lyra_registry.db to backups/ with timestamp."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = BACKUP_DIR / f"lyra_registry_preflush_{ts}.db"
    shutil.copy2(str(DB_PATH), str(dest))
    logger.info("DB backed up to %s", dest)
    return dest


def _delete_chroma(chroma_path: Path, dry_run: bool) -> None:
    if not chroma_path.exists():
        logger.info("chroma_storage not found — nothing to delete")
        return
    if dry_run:
        logger.info("  Would delete %s", chroma_path)
        return
    shutil.rmtree(str(chroma_path))
    logger.info("Deleted %s", chroma_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flush file-dependent DB tables + chroma_storage. "
                    "Backs up DB before any destructive operations."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the flush.  Without this flag it is a dry run.",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    if dry_run:
        logger.info("DRY RUN — pass --apply to execute")
    else:
        logger.warning("APPLY MODE — this will delete data and cannot be undone (backup made first)")

    conn = get_connection()

    # Show current counts
    before = _row_counts(conn)
    logger.info("\nCurrent row counts:")
    logger.info("  --- Tables to FLUSH ---")
    for t in FLUSH_TABLES:
        logger.info("    %-30s  %d", t, before[t])
    logger.info("  --- Tables to PRESERVE ---")
    for t in PRESERVE_TABLES:
        logger.info("    %-30s  %d  ✓ kept", t, before[t])

    if dry_run:
        conn.close()
        chroma_path = Path(str(CHROMA_PATH))
        logger.info("\nWould also delete: %s", chroma_path)
        logger.info("Run with --apply to execute.")
        return

    # Backup before touching anything
    _backup_db()

    # Flush
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = OFF")
    conn.commit()

    for table in FLUSH_TABLES:
        if before[table] < 0:
            logger.info("  SKIP %s (table does not exist)", table)
            continue
        c.execute(f"DELETE FROM {table}")   # noqa: S608
        logger.info("  CLEARED %-30s  (%d rows deleted)", table, before[table])

    c.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()

    # Vacuum to reclaim space
    try:
        conn2 = get_connection()
        conn2.execute("VACUUM")
        conn2.close()
        logger.info("VACUUM complete")
    except Exception as exc:
        logger.warning("VACUUM failed (non-fatal): %s", exc)

    # Delete chroma_storage
    chroma_path = Path(str(CHROMA_PATH))
    _delete_chroma(chroma_path, dry_run=False)

    logger.info("\nFlush complete.  Next steps:")
    logger.info("  oracle pipeline --library A:\\Music")
    logger.info("  oracle status")


if __name__ == "__main__":
    main()

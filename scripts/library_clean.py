"""scripts/library_clean.py — Picard-duplicate + junk sweep for A:\\Music.

Two-pass sweep:
  Pass 1 (dedup): Find Picard numbered duplicates ``*(N).flac`` → keep the
                  canonical (un-numbered) copy, move numbered copies to
                  ``A:\\Rejected\\Duplicates\``.
  Pass 2 (junk):  Run ``guard_file()`` on every remaining audio file.
                  - rejection_category "junk"     → A:\\Rejected\\Junk\\
                  - rejection_category "label"     → A:\\Rejected\\Junk\\
                  - rejection_category "invalid"   → A:\\Rejected\\Uncertain\\
                  - "remix" / "tribute" in title   → A:\\Rejected\\Remixes\\
                  - guard.allowed == False (other) → A:\\Rejected\\Uncertain\\

Usage
-----
  # Dry run (default) — lists moves but does nothing:
  python scripts/library_clean.py

  # Execute moves:
  python scripts/library_clean.py --apply

  # Scan a non-default library root:
  python scripts/library_clean.py --library "A:\\Music" --apply

Moves are appended to A:\\Rejected\\_clean_log.jsonl regardless of --apply.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from oracle.acquirers.guard import guard_file
from oracle.config import LIBRARY_BASE, REJECTED_FOLDER

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".wv"}

# Picard appends ``(1)``, ``(2)`` … before the extension
_PICARD_DUP = re.compile(r"^(.+)\s*\((\d+)\)$")

# Remix / tribute signal in title
_REMIX_RE = re.compile(
    r"\b(remix|rmx|tribute|karaoke|cover\s+version|version|cover\b)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_entry(
    action: str,
    src: Path,
    dest: Path | None,
    reason: str,
    dry_run: bool,
) -> Dict[str, Any]:
    return {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "action": action,
        "dry_run": dry_run,
        "src": str(src),
        "dest": str(dest) if dest else None,
        "reason": reason,
    }


def _safe_move(src: Path, dest: Path, dry_run: bool) -> bool:
    """Move ``src`` to ``dest`` unless dry_run.  Returns True on success."""
    if dry_run:
        return True
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            # Avoid clobber — add a suffix
            dest = dest.with_name(dest.stem + "_dup" + dest.suffix)
        shutil.move(str(src), str(dest))
        return True
    except Exception as exc:
        logger.error("  MOVE FAILED %s → %s : %s", src, dest, exc)
        return False


def _rejected(base: Path, sub: str, rel: Path) -> Path:
    """Build destination path under REJECTED_FOLDER keeping relative structure."""
    return base / sub / rel


# ---------------------------------------------------------------------------
# Pass 1 — Picard duplicates
# ---------------------------------------------------------------------------

def pass1_dedup(
    library_root: Path,
    rejected_root: Path,
    dry_run: bool,
) -> List[Dict[str, Any]]:
    """Find and move `*(N).ext` Picard duplicates."""
    log: List[Dict[str, Any]] = []
    removed = 0

    logger.info("Pass 1: scanning for Picard duplicates in %s", library_root)

    for dup_file in library_root.rglob("*"):
        if not dup_file.is_file():
            continue
        if dup_file.suffix.lower() not in AUDIO_EXTENSIONS:
            continue

        m = _PICARD_DUP.match(dup_file.stem)
        if not m:
            continue

        canonical_stem = m.group(1).rstrip()
        canonical = dup_file.with_name(canonical_stem + dup_file.suffix)

        rel = dup_file.relative_to(library_root)
        dest = _rejected(rejected_root, "Duplicates", rel)

        if canonical.exists():
            reason = f"Picard duplicate — canonical exists: {canonical.name}"
        else:
            reason = f"Picard duplicate — canonical NOT found (keeping anyway)"
            logger.warning("  No canonical for %s — moving to Uncertain", dup_file.name)
            dest = _rejected(rejected_root, "Uncertain", rel)

        entry = _log_entry("dedup", dup_file, dest, reason, dry_run)
        log.append(entry)

        verb = "Would move" if dry_run else "Moving"
        logger.info("  %s: %s → …%s%s", verb, dup_file.name, dest.parent.name, "/" + dest.name)

        if not dry_run:
            ok = _safe_move(dup_file, dest, dry_run=False)
            entry["ok"] = ok
            if ok:
                removed += 1
        else:
            removed += 1

    logger.info("Pass 1 complete: %d duplicate(s) %s.", removed,
                "would be moved" if dry_run else "moved")
    return log


# ---------------------------------------------------------------------------
# Pass 2 — guard sweep on remaining files
# ---------------------------------------------------------------------------

def pass2_guard(
    library_root: Path,
    rejected_root: Path,
    dry_run: bool,
) -> List[Dict[str, Any]]:
    """Run guard_file() on every audio file and route rejects."""
    log: List[Dict[str, Any]] = []
    scanned = rejected = 0

    logger.info("Pass 2: guard sweep in %s", library_root)

    for audio_file in sorted(library_root.rglob("*")):
        if not audio_file.is_file():
            continue
        if audio_file.suffix.lower() not in AUDIO_EXTENSIONS:
            continue

        scanned += 1
        result = guard_file(audio_file)

        if result.allowed:
            continue  # clean — keep it

        # Determine sub-folder
        cat = (result.rejection_category or "").lower()
        title = (result.title or audio_file.stem).lower()

        if cat in ("junk", "label"):
            sub = "Junk"
        elif "remix" in title or "tribute" in title or _REMIX_RE.search(title):
            sub = "Remixes"
        elif cat == "duplicate":
            sub = "Duplicates"
        else:
            sub = "Uncertain"

        rel  = audio_file.relative_to(library_root)
        dest = _rejected(rejected_root, sub, rel)
        reason = result.rejection_reason or f"guard blocked ({cat})"

        entry = _log_entry("guard", audio_file, dest, reason, dry_run)
        log.append(entry)

        verb = "Would reject" if dry_run else "Rejecting"
        logger.info("  %s [%s]: %s — %s", verb, sub, audio_file.name, reason)

        if not dry_run:
            ok = _safe_move(audio_file, dest, dry_run=False)
            entry["ok"] = ok
            if ok:
                rejected += 1
        else:
            rejected += 1

    logger.info(
        "Pass 2 complete: %d scanned, %d %s rejected.",
        scanned,
        rejected,
        "would be" if dry_run else "",
    )
    return log


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep A:\\Music — remove Picard duplicates + guard rejects."
    )
    parser.add_argument(
        "--library",
        default=str(LIBRARY_BASE),
        help="Library root to scan (default: LIBRARY_BASE from .env)",
    )
    parser.add_argument(
        "--rejected",
        default=str(REJECTED_FOLDER),
        help="Root for rejected files (default: REJECTED_FOLDER from .env)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute moves.  Without this flag the script is a dry run.",
    )
    parser.add_argument(
        "--skip-guard",
        action="store_true",
        help="Run duplicate pass only, skip guard sweep.",
    )
    args = parser.parse_args()

    library_root  = Path(args.library)
    rejected_root = Path(args.rejected)
    dry_run       = not args.apply

    if not library_root.exists():
        logger.error("Library root not found: %s", library_root)
        sys.exit(1)

    if dry_run:
        logger.info("DRY RUN — pass --apply to execute moves")
    else:
        logger.warning("APPLY MODE — files will be moved")

    all_log: List[Dict[str, Any]] = []

    all_log.extend(pass1_dedup(library_root, rejected_root, dry_run))

    if not args.skip_guard:
        all_log.extend(pass2_guard(library_root, rejected_root, dry_run))

    # Write jsonl log
    log_path = rejected_root / "_clean_log.jsonl"
    if not dry_run:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for entry in all_log:
                fh.write(json.dumps(entry) + "\n")
        logger.info("Log appended to %s", log_path)

    total = len(all_log)
    logger.info(
        "Summary: %d file(s) %s. Review A:\\Rejected\\ for anything you want to restore.",
        total,
        "would be moved" if dry_run else "moved",
    )


if __name__ == "__main__":
    main()

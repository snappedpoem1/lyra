"""scripts/fast_dedupe.py — Fast local-only deduplication sweep for A:\\Music.

No external API calls. Three passes:

  Pass 1 — Picard *(N).ext duplicates
            Find files matching "stem (N).ext" where canonical "stem.ext" exists.
            If canonical missing → move both to Uncertain for manual review.

  Pass 2 — Content-hash duplicates
            SHA-256 the first 64KB of every file (fast fingerprint).
            When 2+ files hash the same → keep lexicographically first path,
            move the rest to Duplicates.

  Pass 3 — Filename junk patterns (karaoke, tribute, lo-fi, 8-bit etc.)
            Pure regex on filename + path — zero network calls.

Usage:
  python scripts/fast_dedupe.py                 # dry run (safe default)
  python scripts/fast_dedupe.py --apply         # execute moves
  python scripts/fast_dedupe.py --apply --skip-junk   # dupes only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from oracle.config import LIBRARY_BASE, REJECTED_FOLDER

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

AUDIO_EXTS  = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aiff", ".wv"}
_PICARD_DUP = re.compile(r"^(.+?)\s*\((\d+)\)$")

JUNK_RE = re.compile(
    r"\b("
    r"karaoke|karaoke\s*version|instrumental\s*karaoke"
    r"|tribute|tribute\s*to|tribute\s*band|made\s*famous\s*by"
    r"|originally\s*performed|in\s*the\s*style\s*of"
    r"|backing\s*track|backing\s*version"
    r"|lo[_\-\s]?fi\s*(remix|version|edit|mix)?"
    r"|8[\s_\-]?bit\s*(remix|version|edit|mix)?"
    r"|nightcore|sped[\s_\-]?up|slowed[\s_\-]+(reverb)?"
    r"|acapella|a\s*cappella"
    r"|parody|spoof"
    r")",
    re.IGNORECASE,
)

ARTIST_JUNK_RE = re.compile(
    r"\b("
    r"party\s*tyme|prosource|karaoke|ameritz|zoom|stagetrack"
    r"|done\s*again|re[\-\s]?recorded|hit\s*crew"
    r"|the\s*tribute\s*artist|vevo$|[\s_-]topic$"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------

def _hash_quick(path: Path) -> str:
    """Hash three 64KB samples: start, middle, end + file size.

    FLAC files embed album art in the first ~200KB of metadata,
    so same-album tracks produce identical first-chunk hashes.
    Sampling three positions avoids that collision.
    """
    size = path.stat().st_size
    h = hashlib.sha256()
    h.update(str(size).encode())          # size is part of fingerprint
    chunk = 65536
    with path.open("rb") as fh:
        # Start (after potential ID3/FLAC front-matter, skip first 256KB)
        fh.seek(min(262144, max(0, size // 4)))
        h.update(fh.read(chunk))
        # Middle
        fh.seek(max(0, size // 2))
        h.update(fh.read(chunk))
        # End (last chunk)
        fh.seek(max(0, size - chunk))
        h.update(fh.read(chunk))
    return h.hexdigest()


def _safe_move(src: Path, dest: Path, dry_run: bool, log: List[Dict]) -> bool:
    entry = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "src": str(src),
        "dest": str(dest),
        "dry_run": dry_run,
    }
    if dry_run:
        log.append(entry)
        return True
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest = dest.with_name(dest.stem + "_dup2" + dest.suffix)
        shutil.move(str(src), str(dest))
        log.append(entry)
        return True
    except Exception as exc:
        logger.error("  MOVE FAILED %s → %s: %s", src.name, dest, exc)
        return False


# ---------------------------------------------------------------------------
# Pass 1 — Picard *(N) duplicates
# ---------------------------------------------------------------------------

def pass1_picard(library: Path, rejected: Path, dry_run: bool) -> Tuple[int, List[Dict]]:
    log: List[Dict] = []
    moved = 0
    logger.info("Pass 1: Picard *(N) duplicates …")

    for f in library.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in AUDIO_EXTS:
            continue
        m = _PICARD_DUP.match(f.stem)
        if not m:
            continue

        canonical = f.with_name(m.group(1).rstrip() + f.suffix)
        if canonical.exists():
            sub  = "Duplicates"
            why  = f"Picard dup of {canonical.name}"
        else:
            sub  = "Uncertain"
            why  = f"Picard dup but canonical missing"

        rel  = f.relative_to(library)
        dest = rejected / sub / rel
        verb = "Would move" if dry_run else "Moving"
        logger.info("  [%s] %s: %s", sub, verb, f.name)
        if _safe_move(f, dest, dry_run, log):
            log[-1]["reason"] = why
            moved += 1

    logger.info("Pass 1 done: %d %s.", moved, "would move" if dry_run else "moved")
    return moved, log


# ---------------------------------------------------------------------------
# Pass 2 — Content-hash duplicates
# ---------------------------------------------------------------------------

def pass2_hash(library: Path, rejected: Path, dry_run: bool) -> Tuple[int, List[Dict]]:
    log: List[Dict] = []
    moved = 0
    logger.info("Pass 2: content-hash duplicates …")

    hash_map: Dict[str, List[Path]] = defaultdict(list)
    all_files = [f for f in library.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTS]
    logger.info("  Hashing %d files …", len(all_files))

    for f in all_files:
        try:
            h = _hash_quick(f)
            hash_map[h].append(f)
        except Exception as exc:
            logger.warning("  Hash error %s: %s", f.name, exc)

    dupes = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    logger.info("  Found %d hash groups with duplicates.", len(dupes))

    for paths in dupes.values():
        # Keep the shortest path (closest to library root = most canonical)
        paths.sort(key=lambda p: (len(p.parts), str(p)))
        keeper = paths[0]
        for dup in paths[1:]:
            rel  = dup.relative_to(library)
            dest = rejected / "Duplicates" / rel
            verb = "Would move" if dry_run else "Moving"
            logger.info("  [Dup] %s: %s (keeping %s)", verb, dup.name, keeper.name)
            if _safe_move(dup, dest, dry_run, log):
                log[-1]["reason"] = f"content-hash dup of {keeper}"
                moved += 1

    logger.info("Pass 2 done: %d %s.", moved, "would move" if dry_run else "moved")
    return moved, log


# ---------------------------------------------------------------------------
# Pass 3 — Filename junk patterns
# ---------------------------------------------------------------------------

def pass3_junk(library: Path, rejected: Path, dry_run: bool) -> Tuple[int, List[Dict]]:
    log: List[Dict] = []
    moved = 0
    logger.info("Pass 3: filename junk patterns …")

    for f in library.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in AUDIO_EXTS:
            continue

        # Check file name + parent folder name
        target = f.stem + " " + f.parent.name
        artist_folder = f.parent.parent.name  # library/Artist/Album/file

        if ARTIST_JUNK_RE.search(artist_folder):
            sub = "Junk"
            why = f"Junk artist folder: {artist_folder}"
        elif JUNK_RE.search(target):
            m = JUNK_RE.search(target)
            sub = "Junk"
            why = f"Junk pattern: {m.group(0)}"
        else:
            continue

        rel  = f.relative_to(library)
        dest = rejected / sub / rel
        verb = "Would move" if dry_run else "Moving"
        logger.info("  [Junk] %s: %s — %s", verb, f.name, why)
        if _safe_move(f, dest, dry_run, log):
            log[-1]["reason"] = why
            moved += 1

    logger.info("Pass 3 done: %d %s.", moved, "would move" if dry_run else "moved")
    return moved, log


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fast local-only deduplication of A:\\Music")
    parser.add_argument("--library",   default=str(LIBRARY_BASE))
    parser.add_argument("--rejected",  default=str(REJECTED_FOLDER))
    parser.add_argument("--apply",     action="store_true")
    parser.add_argument("--skip-junk", action="store_true")
    parser.add_argument("--skip-hash", action="store_true")
    args = parser.parse_args()

    library  = Path(args.library)
    rejected = Path(args.rejected)
    dry_run  = not args.apply

    if not library.exists():
        logger.error("Library not found: %s", library)
        sys.exit(1)

    logger.info("%s — library: %s", "DRY RUN" if dry_run else "APPLY", library)

    all_log: List[Dict] = []

    n1, l1 = pass1_picard(library, rejected, dry_run)
    all_log.extend(l1)

    if not args.skip_hash:
        n2, l2 = pass2_hash(library, rejected, dry_run)
        all_log.extend(l2)
    else:
        n2 = 0

    if not args.skip_junk:
        n3, l3 = pass3_junk(library, rejected, dry_run)
        all_log.extend(l3)
    else:
        n3 = 0

    total = n1 + n2 + n3
    logger.info("\n=== Summary ===")
    logger.info("  Picard duplicates  : %d", n1)
    logger.info("  Content duplicates : %d", n2)
    logger.info("  Junk files         : %d", n3)
    logger.info("  Total              : %d %s", total, "would move" if dry_run else "moved")

    if not dry_run and all_log:
        log_path = rejected / "_dedupe_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for entry in all_log:
                fh.write(json.dumps(entry) + "\n")
        logger.info("  Log written: %s", log_path)

    if dry_run:
        logger.info("\nRun with --apply to execute. Review A:\\Rejected\\ to restore anything.")


if __name__ == "__main__":
    main()

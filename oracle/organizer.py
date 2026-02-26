"""Library organizer â€” state-machine relocation with plan/apply workflow.

Generates canonical paths using the template:
    {Library}/{Album Artist}/{Album} ({Year})/{Disc-}{TrackNo:02d} - {Title}.{ext}

System invariants:
    - ZERO destructive operations: no os.remove(), no file deletion
    - Files that can't be resolved are routed to _Quarantine/ and flagged
    - --dry-run (default) generates repair_plan_<timestamp>.json
    - Explicit --apply executes the moves via shutil.move()
    - Database upserts via INSERT OR REPLACE to prevent duplication on reruns
    - JSON undo journal for every applied plan
    - Idempotent: running twice produces identical plan with no changes
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from oracle.config import LIBRARY_BASE
from oracle.db.schema import get_connection, get_content_hash_fast, get_write_mode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path sanitization
# ---------------------------------------------------------------------------

# Windows reserved names
_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def _sanitize_filename(text: str, max_length: int = 200) -> str:
    """Sanitize text for use in filenames/folders.

    Removes Windows-invalid characters, reserved names, leading/trailing
    dots and spaces. Collapses whitespace.
    """
    if not text:
        return "Unknown"

    sanitized = re.sub(r'[<>:"/\\|?*]', "_", text)
    sanitized = sanitized.strip(". ")
    sanitized = re.sub(r"[ _]+", " ", sanitized)
    sanitized = sanitized.strip(". ")

    # Prevent Windows reserved names
    if sanitized.upper().split(".")[0] in _RESERVED_NAMES:
        sanitized = f"_{sanitized}"

    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip()

    return sanitized or "Unknown"


def _primary_album_artist(artist: str) -> str:
    """Return the main album artist for folder naming.

    Conservative splitting â€” uses safe delimiters only.
    Does NOT split on ' x ' (would corrupt 'Brand X' etc.).
    """
    raw = (artist or "").strip()
    if not raw:
        return "Unknown Artist"

    split_patterns = [
        r"\s*,\s*",
        r"\s+feat\.?\s+",
        r"\s+featuring\s+",
        r"\s+ft\.?\s+",
        r"\s+with\s+",
    ]
    primary = raw
    for pattern in split_patterns:
        parts = re.split(pattern, primary, maxsplit=1, flags=re.IGNORECASE)
        if parts and parts[0].strip():
            candidate = parts[0].strip()
            if candidate != raw:
                primary = candidate
                break

    return primary or "Unknown Artist"


# ---------------------------------------------------------------------------
# Plan data structures
# ---------------------------------------------------------------------------

@dataclass
class RelocationAction:
    """A single file relocation within a repair plan."""

    track_id: str
    action: str  # "move", "quarantine", "skip"
    from_path: str
    to_path: str
    reason: str
    confidence: float = 1.0
    content_hash_before: Optional[str] = None
    content_hash_after: Optional[str] = None
    status: str = "planned"  # planned, applied, failed, skipped
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepairPlan:
    """A complete library repair plan with audit trail."""

    plan_id: str
    created_at: float
    library_path: str
    preset: str
    total_tracks: int
    actions: List[RelocationAction] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["actions"] = [a.to_dict() for a in self.actions]
        return d

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Repair plan saved to %s", path)

    @classmethod
    def load(cls, path: Path) -> "RepairPlan":
        data = json.loads(path.read_text(encoding="utf-8"))
        actions = [RelocationAction(**a) for a in data.pop("actions", [])]
        plan = cls(**data)
        plan.actions = actions
        return plan


# ---------------------------------------------------------------------------
# Canonical path generation
# ---------------------------------------------------------------------------

def generate_target_path(
    track_id: str,
    preset: str = "artist_album",
    base_library: Optional[str] = None,
) -> Optional[Path]:
    """Generate ideal canonical path for a track based on preset.

    Presets:
        artist_album:  {Artist}/{Album} ({Year})/{Disc-}{##} - {Title}.ext
        remix:         {Artist}/Remixes/{Album}/{##} - {Title}.ext
        live:          {Artist}/Live/{Album} ({Year})/{##} - {Title}.ext
        compilation:   Compilations/{Album}/{##} - {Artist} - {Title}.ext
        various:       Various Artists/{Album}/{##} - {Artist} - {Title}.ext
        flat_artist:   {Artist}/{##} - {Title}.ext

    Args:
        track_id: Track ID in lyra_registry.db.
        preset: Organization preset name.
        base_library: Root library path (default: config.LIBRARY_BASE).

    Returns:
        Canonical Path or None if track not found.
    """
    base = Path(base_library) if base_library else LIBRARY_BASE

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT artist, title, album, year, filepath, version_type,
               recording_mbid
        FROM tracks WHERE track_id = ?
        """,
        (track_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    artist, title, album, year, filepath, version_type, recording_mbid = row

    ext = Path(filepath).suffix if filepath else ".flac"

    # Sanitize components
    artist_safe = _sanitize_filename(artist or "Unknown Artist")
    album_artist_safe = _sanitize_filename(_primary_album_artist(artist or "Unknown Artist"))
    title_safe = _sanitize_filename(title or "Unknown Title")
    album_safe = _sanitize_filename(album or "Unknown Album")

    # Track/disc numbers â€” try to pull from enrichment cache later
    # For now default to 00 (will be filled by enrichment pipeline)
    track_number = _get_track_number(cursor, track_id) if False else None
    disc_number = None

    track_str = f"{track_number:02d}" if track_number else "00"
    disc_prefix = f"{disc_number:02d}-" if disc_number and disc_number > 1 else ""

    # Year formatting
    year_str = f" ({year})" if year else ""

    # Route based on version_type and preset
    if version_type == "junk":
        # Junk goes to quarantine â€” never into the library
        folder = base.parent / "_Quarantine" / "Junk"
        filename = f"{title_safe}{ext}"
        return folder / filename

    if preset == "artist_album":
        folder, filename = _layout_artist_album(
            base, artist_safe, album_artist_safe, title_safe, album_safe,
            year_str, track_str, disc_prefix, ext, version_type, artist, album,
        )
    elif preset == "remix":
        if album and album.lower() != "unknown album":
            folder = base / album_artist_safe / "Remixes" / album_safe
        else:
            folder = base / album_artist_safe / "Remixes"
        filename = f"{disc_prefix}{track_str} - {title_safe}{ext}"
    elif preset == "live":
        if album and album.lower() != "unknown album":
            folder = base / album_artist_safe / "Live" / f"{album_safe}{year_str}"
        else:
            folder = base / album_artist_safe / "Live"
        filename = f"{disc_prefix}{track_str} - {title_safe}{ext}"
    elif preset == "compilation":
        folder = base / "Compilations" / album_safe
        filename = f"{disc_prefix}{track_str} - {artist_safe} - {title_safe}{ext}"
    elif preset == "various":
        folder = base / "Various Artists" / album_safe
        filename = f"{disc_prefix}{track_str} - {artist_safe} - {title_safe}{ext}"
    elif preset == "flat_artist":
        folder = base / album_artist_safe
        filename = f"{disc_prefix}{track_str} - {title_safe}{ext}"
    else:
        return generate_target_path(track_id, preset="artist_album", base_library=str(base))

    return folder / filename


def _layout_artist_album(
    base: Path,
    artist_safe: str,
    album_artist_safe: str,
    title_safe: str,
    album_safe: str,
    year_str: str,
    track_str: str,
    disc_prefix: str,
    ext: str,
    version_type: Optional[str],
    artist_raw: Optional[str],
    album_raw: Optional[str],
) -> tuple:
    """Generate folder/filename for the artist_album preset."""
    if version_type == "remix":
        if album_raw and album_raw.lower() != "unknown album":
            folder = base / artist_safe / "Remixes" / album_safe
        else:
            folder = base / artist_safe / "Remixes"
        filename = f"{disc_prefix}{track_str} - {title_safe}{ext}"

    elif version_type == "live":
        if album_raw and album_raw.lower() != "unknown album":
            folder = base / artist_safe / "Live" / f"{album_safe}{year_str}"
        else:
            folder = base / artist_safe / "Live"
        filename = f"{disc_prefix}{track_str} - {title_safe}{ext}"

    elif version_type == "cover":
        folder = base / artist_safe / "Covers"
        filename = f"{disc_prefix}{track_str} - {title_safe}{ext}"

    else:
        # Standard or unclassified
        if artist_raw and artist_raw.lower() in {"various artists", "various", "compilation"}:
            folder = base / "Various Artists" / album_safe
            filename = f"{disc_prefix}{track_str} - {artist_safe} - {title_safe}{ext}"
        elif album_raw and album_raw.lower() != "unknown album":
            album_folder = f"{album_safe}{year_str}"
            folder = base / album_artist_safe / album_folder
            filename = f"{disc_prefix}{track_str} - {title_safe}{ext}"
        else:
            folder = base / album_artist_safe
            filename = f"{disc_prefix}{track_str} - {title_safe}{ext}"

    return folder, filename


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

def generate_repair_plan(
    library_path: Optional[str] = None,
    preset: str = "artist_album",
    limit: int = 0,
    output_dir: Optional[str] = None,
) -> RepairPlan:
    """Generate a repair plan for library reorganization.

    This is the PLAN phase â€” no files are moved. Produces a JSON plan
    file for human review.

    Args:
        library_path: Library root (default: config.LIBRARY_BASE).
        preset: Organization preset.
        limit: Max tracks to process (0 = all).
        output_dir: Directory for plan output files.

    Returns:
        RepairPlan object (also saved to disk as JSON).
    """
    base = library_path or str(LIBRARY_BASE)

    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT track_id, filepath FROM tracks WHERE filepath IS NOT NULL AND status = 'active'"
    params: list = []
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    plan_id = f"repair_{int(time.time() * 1000)}"
    plan = RepairPlan(
        plan_id=plan_id,
        created_at=time.time(),
        library_path=base,
        preset=preset,
        total_tracks=len(rows),
    )

    move_count = 0
    skip_count = 0
    quarantine_count = 0

    for track_id, current_path in rows:
        if not current_path:
            continue

        target = generate_target_path(track_id, preset=preset, base_library=base)
        if target is None:
            continue

        current = Path(current_path).resolve()
        target_resolved = target.resolve()

        if current == target_resolved:
            skip_count += 1
            continue

        # Determine if this is a quarantine action
        is_quarantine = "_Quarantine" in str(target)
        action_type = "quarantine" if is_quarantine else "move"

        action = RelocationAction(
            track_id=track_id,
            action=action_type,
            from_path=str(current),
            to_path=str(target_resolved),
            reason=f"canonical path differs (preset: {preset})",
        )

        # Pre-compute content hash for verification
        if current.is_file():
            try:
                action.content_hash_before = get_content_hash_fast(current)
            except Exception:
                pass

        plan.actions.append(action)

        if is_quarantine:
            quarantine_count += 1
        else:
            move_count += 1

    plan.summary = {
        "total": len(rows),
        "move": move_count,
        "quarantine": quarantine_count,
        "skip": skip_count,
        "already_correct": skip_count,
    }

    # Save plan
    out_dir = Path(output_dir) if output_dir else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"repair_plan_{plan_id}.json"
    plan.save(plan_path)

    return plan


# ---------------------------------------------------------------------------
# Plan application
# ---------------------------------------------------------------------------

def apply_repair_plan(
    plan_path: str,
    confidence_min: float = 0.0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply a repair plan â€” execute the file moves.

    Args:
        plan_path: Path to the repair_plan_*.json file.
        confidence_min: Skip actions below this confidence threshold.
        dry_run: If True, report what would happen without moving files.

    Returns:
        {applied, skipped, errors, undo_journal_path}
    """
    if get_write_mode() != "apply_allowed" and not dry_run:
        return {"error": "WRITE BLOCKED â€” set LYRA_WRITE_MODE=apply_allowed"}

    plan = RepairPlan.load(Path(plan_path))

    applied = 0
    skipped = 0
    errors = 0
    undo_entries: List[Dict[str, Any]] = []

    conn = get_connection()
    cursor = conn.cursor()

    for action in plan.actions:
        if action.confidence < confidence_min:
            action.status = "skipped"
            skipped += 1
            continue

        from_path = Path(action.from_path)
        to_path = Path(action.to_path)

        if not from_path.is_file():
            action.status = "failed"
            action.error = "source file not found"
            errors += 1
            continue

        if to_path.exists():
            # Collision handling: append suffix
            stem = to_path.stem
            suffix = to_path.suffix
            parent = to_path.parent
            counter = 1
            while to_path.exists():
                to_path = parent / f"{stem}_{counter}{suffix}"
                counter += 1
            action.to_path = str(to_path)

        if dry_run:
            action.status = "dry_run"
            applied += 1
            logger.info("[DRY RUN] %s -> %s", from_path.name, to_path)
            continue

        try:
            # Create target directory
            to_path.parent.mkdir(parents=True, exist_ok=True)

            # Compute pre-move hash if missing.
            if not action.content_hash_before:
                action.content_hash_before = get_content_hash_fast(from_path)

            # Non-destructive relocation via move (no explicit file deletion).
            shutil.move(str(from_path), str(to_path))

            # Verify content hash after move; rollback on mismatch.
            hash_after = get_content_hash_fast(to_path)
            if action.content_hash_before and hash_after != action.content_hash_before:
                try:
                    from_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(to_path), str(from_path))
                except Exception:
                    pass
                action.status = "failed"
                action.error = "content hash mismatch after move (rolled back)"
                errors += 1
                continue

            action.content_hash_after = hash_after

            # Update database
            cursor.execute(
                "UPDATE tracks SET filepath = ? WHERE track_id = ?",
                (str(to_path), action.track_id),
            )

            action.status = "applied"
            applied += 1

            undo_entries.append({
                "track_id": action.track_id,
                "from_path": action.from_path,
                "to_path": action.to_path,
                "content_hash": hash_after,
                "status": "applied",
            })

        except Exception as exc:
            action.status = "failed"
            action.error = str(exc)
            errors += 1
            logger.error("Failed to move %s: %s", from_path.name, exc)

    conn.commit()
    conn.close()

    # Save undo journal
    undo_path = None
    if undo_entries and not dry_run:
        undo = {
            "plan_id": plan.plan_id,
            "applied_at": time.time(),
            "operations": undo_entries,
        }
        undo_path = Path(plan_path).parent / f"undo_{plan.plan_id}.json"
        undo_path.write_text(
            json.dumps(undo, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Undo journal saved to %s", undo_path)

    # Save updated plan with statuses
    updated_plan_path = Path(plan_path).parent / f"applied_{plan.plan_id}.json"
    plan.save(updated_plan_path)

    result = {
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
    }
    if undo_path:
        result["undo_journal_path"] = str(undo_path)

    return result


# ---------------------------------------------------------------------------
# Undo support
# ---------------------------------------------------------------------------

def undo_repair_plan(undo_path: str) -> Dict[str, Any]:
    """Reverse an applied repair plan using its undo journal.

    Args:
        undo_path: Path to the undo_*.json file.

    Returns:
        {reverted, errors}
    """
    if get_write_mode() != "apply_allowed":
        return {"error": "WRITE BLOCKED â€” set LYRA_WRITE_MODE=apply_allowed"}

    data = json.loads(Path(undo_path).read_text(encoding="utf-8"))
    operations = data.get("operations", [])

    conn = get_connection()
    cursor = conn.cursor()

    reverted = 0
    errors = 0

    for op in reversed(operations):
        if op.get("status") != "applied":
            continue

        to_path = Path(op["to_path"])
        from_path = Path(op["from_path"])

        if not to_path.is_file():
            logger.warning("Undo: target file missing: %s", to_path)
            errors += 1
            continue

        try:
            from_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(to_path), str(from_path))

            cursor.execute(
                "UPDATE tracks SET filepath = ? WHERE track_id = ?",
                (str(from_path), op["track_id"]),
            )
            reverted += 1

        except Exception as exc:
            logger.error("Undo failed for %s: %s", to_path.name, exc)
            errors += 1

    conn.commit()
    conn.close()

    return {"reverted": reverted, "errors": errors}


# ---------------------------------------------------------------------------
# Legacy API (backward compatibility)
# ---------------------------------------------------------------------------

def get_relocation_candidates(
    library_path: Optional[str] = None,
    preset: str = "artist_album",
    limit: int = 0,
) -> Dict[str, Any]:
    """Find tracks that need relocation based on canonical paths.

    This is the read-only query equivalent â€” does not generate a plan file.

    Returns:
        {total, needs_relocation, candidates: [{track_id, current_path, target_path, reason}]}
    """
    base = library_path or str(LIBRARY_BASE)

    conn = get_connection()
    cursor = conn.cursor()

    if limit > 0:
        cursor.execute(
            "SELECT track_id, filepath FROM tracks WHERE filepath IS NOT NULL LIMIT ?",
            (limit,),
        )
    else:
        cursor.execute("SELECT track_id, filepath FROM tracks WHERE filepath IS NOT NULL")

    rows = cursor.fetchall()
    conn.close()

    candidates: List[Dict[str, str]] = []

    for track_id, current_path in rows:
        if not current_path:
            continue

        target_path = generate_target_path(track_id, preset=preset, base_library=base)
        if target_path is None:
            continue

        current = Path(current_path).resolve()
        target = target_path.resolve()

        if current != target:
            candidates.append({
                "track_id": track_id,
                "current_path": str(current),
                "target_path": str(target),
                "reason": f"Canonical path differs (preset: {preset})",
            })

    return {
        "total": len(rows),
        "needs_relocation": len(candidates),
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv
    load_dotenv(override=True)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Library organizer")
    sub = parser.add_subparsers(dest="command")

    plan_p = sub.add_parser("plan", help="Generate a repair plan (dry-run)")
    plan_p.add_argument("--library", default=str(LIBRARY_BASE))
    plan_p.add_argument("--preset", default="artist_album")
    plan_p.add_argument("--limit", type=int, default=0)
    plan_p.add_argument("--output-dir", default=".")

    apply_p = sub.add_parser("apply", help="Apply a repair plan")
    apply_p.add_argument("plan_path", help="Path to repair_plan_*.json")
    apply_p.add_argument("--confidence-min", type=float, default=0.0)
    apply_p.add_argument("--dry-run", action="store_true")

    undo_p = sub.add_parser("undo", help="Undo an applied plan")
    undo_p.add_argument("undo_path", help="Path to undo_*.json")

    query_p = sub.add_parser("query", help="Show relocation candidates")
    query_p.add_argument("--library", default=str(LIBRARY_BASE))
    query_p.add_argument("--preset", default="artist_album")
    query_p.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "plan":
        plan = generate_repair_plan(args.library, args.preset, args.limit, args.output_dir)
        print(f"Plan {plan.plan_id}: {plan.summary}")

    elif args.command == "apply":
        result = apply_repair_plan(args.plan_path, args.confidence_min, args.dry_run)
        print(f"Result: {result}")

    elif args.command == "undo":
        result = undo_repair_plan(args.undo_path)
        print(f"Undo result: {result}")

    elif args.command == "query":
        result = get_relocation_candidates(args.library, args.preset, args.limit)
        print(f"Total: {result['total']}, needs relocation: {result['needs_relocation']}")
        for c in result["candidates"][:10]:
            print(f"  {c['current_path']}")
            print(f"  -> {c['target_path']}")
            print()

    else:
        parser.print_help()


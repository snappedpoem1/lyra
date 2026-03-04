"""Guarded Import Processor - Screen files BEFORE they enter the library.

This is the final checkpoint. Any file entering the library must pass through here.
Runs the full guard check on existing files in downloads/staging folders.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

import mutagen

from oracle.acquirers.guard import guard_file, move_rejected_file, GuardResult
from oracle.config import LIBRARY_BASE, REJECTED_FOLDER

logger = logging.getLogger(__name__)

# Audio file extensions we care about
AUDIO_EXTENSIONS: Set[str] = {
    ".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".wma", ".aiff",
}


def _extract_metadata(filepath: Path) -> Dict[str, str]:
    """Extract metadata from audio file."""
    try:
        audio = mutagen.File(str(filepath), easy=True)
        if audio:
            return {
                "artist": audio.get("artist", [""])[0] if audio.get("artist") else "",
                "title": audio.get("title", [""])[0] if audio.get("title") else "",
                "album": audio.get("album", [""])[0] if audio.get("album") else "",
            }
    except Exception:
        pass
    
    # Fall back to filename parsing
    stem = filepath.stem
    if " - " in stem:
        parts = stem.split(" - ", 1)
        return {
            "artist": parts[0].strip(),
            "title": parts[1].strip() if len(parts) > 1 else "",
            "album": "",
        }
    
    return {"artist": "", "title": stem, "album": ""}


def _sanitize_filename(s: str) -> str:
    """Remove problematic characters from filename."""
    import re
    s = re.sub(r'[<>:"/\\|?*]', '_', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:200]  # Max filename length


def scan_folder(
    folder: Path,
    recursive: bool = False,
) -> List[Tuple[Path, GuardResult]]:
    """Scan folder and run guard check on all audio files.
    
    Returns:
        List of (filepath, GuardResult) tuples
    """
    results = []
    
    if recursive:
        files = folder.rglob("*")
    else:
        files = folder.iterdir()
    
    for filepath in files:
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        
        result = guard_file(filepath)
        results.append((filepath, result))
    
    return results


def process_downloads(
    downloads_folder: Path,
    library_folder: Path,
    dry_run: bool = False,
    delete_rejected: bool = False,
    min_confidence: float = 0.3,
) -> Dict:
    """Process downloads folder with guard checks.
    
    For each file:
    1. Run guard check
    2. If rejected: optionally delete or move to quarantine
    3. If allowed: rename to clean format and move to library
    
    Returns:
        Summary dict with counts and details
    """
    downloads_folder = Path(downloads_folder)
    library_folder = Path(library_folder)

    if not downloads_folder.exists():
        return {"error": f"Downloads folder not found: {downloads_folder}"}
    
    results = scan_folder(downloads_folder, recursive=True)
    
    summary = {
        "total": len(results),
        "imported": 0,
        "rejected": 0,
        "low_confidence": 0,
        "errors": 0,
        "imported_files": [],
        "rejected_files": [],
        "low_confidence_files": [],
    }
    
    for filepath, guard_result in results:
        action_taken = "none"
        
        if not guard_result.allowed:
            # REJECTED
            summary["rejected"] += 1
            summary["rejected_files"].append({
                "file": str(filepath),
                "reason": guard_result.rejection_reason,
                "category": guard_result.rejection_category,
            })
            
            if not dry_run:
                if delete_rejected:
                    try:
                        filepath.unlink()
                        action_taken = "deleted"
                    except Exception as e:
                        logger.error(f"Failed to delete {filepath}: {e}")
                        action_taken = "delete_failed"
                else:
                    # Route to REJECTED_FOLDER sub-directory via guard helper
                    dest = move_rejected_file(filepath, guard_result)
                    action_taken = "rejected" if dest else "reject_failed"
            
            logger.info(f"âŒ REJECTED: {filepath.name[:50]} â†’ {guard_result.rejection_reason[:40]} ({action_taken})")
            
        elif guard_result.confidence < min_confidence:
            # LOW CONFIDENCE - move to quarantine for manual review
            summary["low_confidence"] += 1
            summary["low_confidence_files"].append({
                "file": str(filepath),
                "confidence": guard_result.confidence,
                "artist": guard_result.artist,
                "title": guard_result.title,
                "warnings": guard_result.warnings,
            })
            
            if not dry_run:
                try:
                    uncertain = REJECTED_FOLDER / "Uncertain"
                    uncertain.mkdir(parents=True, exist_ok=True)
                    dest = uncertain / filepath.name
                    shutil.move(str(filepath), str(dest))
                    action_taken = "moved_uncertain"
                except Exception as e:
                    logger.error(f"Failed to move low-confidence file {filepath}: {e}")

            logger.warning(f"⚠️ LOW CONFIDENCE ({guard_result.confidence:.0%}): {filepath.name[:50]} ({action_taken})")
            
        else:
            # ALLOWED - import to library
            try:
                # Create clean filename
                clean_name = f"{guard_result.artist} - {guard_result.title}{filepath.suffix}"
                clean_name = _sanitize_filename(clean_name)
                
                dest = library_folder / clean_name
                
                # Handle collision
                if dest.exists():
                    # Check if it's truly a duplicate
                    summary["errors"] += 1
                    logger.warning(f"âš ï¸ File exists: {clean_name}")
                    continue
                
                if not dry_run:
                    library_folder.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(filepath), str(dest))
                    action_taken = "imported"
                else:
                    action_taken = "would_import"
                
                summary["imported"] += 1
                summary["imported_files"].append({
                    "source": str(filepath),
                    "destination": str(dest),
                    "artist": guard_result.artist,
                    "title": guard_result.title,
                    "confidence": guard_result.confidence,
                    "validated_by": guard_result.validated_by,
                })
                
                logger.info(f"âœ… IMPORTED: {guard_result.artist} - {guard_result.title} ({guard_result.confidence:.0%})")
                
            except Exception as e:
                summary["errors"] += 1
                logger.error(f"Failed to import {filepath}: {e}")
    
    return summary


def audit_library(library_folder: Path) -> Dict:
    """Audit existing library for junk that slipped through.
    
    Useful for cleaning up libraries that were populated before guard was added.
    """
    library_folder = Path(library_folder)
    results = scan_folder(library_folder, recursive=True)
    
    junk = []
    clean = []
    
    for filepath, guard_result in results:
        if not guard_result.allowed:
            junk.append({
                "file": str(filepath),
                "reason": guard_result.rejection_reason,
                "category": guard_result.rejection_category,
            })
        else:
            clean.append({
                "file": str(filepath),
                "artist": guard_result.artist,
                "title": guard_result.title,
                "confidence": guard_result.confidence,
            })
    
    return {
        "total": len(results),
        "clean": len(clean),
        "junk": len(junk),
        "junk_files": junk,
    }


def quarantine_junk(library_folder: Path, dry_run: bool = True) -> Dict:
    """Find and quarantine junk files in library.
    
    Default is dry_run=True for safety.
    """
    library_folder = Path(library_folder)
    quarantine_folder = library_folder.parent / "quarantine"
    
    audit = audit_library(library_folder)
    
    if dry_run:
        return {
            "dry_run": True,
            "would_quarantine": len(audit["junk_files"]),
            "files": audit["junk_files"],
        }
    
    quarantined = 0
    errors = 0
    
    for item in audit["junk_files"]:
        filepath = Path(item["file"])
        try:
            quarantine_folder.mkdir(parents=True, exist_ok=True)
            dest = quarantine_folder / filepath.name
            if dest.exists():
                dest = quarantine_folder / f"{filepath.stem}_{int(time.time())}{filepath.suffix}"
            shutil.move(str(filepath), str(dest))
            quarantined += 1
            logger.info(f"Quarantined: {filepath.name}")
        except Exception as e:
            errors += 1
            logger.error(f"Failed to quarantine {filepath}: {e}")
    
    return {
        "quarantined": quarantined,
        "errors": errors,
    }


if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    parser = argparse.ArgumentParser(description="Guarded Import Processor")
    parser.add_argument("command", choices=["scan", "import", "audit", "quarantine"])
    parser.add_argument("--downloads", default="downloads", help="Downloads folder")
    parser.add_argument("--library", default=str(LIBRARY_BASE))
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--delete-rejected", action="store_true", help="Delete rejected files")
    parser.add_argument("--min-confidence", type=float, default=0.3)
    
    args = parser.parse_args()
    
    downloads = Path(args.downloads)
    library = Path(args.library)
    
    if args.command == "scan":
        results = scan_folder(downloads)
        print(f"\n{'='*60}")
        print(f"SCAN RESULTS: {downloads}")
        print(f"{'='*60}")
        
        allowed = [r for r in results if r[1].allowed]
        rejected = [r for r in results if not r[1].allowed]
        
        print(f"\nTotal: {len(results)}")
        print(f"Allowed: {len(allowed)}")
        print(f"Rejected: {len(rejected)}")
        
        if rejected:
            print("\nâŒ REJECTED:")
            for filepath, result in rejected:
                print(f"  â€¢ {filepath.name[:50]}")
                print(f"    Reason: {result.rejection_reason}")
        
        if allowed:
            print("\nâœ… ALLOWED:")
            for filepath, result in allowed[:10]:
                print(f"  â€¢ {result.artist[:25]:25s} - {result.title[:30]}")
            if len(allowed) > 10:
                print(f"  ... and {len(allowed) - 10} more")
    
    elif args.command == "import":
        summary = process_downloads(
            downloads,
            library,
            dry_run=args.dry_run,
            delete_rejected=args.delete_rejected,
            min_confidence=args.min_confidence,
        )
        
        print(f"\n{'='*60}")
        print("IMPORT SUMMARY")
        print(f"{'='*60}")
        print(f"Total scanned: {summary.get('total', 0)}")
        print(f"Imported: {summary.get('imported', 0)}")
        print(f"Rejected: {summary.get('rejected', 0)}")
        print(f"Low confidence: {summary.get('low_confidence', 0)}")
        print(f"Errors: {summary.get('errors', 0)}")
        
        if args.dry_run:
            print("\n(DRY RUN - no changes made)")
    
    elif args.command == "audit":
        audit = audit_library(library)
        
        print(f"\n{'='*60}")
        print(f"LIBRARY AUDIT: {library}")
        print(f"{'='*60}")
        print(f"Total tracks: {audit['total']}")
        print(f"Clean: {audit['clean']}")
        print(f"Junk: {audit['junk']}")
        
        if audit["junk_files"]:
            print("\nâŒ JUNK FILES:")
            for item in audit["junk_files"][:20]:
                filepath = Path(item["file"])
                print(f"  â€¢ {filepath.name[:50]}")
                print(f"    Reason: {item['reason']}")
            if len(audit["junk_files"]) > 20:
                print(f"  ... and {len(audit['junk_files']) - 20} more")
    
    elif args.command == "quarantine":
        result = quarantine_junk(library, dry_run=args.dry_run)
        
        print(f"\n{'='*60}")
        print("QUARANTINE RESULTS")
        print(f"{'='*60}")
        
        if result.get("dry_run"):
            print(f"Would quarantine: {result.get('would_quarantine', 0)} files")
            print("\n(DRY RUN - use without --dry-run to execute)")
        else:
            print(f"Quarantined: {result.get('quarantined', 0)}")
            print(f"Errors: {result.get('errors', 0)}")

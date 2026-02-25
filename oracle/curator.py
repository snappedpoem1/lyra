"""Curation plan generator and executor."""

from __future__ import annotations

import csv
import json
import shutil
import time
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

from oracle.config import LIBRARY_BASE
from oracle.db.schema import get_connection, get_write_mode, get_content_hash_fast
from oracle.classifier import classify_track
from oracle.organizer import generate_target_path


def generate_plan(
    library_path: str = str(LIBRARY_BASE),
    preset: str = "artist_album",
    classify_first: bool = True,
    limit: int = 0,
    output_dir: str = "Reports"
) -> Dict:
    """
    Generate curation plan for library reorganization.
    
    Args:
        library_path: Library root path
        preset: Organization preset (artist_album, remix, live, etc.)
        classify_first: Run classifier before generating plan
        limit: Max tracks to process (0 = all)
        output_dir: Directory for plan files
        
    Returns:
        {
            "plan_id": str (timestamp),
            "total_tracks": int,
            "actions": [action dicts],
            "summary": {action_type: count}
        }
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get tracks
    if limit > 0:
        cursor.execute(
            "SELECT track_id, filepath, version_type, confidence FROM tracks WHERE filepath IS NOT NULL LIMIT ?",
            (limit,)
        )
    else:
        cursor.execute(
            "SELECT track_id, filepath, version_type, confidence FROM tracks WHERE filepath IS NOT NULL"
        )
    
    tracks = cursor.fetchall()
    conn.close()
    
    # Classify if requested
    if classify_first:
        print(f"Classifying {len(tracks)} tracks...")
        for track_id, _, _, _ in tracks:
            classify_track(track_id)
        
        # Re-fetch with updated classifications
        conn = get_connection()
        cursor = conn.cursor()
        if limit > 0:
            cursor.execute(
                "SELECT track_id, filepath, version_type, confidence FROM tracks WHERE filepath IS NOT NULL LIMIT ?",
                (limit,)
            )
        else:
            cursor.execute(
                "SELECT track_id, filepath, version_type, confidence FROM tracks WHERE filepath IS NOT NULL"
            )
        tracks = cursor.fetchall()
        conn.close()
    
    # Generate plan
    plan_id = time.strftime("%Y%m%d_%H%M%S")
    actions = []
    summary = {
        "move": 0,
        "rename": 0,
        "quarantine": 0,
        "ignore": 0,
        "metadata_update": 0
    }
    
    print(f"Generating plan for {len(tracks)} tracks...")
    
    for track_id, filepath, version_type, confidence in tracks:
        if not filepath:
            continue
        
        current_path = Path(filepath).resolve()
        
        # Check if file exists
        if not current_path.exists():
            actions.append({
                "track_id": track_id,
                "action": "ignore",
                "from_path": str(current_path),
                "to_path": None,
                "reason": "File not found",
                "confidence": 0.0
            })
            summary["ignore"] += 1
            continue
        
        # Generate target path
        target_path = generate_target_path(track_id, preset=preset, base_library=library_path)
        
        if target_path is None:
            actions.append({
                "track_id": track_id,
                "action": "ignore",
                "from_path": str(current_path),
                "to_path": None,
                "reason": "Could not generate target path",
                "confidence": 0.0
            })
            summary["ignore"] += 1
            continue
        
        target_path = target_path.resolve()
        
        # Quarantine junk files
        if version_type == "junk":
            quarantine_dir = Path(library_path).parent / "_Quarantine" / "Junk"
            quarantine_path = quarantine_dir / current_path.name
            
            actions.append({
                "track_id": track_id,
                "action": "quarantine",
                "from_path": str(current_path),
                "to_path": str(quarantine_path),
                "reason": f"Junk file (confidence: {confidence:.2f})",
                "confidence": confidence or 0.7
            })
            summary["quarantine"] += 1
            continue
        
        # Check if already in correct location
        if current_path == target_path:
            actions.append({
                "track_id": track_id,
                "action": "ignore",
                "from_path": str(current_path),
                "to_path": str(target_path),
                "reason": "Already in correct location",
                "confidence": 1.0
            })
            summary["ignore"] += 1
            continue
        
        # Check if only filename differs (same directory)
        if current_path.parent == target_path.parent:
            actions.append({
                "track_id": track_id,
                "action": "rename",
                "from_path": str(current_path),
                "to_path": str(target_path),
                "reason": f"Rename to canonical filename (preset: {preset})",
                "confidence": confidence or 0.8
            })
            summary["rename"] += 1
        else:
            # Different directory: move
            actions.append({
                "track_id": track_id,
                "action": "move",
                "from_path": str(current_path),
                "to_path": str(target_path),
                "reason": f"Move to canonical location (preset: {preset}, version: {version_type})",
                "confidence": confidence or 0.7
            })
            summary["move"] += 1
    
    plan = {
        "plan_id": plan_id,
        "created_at": time.time(),
        "library_path": library_path,
        "preset": preset,
        "total_tracks": len(tracks),
        "actions": actions,
        "summary": summary
    }
    
    # Save plan
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    
    # Save JSON (truth)
    json_path = output / f"curation_plan_{plan_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    
    # Save CSV (human-readable)
    csv_path = output / f"curation_plan_{plan_id}.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "track_id", "action", "from_path", "to_path", "reason", "confidence"
        ])
        writer.writeheader()
        writer.writerows(actions)
    
    print(f"\nPlan generated: {plan_id}")
    print(f"  JSON: {json_path}")
    print(f"  CSV: {csv_path}")
    print(f"\nSummary:")
    for action_type, count in summary.items():
        if count > 0:
            print(f"  {action_type}: {count}")
    
    # Store plan in database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO curation_plans (plan_id, created_at, plan_json)
        VALUES (?, ?, ?)
        """,
        (plan_id, time.time(), json.dumps(plan))
    )
    conn.commit()
    conn.close()
    
    return plan


def apply_plan(
    plan_path: str,
    confidence_min: float = 0.5,
    dry_run: bool = False
) -> Dict:
    """
    Apply a curation plan.
    
    Args:
        plan_path: Path to plan JSON file
        confidence_min: Minimum confidence to execute action
        dry_run: If True, don't actually move files
        
    Returns:
        {
            "applied": int,
            "skipped": int,
            "errors": int,
            "journal_path": str
        }
    """
    # Check write mode
    if get_write_mode() != "apply_allowed" and not dry_run:
        return {"error": "WRITE BLOCKED: set LYRA_WRITE_MODE=apply_allowed to apply plans"}
    
    # Load plan
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    
    plan_id = plan["plan_id"]
    actions = plan["actions"]
    
    # Journal for undo
    journal = {
        "plan_id": plan_id,
        "applied_at": time.time(),
        "dry_run": dry_run,
        "operations": []
    }
    
    stats = {
        "applied": 0,
        "skipped": 0,
        "errors": 0
    }
    
    conn = get_connection()
    
    print(f"Applying plan {plan_id} (dry_run={dry_run}, confidence_min={confidence_min})...")
    
    for action in actions:
        track_id = action["track_id"]
        action_type = action["action"]
        from_path = Path(action["from_path"])
        to_path_str = action.get("to_path")
        confidence = action.get("confidence", 0.0)
        # Skip low confidence
        if confidence < confidence_min:
            print(f"SKIP: {from_path.name} (confidence {confidence:.2f} < {confidence_min:.2f})")
            stats["skipped"] += 1
            continue
        
        # Skip ignored actions
        if action_type == "ignore":
            stats["skipped"] += 1
            continue
        
        # Check source exists
        if not from_path.exists():
            print(f"ERROR: Source not found: {from_path}")
            stats["errors"] += 1
            continue
        
        if not to_path_str:
            print(f"ERROR: No target path for {from_path.name}")
            stats["errors"] += 1
            continue
        
        to_path = Path(to_path_str)
        
        # Execute action
        try:
            if action_type in ["move", "rename", "quarantine"]:
                print(f"{action_type.upper()}: {from_path.name} -> {to_path}")
                
                if not dry_run:
                    # Create target directory
                    to_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Handle collisions
                    if to_path.exists():
                        # Generate unique name
                        stem = to_path.stem
                        ext = to_path.suffix
                        counter = 1
                        while to_path.exists():
                            to_path = to_path.parent / f"{stem}_{counter}{ext}"
                            counter += 1
                    
                    # Copy file
                    shutil.copy2(from_path, to_path)
                    
                    # Verify hash
                    from_hash = get_content_hash_fast(from_path)
                    to_hash = get_content_hash_fast(to_path)
                    
                    if from_hash != to_hash:
                        print(f"ERROR: Hash mismatch after copy! Removing dest file.")
                        to_path.unlink()
                        raise RuntimeError("Hash verification failed")
                    
                    # Update database
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE tracks SET filepath = ? WHERE track_id = ?",
                        (str(to_path), track_id)
                    )
                    conn.commit()
                    
                    # Delete source
                    from_path.unlink()
                    
                    # Journal entry
                    journal["operations"].append({
                        "track_id": track_id,
                        "action": action_type,
                        "from_path": str(from_path),
                        "to_path": str(to_path),
                        "timestamp": time.time()
                    })
                
                stats["applied"] += 1
            
            else:
                print(f"SKIP: Unknown action type {action_type}")
                stats["skipped"] += 1
        
        except Exception as exc:
            print(f"ERROR: {exc}")
            stats["errors"] += 1
    
    conn.close()
    
    # Save journal
    if not dry_run:
        journal_dir = Path("Reports")
        journal_dir.mkdir(parents=True, exist_ok=True)
        journal_path = journal_dir / f"curation_journal_{plan_id}.json"
        
        with open(journal_path, "w", encoding="utf-8") as f:
            json.dump(journal, f, indent=2, ensure_ascii=False)
        
        # Update plan as applied
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE curation_plans SET applied_at = ? WHERE plan_id = ?",
            (time.time(), plan_id)
        )
        conn.commit()
        conn.close()
        
        print(f"\nJournal saved: {journal_path}")
    
    print(f"\nResults:")
    print(f"  Applied: {stats['applied']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")
    
    result = {**stats}
    if not dry_run:
        result["journal_path"] = str(journal_path)
    
    return result


def undo_plan(journal_path: str, dry_run: bool = False) -> Dict:
    """
    Undo a previously applied curation plan.
    
    Args:
        journal_path: Path to journal JSON file
        dry_run: If True, don't actually move files
        
    Returns:
        {
            "reverted": int,
            "errors": int
        }
    """
    # Check write mode
    if get_write_mode() != "apply_allowed" and not dry_run:
        return {"error": "WRITE BLOCKED: set LYRA_WRITE_MODE=apply_allowed to undo"}
    
    # Load journal
    with open(journal_path, "r", encoding="utf-8") as f:
        journal = json.load(f)
    
    operations = journal["operations"]
    
    stats = {
        "reverted": 0,
        "errors": 0
    }
    
    conn = get_connection()
    
    print(f"Undoing {len(operations)} operations (dry_run={dry_run})...")
    
    # Reverse order
    for op in reversed(operations):
        track_id = op["track_id"]
        from_path = Path(op["from_path"])
        to_path = Path(op["to_path"])
        
        print(f"REVERT: {to_path.name} -> {from_path}")
        
        try:
            if not dry_run:
                # Check current file exists
                if not to_path.exists():
                    print(f"  WARNING: Destination file missing, skipping")
                    stats["errors"] += 1
                    continue
                
                # Recreate original directory
                from_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Move back
                shutil.move(str(to_path), str(from_path))
                
                # Update database
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE tracks SET filepath = ? WHERE track_id = ?",
                    (str(from_path), track_id)
                )
                conn.commit()
            
            stats["reverted"] += 1
        
        except Exception as exc:
            print(f"ERROR: {exc}")
            stats["errors"] += 1
    
    conn.close()
    
    print(f"\nResults:")
    print(f"  Reverted: {stats['reverted']}")
    print(f"  Errors: {stats['errors']}")
    
    return stats


if __name__ == "__main__":
    load_dotenv(override=True)
    
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "plan":
            preset = sys.argv[2] if len(sys.argv) > 2 else "artist_album"
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
            generate_plan(preset=preset, limit=limit)
        
        elif command == "apply":
            plan_path = sys.argv[2]
            confidence_min = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
            apply_plan(plan_path, confidence_min=confidence_min)
        
        elif command == "undo":
            journal_path = sys.argv[2]
            undo_plan(journal_path)
        
        else:
            print(f"Unknown command: {command}")
            print("Usage:")
            print("  python -m oracle.curator plan [preset] [limit]")
            print("  python -m oracle.curator apply <plan.json> [confidence_min]")
            print("  python -m oracle.curator undo <journal.json>")
    else:
        print("Usage:")
        print("  python -m oracle.curator plan [preset] [limit]")
        print("  python -m oracle.curator apply <plan.json> [confidence_min]")
        print("  python -m oracle.curator undo <journal.json>")

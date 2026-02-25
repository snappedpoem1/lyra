"""System repair and recovery utilities."""

from __future__ import annotations

import os
import re
import sys
import shutil
import time
from typing import Dict

from oracle.db.schema import get_connection, migrate, get_write_mode
from oracle.config import (
    LIBRARY_BASE,
    CHROMA_PATH,
    DOWNLOADS_FOLDER,
    STAGING_FOLDER,
    REPORTS_FOLDER,
    PLAYLISTS_FOLDER,
    VIBES_FOLDER,
)


def check_directories() -> Dict[str, bool]:
    """Check if all required directories exist."""
    print("\n" + "="*60)
    print("CHECKING DIRECTORIES")
    print("="*60)
    
    dirs_to_check = {
        "Library": LIBRARY_BASE,
        "ChromaDB": CHROMA_PATH,
        "Downloads": DOWNLOADS_FOLDER,
        "Staging": STAGING_FOLDER,
        "Reports": REPORTS_FOLDER,
        "Playlists": PLAYLISTS_FOLDER,
        "Vibes": VIBES_FOLDER,
    }
    
    results = {}
    for name, path in dirs_to_check.items():
        exists = os.path.exists(path)
        results[name] = exists
        status = "âœ“" if exists else "âœ—"
        print(f"  {status} {name}: {path}")
    
    return results


def create_missing_directories() -> Dict[str, bool]:
    """Create any missing directories."""
    print("\n" + "="*60)
    print("CREATING MISSING DIRECTORIES")
    print("="*60)
    
    dirs_to_create = {
        "ChromaDB": CHROMA_PATH,
        "Downloads": DOWNLOADS_FOLDER,
        "Staging": STAGING_FOLDER,
        "Reports": REPORTS_FOLDER,
        "Playlists": PLAYLISTS_FOLDER,
        "Vibes": VIBES_FOLDER,
    }
    
    results = {}
    for name, path in dirs_to_create.items():
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
                print(f"  âœ“ Created: {name} -> {path}")
                results[name] = True
            except Exception as e:
                print(f"  âœ— Failed to create {name}: {e}")
                results[name] = False
        else:
            print(f"  â†· Already exists: {name}")
            results[name] = True
    
    return results


def check_database() -> Dict[str, any]:
    """Check database integrity."""
    print("\n" + "="*60)
    print("CHECKING DATABASE")
    print("="*60)
    
    try:
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"  âœ“ Tables found: {len(tables)}")
        for table in sorted(tables):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
                print(f"    - {table}: skipped (unsafe table name)")
                continue
            cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cursor.fetchone()[0]
            print(f"    - {table}: {count} rows")
        
        conn.close()
        
        return {
            "status": "ok",
            "tables": tables,
        }
    
    except Exception as e:
        print(f"  âœ— Database error: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


def check_chromadb() -> Dict[str, any]:
    """Check ChromaDB status."""
    print("\n" + "="*60)
    print("CHECKING CHROMADB")
    print("="*60)
    
    try:
        import chromadb
        from chromadb.config import Settings
        
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )
        
        client.get_or_create_collection(name="clap_embeddings")
        count = collection.count()
        
        print(f"  âœ“ ChromaDB initialized")
        print(f"  âœ“ Collection: clap_embeddings")
        print(f"  âœ“ Embeddings: {count}")
        
        return {
            "status": "ok",
            "count": count,
        }
    
    except Exception as e:
        print(f"  âœ— ChromaDB error: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


def reinitialize_chromadb() -> Dict[str, any]:
    """Reinitialize ChromaDB (WARNING: deletes existing embeddings)."""
    print("\n" + "="*60)
    print("REINITIALIZING CHROMADB")
    print("="*60)
    print("  âš  WARNING: This will delete all existing embeddings!")
    
    try:
        # Backup old ChromaDB
        if os.path.exists(CHROMA_PATH):
            backup_path = CHROMA_PATH.parent / f"chroma_storage_backup_{int(time.time())}"
            print(f"  â†· Backing up to: {backup_path}")
            shutil.move(str(CHROMA_PATH), str(backup_path))
        
        # Create fresh ChromaDB
        import chromadb
        from chromadb.config import Settings
        
        os.makedirs(CHROMA_PATH, exist_ok=True)
        
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )
        
        client.get_or_create_collection(name="clap_embeddings")
        
        print(f"  âœ“ ChromaDB reinitialized")
        print(f"  âœ“ Collection created: clap_embeddings")
        
        return {
            "status": "ok",
        }
    
    except Exception as e:
        print(f"  âœ— Failed to reinitialize: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


def smoke_test() -> Dict[str, bool]:
    """Run smoke tests on core functionality."""
    print("\n" + "="*60)
    print("RUNNING SMOKE TESTS")
    print("="*60)
    
    results = {}
    
    # Test 1: Database connection
    print("\n  Test 1: Database Connection")
    try:
        conn = get_connection(timeout=5.0)
        conn.close()
        print("    âœ“ PASS")
        results["database"] = True
    except Exception as e:
        print(f"    âœ— FAIL: {e}")
        results["database"] = False
    
    # Test 2: ChromaDB connection
    print("\n  Test 2: ChromaDB Connection")
    try:
        import chromadb
        from chromadb.config import Settings
        
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )
        client.get_or_create_collection(name="clap_embeddings")
        print("    âœ“ PASS")
        results["chromadb"] = True
    except Exception as e:
        print(f"    âœ— FAIL: {e}")
        results["chromadb"] = False
    
    # Test 3: Model loading (optional, can be slow)
    print("\n  Test 3: CLAP Model Loading")
    try:
        from oracle.indexer import load_clap_model
        model, processor = load_clap_model()
        print("    âœ“ PASS")
        results["model"] = True
    except Exception as e:
        print(f"    âœ— FAIL: {e}")
        results["model"] = False
    
    # Test 4: Write mode
    print("\n  Test 4: Write Mode")
    try:
        mode = get_write_mode()
        print(f"    âœ“ PASS (mode: {mode})")
        results["write_mode"] = True
    except Exception as e:
        print(f"    âœ— FAIL: {e}")
        results["write_mode"] = False
    
    return results


def full_repair(skip_chromadb: bool = False) -> Dict[str, any]:
    """Run full system repair."""
    print("\n" + "="*80)
    print(" "*25 + "LYRA ORACLE REPAIR")
    print("="*80)
    
    results = {}
    
    # Step 1: Create directories
    results["directories"] = create_missing_directories()
    
    # Step 2: Migrate database
    print("\n" + "="*60)
    print("MIGRATING DATABASE")
    print("="*60)
    try:
        migrate()
        print("  âœ“ Database migrated")
        results["database_migration"] = True
    except Exception as e:
        print(f"  âœ— Migration failed: {e}")
        results["database_migration"] = False
    
    # Step 3: Check database
    results["database_check"] = check_database()
    
    # Step 4: ChromaDB (optional)
    if not skip_chromadb:
        results["chromadb_check"] = check_chromadb()
    
    # Step 5: Smoke tests
    results["smoke_tests"] = smoke_test()
    
    # Summary
    print("\n" + "="*80)
    print(" "*30 + "REPAIR SUMMARY")
    print("="*80)
    
    all_passed = all([
        all(results["directories"].values()),
        results["database_migration"],
        results["database_check"]["status"] == "ok",
        all(results["smoke_tests"].values()),
    ])
    
    if all_passed:
        print("\n  âœ“âœ“âœ“ ALL CHECKS PASSED âœ“âœ“âœ“")
        print("\n  System is healthy and ready to use.")
    else:
        print("\n  âš âš âš  SOME CHECKS FAILED âš âš âš ")
        print("\n  Review the output above for details.")
    
    print("="*80 + "\n")
    
    return results


def print_help():
    """Print repair utility help."""
    print("""
Lyra Oracle Repair Utility
===========================

Usage:
    python -m oracle.repair <command>

Commands:
    check          - Check system status (non-destructive)
    repair         - Run full system repair (creates missing directories, migrates DB)
    reset-chroma   - Reinitialize ChromaDB (WARNING: deletes embeddings)
    smoke-test     - Run smoke tests only

Examples:
    python -m oracle.repair check
    python -m oracle.repair repair
    python -m oracle.repair smoke-test
""")


def main():
    """Main entry point."""
    
    if len(sys.argv) < 2:
        print_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "check":
        check_directories()
        check_database()
        check_chromadb()
    
    elif command == "repair":
        full_repair()
    
    elif command == "reset-chroma":
        print("\nâš  WARNING: This will delete all ChromaDB embeddings!")
        response = input("Type 'YES' to confirm: ")
        if response == "YES":
            reinitialize_chromadb()
        else:
            print("Aborted.")
    
    elif command == "smoke-test":
        smoke_test()
    
    else:
        print(f"Unknown command: {command}")
        print_help()


if __name__ == "__main__":
    main()

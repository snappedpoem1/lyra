"""Download processor for Lyra Oracle - finds and organizes new downloads."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple
import shutil

from oracle.config import LIBRARY_BASE
from oracle.name_cleaner import clean_metadata, suggest_rename
from oracle.db.schema import get_write_mode, get_content_hash_fast
from oracle.scanner import AUDIO_EXTS, extract_metadata

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
STAGING_DIR = PROJECT_ROOT / "staging"


def find_new_downloads() -> List[Path]:
    """
    Find all audio files in downloads/ and staging/ directories.
    
    Returns:
        List of audio file paths
    """
    files = []
    
    for directory in [DOWNLOADS_DIR, STAGING_DIR]:
        if not directory.exists():
            continue
        
        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTS:
                files.append(file_path)
    
    return sorted(files)


def clean_filename_inplace(file_path: Path, dry_run: bool = False) -> Tuple[Path, bool]:
    """
    Rename a file to clean filename.
    
    Args:
        file_path: File to rename
        dry_run: If True, only suggest rename without executing
        
    Returns:
        Tuple of (new_path, was_renamed)
    """
    new_path, needs_rename = suggest_rename(file_path)
    
    if not needs_rename:
        return file_path, False
    
    if dry_run:
        return new_path, True
    
    # Check if target exists
    if new_path.exists():
        # Add suffix
        suffix = 1
        while new_path.exists():
            new_path = file_path.parent / f"{new_path.stem}_{suffix}{file_path.suffix}"
            suffix += 1
    
    try:
        file_path.rename(new_path)
        return new_path, True
    except Exception as e:
        print(f"Failed to rename {file_path.name}: {e}")
        return file_path, False


def organize_download(
    file_path: Path,
    target_library: str = str(LIBRARY_BASE),
    clean_names: bool = True,
    dry_run: bool = False
) -> Dict[str, any]:
    """
    Organize a downloaded file into library.

    Steps:
    1. Clean filename if requested
    2. Extract metadata
    3. Clean metadata
    4. Generate target path based on metadata
    5. Copy to library (or report if dry_run)

    Args:
        file_path: Downloaded file to organize
        target_library: Library root path
        clean_names: Clean filenames and metadata
        dry_run: Only simulate, don't actually move files
        
    Returns:
        Dict with status and details
    """
    result = {
        'file': str(file_path),
        'status': 'pending',
        'original_name': file_path.name,
        'cleaned_name': None,
        'metadata': {},
        'target': None,
        'error': None
    }
    
    try:
        # Step 1: Clean filename
        current_path = file_path
        if clean_names:
            current_path, was_renamed = clean_filename_inplace(file_path, dry_run=dry_run)
            if was_renamed:
                result['cleaned_name'] = current_path.name
        
        # Step 2: Extract metadata
        meta = extract_metadata(current_path)
        
        # Step 3: Clean metadata
        if clean_names:
            meta = clean_metadata(meta)
        
        result['metadata'] = meta
        
        # Step 4: Generate target path
        # Use simple artist/album structure
        artist = meta.get('artist', 'Unknown Artist')
        album = meta.get('album', 'Unknown Album')
        year = meta.get('year', '')
        title = meta.get('title', current_path.stem)
        
        # Sanitize path components
        from oracle.organizer import _sanitize_filename
        artist_folder = _sanitize_filename(artist)
        
        if album and album != 'Unknown Album':
            if year:
                album_folder = f"{_sanitize_filename(album)} ({year})"
            else:
                album_folder = _sanitize_filename(album)
            target_dir = Path(target_library) / artist_folder / album_folder
        else:
            # No album, use flat structure
            target_dir = Path(target_library) / artist_folder
        
        target_path = target_dir / f"{_sanitize_filename(title)}{current_path.suffix}"
        result['target'] = str(target_path)
        
        # Step 5: Copy/move to library
        if not dry_run:
            if get_write_mode() != "apply_allowed":
                result['status'] = 'blocked'
                result['error'] = 'LYRA_WRITE_MODE must be apply_allowed'
                return result
            
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Check if target exists
            if target_path.exists():
                # Check if identical
                source_hash = get_content_hash_fast(str(current_path))
                target_hash = get_content_hash_fast(str(target_path))
                
                if source_hash == target_hash:
                    # Delete duplicate download
                    current_path.unlink()
                    result['status'] = 'duplicate_removed'
                    return result
                else:
                    # Different file, add suffix
                    suffix = 1
                    while target_path.exists():
                        target_path = target_dir / f"{_sanitize_filename(title)}_{suffix}{current_path.suffix}"
                        suffix += 1
                    result['target'] = str(target_path)
            
            # Copy file
            shutil.copy2(str(current_path), str(target_path))
            
            # Verify copy
            if target_path.stat().st_size == current_path.stat().st_size:
                current_path.unlink()  # Remove from downloads
                result['status'] = 'success'
            else:
                target_path.unlink()  # Remove bad copy
                result['status'] = 'failed'
                result['error'] = 'Copy verification failed'
        else:
            result['status'] = 'would_copy'
        
        return result
        
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
        return result


def process_downloads(
    target_library: str = str(LIBRARY_BASE),
    clean_names: bool = True,
    dry_run: bool = False,
    scan_after: bool = True
) -> Dict[str, int]:
    """
    Process all files in downloads/staging directories.
    
    Args:
        target_library: Library root path
        clean_names: Clean filenames and metadata
        dry_run: Only simulate, don't actually move files
        scan_after: Run scanner after processing
        
    Returns:
        Dict with counts of successes/failures
    """
    files = find_new_downloads()
    
    if not files:
        print("No downloads found.")
        return {'found': 0, 'success': 0, 'failed': 0, 'duplicate': 0, 'error': 0}
    
    print(f"Found {len(files)} downloads to process...")
    
    stats = {'found': len(files), 'success': 0, 'failed': 0, 'duplicate': 0, 'error': 0}
    
    for file_path in files:
        print(f"\nProcessing: {file_path.name}")
        
        result = organize_download(file_path, target_library, clean_names, dry_run)
        
        if result['status'] == 'success':
            stats['success'] += 1
            print(f"  âœ“ Organized to: {result['target']}")
            if result['cleaned_name']:
                print(f"  âœ“ Cleaned name: {result['original_name']} â†’ {result['cleaned_name']}")
            print(f"  âœ“ Metadata: {result['metadata'].get('artist', '?')} - {result['metadata'].get('title', '?')}")
        
        elif result['status'] == 'duplicate_removed':
            stats['duplicate'] += 1
            print(f"  âœ“ Removed duplicate (exists at {result['target']})")
        
        elif result['status'] == 'would_copy':
            print(f"  â†’ Would copy to: {result['target']}")
            if result['cleaned_name']:
                print(f"  â†’ Would clean: {result['original_name']} â†’ {result['cleaned_name']}")
        
        elif result['status'] in ['failed', 'error', 'blocked']:
            stats['error'] += 1
            print(f"  âœ— Failed: {result.get('error', 'Unknown error')}")
    
    print(f"\n{'='*60}")
    print(f"Processed {stats['found']} files:")
    print(f"  Success:    {stats['success']}")
    print(f"  Duplicates: {stats['duplicate']}")
    print(f"  Errors:     {stats['error']}")
    
    # Run scanner if requested and not dry run
    if scan_after and not dry_run and stats['success'] > 0:
        print(f"\nScanning library to index new files...")
        from oracle.scanner import scan_library
        scan_library(target_library)
    
    return stats


def list_downloads(show_metadata: bool = False) -> List[Dict]:
    """
    List all downloads with metadata preview.
    
    Args:
        show_metadata: Extract and show metadata
        
    Returns:
        List of file info dicts
    """
    files = find_new_downloads()
    results = []
    
    for file_path in files:
        info = {
            'path': str(file_path),
            'name': file_path.name,
            'size_mb': file_path.stat().st_size / (1024 * 1024),
            'folder': file_path.parent.name
        }
        
        if show_metadata:
            meta = extract_metadata(file_path)
            cleaned = clean_metadata(meta.copy())
            info['metadata_raw'] = meta
            info['metadata_clean'] = cleaned
        
        results.append(info)
    
    return results

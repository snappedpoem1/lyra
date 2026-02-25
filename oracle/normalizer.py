"""Metadata Normalizer - Fix common metadata issues across library.

Fixes:
- Artist name variations (Coheed And Cambria vs Coheed and Cambria)
- Featured artists extraction
- YouTube cruft removal
- Record label â†’ real artist extraction
- Title cleanup (Official Video, etc.)
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from typing import List, Optional, Tuple
from difflib import SequenceMatcher


# Canonical artist names (lowercase key â†’ proper case)
ARTIST_CANONICAL = {
    "coheed and cambria": "Coheed and Cambria",
    "coheed & cambria": "Coheed and Cambria",
    "coheed, cambria": "Coheed and Cambria",
    "fall out boy": "Fall Out Boy",
    "fallout boy": "Fall Out Boy",
    "brand new": "Brand New",
    "taking back sunday": "Taking Back Sunday",
    "takingbacksunday": "Taking Back Sunday",
    "rise against": "Rise Against",
    "riseagainst": "Rise Against",
    "run the jewels": "Run the Jewels",
    "runthejewels": "Run the Jewels",
    "massive attack": "Massive Attack",
    "massiveattack": "Massive Attack",
    "tv on the radio": "TV on the Radio",
    "a day to remember": "A Day to Remember",
    "my chemical romance": "My Chemical Romance",
    "panic! at the disco": "Panic! at the Disco",
    "panic at the disco": "Panic! at the Disco",
    "twenty one pilots": "Twenty One Pilots",
    "twentyone pilots": "Twenty One Pilots",
    "21 pilots": "Twenty One Pilots",
    "blink-182": "blink-182",
    "blink 182": "blink-182",
    "system of a down": "System of a Down",
    "rage against the machine": "Rage Against the Machine",
    "red hot chili peppers": "Red Hot Chili Peppers",
    "rhcp": "Red Hot Chili Peppers",
    "foo fighters": "Foo Fighters",
    "the foo fighters": "Foo Fighters",
    "green day": "Green Day",
    "weezer": "Weezer",
    "linkin park": "Linkin Park",
    "deftones": "Deftones",
    "the deftones": "Deftones",
    "tool": "Tool",
    "radiohead": "Radiohead",
    "muse": "Muse",
    "arctic monkeys": "Arctic Monkeys",
    "the killers": "The Killers",
    "queens of the stone age": "Queens of the Stone Age",
    "qotsa": "Queens of the Stone Age",
    "kendrick lamar": "Kendrick Lamar",
    "j. cole": "J. Cole",
    "j cole": "J. Cole",
    "childish gambino": "Childish Gambino",
    "tyler, the creator": "Tyler, the Creator",
    "tyler the creator": "Tyler, the Creator",
    "denzel curry": "Denzel Curry",
    "jid": "JID",
    "alt-j": "alt-J",
    "alt j": "alt-J",
}

# Patterns that indicate featured artists
FEAT_PATTERNS = [
    r'\s*[\(\[]feat\.?\s+([^\)\]]+)[\)\]]',
    r'\s*[\(\[]ft\.?\s+([^\)\]]+)[\)\]]',
    r'\s*[\(\[]featuring\s+([^\)\]]+)[\)\]]',
    r'\s*[\(\[]with\s+([^\)\]]+)[\)\]]',
    r'\s+feat\.?\s+(.+?)(?:\s*[\(\[]|$)',
    r'\s+ft\.?\s+(.+?)(?:\s*[\(\[]|$)',
]

# Patterns to remove from titles
TITLE_CLEANUP_PATTERNS = [
    r'\s*[\(\[]official\s*(music\s*)?(video|audio|lyric\s*video|visualizer)[\)\]]',
    r'\s*[\(\[]explicit[\)\]]',
    r'\s*[\(\[]clean[\)\]]',
    r'\s*[\(\[]hd\s*\d*p?[\)\]]',
    r'\s*[\(\[]4k[\)\]]',
    r'\s*[\(\[]lyrics?[\)\]]',
    r'\s*[\(\[]audio[\)\]]',
    r'\s*[\(\[]video[\)\]]',
    r'\s*-\s*official\s*(music\s*)?(video|audio).*$',
    r'\s*\|\s*[^|]+$',  # Remove " | Channel Name"
]


def normalize_artist(artist: str) -> Tuple[str, List[str]]:
    """Normalize artist name and extract featured artists.
    
    Returns:
        (primary_artist, [featured_artists])
    """
    if not artist:
        return "", []
    
    original = artist.strip()
    featured = []
    
    # Check canonical mapping first
    lookup = original.lower().strip()
    if lookup in ARTIST_CANONICAL:
        return ARTIST_CANONICAL[lookup], []
    
    # Extract featured artists
    for pattern in FEAT_PATTERNS:
        match = re.search(pattern, original, re.IGNORECASE)
        if match:
            feat_artist = match.group(1).strip()
            featured.append(feat_artist)
            original = re.sub(pattern, '', original, flags=re.IGNORECASE).strip()
    
    # Handle "Artist, Artist2" format (but not "Artist, The")
    if ', ' in original and not re.search(r',\s*(The|Jr|Sr|III?|IV)\.?$', original):
        parts = [p.strip() for p in original.split(', ')]
        if len(parts) == 2 and len(parts[0]) > 3 and len(parts[1]) > 3:
            # Might be "Artist1, Artist2" collab
            # Check if second part looks like a name
            if not parts[1][0].islower():  # Not "feat. artist"
                # Keep as-is for now, but note the collaboration
                pass
    
    # Check canonical again after cleanup
    lookup = original.lower().strip()
    if lookup in ARTIST_CANONICAL:
        return ARTIST_CANONICAL[lookup], featured
    
    # Title case if all lowercase or all uppercase
    if original.islower() or original.isupper():
        original = original.title()
    
    return original.strip(), featured


def normalize_title(title: str) -> Tuple[str, List[str]]:
    """Clean up track title.
    
    Returns:
        (clean_title, [featured_artists])
    """
    if not title:
        return "", []
    
    original = title.strip()
    featured = []
    
    # Extract featured artists from title
    for pattern in FEAT_PATTERNS:
        match = re.search(pattern, original, re.IGNORECASE)
        if match:
            feat_artist = match.group(1).strip()
            featured.append(feat_artist)
            original = re.sub(pattern, '', original, flags=re.IGNORECASE).strip()
    
    # Remove YouTube/video cruft
    for pattern in TITLE_CLEANUP_PATTERNS:
        original = re.sub(pattern, '', original, flags=re.IGNORECASE).strip()
    
    # Remove duplicate artist name from title ("Artist - Artist - Song" â†’ "Song")
    # This is common in YouTube rips
    parts = original.split(' - ')
    if len(parts) >= 2:
        # Check if first part repeats
        if len(parts) >= 3 and parts[0].lower().strip() == parts[1].lower().strip():
            original = ' - '.join(parts[2:])
    
    # Clean up whitespace
    original = re.sub(r'\s+', ' ', original).strip()
    
    return original, featured


def extract_artist_from_title(title: str) -> Tuple[Optional[str], str]:
    """Extract artist from 'Artist - Title' format.
    
    Returns:
        (artist or None, remaining_title)
    """
    if ' - ' not in title:
        return None, title
    
    parts = title.split(' - ', 1)
    potential_artist = parts[0].strip()
    remaining = parts[1].strip() if len(parts) > 1 else ""
    
    # Check if it looks like an artist name
    # Reject if it's too short or looks like a label
    if len(potential_artist) < 2:
        return None, title
    
    labels = {"official", "vevo", "records", "music", "audio", "video"}
    if any(label in potential_artist.lower() for label in labels):
        return None, title
    
    return potential_artist, remaining


def find_similar_artists(artist: str, all_artists: List[str], threshold: float = 0.85) -> List[str]:
    """Find artists with similar names (potential duplicates)."""
    artist_lower = artist.lower()
    similar = []
    
    for other in all_artists:
        if other.lower() == artist_lower:
            continue
        
        ratio = SequenceMatcher(None, artist_lower, other.lower()).ratio()
        if ratio >= threshold:
            similar.append((other, ratio))
    
    return [a for a, _ in sorted(similar, key=lambda x: -x[1])]


def normalize_library(db_path: str = "lyra_registry.db", apply: bool = False):
    """Normalize all metadata in library."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT track_id, artist, title, filepath FROM tracks 
        WHERE status = 'active'
        ORDER BY artist, title
    """)
    tracks = cursor.fetchall()
    
    print(f"Analyzing {len(tracks)} tracks...\n")
    
    changes = []
    artist_counts = defaultdict(int)
    
    for track_id, artist, title, filepath in tracks:
        # Normalize artist
        norm_artist, feat_from_artist = normalize_artist(artist)
        
        # Normalize title
        norm_title, feat_from_title = normalize_title(title)
        
        # Combine featured artists
        all_featured = feat_from_artist + feat_from_title
        
        # Check if artist was in title
        if not norm_artist or norm_artist.lower() in {"", "unknown", "various", "various artists"}:
            extracted, norm_title = extract_artist_from_title(norm_title)
            if extracted:
                norm_artist, _ = normalize_artist(extracted)
        
        # Track artist usage
        artist_counts[norm_artist] += 1
        
        # Record changes
        if norm_artist != artist or norm_title != title:
            changes.append({
                "track_id": track_id,
                "old_artist": artist,
                "new_artist": norm_artist,
                "old_title": title,
                "new_title": norm_title,
                "featured": all_featured,
            })
    
    # Find similar artist names
    all_artists = list(artist_counts.keys())
    artist_groups = defaultdict(set)
    
    for artist in all_artists:
        similar = find_similar_artists(artist, all_artists)
        if similar:
            # Group similar artists
            key = min([artist] + similar, key=str.lower)
            artist_groups[key].add(artist)
            for s in similar:
                artist_groups[key].add(s)
    
    # Report
    print(f"=== NORMALIZATION REPORT ===\n")
    print(f"Tracks to update: {len(changes)}")
    
    if changes:
        print(f"\nSample changes:")
        for change in changes[:15]:
            if change["old_artist"] != change["new_artist"]:
                print(f"  Artist: '{change['old_artist'][:30]}' â†’ '{change['new_artist'][:30]}'")
            if change["old_title"] != change["new_title"]:
                print(f"  Title:  '{change['old_title'][:35]}' â†’ '{change['new_title'][:35]}'")
            print()
    
    if artist_groups:
        print(f"\nSimilar artist names (potential duplicates):")
        for key, group in list(artist_groups.items())[:10]:
            if len(group) > 1:
                print(f"  {list(group)}")
    
    if not apply:
        print(f"\nRun with --apply to make changes")
        conn.close()
        return changes
    
    # Apply changes
    print(f"\nApplying {len(changes)} changes...")
    for change in changes:
        cursor.execute(
            "UPDATE tracks SET artist = ?, title = ? WHERE track_id = ?",
            (change["new_artist"], change["new_title"], change["track_id"])
        )
    
    conn.commit()
    conn.close()
    print(f"âœ“ Updated {len(changes)} tracks")
    
    return changes


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Normalize library metadata")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    parser.add_argument("--db", default="lyra_registry.db", help="Database path")
    
    args = parser.parse_args()
    normalize_library(args.db, apply=args.apply)

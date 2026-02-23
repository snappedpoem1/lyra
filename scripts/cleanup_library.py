"""Clean up polluted library - fix artists, remove duplicates, delete junk."""
import sqlite3
import os
import re
from pathlib import Path
from collections import defaultdict

db_path = Path("lyra_registry.db")
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# === PHASE 1: Identify problems ===

print("=== LIBRARY CLEANUP ANALYSIS ===\n")

# Record labels that got tagged as artists
RECORD_LABELS = [
    "dine alone records", "epitaph records", "vagrant records", "rise records",
    "riserecords", "fueled by ramen", "hopeless records", "victory records",
    "fearless records", "equal vision", "tooth & nail", "solid state",
    "roadrunner records", "interscope", "atlantic records", "columbia records",
]

# YouTube channels / compilations mistaken as artists
YOUTUBE_CHANNELS = [
    "lyrical lemonade", "worldstarhiphop", "colors", "genius", "vevo",
    "officialpsy", "theneedledrop", "complex", "noisey", "pitchfork",
]

# Artist name fixes (wrong -> correct)
ARTIST_FIXES = {
    "coheed, cambria": "Coheed and Cambria",
    "coheed and cambria": "Coheed and Cambria",
    "coheed and cambria": "Coheed and Cambria",
    "riseagainst": "Rise Against",
    "runthejewels": "Run the Jewels",
    "takingbacksunday": "Taking Back Sunday",
    "massiveattack": "Massive Attack",
    "spacevoyage": "TV on the Radio",  # This seems to be a channel
    "fallout boy": "Fall Out Boy",
    "brand new": "Brand New",
}

# Get all tracks
cursor.execute("SELECT track_id, artist, title, filepath FROM tracks WHERE status='active'")
all_tracks = cursor.fetchall()

print(f"Total tracks: {len(all_tracks)}\n")

# Categorize problems
label_tracks = []
channel_tracks = []
fixable_artists = []
duplicates = []

# Track by normalized (artist, title) for duplicate detection
seen = defaultdict(list)

for track_id, artist, title, filepath in all_tracks:
    artist_lower = (artist or "").lower().strip()
    title_lower = (title or "").lower().strip()
    
    # Clean title for comparison (remove video markers, etc.)
    clean_title = re.sub(r'\s*[\(\[].*?[\)\]]', '', title_lower).strip()
    clean_title = re.sub(r'\s*-\s*(official|video|audio|lyric|visualizer).*', '', clean_title, flags=re.I).strip()
    
    # Check for record labels
    for label in RECORD_LABELS:
        if label in artist_lower:
            label_tracks.append((track_id, artist, title, filepath))
            break
    
    # Check for YouTube channels
    for channel in YOUTUBE_CHANNELS:
        if channel in artist_lower:
            channel_tracks.append((track_id, artist, title, filepath))
            break
    
    # Check for fixable artist names
    if artist_lower in ARTIST_FIXES:
        fixable_artists.append((track_id, artist, ARTIST_FIXES[artist_lower], filepath))
    
    # Track for duplicates
    # Normalize artist too
    norm_artist = artist_lower
    for wrong, correct in ARTIST_FIXES.items():
        if norm_artist == wrong:
            norm_artist = correct.lower()
            break
    
    key = (norm_artist, clean_title)
    seen[key].append((track_id, artist, title, filepath))

# Find actual duplicates (same song, multiple versions)
for key, tracks in seen.items():
    if len(tracks) > 1:
        duplicates.append((key, tracks))

# === PHASE 2: Report ===

print(f"🏷️  RECORD LABELS AS ARTISTS ({len(label_tracks)}):")
for _, artist, title, _ in label_tracks[:10]:
    print(f"   {artist[:35]:35s} | {title[:40]}")
if len(label_tracks) > 10:
    print(f"   ... and {len(label_tracks) - 10} more")

print(f"\n📺 YOUTUBE CHANNELS AS ARTISTS ({len(channel_tracks)}):")
for _, artist, title, _ in channel_tracks[:10]:
    print(f"   {artist[:35]:35s} | {title[:40]}")

print(f"\n✏️  FIXABLE ARTIST NAMES ({len(fixable_artists)}):")
for _, old, new, _ in fixable_artists[:10]:
    print(f"   '{old}' → '{new}'")

print(f"\n📋 DUPLICATE SONGS ({len(duplicates)} groups):")
for (artist, title), tracks in duplicates[:10]:
    print(f"   '{artist[:25]}' - '{title[:30]}' ({len(tracks)} versions)")
    for _, a, t, fp in tracks[:3]:
        print(f"      • {Path(fp).name[:60]}")

# === PHASE 3: Offer cleanup ===

print("\n" + "="*60)
print("CLEANUP OPTIONS:")
print("="*60)

to_delete = []
to_delete.extend(label_tracks)
to_delete.extend(channel_tracks)

# For duplicates, keep the first (usually best quality), delete rest
for (artist, title), tracks in duplicates:
    # Sort by preference: FLAC > other, shorter filename usually = cleaner
    def score(t):
        fp = t[3] or ""
        s = 0
        if fp.endswith('.flac'):
            s += 100
        if '(official' in fp.lower() or '[official' in fp.lower():
            s -= 10  # Penalize "official video" rips
        if 'demo' in fp.lower():
            s -= 50
        if 'remix' in fp.lower() or 'live' in fp.lower():
            s -= 20
        return s
    
    sorted_tracks = sorted(tracks, key=score, reverse=True)
    # Keep first, delete rest
    to_delete.extend(sorted_tracks[1:])

# Deduplicate the delete list
delete_ids = list(set(t[0] for t in to_delete))

print(f"\nWill DELETE: {len(delete_ids)} tracks")
print(f"Will FIX: {len(fixable_artists)} artist names")
print(f"Will KEEP: {len(all_tracks) - len(delete_ids)} tracks")

response = input("\nProceed with cleanup? [y/N]: ")
if response.lower() != 'y':
    print("Aborted.")
    conn.close()
    exit(0)

# === PHASE 4: Execute cleanup ===

# Fix artist names first
print("\nFixing artist names...")
for track_id, old, new, _ in fixable_artists:
    cursor.execute("UPDATE tracks SET artist = ? WHERE track_id = ?", (new, track_id))
print(f"  Fixed {len(fixable_artists)} artist names")

# Delete junk tracks
print("\nDeleting junk tracks...")
from oracle.chroma_store import LyraChromaStore
store = LyraChromaStore(persist_dir="./chroma_storage")

# Delete from ChromaDB
try:
    store.collection.delete(ids=delete_ids)
    print(f"  Deleted {len(delete_ids)} embeddings from ChromaDB")
except Exception as e:
    print(f"  ⚠ ChromaDB deletion failed: {e}")

# Delete from SQLite and filesystem
deleted_files = 0
for track_id, artist, title, filepath in to_delete:
    if track_id not in delete_ids:
        continue  # Already handled (deduped)
    
    cursor.execute("DELETE FROM tracks WHERE track_id = ?", (track_id,))
    cursor.execute("DELETE FROM embeddings WHERE track_id = ?", (track_id,))
    cursor.execute("DELETE FROM track_scores WHERE track_id = ?", (track_id,))
    
    if filepath and Path(filepath).exists():
        try:
            os.remove(filepath)
            deleted_files += 1
        except:
            pass

conn.commit()
conn.close()

print(f"\n✓ Deleted {len(delete_ids)} tracks from database")
print(f"✓ Deleted {deleted_files} files from filesystem")
print(f"✓ Fixed {len(fixable_artists)} artist names")

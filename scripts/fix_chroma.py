"""Fix ChromaDB - remove stale embeddings not in SQLite."""
import sqlite3
from pathlib import Path

db_path = Path("lyra_registry.db")
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Get all valid track IDs from SQLite
cursor.execute("SELECT track_id FROM tracks WHERE status='active'")
valid_ids = set(row[0] for row in cursor.fetchall())
print(f"Valid track IDs in SQLite: {len(valid_ids)}")

# Get all IDs from ChromaDB
from oracle.chroma_store import LyraChromaStore
store = LyraChromaStore(persist_dir="./chroma_storage")

chroma_count = store.collection.count()
print(f"Total items in ChromaDB: {chroma_count}")

# Get all ChromaDB IDs
all_chroma = store.collection.get(include=[])
chroma_ids = set(all_chroma.get("ids", []))
print(f"Unique IDs in ChromaDB: {len(chroma_ids)}")

# Find orphaned IDs (in Chroma but not in SQLite)
orphaned = chroma_ids - valid_ids
print(f"Orphaned IDs (in Chroma, not in SQLite): {len(orphaned)}")

if orphaned:
    print(f"\nSample orphaned IDs:")
    for oid in list(orphaned)[:5]:
        print(f"  {oid}")
    
    response = input(f"\nDelete {len(orphaned)} orphaned embeddings? [y/N]: ")
    if response.lower() == 'y':
        # Delete in batches
        orphan_list = list(orphaned)
        batch_size = 100
        for i in range(0, len(orphan_list), batch_size):
            batch = orphan_list[i:i+batch_size]
            store.collection.delete(ids=batch)
            print(f"  Deleted {min(i+batch_size, len(orphan_list))}/{len(orphan_list)}")
        print(f"\n✓ Deleted {len(orphaned)} orphaned embeddings")
        print(f"ChromaDB now has: {store.collection.count()} items")
else:
    print("\n✓ No orphaned embeddings found")

conn.close()

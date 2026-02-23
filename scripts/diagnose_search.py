"""Diagnose search/embedding mismatch."""
import sqlite3
from pathlib import Path

db_path = Path("lyra_registry.db")
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("=== Sample Track IDs from SQLite ===")
cursor.execute("SELECT track_id, artist, title FROM tracks WHERE status='active' LIMIT 5")
for row in cursor.fetchall():
    print(f"  {row[0]} | {row[1]} - {row[2]}")

print("\n=== Sample IDs from ChromaDB ===")
from oracle.chroma_store import LyraChromaStore
store = LyraChromaStore(persist_dir="./chroma_storage")

# Get some IDs from ChromaDB
result = store.collection.peek(limit=5)
chroma_ids = result.get("ids", [])
for cid in chroma_ids:
    print(f"  {cid}")

print("\n=== Cross-check: Do ChromaDB IDs exist in SQLite? ===")
for cid in chroma_ids[:5]:
    cursor.execute("SELECT track_id, artist, title FROM tracks WHERE track_id = ?", (cid,))
    row = cursor.fetchone()
    if row:
        print(f"  ✓ {cid} → {row[1]} - {row[2]}")
    else:
        cursor.execute("SELECT track_id, artist, title FROM tracks WHERE track_id LIKE ?", (f"%{cid[:8]}%",))
        similar = cursor.fetchone()
        if similar:
            print(f"  ✗ {cid} NOT FOUND (similar: {similar[0]})")
        else:
            print(f"  ✗ {cid} NOT FOUND")

print("\n=== Embeddings table sample ===")
cursor.execute("SELECT track_id, model FROM embeddings LIMIT 5")
for row in cursor.fetchall():
    print(f"  {row[0]} | model={row[1]}")

conn.close()

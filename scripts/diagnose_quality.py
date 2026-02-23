"""Diagnose search quality and library contents."""
import sqlite3
from pathlib import Path
from collections import Counter

db_path = Path("lyra_registry.db")
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("=== Library Genre Distribution ===")
cursor.execute("SELECT genre FROM tracks WHERE status='active' AND genre IS NOT NULL AND genre != ''")
genres = [row[0] for row in cursor.fetchall()]
genre_counts = Counter(genres)
for genre, count in genre_counts.most_common(20):
    print(f"  {count:3d} | {genre[:60]}")

print(f"\n=== Artists with most tracks ===")
cursor.execute("""
    SELECT artist, COUNT(*) as cnt 
    FROM tracks WHERE status='active' 
    GROUP BY artist ORDER BY cnt DESC LIMIT 15
""")
for row in cursor.fetchall():
    print(f"  {row[1]:3d} | {row[0][:50]}")

print(f"\n=== Sample tracks that SHOULD be 'aggressive punk rock' ===")
# Look for punk-related keywords
cursor.execute("""
    SELECT artist, title, genre FROM tracks 
    WHERE status='active' AND (
        LOWER(genre) LIKE '%punk%' OR 
        LOWER(genre) LIKE '%hardcore%' OR
        LOWER(artist) LIKE '%day to remember%' OR
        LOWER(artist) LIKE '%fall out boy%' OR
        LOWER(artist) LIKE '%blink%' OR
        LOWER(artist) LIKE '%green day%' OR
        LOWER(artist) LIKE '%sum 41%'
    )
    LIMIT 15
""")
for row in cursor.fetchall():
    print(f"  {row[0][:25]:25s} | {row[1][:30]:30s} | {row[2] or 'no genre'}")

print(f"\n=== Tracks with 'Brand New' in title (why are these matching?) ===")
cursor.execute("""
    SELECT artist, title, genre FROM tracks 
    WHERE status='active' AND LOWER(title) LIKE '%brand new%'
""")
for row in cursor.fetchall():
    print(f"  {row[0][:25]:25s} | {row[1][:35]:35s} | {row[2] or 'no genre'}")

conn.close()

print("\n=== Testing CLAP embedding similarity ===")
from oracle.chroma_store import LyraChromaStore
from oracle.embedders.clap_embedder import CLAPEmbedder

embedder = CLAPEmbedder()
store = LyraChromaStore(persist_dir="./chroma_storage")

# Test different queries
queries = [
    "aggressive punk rock screaming",
    "heavy metal guitar distortion",
    "soft acoustic guitar peaceful",
    "electronic dance synth bass",
]

for q in queries:
    print(f"\nQuery: '{q}'")
    vec = embedder.embed_text(q)
    if vec is None:
        print("  Failed to embed")
        continue
    
    results = store.search(vec.tolist(), n=3)
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    for i, (tid, dist) in enumerate(zip(ids, distances)):
        cursor.execute("SELECT artist, title FROM tracks WHERE track_id = ?", (tid,))
        row = cursor.fetchone()
        if row:
            print(f"  {i+1}. {row[0][:20]:20s} - {row[1][:30]:30s} (dist: {dist:.4f})")
    conn.close()

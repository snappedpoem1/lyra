"""Quick diagnostic to check embedding errors."""
import sqlite3
from pathlib import Path

db_path = Path("lyra_registry.db")
if not db_path.exists():
    print("Database not found")
    exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

print("\n=== Recent Errors ===")
cursor.execute("""
    SELECT stage, error, COUNT(*) as cnt 
    FROM errors 
    GROUP BY stage, error 
    ORDER BY cnt DESC 
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"  [{row[0]}] {row[1][:80]}... ({row[2]} occurrences)")

print("\n=== Sample Error Details ===")
cursor.execute("""
    SELECT track_id, stage, error, ts
    FROM errors 
    ORDER BY ts DESC 
    LIMIT 5
""")
for row in cursor.fetchall():
    print(f"  Track: {row[0]}")
    print(f"  Stage: {row[1]}")
    print(f"  Error: {row[2][:200]}")
    print()

print("\n=== Track File Check ===")
cursor.execute("""
    SELECT track_id, filepath 
    FROM tracks 
    WHERE status = 'active' 
    LIMIT 3
""")
for row in cursor.fetchall():
    fp = Path(row[1])
    exists = "✓" if fp.exists() else "✗ MISSING"
    print(f"  {exists} {fp}")

conn.close()

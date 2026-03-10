"""List all artists in library."""
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from oracle.config import LYRA_DB_PATH

conn = sqlite3.connect(str(LYRA_DB_PATH))
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT artist FROM tracks WHERE status='active' ORDER BY artist")
for row in cursor.fetchall():
    print(row[0])
conn.close()

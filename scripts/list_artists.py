"""List all artists in library."""
import sqlite3
conn = sqlite3.connect('lyra_registry.db')
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT artist FROM tracks WHERE status='active' ORDER BY artist")
for row in cursor.fetchall():
    print(row[0])
conn.close()

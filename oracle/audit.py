import sqlite3
from oracle.config import get_connection


def run_audit():
    try:
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error: Could not connect to database. {e}")
        return

    try:
        existing_tables = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "spotify_history" not in existing_tables:
            print("Error: spotify_history table not found. Run 'python spotify_import.py --all' first.")
            return
        if "spotify_library" not in existing_tables:
            print("Error: spotify_library table not found. Run 'python spotify_import.py --all' first.")
            return

        history_cols = {
            row[1] for row in cursor.execute("PRAGMA table_info(spotify_history)").fetchall()
        }
        library_cols = {
            row[1] for row in cursor.execute("PRAGMA table_info(spotify_library)").fetchall()
        }
        track_cols = {
            row[1] for row in cursor.execute("PRAGMA table_info(tracks)").fetchall()
        }

        required_history = {"artist", "track"}
        required_library = {"artist"}
        required_tracks = {"artist"}

        if not required_history.issubset(history_cols):
            print("Error: spotify_history schema mismatch. Expected columns: artist, track.")
            return
        if not required_library.issubset(library_cols):
            print("Error: spotify_library schema mismatch. Expected column: artist.")
            return
        if not required_tracks.issubset(track_cols):
            print("Error: tracks schema mismatch. Expected column: artist.")
            return

        cursor.execute(
            """
            SELECT artist, COUNT(*) as plays, COUNT(DISTINCT track) as unique_history
            FROM spotify_history
            GROUP BY artist
            ORDER BY plays DESC
            LIMIT 50
            """
        )
        top_50 = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Error: SQL failure while building audit: {e}")
        return

    print(f"\n{'#':<3} {'ARTIST':<25} {'PLAYS':<8} {'LIKED':<8} {'LOCAL':<8} {'STATUS'}")
    print("-" * 75)

    for i, (name, plays, history_unique) in enumerate(top_50, 1):
        cursor.execute("SELECT COUNT(*) FROM spotify_library WHERE artist = ?", (name,))
        liked = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tracks WHERE artist = ?", (name,))
        local = cursor.fetchone()[0]

        if local >= history_unique and local > 0:
            status = "COMPLETE"
        elif local > 0:
            pct = int((local / history_unique) * 100) if history_unique > 0 else 100
            status = f"{pct}% OWNED"
        else:
            status = "UNOWNED"

        print(f"{i:<3} {name[:25]:<25} {plays:<8} {f'LIKE {liked}':<8} {f'LOC {local}':<8} {status}")

    conn.close()


if __name__ == "__main__":
    run_audit()

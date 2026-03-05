"""Enrich track metadata from Last.fm API."""
import argparse
import sqlite3
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
import os
import sys

load_dotenv(override=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_URL = "http://ws.audioscrobbler.com/2.0/"

def get_track_info(artist: str, title: str) -> dict:
    """Fetch track info from Last.fm."""
    # Clean up title - remove video markers, etc.
    clean_title = title
    for marker in ["(Official Video)", "(Official Music Video)", "(Lyric Video)", 
                   "(Audio)", "(Visualizer)", "[Official Video]", "(Official Audio)"]:
        clean_title = clean_title.replace(marker, "").strip()
    
    # Also try to extract just the song name if artist is duplicated
    if " - " in clean_title:
        parts = clean_title.split(" - ", 1)
        if parts[0].lower().strip() == artist.lower().strip():
            clean_title = parts[1].strip()
    
    try:
        resp = requests.get(LASTFM_URL, params={
            "method": "track.getInfo",
            "api_key": LASTFM_API_KEY,
            "artist": artist,
            "track": clean_title,
            "format": "json"
        }, timeout=10)
        
        if resp.status_code != 200:
            return {}
        
        data = resp.json()
        track = data.get("track", {})
        
        # Extract tags/genres
        tags = []
        for tag in track.get("toptags", {}).get("tag", []):
            tag_name = tag.get("name", "").lower()
            if tag_name:
                tags.append(tag_name)
        
        return {
            "genre": ", ".join(tags[:3]) if tags else None,
            "playcount": track.get("playcount"),
            "listeners": track.get("listeners"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_artist_tags(artist: str) -> list:
    """Fetch artist tags from Last.fm as fallback."""
    try:
        resp = requests.get(LASTFM_URL, params={
            "method": "artist.getTopTags",
            "api_key": LASTFM_API_KEY,
            "artist": artist,
            "format": "json"
        }, timeout=10)
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        tags = []
        for tag in data.get("toptags", {}).get("tag", [])[:5]:
            tag_name = tag.get("name", "").lower()
            if tag_name and tag_name not in ["seen live", "favorites", "my favorite"]:
                tags.append(tag_name)
        return tags[:3]
    except:
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich missing track genres from Last.fm.")
    parser.add_argument("--limit", type=int, default=25, help="Max tracks to inspect (default: 25)")
    parser.add_argument("--apply", action="store_true", help="Write genre updates to DB (default: dry-run)")
    parser.add_argument("--sleep", type=float, default=0.25, help="Delay between API calls in seconds")
    args = parser.parse_args()

    if not LASTFM_API_KEY:
        print("ERROR: LASTFM_API_KEY not set in .env")
        return
    
    db_path = Path("lyra_registry.db")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Get tracks without genre
    cursor.execute("""
        SELECT track_id, artist, title FROM tracks 
        WHERE status='active' AND (genre IS NULL OR genre = '')
        ORDER BY artist
        LIMIT ?
    """, (max(1, args.limit),))
    tracks = cursor.fetchall()
    
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"Found {len(tracks)} tracks without genre\n")
    
    if not tracks:
        print("All tracks already have genre tags!")
        conn.close()
        return
    
    enriched = 0
    failed = 0
    artist_cache = {}  # Cache artist tags
    
    for i, (track_id, artist, title) in enumerate(tracks):
        print(f"[{i+1}/{len(tracks)}] {artist[:30]:30s} - {title[:40]}", end=" ")
        
        # Try track-level lookup first
        info = get_track_info(artist, title)
        genre = info.get("genre")
        
        # Fallback to artist tags
        if not genre:
            if artist not in artist_cache:
                artist_cache[artist] = get_artist_tags(artist)
                time.sleep(0.2)  # Rate limit
            
            artist_tags = artist_cache[artist]
            if artist_tags:
                genre = ", ".join(artist_tags)
        
        if genre:
            if args.apply:
                cursor.execute("UPDATE tracks SET genre = ? WHERE track_id = ?", (genre, track_id))
                print(f"-> {genre[:40]}")
            else:
                print(f"-> would set {genre[:40]}")
            enriched += 1
        else:
            print("-> (no tags found)")
            failed += 1
        
        time.sleep(max(0.0, args.sleep))
        
        # Commit every 50 tracks
        if args.apply and (i + 1) % 50 == 0:
            conn.commit()
            print(f"\n  Checkpoint: {enriched} enriched, {failed} failed\n")
    
    if args.apply:
        conn.commit()
    conn.close()
    
    print(f"\n=== Complete ===")
    print(f"Enriched: {enriched}")
    print(f"No tags found: {failed}")


if __name__ == "__main__":
    main()

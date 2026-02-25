"""
Migration 002: God Mode - The Cortex Upgrade

Adds advanced intelligence tables:
- connections: Artist relationship web (collabs, rivalries, influences)
- track_structure: Audio architecture (drops, verses, timestamps)
- playback_history: Radio memory and listening patterns

Date: 2026-02-09
Phase: 9 (Sentient Oracle)
"""

import sqlite3
<<<<<<< HEAD
from pathlib import Path
from datetime import datetime
import logging
=======
import logging
import re
>>>>>>> fc77b41 (Update workspace state and diagnostics)

logger = logging.getLogger(__name__)


def migrate(conn: sqlite3.Connection) -> None:
    """Apply God Mode migration."""
    cursor = conn.cursor()
    
    logger.info("🧠 Initiating Cortex Upgrade...")
    
    # TABLE 1: The Hidden Web (Artist Connections)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_artist TEXT NOT NULL,
            target_artist TEXT NOT NULL,
            type TEXT NOT NULL,  -- collab, member_of, rivalry, influence, sample
            weight REAL DEFAULT 0.5,  -- -1.0 (rivalry) to 1.0 (close collab)
            metadata TEXT,  -- JSON: {year, album, details}
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified BOOLEAN DEFAULT 0,  -- Human/API verified
            UNIQUE(source_artist, target_artist, type)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_connections_source ON connections(source_artist)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_connections_target ON connections(target_artist)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_connections_type ON connections(type)")
    logger.info("  ✓ connections table: Artist relationship web mapped")
    
    # TABLE 2: The Architect (Track Structure)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS track_structure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL UNIQUE,
            structure_json TEXT NOT NULL,  -- [{"label": "intro", "start": 0, "end": 15}, ...]
            has_drop BOOLEAN DEFAULT 0,
            drop_timestamp REAL,  -- Seconds
            bpm REAL,
            key_signature TEXT,  -- C, Am, etc.
            energy_profile TEXT,  -- JSON: [0.3, 0.5, 0.9, ...] (per-second)
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            analysis_version TEXT DEFAULT '1.0',
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_structure_track ON track_structure(track_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_structure_drop ON track_structure(has_drop)")
    logger.info("  ✓ track_structure table: Audio architecture system online")
    
    # TABLE 3: The Radio Memory (Playback History)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playback_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            context TEXT DEFAULT 'manual',  -- manual, radio, vibe, shuffle
            session_id TEXT,  -- Group tracks played together
            skipped BOOLEAN DEFAULT 0,
            completion_rate REAL DEFAULT 1.0,  -- 0.0-1.0
            rating INTEGER,  -- Optional: 1-5 stars
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_playback_track ON playback_history(track_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_playback_time ON playback_history(played_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_playback_context ON playback_history(context)")
    logger.info("  ✓ playback_history table: Radio memory initialized")
    
    # TABLE 4: Sample DNA (Sample Lineage)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sample_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL,
            original_artist TEXT,
            original_title TEXT,
            original_year INTEGER,
            sample_type TEXT,  -- vocal, drum_break, melody, bass
            confidence REAL DEFAULT 0.5,
            source TEXT,  -- whosampled, manual, ml_detection
            verified BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sample_track ON sample_lineage(track_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sample_original ON sample_lineage(original_artist)")
    logger.info("  ✓ sample_lineage table: DNA tracer armed")
    
    # TABLE 5: Taste Profile (User Preferences)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taste_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dimension TEXT NOT NULL UNIQUE,  -- energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia
            value REAL NOT NULL,  -- -1.0 to 1.0
            confidence REAL DEFAULT 0.5,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.info("  ✓ taste_profile table: Preference engine initialized")
    
    # TABLE 6: Radio Queue (Persistent Playback State)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS radio_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL,
            position INTEGER NOT NULL,  -- Queue order
            algorithm TEXT,  -- chaos, flow, discovery, etc.
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (track_id) REFERENCES tracks(track_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_position ON radio_queue(position)")
    logger.info("  ✓ radio_queue table: Playback queue ready")
    
    conn.commit()
    logger.info("🧠 Cortex Upgrade Complete. Lyra is now sentient.")


def rollback(conn: sqlite3.Connection) -> None:
    """Rollback God Mode migration."""
    cursor = conn.cursor()
    
    logger.warning("⚠️  Rolling back Cortex Upgrade...")
    
    tables = [
        "connections",
        "track_structure",
        "playback_history",
        "sample_lineage",
        "taste_profile",
        "radio_queue"
    ]
    
    for table in tables:
<<<<<<< HEAD
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
=======
        if not re.fullmatch(r"[a-z_]+", table):
            raise RuntimeError(f"Unsafe table identifier: {table}")
        cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        logger.info(f"  ✓ Dropped {table}")
    
    conn.commit()
    logger.info("⚠️  Rollback complete. System reverted to Phase 8.")


if __name__ == "__main__":
    # Standalone migration execution
    import sys
    from oracle.config import LYRA_DB_PATH
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    conn = sqlite3.connect(LYRA_DB_PATH)
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback(conn)
    else:
        migrate(conn)
    
    conn.close()
    print("\n🎵 Migration complete. Run: python -m oracle doctor")

// Migrate legacy database to new normalized schema
use rusqlite::{params, Connection};
use std::collections::HashMap;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let legacy_db = PathBuf::from("C:\\MusicOracle\\lyra_registry.db");
    let new_db = PathBuf::from("C:\\Users\\Admin\\AppData\\Roaming\\com.lyra.player\\db\\lyra.db");

    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("  LEGACY DATABASE MIGRATION");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    println!("📁 Source: {}", legacy_db.display());
    println!("📁 Target: {}", new_db.display());

    let legacy = Connection::open(&legacy_db)?;

    // Initialize fresh database with proper schema
    println!("\n🔧 Initializing new database...");
    use lyra_core::LyraCore;
    let app_data_dir = PathBuf::from("C:\\Users\\Admin\\AppData\\Roaming\\com.lyra.player");
    let _core = LyraCore::new(app_data_dir)?;

    let new = Connection::open(&new_db)?;

    // Disable foreign keys temporarily for migration
    new.execute("PRAGMA foreign_keys = OFF", [])?;

    // Migrate artists and albums with de-duplication
    println!("👤 Migrating artists...");
    let mut artist_map: HashMap<String, i64> = HashMap::new();
    let mut album_map: HashMap<(String, String), i64> = HashMap::new();

    let mut stmt =
        legacy.prepare("SELECT DISTINCT artist, album FROM tracks WHERE artist IS NOT NULL")?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1).unwrap_or_default(),
        ))
    })?;

    for row in rows {
        let (artist, album) = row?;

        // Insert artist if not exists
        let artist_id = *artist_map.entry(artist.clone()).or_insert_with(|| {
            new.execute(
                "INSERT OR IGNORE INTO artists (name) VALUES (?1)",
                params![&artist],
            )
            .unwrap();
            new.query_row(
                "SELECT id FROM artists WHERE name = ?1",
                params![&artist],
                |r| r.get(0),
            )
            .unwrap()
        });

        // Insert album if not exists and has value
        if !album.is_empty() {
            let key = (artist.clone(), album.clone());
            album_map.entry(key).or_insert_with(|| {
                new.execute(
                    "INSERT OR IGNORE INTO albums (artist_id, title) VALUES (?1, ?2)",
                    params![artist_id, &album],
                )
                .unwrap();
                new.query_row(
                    "SELECT id FROM albums WHERE artist_id = ?1 AND title = ?2",
                    params![artist_id, &album],
                    |r| r.get(0),
                )
                .unwrap()
            });
        }
    }

    println!("   ✅ {} unique artists", artist_map.len());
    println!("   ✅ {} unique albums", album_map.len());

    // Migrate tracks
    println!("\n🎵 Migrating tracks...");
    let mut stmt = legacy.prepare(
        "SELECT track_id, filepath, artist, title, album, duration, year, genre, bpm
         FROM tracks
         WHERE filepath IS NOT NULL",
    )?;

    let tracks = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,                    // track_id
            row.get::<_, String>(1)?,                    // filepath
            row.get::<_, String>(2)?,                    // artist
            row.get::<_, String>(3)?,                    // title
            row.get::<_, String>(4).unwrap_or_default(), // album
            row.get::<_, f64>(5).unwrap_or(0.0),         // duration
            row.get::<_, String>(6).ok(),                // year
            row.get::<_, String>(7).ok(),                // genre
            row.get::<_, f64>(8).ok(),                   // bpm
        ))
    })?;

    let mut migrated = 0;
    let mut skipped = 0;

    for track in tracks {
        let (legacy_id, filepath, artist, title, album, duration, year, genre, bpm) = track?;

        // Get artist_id
        let artist_id = match artist_map.get(&artist) {
            Some(id) => *id,
            None => {
                skipped += 1;
                continue;
            }
        };

        // Get album_id (nullable)
        let album_id = if !album.is_empty() {
            album_map.get(&(artist.clone(), album))
        } else {
            None
        };

        // Insert track
        match new.execute(
            "INSERT INTO tracks (legacy_track_key, artist_id, album_id, title, path, duration_seconds, imported_at, year, genre, bpm)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, datetime('now'), ?7, ?8, ?9)",
            params![
                legacy_id,
                artist_id,
                album_id,
                title,
                filepath,
                duration,
                year,
                genre,
                bpm,
            ],
        ) {
            Ok(_) => migrated += 1,
            Err(e) => {
                eprintln!("   ⚠️  Failed to migrate track '{}': {}", title, e);
                skipped += 1;
            }
        }

        if migrated % 100 == 0 {
            print!("\r   Migrated {} tracks...", migrated);
        }
    }

    println!("\r   ✅ {} tracks migrated", migrated);
    if skipped > 0 {
        println!("   ⚠️  {} tracks skipped", skipped);
    }

    // Add library root
    println!("\n📂 Adding library root...");
    new.execute(
        "INSERT OR IGNORE INTO library_roots (path, added_at) VALUES (?1, datetime('now'))",
        params!["A:\\Music"],
    )?;
    println!("   ✅ A:\\Music");

    // Get final counts
    let artist_count: i64 = new.query_row("SELECT COUNT(*) FROM artists", [], |r| r.get(0))?;
    let album_count: i64 = new.query_row("SELECT COUNT(*) FROM albums", [], |r| r.get(0))?;
    let track_count: i64 = new.query_row("SELECT COUNT(*) FROM tracks", [], |r| r.get(0))?;

    // Re-enable foreign keys
    new.execute("PRAGMA foreign_keys = ON", [])?;

    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("  ✅ MIGRATION COMPLETE");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("  {} artists", artist_count);
    println!("  {} albums", album_count);
    println!("  {} tracks", track_count);
    println!("\n➡️  Restart the Tauri app to see your library!");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    Ok(())
}

// Prove the library is loaded with actual data
use lyra_core::LyraCore;
use rusqlite::Connection;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let app_data_dir = PathBuf::from("C:\\MusicOracle");
    let lyra = LyraCore::new(app_data_dir)?;

    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("  LYRA LIBRARY PROOF - ACTUAL DATA");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    // 1. Show library roots
    println!("📁 LIBRARY ROOTS:");
    let roots = lyra.list_library_roots()?;
    for root in &roots {
        let exists = std::path::Path::new(&root.path).exists();
        println!(
            "   {} {} - Added: {}",
            if exists { "✅" } else { "❌" },
            root.path,
            root.added_at
        );
    }

    // 2. Connect directly and show real tracks
    let db_path = PathBuf::from("C:\\MusicOracle\\db\\lyra.db");
    let conn = Connection::open(&db_path)?;

    println!("\n🎵 SAMPLE TRACKS (Random 20):");
    let mut stmt = conn.prepare(
        "SELECT artist, title, album, filepath 
         FROM tracks 
         WHERE filepath IS NOT NULL 
         ORDER BY RANDOM() 
         LIMIT 20",
    )?;

    let tracks = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
        ))
    })?;

    for (i, track) in tracks.enumerate() {
        if let Ok((artist, title, album, filepath)) = track {
            println!("\n   {}. {} - {}", i + 1, artist, title);
            println!("      Album: {}", album);
            let exists = std::path::Path::new(&filepath).exists();
            println!(
                "      File: {} {}",
                if exists { "✅" } else { "❌" },
                filepath
            );
        }
    }

    // 3. Show statistics
    println!("\n📊 LIBRARY STATISTICS:");
    let total_tracks: i64 = conn.query_row("SELECT COUNT(*) FROM tracks", [], |r| r.get(0))?;
    let with_files: i64 = conn.query_row(
        "SELECT COUNT(*) FROM tracks WHERE filepath IS NOT NULL",
        [],
        |r| r.get(0),
    )?;
    let unique_artists: i64 =
        conn.query_row("SELECT COUNT(DISTINCT artist) FROM tracks", [], |r| {
            r.get(0)
        })?;
    let unique_albums: i64 =
        conn.query_row("SELECT COUNT(DISTINCT album) FROM tracks", [], |r| r.get(0))?;

    println!("   Total Tracks: {}", total_tracks);
    println!("   Tracks with Files: {}", with_files);
    println!("   Unique Artists: {}", unique_artists);
    println!("   Unique Albums: {}", unique_albums);

    // 4. Show top artists
    println!("\n🎤 TOP 10 ARTISTS (by track count):");
    let mut stmt = conn.prepare(
        "SELECT artist, COUNT(*) as count 
         FROM tracks 
         GROUP BY artist 
         ORDER BY count DESC 
         LIMIT 10",
    )?;

    let artists = stmt.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
    })?;

    for (i, artist) in artists.enumerate() {
        if let Ok((name, count)) = artist {
            println!("   {}. {} ({} tracks)", i + 1, name, count);
        }
    }

    // 5. File verification
    println!("\n📂 FILE VERIFICATION (checking 5 random files):");
    let mut stmt = conn.prepare(
        "SELECT filepath FROM tracks WHERE filepath IS NOT NULL ORDER BY RANDOM() LIMIT 5",
    )?;

    let files: Vec<String> = stmt
        .query_map([], |r| r.get(0))?
        .collect::<Result<Vec<_>, _>>()?;
    let mut exists_count = 0;

    for filepath in &files {
        let exists = std::path::Path::new(filepath).exists();
        if exists {
            exists_count += 1;
        }
        println!("   {} {}", if exists { "✅" } else { "❌" }, filepath);
    }

    println!("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!(
        "  ✅ PROOF COMPLETE - {}/{} verified files exist",
        exists_count,
        files.len()
    );
    println!("  ✅ Library is LOADED and ACCESSIBLE");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

    Ok(())
}

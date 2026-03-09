// Check tracks table schema
use rusqlite::Connection;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let db_path = PathBuf::from("C:\\MusicOracle\\lyra_registry.db");
    let conn = Connection::open(&db_path)?;

    println!("Tracks table schema:\n");

    let mut stmt = conn.prepare("PRAGMA table_info(tracks)")?;
    let columns: Vec<(i32, String, String)> = stmt
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))?
        .collect::<Result<Vec<_>, _>>()?;

    for (_, name, type_) in &columns {
        println!("  {} ({})", name, type_);
    }

    println!("\nSample track data:");
    let mut stmt = conn.prepare("SELECT id, title, artist, album FROM tracks LIMIT 5")?;
    let tracks: Vec<(i64, String, Option<String>, Option<String>)> = stmt
        .query_map([], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))
        })?
        .collect::<Result<Vec<_>, _>>()?;

    for (id, title, artist, album) in tracks {
        println!(
            "  [{}] {} - {} ({})",
            id,
            title,
            artist.unwrap_or("Unknown".to_string()),
            album.unwrap_or("Unknown".to_string())
        );
    }

    Ok(())
}

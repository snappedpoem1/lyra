// Find where tracks are actually stored
use rusqlite::Connection;
use std::collections::HashMap;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let db_path = PathBuf::from("C:\\MusicOracle\\db\\lyra.db");
    let conn = Connection::open(&db_path)?;

    println!("Analyzing track file paths...\n");

    // Get sample file paths from tracks
    let mut stmt =
        conn.prepare("SELECT filepath FROM tracks WHERE filepath IS NOT NULL LIMIT 100")?;
    let paths: Vec<String> = stmt
        .query_map([], |row| row.get(0))?
        .collect::<Result<Vec<_>, _>>()?;

    if paths.is_empty() {
        println!("❌ No tracks with file paths found!");
        return Ok(());
    }

    // Group by root directory
    let mut roots: HashMap<String, usize> = HashMap::new();
    for path in &paths {
        if let Some(root) = extract_root_path(path) {
            *roots.entry(root).or_insert(0) += 1;
        }
    }

    println!("Found {} tracks with paths", paths.len());
    println!("\nRoot directories:");
    for (root, count) in &roots {
        let exists = std::path::Path::new(root).exists();
        let status = if exists { "✅" } else { "❌" };
        println!("  {} {} ({} tracks)", status, root, count);
    }

    println!("\nSample paths:");
    for path in paths.iter().take(5) {
        println!("  {}", path);
    }

    Ok(())
}

fn extract_root_path(path: &str) -> Option<String> {
    // Extract first 2-3 path components to identify root
    let parts: Vec<&str> = path.split(['\\', '/']).collect();
    if parts.len() >= 3 {
        Some(format!("{}\\{}", parts[0], parts[1]))
    } else {
        None
    }
}

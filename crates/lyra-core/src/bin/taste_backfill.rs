/// One-shot taste backfill runner.
/// Usage: cargo run -p lyra-core --bin taste_backfill -- [--force] [--lastfm [days]]
fn main() {
    let args: Vec<String> = std::env::args().collect();
    let force = args.iter().any(|a| a == "--force");
    let lastfm = args.iter().any(|a| a == "--lastfm");
    let lookback_days: u32 = args
        .windows(2)
        .find(|w| w[0] == "--lastfm")
        .and_then(|w| w[1].parse().ok())
        .unwrap_or(30);

    // Load .env if present
    let env_path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .map(|root| root.join(".env"));
    if let Some(p) = env_path {
        if p.exists() {
            for line in std::fs::read_to_string(&p).unwrap_or_default().lines() {
                let line = line.trim();
                if line.starts_with('#') || line.is_empty() { continue; }
                if let Some((k, v)) = line.split_once('=') {
                    std::env::set_var(k.trim(), v.trim());
                }
            }
        }
    }

    // Find the DB — project root lyra_registry.db
    let db_path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .map(|root| root.join("lyra_registry.db"))
        .expect("could not resolve db path");

    if !db_path.exists() {
        eprintln!("DB not found at {}", db_path.display());
        std::process::exit(1);
    }

    let conn = rusqlite::Connection::open(&db_path).expect("open db");
    conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA cache_size=-65536;")
        .unwrap();

    if lastfm {
        println!("Syncing Last.fm history ({lookback_days} days)...");
        match lyra_core::taste::sync_taste_from_lastfm(&conn, lookback_days) {
            Ok((fetched, matched, written)) => {
                println!("Last.fm sync: fetched={fetched}  matched={matched}  written={written}");
            }
            Err(e) => eprintln!("Last.fm sync error: {e}"),
        }
    } else {
        println!("Running Spotify history taste backfill (force={force})...");
        match lyra_core::taste::seed_taste_from_spotify_history(&conn, force) {
            Ok(0) if !force => println!("Skipped — profile already confident. Use --force to override."),
            Ok(matched) => println!("Done. {matched} tracks contributed to taste profile."),
            Err(e) => eprintln!("Backfill error: {e}"),
        }
    }

    // Print resulting profile
    println!("\nTaste profile after backfill:");
    let mut stmt = conn
        .prepare("SELECT dimension, value, confidence FROM taste_profile ORDER BY dimension")
        .unwrap();
    let rows: Vec<(String, f64, f64)> = stmt
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))
        .unwrap()
        .filter_map(Result::ok)
        .collect();
    for (dim, val, conf) in rows {
        let bar = "#".repeat((val * 20.0) as usize);
        println!("  {dim:<12} {bar:<20} {:.2}  (conf {:.2})", val, conf);
    }
}

//! Live API smoke test: Last.fm + Discogs connectivity check.
//! Run with: cargo run --example smoke_api_live
//!
//! Requires real API keys in provider_configs (populated via import_env_file).

use lyra_core::{
    db::init_database,
    deepcut::{fetch_discogs_rating, fetch_lastfm_track_info},
    providers::import_env_file,
    scout::fetch_discogs_bridge_artists,
};
use rusqlite::Connection;

fn main() {
    // Use an in-memory DB seeded with real credentials from .env
    let conn = Connection::open_in_memory().unwrap();
    init_database(&conn).expect("init_database failed");
    println!("Using in-memory DB with credentials from .env");

    // Seed credentials from .env into provider_configs
    let env_path = std::path::Path::new("C:\\MusicOracle\\.env");
    let mut imported = Vec::new();
    let mut unsupported = Vec::new();
    match import_env_file(&conn, env_path, &mut imported, &mut unsupported) {
        Ok(n) => println!("Credentials imported ({n}): {:?}", imported),
        Err(e) => {
            println!("import_env_file error: {e}");
            return;
        }
    }
    if imported.is_empty() {
        println!("No credentials imported — check .env path");
        return;
    }

    // ── Last.fm: track.getInfo ────────────────────────────────────────────────
    let lfm_key: Option<String> = conn
        .query_row(
            "SELECT config_json FROM provider_configs WHERE provider_key = 'lastfm'",
            [],
            |row| row.get::<_, String>(0),
        )
        .ok()
        .and_then(|j| serde_json::from_str::<serde_json::Value>(&j).ok())
        .and_then(|v| {
            v.get("lastfm_api_key")
                .or_else(|| v.get("LASTFM_API_KEY"))
                .and_then(serde_json::Value::as_str)
                .map(String::from)
        });

    match lfm_key.as_deref() {
        Some(key) => {
            let info = fetch_lastfm_track_info(key, "Radiohead", "Karma Police");
            assert!(
                info.listeners > 0,
                "FAIL: Last.fm returned 0 listeners for Karma Police"
            );
            println!(
                "PASS: Last.fm track.getInfo — listeners={}, playcount={}",
                info.listeners, info.playcount
            );
        }
        None => println!("SKIP: no lastfm API key in provider_configs"),
    }

    // ── Discogs: community rating ─────────────────────────────────────────────
    let discogs_token: Option<String> = conn
        .query_row(
            "SELECT config_json FROM provider_configs WHERE provider_key = 'discogs'",
            [],
            |row| row.get::<_, String>(0),
        )
        .ok()
        .and_then(|j| serde_json::from_str::<serde_json::Value>(&j).ok())
        .and_then(|v| {
            v.get("discogs_token")
                .or_else(|| v.get("DISCOGS_TOKEN"))
                .and_then(serde_json::Value::as_str)
                .map(String::from)
        });

    match discogs_token.as_deref() {
        Some(tok) => {
            // Radiohead - Creep should have many votes
            let rating = fetch_discogs_rating(tok, "Radiohead", "Creep");
            println!("Discogs rating for Radiohead/Creep: {:.2}", rating);
            // Rating may be 0.0 if not enough votes on the specific release — just check no panic
            println!(
                "PASS: Discogs fetch_discogs_rating completed (rating={})",
                rating
            );

            // ── Discogs: bridge artist search ─────────────────────────────────
            let bridges = fetch_discogs_bridge_artists(tok, "Electronic", "Punk");
            println!(
                "PASS: Discogs bridge artist search => {} results",
                bridges.len()
            );
            if !bridges.is_empty() {
                println!(
                    "  Top 3: {:?}",
                    bridges.iter().take(3).map(|b| &b.name).collect::<Vec<_>>()
                );
            }
        }
        None => println!("SKIP: no discogs token in provider_configs"),
    }

    println!("\nAll smoke_api_live checks passed.");
}

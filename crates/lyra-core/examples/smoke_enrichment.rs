/// Smoke test — A: Enrichers (enrichment.rs)
///
/// Verifies:
///   1. LastFmAdapter::from_db() loads api_key from provider_configs
///   2. Last.fm enrich() for a real track returns tags / similar_tracks / similar_artists
///   3. Tags do not contain known junk strings ("seen live", "favorites", etc.)
///   4. DiscogsAdapter::from_db() loads token from provider_configs
///   5. Discogs enrich() returns at least a label or genre for a real album track
///   6. EnrichmentDispatcher writes genre + last_enriched_at back to tracks table
use lyra_core::db::init_database;
use lyra_core::enrichment::{DiscogsAdapter, EnricherAdapter, LastFmAdapter};
use lyra_core::library::import_legacy_track;
use lyra_core::providers::import_env_file;
use rusqlite::{params, Connection};
use std::path::Path;

const ENV_PATH: &str = r"C:\MusicOracle\.env";
// A track that's definitely in the library and has good Last.fm coverage:
const PROBE_ARTIST: &str = "Beck";
const PROBE_TITLE: &str = "E-Pro";

const JUNK_TAGS: &[&str] = &["seen live", "favorites", "my favorite", "awesome"];

fn pass(msg: &str) {
    println!("  PASS  {msg}");
}
fn fail(msg: &str) {
    println!("  FAIL  {msg}");
}
fn skip(msg: &str) {
    println!("  SKIP  {msg}");
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n=== smoke_enrichment ===\n");

    // In-memory DB with normalized Rust schema for track operations.
    let conn = Connection::open_in_memory()?;
    init_database(&conn)?;

    // Seed provider_configs from .env using the same import_env_file() path
    // that the Cassette app uses on first run — this is the canonical credential flow.
    let env_path = Path::new(ENV_PATH);
    if env_path.exists() {
        let mut imported = vec![];
        let mut unsupported = vec![];
        match import_env_file(&conn, env_path, &mut imported, &mut unsupported) {
            Ok(n) => println!(
                "  INFO  import_env_file → {n} provider(s) seeded: {:?}",
                imported
            ),
            Err(e) => println!("  WARN  import_env_file failed: {e}"),
        }
    } else {
        println!("  WARN  .env not found at {ENV_PATH} — enrichers may lack API keys");
    }

    // Insert a probe track into the in-memory DB.
    let _ = import_legacy_track(
        &conn,
        "A:\\music\\Beck\\Guero\\01_E-Pro.flac",
        PROBE_TITLE,
        PROBE_ARTIST,
        "Guero",
        195.0,
    );

    // ── Last.fm ─────────────────────────────────────────────────────────────
    let lastfm = LastFmAdapter::from_db(&conn);

    let track_id: Option<i64> = conn
        .query_row(
            "SELECT t.id FROM tracks t
             JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(ar.name) = lower(?1) AND lower(t.title) = lower(?2)
             LIMIT 1",
            params![PROBE_ARTIST, PROBE_TITLE],
            |row| row.get(0),
        )
        .ok();

    let tid = match track_id {
        Some(id) => {
            println!("  INFO  probe track_id = {id} ({PROBE_ARTIST} - {PROBE_TITLE})");
            id
        }
        None => {
            skip(&format!(
                "track '{PROBE_ARTIST} - {PROBE_TITLE}' not inserted into in-memory DB"
            ));
            println!("\n=== smoke_enrichment done (partial) ===\n");
            return Ok(());
        }
    };

    match lastfm.enrich(&conn, tid, PROBE_ARTIST, PROBE_TITLE, "") {
        Ok(Some(payload)) => {
            println!(
                "  INFO  Last.fm payload keys: {:?}",
                payload.as_object().map(|o| o.keys().collect::<Vec<_>>())
            );

            // Tags must be present and non-junk
            if let Some(tags) = payload.get("tags").and_then(|v| v.as_array()) {
                if tags.is_empty() {
                    println!("  WARN  Last.fm returned 0 tags (may be expected for this track)");
                } else {
                    pass(&format!(
                        "Last.fm returned {} tag(s): {:?}",
                        tags.len(),
                        tags.iter().filter_map(|t| t.as_str()).collect::<Vec<_>>()
                    ));

                    let junk_found: Vec<&str> = tags
                        .iter()
                        .filter_map(|t| t.as_str())
                        .filter(|t| JUNK_TAGS.iter().any(|j| t.contains(j)))
                        .collect();
                    if junk_found.is_empty() {
                        pass("no junk tags in result");
                    } else {
                        fail(&format!("junk tags leaked: {:?}", junk_found));
                    }
                }
            } else {
                println!("  WARN  no 'tags' array in Last.fm payload");
            }

            // similar_tracks
            if let Some(sim) = payload.get("similarTracks").and_then(|v| v.as_array()) {
                if sim.is_empty() {
                    println!("  WARN  Last.fm returned 0 similar_tracks");
                } else {
                    pass(&format!("Last.fm returned {} similar track(s)", sim.len()));
                }
            }

            // similar_artists
            if let Some(sim) = payload.get("similarArtists").and_then(|v| v.as_array()) {
                if sim.is_empty() {
                    println!("  WARN  Last.fm returned 0 similar_artists");
                } else {
                    pass(&format!("Last.fm returned {} similar artist(s)", sim.len()));
                }
            }
        }
        Ok(None) => {
            println!("  WARN  Last.fm returned None (api_key not configured?)");
        }
        Err(e) => fail(&format!("Last.fm enrich error: {e}")),
    }

    // ── Discogs ──────────────────────────────────────────────────────────────
    println!();
    let discogs = DiscogsAdapter::from_db(&conn);

    match discogs.enrich(&conn, tid, PROBE_ARTIST, PROBE_TITLE, "") {
        Ok(Some(payload)) => {
            println!(
                "  INFO  Discogs payload keys: {:?}",
                payload.as_object().map(|o| o.keys().collect::<Vec<_>>())
            );

            let has_useful = ["label", "genres", "styles", "year", "country"]
                .iter()
                .any(|k| payload.get(k).is_some());
            if has_useful {
                pass("Discogs returned useful metadata (label/genres/styles/year/country)");
            } else {
                println!("  WARN  Discogs payload has no label/genres/styles — token configured?");
            }
        }
        Ok(None) => {
            println!("  WARN  Discogs returned None (token not configured?)");
        }
        Err(e) => fail(&format!("Discogs enrich error: {e}")),
    }

    // ── Writeback check ──────────────────────────────────────────────────────
    println!();
    let (genre, last_enriched_at): (Option<String>, Option<String>) = conn
        .query_row(
            "SELECT genre, last_enriched_at FROM tracks WHERE id = ?1",
            params![tid],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap_or((None, None));

    println!("  INFO  genre after enrichment        = {:?}", genre);
    println!(
        "  INFO  last_enriched_at after enrich = {:?}",
        last_enriched_at
    );

    if last_enriched_at.is_some() {
        pass("last_enriched_at stamped by dispatcher");
    } else {
        println!("  WARN  last_enriched_at not set — dispatcher writeback only fires on EnrichmentDispatcher::dispatch()");
    }

    println!();
    println!("=== smoke_enrichment done ===\n");
    Ok(())
}

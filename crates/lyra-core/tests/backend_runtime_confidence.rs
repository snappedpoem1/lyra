use std::fs;
use std::path::PathBuf;

use chrono::Utc;
use lyra_core::{db, LyraCore};
use rusqlite::{params, Connection};
use serde_json::json;

const MUSICBRAINZ_CACHE_PROVIDER: &str = "musicbrainz_catalog";

fn temp_app_root(label: &str) -> PathBuf {
    std::env::temp_dir().join(format!(
        "lyra-core-{label}-{}-{}",
        std::process::id(),
        Utc::now().timestamp_nanos_opt().unwrap_or_default()
    ))
}

fn artist_search_cache_key(artist_name: &str) -> String {
    format!("artist-search:{}", artist_name.trim().to_ascii_lowercase())
}

fn release_group_cache_key(artist_mbid: &str, release_type: &str) -> String {
    format!(
        "release-groups:{}:{}",
        artist_mbid.trim().to_ascii_lowercase(),
        release_type.trim().to_ascii_lowercase()
    )
}

fn release_candidates_cache_key(release_group_mbid: &str) -> String {
    format!(
        "release-candidates:{}",
        release_group_mbid.trim().to_ascii_lowercase()
    )
}

fn release_detail_cache_key(release_mbid: &str) -> String {
    format!(
        "release-detail:{}",
        release_mbid.trim().to_ascii_lowercase()
    )
}

fn seed_cache(conn: &Connection, key: &str, payload: serde_json::Value) {
    conn.execute(
        "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
         VALUES (?1, ?2, ?3, ?4)",
        params![
            MUSICBRAINZ_CACHE_PROVIDER,
            key,
            payload.to_string(),
            Utc::now().to_rfc3339()
        ],
    )
    .expect("catalog cache seed");
}

fn seed_cursive_catalog(conn: &Connection) {
    seed_cache(
        conn,
        &artist_search_cache_key("Cursive"),
        json!({
            "artists": [{
                "id": "artist-cursive",
                "name": "Cursive",
                "type": "Group",
                "score": 100
            }]
        }),
    );
    seed_cache(
        conn,
        &release_group_cache_key("artist-cursive", "album"),
        json!({
            "release-groups": [
                {
                    "id": "rg-domestica",
                    "title": "Domestica",
                    "primary-type": "Album",
                    "secondary-types": [],
                    "first-release-date": "2000-06-13"
                },
                {
                    "id": "rg-ugly",
                    "title": "The Ugly Organ",
                    "primary-type": "Album",
                    "secondary-types": [],
                    "first-release-date": "2003-10-07"
                },
                {
                    "id": "rg-live",
                    "title": "Domestica Live",
                    "primary-type": "Album",
                    "secondary-types": [],
                    "first-release-date": "2005-06-13"
                }
            ]
        }),
    );
    seed_cache(
        conn,
        &release_group_cache_key("artist-cursive", "ep"),
        json!({ "release-groups": [] }),
    );

    for (release_group_id, release_id, title, tracks) in [
        (
            "rg-domestica",
            "release-domestica",
            "Domestica",
            vec![
                json!({
                    "position": 1,
                    "title": "The Casualty",
                    "recording": {"id": "rec-dom-1", "length": 191000}
                }),
                json!({
                    "position": 2,
                    "title": "A Red So Deep",
                    "recording": {"id": "rec-dom-2", "length": 233000}
                }),
            ],
        ),
        (
            "rg-ugly",
            "release-ugly",
            "The Ugly Organ",
            vec![
                json!({
                    "position": 1,
                    "title": "Some Red-Handed Sleight of Hand",
                    "recording": {"id": "rec-ugly-1", "length": 255000}
                }),
                json!({
                    "position": 2,
                    "title": "Art Is Hard",
                    "recording": {"id": "rec-ugly-2", "length": 160000}
                }),
            ],
        ),
    ] {
        seed_cache(
            conn,
            &release_candidates_cache_key(release_group_id),
            json!({
                "releases": [{
                    "id": release_id,
                    "title": title,
                    "status": "Official",
                    "country": "US",
                    "date": "2000-06-13",
                    "media": [{"track-count": tracks.len()}]
                }]
            }),
        );
        seed_cache(
            conn,
            &release_detail_cache_key(release_id),
            json!({ "media": [{"tracks": tracks}] }),
        );
    }
}

#[test]
fn backend_runtime_confidence_plans_discography_from_isolated_app_data_root() {
    let root = temp_app_root("runtime-confidence");
    let app_data_dir = root.join("Cassette").join("data");
    let library_root = root.join("Library");
    fs::create_dir_all(&library_root).expect("library root");

    let core = LyraCore::new(app_data_dir).expect("lyra core");
    let roots = core
        .add_library_root(library_root.display().to_string())
        .expect("add library root");
    assert_eq!(roots.len(), 1);
    assert!(core.paths().db_path.exists());

    let conn = db::connect(core.paths()).expect("open runtime db");
    seed_cursive_catalog(&conn);

    let preflight = core.acquisition_preflight().expect("acquisition preflight");
    assert!(preflight
        .notes
        .iter()
        .any(|note| note.contains("Rust-native") || note.contains("Rust planner")));

    let plan = core
        .plan_discography_acquisition(
            "Cursive".to_string(),
            Some("runtime-proof".to_string()),
            None,
            None,
        )
        .expect("discography plan");

    assert_eq!(plan.plan.kind, "discography");
    assert_eq!(plan.plan.canonical_artist.as_deref(), Some("Cursive"));
    assert_eq!(plan.queue_items.len(), 4);
    assert!(plan
        .items
        .iter()
        .all(|item| item.evidence_level == "provider_metadata"));

    let _ = fs::remove_dir_all(&root);
}

// ── BA-10: lineage ingest with cached edges ────────────────────────────────────

const MB_AI_PROVIDER: &str = "musicbrainz_artist_intelligence";

fn seed_mb_cache(conn: &Connection, key: &str, payload: serde_json::Value) {
    conn.execute(
        "INSERT OR REPLACE INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
         VALUES (?1, ?2, ?3, ?4)",
        params![
            MB_AI_PROVIDER,
            key,
            payload.to_string(),
            Utc::now().to_rfc3339()
        ],
    )
    .expect("mb cache seed");
}

#[test]
fn lineage_ingest_run_with_cached_mb_edges_persists_and_is_queryable() {
    use lyra_core::artist_intelligence::{ingest_artist_relationships, ingest_status};

    let root = temp_app_root("lineage-ingest");
    let app_data_dir = root.join("Cassette").join("data");

    let core = LyraCore::new(app_data_dir).expect("lyra core");
    let conn = db::connect(core.paths()).expect("open runtime db");

    // Insert a library artist that needs ingestion
    conn.execute("INSERT INTO artists (id, name) VALUES (1, 'Godspeed You! Black Emperor')", [])
        .expect("artist");
    conn.execute(
        "INSERT INTO albums (id, artist_id, title) VALUES (1, 1, 'F# A# ∞')",
        [],
    )
    .expect("album");
    conn.execute(
        "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, imported_at)
         VALUES (1, 1, 1, 'The Dead Flag Blues', 'C:/fake/gy!be-dead-flag.flac', 1000.0, '2026-03-10T00:00:00Z')",
        [],
    )
    .expect("track");

    // Seed the MB lookup cache so the ingestor doesn't make real HTTP calls
    let artist_mbid = "3648db01-b29d-4ab9-835c-83f6a5d2be51";
    seed_mb_cache(
        &conn,
        "mbid:godspeed you! black emperor",
        json!({ "id": artist_mbid, "name": "Godspeed You! Black Emperor" }),
    );

    let related_mbid = "1e5bee64-f9dd-4bc1-b4a8-371e29c41d23";
    seed_mb_cache(
        &conn,
        &format!("relations:{}", artist_mbid),
        json!({
            "relations": [{
                "type": "member of band",
                "direction": "forward",
                "artist": { "id": related_mbid, "name": "A Silver Mt. Zion" },
                "attributes": []
            }]
        }),
    );

    let result = ingest_artist_relationships(&conn, 5).expect("ingest");
    assert!(
        result.edges_inserted > 0,
        "expected at least one lineage edge to be inserted from cached MB data, got edges_inserted={}",
        result.edges_inserted
    );
    assert_eq!(result.artists_processed, 1);
    assert_eq!(result.errors.len(), 0);

    // Status reflects the run
    let status = ingest_status(&conn);
    assert!(
        status.last_run_at.is_some(),
        "ingest_status() should show a last_run_at after a run"
    );
    assert!(status.total_verified_edges > 0);

    let _ = fs::remove_dir_all(&root);
}

// ── BA-13: audio extraction status reporting ───────────────────────────────────

#[test]
fn audio_extraction_status_reports_after_batch_run() {
    use lyra_core::track_audio_features::{batch_extract, extraction_status};

    let root = temp_app_root("audio-extraction-status");
    let app_data_dir = root.join("Cassette").join("data");

    let core = LyraCore::new(app_data_dir).expect("lyra core");
    let conn = db::connect(core.paths()).expect("open runtime db");

    // Before any run the status has no last_run_at
    let before = extraction_status(&conn);
    assert!(before.last_run_at.is_none());

    // Run on an empty library — no tracks, so processed = 0 but log row still written
    let result = batch_extract(&conn, 50, false);
    assert_eq!(result.processed, 0, "empty library should yield 0 processed");

    let after = extraction_status(&conn);
    assert!(
        after.last_run_at.is_some(),
        "extraction_status() should show a last_run_at immediately after batch_extract()"
    );
    assert_eq!(after.last_run_processed, Some(0));

    let _ = fs::remove_dir_all(&root);
}

// ── G-060: acquisition lifecycle state transitions ─────────────────────────────

#[test]
fn acquisition_lifecycle_transitions_are_honest() {
    use lyra_core::acquisition::{add_acquisition_item, mark_failed, update_acquisition_status};

    let root = temp_app_root("acq-lifecycle");
    let app_data_dir = root.join("Cassette").join("data");

    let core = LyraCore::new(app_data_dir).expect("lyra core");
    let conn = db::connect(core.paths()).expect("open runtime db");

    // Queue a track acquisition item
    let item = add_acquisition_item(
        &conn,
        "Mogwai",
        "Mogwai Fear Satan",
        Some("Young Team"),
        Some("manual_test"),
        1.0,
        None,
        Some("Test track"),
        None,
        None,
    )
    .expect("queue item");

    assert_eq!(item.status, "queued", "newly added item should be queued");
    assert_eq!(item.lifecycle_stage.as_deref(), Some("queued"));
    let id = item.id;

    // Transition to validating
    let validating = update_acquisition_status(&conn, id, "validating", None)
        .expect("update status")
        .expect("item");
    assert_eq!(validating.status, "validating");
    assert_eq!(validating.lifecycle_stage.as_deref(), Some("validating"));

    // Transition to failed with a meaningful reason
    let failed = mark_failed(&conn, id, "validating", "No provider could confirm the track exists", None)
        .expect("mark failed")
        .expect("item");
    assert_eq!(failed.status, "failed");
    assert_eq!(failed.failure_stage.as_deref(), Some("validating"));
    assert!(
        failed.failure_reason.as_deref().unwrap_or("").contains("provider"),
        "failure_reason should describe why it failed"
    );
    assert!(
        failed.failed_at.is_some(),
        "failed_at timestamp must be set on failure"
    );

    // Verify that re-reading the item reflects the terminal failed state
    let reread = lyra_core::acquisition::get_acquisition_item(&conn, id)
        .expect("read")
        .expect("item still exists");
    assert_eq!(reread.status, "failed");

    let _ = fs::remove_dir_all(&root);
}

// ── BA-14: repeated bootstrap cycles (stability soak) ─────────────────────────

#[test]
fn repeated_bootstrap_cycles_are_stable() {
    // Create, use, and drop LyraCore 3x from the same app data root.
    // Each cycle must succeed and find the same library state as the previous.
    let root = temp_app_root("soak-cycle");
    let app_data_dir = root.join("Cassette").join("data");
    let library_root = root.join("Library");
    fs::create_dir_all(&library_root).expect("library root");

    for cycle in 1..=3 {
        let core = LyraCore::new(app_data_dir.clone()).expect(&format!("lyra core cycle {cycle}"));

        if cycle == 1 {
            // First cycle adds the library root
            let roots = core
                .add_library_root(library_root.display().to_string())
                .expect("add library root");
            assert_eq!(roots.len(), 1, "cycle 1: should have 1 root");
        } else {
            // Subsequent cycles should see the existing root
            let roots = core.list_library_roots().expect("list roots");
            assert_eq!(
                roots.len(),
                1,
                "cycle {cycle}: library root should persist across bootstrap"
            );
        }

        // DB path must exist on every cycle
        assert!(
            core.paths().db_path.exists(),
            "cycle {cycle}: db_path must exist after bootstrap"
        );

        // Drop the core, which should cleanly release the DB connection
        drop(core);
    }

    let _ = fs::remove_dir_all(&root);
}

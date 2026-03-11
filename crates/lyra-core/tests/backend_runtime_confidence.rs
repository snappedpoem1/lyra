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

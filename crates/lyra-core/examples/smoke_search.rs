//! Smoke test: search module — fallback_text_search, find_remixes, hybrid_search.

use lyra_core::{
    db::init_database,
    search::{fallback_text_search, find_remixes, hybrid_search, SearchFilters, SortBy},
};
use rusqlite::Connection;
use std::collections::HashMap;

fn seed(conn: &Connection) {
    // artists
    for (id, name) in [(1, "Radiohead"), (2, "Boards of Canada"), (3, "Portishead")] {
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (?1, ?2)",
            rusqlite::params![id, name],
        )
        .unwrap();
    }

    // albums
    for (id, artist_id, title) in [(1, 1, "OK Computer"), (2, 2, "Music Has the Right"), (3, 3, "Dummy"), (4, 1, "Pablo Honey")] {
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (?1, ?2, ?3)",
            rusqlite::params![id, artist_id, title],
        ).unwrap();
    }

    // tracks
    let tracks = [
        (1, 1, "Karma Police",         Some(1i64), Some(1997i32), "art rock",   None::<f64>),
        (2, 1, "Karma Police (Remix)", Some(1i64), Some(1997),    "art rock",   None),
        (3, 2, "Roygbiv",              Some(2i64), Some(1998),    "electronic", None),
        (4, 3, "Glory Box",            Some(3i64), Some(1994),    "trip hop",   None),
        (5, 1, "Creep",                Some(4i64), Some(1993),    "alternative",Some(92.0_f64)),
    ];
    for (id, artist_id, title, album_id, year, genre, bpm) in &tracks {
        conn.execute(
            "INSERT INTO tracks (id, artist_id, title, album_id, year, genre, bpm, path, imported_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, '2026-01-01')",
            rusqlite::params![
                id, artist_id, title, album_id, year, genre, bpm,
                format!("/music/{}.flac", title)
            ],
        )
        .unwrap();
    }

    // version_type column (added by classifier migration — add here for smoke test)
    conn.execute_batch(
        "ALTER TABLE tracks ADD COLUMN version_type TEXT;
         UPDATE tracks SET version_type='remix' WHERE id=2;"
    ).unwrap();

    // track_scores for dimensional filter tests
    let scores = [
        (1, 0.8, 0.4, 0.6, 0.5, 0.3, 0.5, 0.4, 0.7, 0.7, 0.2),
        (3, 0.6, 0.5, 0.4, 0.8, 0.2, 0.9, 0.6, 0.3, 0.8, 0.1),
        (4, 0.4, 0.7, 0.3, 0.3, 0.8, 0.4, 0.5, 0.4, 0.5, 0.5),
        (5, 0.6, 0.5, 0.3, 0.4, 0.4, 0.5, 0.4, 0.5, 0.4, 0.4),
    ];
    for (tid, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia) in &scores {
        conn.execute(
            "INSERT INTO track_scores (track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia, scored_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, '2026-01-01')",
            rusqlite::params![tid, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia],
        ).unwrap();
    }
}

fn main() {
    let conn = Connection::open_in_memory().unwrap();
    init_database(&conn).unwrap();
    seed(&conn);

    // ── Test 1: fallback_text_search ─────────────────────────────────────────
    let results = fallback_text_search(&conn, "karma police", 10).unwrap();
    assert!(!results.is_empty(), "FAIL: expected results for 'karma police'");
    assert!(
        results.iter().any(|r| r.title.contains("Karma Police")),
        "FAIL: 'Karma Police' not in results"
    );
    println!("PASS: fallback_text_search found {} result(s) for 'karma police'", results.len());

    // ── Test 2: artist-only search ────────────────────────────────────────────
    let results = fallback_text_search(&conn, "radiohead", 10).unwrap();
    assert!(
        results.iter().all(|r| r.artist.to_lowercase().contains("radiohead")),
        "FAIL: artist-only search returned non-Radiohead track"
    );
    println!("PASS: artist-only search => {} Radiohead tracks", results.len());

    // ── Test 3: empty query → returns all (browse mode) ──────────────────────
    let results = fallback_text_search(&conn, "", 10).unwrap();
    assert!(!results.is_empty(), "FAIL: empty query should return all tracks (browse mode)");
    println!("PASS: empty query returns {} tracks (browse mode)", results.len());

    // ── Test 4: find_remixes ──────────────────────────────────────────────────
    let remixes = find_remixes(&conn, Some("Radiohead"), Some("OK Computer"), Some("Karma Police"), 10, true, "relevance").unwrap();
    assert!(!remixes.is_empty(), "FAIL: expected at least 1 remix result");
    assert!(
        remixes.iter().any(|r| r.title.contains("Remix")),
        "FAIL: remix result title should contain 'Remix'"
    );
    println!("PASS: find_remixes found {} remix(es)", remixes.len());

    // ── Test 5: hybrid_search — no filters, all candidates ───────────────────
    let all_ids: Vec<i64> = (1..=5).collect();
    let filters = SearchFilters::default();
    let dim_ranges: HashMap<String, (f64, f64)> = HashMap::new();
    let results = hybrid_search(&conn, &all_ids, &filters, &dim_ranges, SortBy::Relevance, None, true, 10).unwrap();
    assert!(!results.is_empty(), "FAIL: hybrid_search with no filters should return results");
    println!("PASS: hybrid_search (no filters) => {} results", results.len());

    // ── Test 6: hybrid_search — artist filter ─────────────────────────────────
    let filters = SearchFilters {
        artist: Some("Radiohead".into()),
        ..Default::default()
    };
    let results = hybrid_search(&conn, &all_ids, &filters, &dim_ranges, SortBy::Artist, None, true, 10).unwrap();
    assert!(
        results.iter().all(|r| r.artist.to_lowercase().contains("radiohead")),
        "FAIL: artist filter returned non-Radiohead track"
    );
    println!("PASS: hybrid_search artist filter => {} Radiohead tracks", results.len());

    // ── Test 7: hybrid_search — exclude_remix ─────────────────────────────────
    let filters = SearchFilters { exclude_remix: true, ..Default::default() };
    let results = hybrid_search(&conn, &all_ids, &filters, &dim_ranges, SortBy::Relevance, None, true, 10).unwrap();
    assert!(
        results.iter().all(|r| r.version_type.as_deref() != Some("remix")),
        "FAIL: exclude_remix still returned a remix track"
    );
    println!("PASS: hybrid_search exclude_remix => {} non-remix tracks", results.len());

    // ── Test 8: hybrid_search — dimensional range ─────────────────────────────
    let mut dim_ranges_energy = HashMap::new();
    dim_ranges_energy.insert("energy".to_string(), (0.7_f64, 1.0_f64));
    let results = hybrid_search(&conn, &all_ids, &SearchFilters::default(), &dim_ranges_energy, SortBy::Dimension, Some("energy"), true, 10).unwrap();
    for r in &results {
        let energy = r.scores.get("energy").copied().unwrap_or(0.0);
        assert!(
            energy >= 0.7,
            "FAIL: track {} has energy {:.2} below dim range min 0.7",
            r.title, energy
        );
    }
    println!("PASS: dimensional range filter energy>=0.7 => {} tracks", results.len());

    println!("\nAll smoke_search checks passed.");
}

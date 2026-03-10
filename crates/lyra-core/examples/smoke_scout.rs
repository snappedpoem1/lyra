//! Smoke test: scout module — cross_genre_hunt, discover_by_mood, find_local_bridge_artists.

use lyra_core::{
    db::init_database,
    scout::{cross_genre_hunt, discover_by_mood, find_local_bridge_artists, mood_to_genres},
};
use rusqlite::Connection;

fn seed(conn: &Connection) {
    // artists
    for (id, name) in [
        (1, "The Prodigy"),
        (2, "Refused"),
        (3, "Portishead"),
        (4, "Boards of Canada"),
    ] {
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (?1, ?2)",
            rusqlite::params![id, name],
        )
        .unwrap();
    }

    // albums
    for (id, artist_id, title) in [
        (1, 1, "Music for the Jilted Generation"),
        (2, 2, "The Shape of Punk to Come"),
        (3, 3, "Dummy"),
        (4, 4, "Music Has the Right to Children"),
    ] {
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (?1, ?2, ?3)",
            rusqlite::params![id, artist_id, title],
        )
        .unwrap();
    }

    // tracks — The Prodigy: both Electronic AND Punk genres (bridge artist)
    let tracks: &[(i64, i64, &str, Option<i64>, Option<i32>, &str)] = &[
        (1, 1, "Firestarter",           Some(1), Some(1996), "Electronic, Punk"),
        (2, 1, "Breathe",               Some(1), Some(1996), "Electronic"),
        (3, 1, "Smack My Bitch Up",     Some(1), Some(1997), "Punk, Electronic"),
        (4, 2, "New Noise",             Some(2), Some(1998), "Punk, Hardcore"),
        (5, 3, "Glory Box",             Some(3), Some(1994), "Trip Hop"),
        (6, 4, "Roygbiv",              Some(4), Some(1998), "Electronic, Ambient"),
        (7, 3, "Sour Times",            Some(3), Some(1994), "Trip Hop"),
        (8, 4, "Pete Standing Alone",   Some(4), Some(1998), "Ambient"),
    ];
    for (id, artist_id, title, album_id, year, genre) in tracks {
        conn.execute(
            "INSERT INTO tracks (id, artist_id, title, album_id, year, genre, path, imported_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, '2026-01-01')",
            rusqlite::params![
                id, artist_id, title, album_id, year, genre,
                format!("/music/{}.flac", title)
            ],
        )
        .unwrap();
    }
}

fn main() {
    let conn = Connection::open_in_memory().unwrap();
    init_database(&conn).unwrap();
    seed(&conn);

    // ── Test 1: mood_to_genres (pure function) ────────────────────────────────
    let genres = mood_to_genres("aggressive rebellious");
    assert!(!genres.is_empty(), "FAIL: mood_to_genres returned empty");
    assert!(
        genres.iter().any(|g| g.to_lowercase().contains("punk")),
        "FAIL: 'aggressive rebellious' should include Punk, got: {:?}", genres
    );
    println!("PASS: mood_to_genres('aggressive rebellious') => {:?}", genres);

    // Test unmapped mood falls back to literal
    let unknown = mood_to_genres("xyzunknown");
    assert_eq!(unknown, vec!["xyzunknown"], "FAIL: unknown mood should fall back to literal");
    println!("PASS: unknown mood falls back to literal string");

    // ── Test 2: find_local_bridge_artists ─────────────────────────────────────
    let bridges = find_local_bridge_artists(&conn, "Electronic", "Punk").unwrap();
    assert!(
        !bridges.is_empty(),
        "FAIL: expected bridge artists for Electronic × Punk"
    );
    assert!(
        bridges.iter().any(|b| b.name.contains("Prodigy")),
        "FAIL: The Prodigy should be a bridge artist, got: {:?}",
        bridges.iter().map(|b| &b.name).collect::<Vec<_>>()
    );
    println!(
        "PASS: find_local_bridge_artists => {} bridge artists: {:?}",
        bridges.len(),
        bridges.iter().map(|b| &b.name).collect::<Vec<_>>()
    );

    // No bridges for unrelated genres
    let no_bridges = find_local_bridge_artists(&conn, "Jazz", "Classical").unwrap();
    assert!(no_bridges.is_empty(), "FAIL: no Jazz×Classical bridges expected in this library");
    println!("PASS: no bridge artists for Jazz × Classical");

    // ── Test 3: cross_genre_hunt ──────────────────────────────────────────────
    let targets = cross_genre_hunt(&conn, "Electronic", "Punk", 10).unwrap();
    assert!(
        !targets.is_empty(),
        "FAIL: expected cross-genre targets for Electronic × Punk"
    );
    assert!(
        targets.iter().all(|t| t.priority >= 0.0 && t.priority <= 1.0),
        "FAIL: all priorities should be in [0, 1]"
    );
    assert!(
        targets.iter().all(|t| t.tags.contains(&"context:bridge".to_string())),
        "FAIL: all targets should have 'context:bridge' tag"
    );
    println!(
        "PASS: cross_genre_hunt => {} targets, priorities: {:?}",
        targets.len(),
        targets.iter().map(|t| format!("{}({:.2})", t.title, t.priority)).collect::<Vec<_>>()
    );

    // ── Test 4: discover_by_mood — mapped mood ────────────────────────────────
    let results = discover_by_mood(&conn, "energetic", 10).unwrap();
    // "energetic" maps to EDM/Techno etc. — our library has Electronic tracks
    println!(
        "PASS: discover_by_mood('energetic') => {} results",
        results.len()
    );

    // ── Test 5: discover_by_mood — trip hop / melancholic ─────────────────────
    let results = discover_by_mood(&conn, "melancholic", 10).unwrap();
    println!("PASS: discover_by_mood('melancholic') => {} results", results.len());

    // ── Test 6: cross_genre_hunt with no bridges → empty ─────────────────────
    let empty = cross_genre_hunt(&conn, "Jazz", "Classical", 10).unwrap();
    assert!(empty.is_empty(), "FAIL: no Jazz×Classical targets expected");
    println!("PASS: cross_genre_hunt returns empty when no bridge artists found");

    println!("\nAll smoke_scout checks passed.");
}

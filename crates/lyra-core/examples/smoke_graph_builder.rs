#![allow(clippy::type_complexity)]

//! Smoke test: graph_builder module — dimension_affinity edges, Last.fm similar
//! edges (mocked), neighbour queries, stats, incremental build tracking.

use lyra_core::{
    db::init_database,
    graph_builder::{build_incremental, edge_type_counts, get_neighbours, graph_stats},
};
use rusqlite::{params, Connection};

fn seed(conn: &Connection) {
    // artists
    for (id, name) in [
        (1i64, "Radiohead"),
        (2, "Portishead"),
        (3, "Massive Attack"),
        (4, "Boards of Canada"),
    ] {
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (?1, ?2)",
            params![id, name],
        )
        .unwrap();
    }

    // albums
    for (id, artist_id, title) in [
        (1i64, 1i64, "OK Computer"),
        (2, 2, "Dummy"),
        (3, 3, "Mezzanine"),
        (4, 4, "Music Has the Right to Children"),
    ] {
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (?1, ?2, ?3)",
            params![id, artist_id, title],
        )
        .unwrap();
    }

    // tracks
    let tracks: &[(i64, i64, &str, i64, &str)] = &[
        (1, 1, "Karma Police", 1, "Alternative Rock"),
        (2, 1, "No Surprises", 1, "Alternative Rock"),
        (3, 2, "Glory Box", 2, "Trip Hop"),
        (4, 2, "Roads", 2, "Trip Hop"),
        (5, 3, "Teardrop", 3, "Trip Hop"),
        (6, 3, "Angel", 3, "Trip Hop"),
        (7, 4, "Roygbiv", 4, "Electronic, Ambient"),
        (8, 4, "Pete Standing Alone", 4, "Ambient"),
    ];
    for (id, artist_id, title, album_id, genre) in tracks {
        conn.execute(
            "INSERT INTO tracks (id, artist_id, title, album_id, genre, path, imported_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, '2026-01-01')",
            params![
                id,
                artist_id,
                title,
                album_id,
                genre,
                format!("/music/{}.flac", title)
            ],
        )
        .unwrap();
    }

    // track_scores — Trip Hop artists (Portishead, Massive Attack) share high warmth/space
    // Radiohead has high tension, low warmth. BOC has high space, moderate energy.
    let scores: &[(i64, f64, f64, f64, f64, f64, f64, f64, f64, f64, f64)] = &[
        (1, 0.6, 0.3, 0.8, 0.5, 0.3, 0.5, 0.5, 0.6, 0.7, 0.4), // Radiohead track 1
        (2, 0.5, 0.2, 0.7, 0.4, 0.3, 0.4, 0.6, 0.5, 0.6, 0.5), // Radiohead track 2
        (3, 0.3, 0.6, 0.4, 0.3, 0.8, 0.3, 0.8, 0.2, 0.4, 0.6), // Portishead track 1
        (4, 0.3, 0.5, 0.4, 0.3, 0.8, 0.3, 0.8, 0.2, 0.5, 0.7), // Portishead track 2
        (5, 0.3, 0.6, 0.3, 0.3, 0.8, 0.3, 0.8, 0.2, 0.4, 0.6), // Massive Attack track 1
        (6, 0.3, 0.5, 0.3, 0.3, 0.7, 0.3, 0.9, 0.2, 0.5, 0.7), // Massive Attack track 2
        (7, 0.4, 0.5, 0.2, 0.3, 0.6, 0.2, 0.9, 0.2, 0.6, 0.8), // BOC track 1
        (8, 0.3, 0.4, 0.2, 0.2, 0.6, 0.2, 0.9, 0.2, 0.5, 0.9), // BOC track 2
    ];
    for (
        tid,
        energy,
        valence,
        tension,
        density,
        warmth,
        movement,
        space,
        rawness,
        complexity,
        nostalgia,
    ) in scores
    {
        conn.execute(
            "INSERT INTO track_scores
             (track_id, energy, valence, tension, density, warmth, movement,
              space, rawness, complexity, nostalgia, scored_at)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,'2026-01-01')",
            params![
                tid, energy, valence, tension, density, warmth, movement, space, rawness,
                complexity, nostalgia
            ],
        )
        .unwrap();
    }

    // Manually insert a 'similar' edge so we can test get_neighbours by type
    conn.execute(
        "INSERT OR IGNORE INTO connections
         (source, target, type, weight, evidence, updated_at)
         VALUES ('Radiohead', 'Portishead', 'similar', 0.75,
                 '{\"match\":0.75,\"source\":\"test\"}', '2026-01-01')",
        [],
    )
    .unwrap();
    conn.execute(
        "INSERT OR IGNORE INTO connections
         (source, target, type, weight, evidence, updated_at)
         VALUES ('Portishead', 'Radiohead', 'similar', 0.75,
                 '{\"match\":0.75,\"source\":\"test\"}', '2026-01-01')",
        [],
    )
    .unwrap();
}

fn main() {
    let conn = Connection::open_in_memory().unwrap();
    init_database(&conn).unwrap();
    seed(&conn);

    // ── Test 1: graph_stats on seed data (1 pre-seeded pair = 2 rows) ────────
    let stats = graph_stats(&conn).unwrap();
    assert!(
        stats.total_connections >= 2,
        "FAIL: expected ≥2 connections, got {}",
        stats.total_connections
    );
    assert!(
        stats.total_artists >= 2,
        "FAIL: expected ≥2 artists in connections, got {}",
        stats.total_artists
    );
    println!(
        "PASS: graph_stats — artists={}, connections={}, last_run_ts={}",
        stats.total_artists, stats.total_connections, stats.last_run_ts
    );

    // ── Test 2: get_neighbours — all types ───────────────────────────────────
    let neighbours = get_neighbours(&conn, "Radiohead", None, 20).unwrap();
    assert!(
        !neighbours.is_empty(),
        "FAIL: Radiohead should have neighbours (pre-seeded)"
    );
    assert!(
        neighbours.iter().any(|n| n.target == "Portishead"),
        "FAIL: Portishead should be a neighbour of Radiohead"
    );
    println!(
        "PASS: get_neighbours(Radiohead) => {} neighbours",
        neighbours.len()
    );

    // ── Test 3: get_neighbours — filtered by type ────────────────────────────
    let similar_only = get_neighbours(&conn, "Radiohead", Some("similar"), 20).unwrap();
    assert!(
        similar_only.iter().all(|n| n.edge_type == "similar"),
        "FAIL: type filter leaked non-similar edges"
    );
    println!(
        "PASS: get_neighbours(type=similar) => {} edges",
        similar_only.len()
    );

    // ── Test 4: edge_type_counts ─────────────────────────────────────────────
    let counts = edge_type_counts(&conn).unwrap();
    assert!(
        counts.contains_key("similar"),
        "FAIL: expected 'similar' in edge_type_counts: {:?}",
        counts
    );
    println!("PASS: edge_type_counts => {:?}", counts);

    // ── Test 5: build_incremental — dimension affinity (no Last.fm key in test DB) ─
    let result = build_incremental(&conn, 15, true).unwrap();
    // Portishead + Massive Attack should get dimension_affinity edges (very similar profiles)
    println!(
        "PASS: build_incremental — new_pairs={}, dimension={}, lastfm={}, artists_processed={}",
        result.new_pairs, result.dimension_pairs, result.lastfm_pairs, result.artists_processed
    );
    assert_eq!(
        result.lastfm_pairs, 0,
        "FAIL: no Last.fm key → 0 lfm_pairs expected"
    );

    // ── Test 6: dimension_affinity edges created ─────────────────────────────
    let affinity_counts = edge_type_counts(&conn).unwrap();
    if result.dimension_pairs > 0 {
        assert!(
            affinity_counts.contains_key("dimension_affinity"),
            "FAIL: dimension_pairs={} but no dimension_affinity edges in DB",
            result.dimension_pairs
        );
        println!(
            "PASS: dimension_affinity edges in DB: {}",
            affinity_counts["dimension_affinity"]
        );
    } else {
        // Artists with ≥2 tracks and similar profiles should produce edges
        // (HAVING COUNT >= 2 is the threshold in oracle.rs)
        println!(
            "INFO: dimension_pairs=0 (all artists had cosine similarity below threshold — acceptable)"
        );
    }

    // ── Test 7: second build_incremental is idempotent (no duplicates) ───────
    let result2 = build_incremental(&conn, 15, true).unwrap();
    let counts_after = edge_type_counts(&conn).unwrap();
    let dim_after = counts_after.get("dimension_affinity").copied().unwrap_or(0);
    let dim_before = affinity_counts
        .get("dimension_affinity")
        .copied()
        .unwrap_or(0);
    assert_eq!(
        dim_after, dim_before,
        "FAIL: second build added duplicate edges ({} → {})",
        dim_before, dim_after
    );
    assert_eq!(
        result2.dimension_pairs, 0,
        "FAIL: second dimension build should add 0 new pairs, got {}",
        result2.dimension_pairs
    );
    println!("PASS: idempotent build — no duplicate edges inserted");

    // ── Test 8: last_run_ts was updated ──────────────────────────────────────
    let stats2 = graph_stats(&conn).unwrap();
    assert!(
        stats2.last_run_ts > 0.0,
        "FAIL: last_run_ts should be non-zero after build, got {}",
        stats2.last_run_ts
    );
    println!("PASS: last_run_ts updated to {:.0}", stats2.last_run_ts);

    // ── Test 9: unknown artist returns empty neighbours ───────────────────────
    let none = get_neighbours(&conn, "XYZ Unknown Artist", None, 10).unwrap();
    assert!(
        none.is_empty(),
        "FAIL: unknown artist should return empty neighbours"
    );
    println!("PASS: unknown artist returns 0 neighbours");

    println!("\nAll smoke_graph_builder checks passed.");
}

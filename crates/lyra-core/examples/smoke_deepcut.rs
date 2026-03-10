//! Smoke test: deepcut module — hunt_by_obscurity, hunt_with_taste_context, get_stats.

use lyra_core::{
    db::init_database,
    deepcut::{
        build_tags, compute_acclaim, compute_popularity_percentile,
        get_stats, hunt_by_obscurity, hunt_with_taste_context,
        DEFAULT_LISTENER_BUCKETS,
    },
};
use rusqlite::Connection;
use std::collections::HashMap;

fn seed(conn: &Connection) {
    for (id, name) in [(1, "Grouper"), (2, "Xiu Xiu"), (3, "Lana Del Rey")] {
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (?1, ?2)",
            rusqlite::params![id, name],
        )
        .unwrap();
    }

    for (id, artist_id, title_) in [(1, 1, "Ruins"), (2, 2, "A Promise"), (3, 3, "Born to Die")] {
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (?1, ?2, ?3)",
            rusqlite::params![id, artist_id, title_],
        )
        .unwrap();
    }

    let tracks: &[(i64, i64, &str, Option<i64>, &str)] = &[
        (1, 1, "Clearing",           Some(1), "Ambient"),
        (2, 1, "Labyrinthine",       Some(1), "Ambient"),
        (3, 2, "I Broke Up",         Some(2), "Experimental"),
        (4, 3, "Video Games",        Some(3), "Dream Pop"),
        (5, 3, "Summertime Sadness", Some(3), "Dream Pop"),
    ];
    for (id, artist_id, title, album_id, genre) in tracks {
        conn.execute(
            "INSERT INTO tracks (id, artist_id, title, album_id, genre, path, imported_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, '2026-01-01')",
            rusqlite::params![
                id, artist_id, title, album_id, genre,
                format!("/music/{}.flac", title)
            ],
        )
        .unwrap();
    }

    // Playback history — Lana Del Rey more played (mainstream proxy)
    for track_id in [4i64, 4, 5, 5, 5] {
        conn.execute(
            "INSERT INTO playback_history (track_id, ts, skipped) VALUES (?1, '2026-01-01', 0)",
            rusqlite::params![track_id],
        )
        .unwrap();
    }

    // track_scores for taste-context hunt
    let scores: &[(i64, f64, f64, f64, f64, f64, f64, f64, f64, f64, f64)] = &[
        (1, 0.1, 0.2, 0.3, 0.1, 0.8, 0.2, 0.9, 0.2, 0.6, 0.7), // Grouper: low energy, high space
        (2, 0.1, 0.2, 0.2, 0.1, 0.9, 0.1, 0.9, 0.2, 0.5, 0.8),
        (4, 0.5, 0.7, 0.3, 0.4, 0.6, 0.5, 0.4, 0.3, 0.4, 0.6), // Lana: mid energy
        (5, 0.5, 0.6, 0.3, 0.4, 0.6, 0.5, 0.4, 0.3, 0.4, 0.7),
    ];
    for (tid, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia) in scores {
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

    // ── Test 1: compute_popularity_percentile — pure math ─────────────────────
    let pct_unknown = compute_popularity_percentile(0, DEFAULT_LISTENER_BUCKETS);
    assert!(pct_unknown <= 0.01, "FAIL: 0 listeners should be nearly unknown, got {}", pct_unknown);

    let pct_mid = compute_popularity_percentile(150_000, DEFAULT_LISTENER_BUCKETS);
    assert!(pct_mid >= 0.5, "FAIL: 150k listeners expected ≥ 0.5 percentile, got {}", pct_mid);

    let pct_max = compute_popularity_percentile(10_000_000, DEFAULT_LISTENER_BUCKETS);
    assert_eq!(pct_max, 1.0, "FAIL: 10M listeners should be 1.0, got {}", pct_max);
    println!("PASS: compute_popularity_percentile (unknown={:.2}, mid={:.2}, max={:.2})", pct_unknown, pct_mid, pct_max);

    // ── Test 2: compute_acclaim — pure math ──────────────────────────────────
    let no_data = compute_acclaim(0.0);
    assert!((no_data - 0.5).abs() < 0.001, "FAIL: no Discogs data should yield 0.5, got {}", no_data);

    let high = compute_acclaim(4.5);
    assert!(high >= 0.8, "FAIL: 4.5/5 Discogs should be ≥ 0.8, got {}", high);
    println!("PASS: compute_acclaim (no_data={:.2}, high={:.2})", no_data, high);

    // ── Test 3: build_tags ───────────────────────────────────────────────────
    let tags = build_tags(1.2, 0.7, 0.08, "ambient");
    assert!(tags.contains(&"deepcut:true".to_string()), "FAIL: missing deepcut:true");
    assert!(tags.contains(&"tier:hidden_gem".to_string()), "FAIL: missing tier:hidden_gem");
    assert!(tags.contains(&"visibility:nearly_unknown".to_string()), "FAIL: missing visibility:nearly_unknown");
    assert!(tags.contains(&"quality:acclaimed".to_string()), "FAIL: missing quality:acclaimed");
    println!("PASS: build_tags => {:?}", tags);

    // ── Test 4: hunt_by_obscurity — no genre filter ────────────────────────
    let tracks = hunt_by_obscurity(&conn, None, None, 0.0, 20.0, 20).unwrap();
    assert!(!tracks.is_empty(), "FAIL: expected deep cut results");
    for t in &tracks {
        assert!(
            t.obscurity_score >= 0.0,
            "FAIL: negative obscurity_score for {}", t.title
        );
    }
    println!("PASS: hunt_by_obscurity => {} results", tracks.len());

    // ── Test 5: hunt_by_obscurity — Grouper (0 plays) should outscore Lana (5 plays) ──
    let grouper_max = tracks
        .iter()
        .filter(|t| t.artist.contains("Grouper"))
        .map(|t| t.obscurity_score)
        .fold(0.0_f64, f64::max);
    let lana_max = tracks
        .iter()
        .filter(|t| t.artist.contains("Lana"))
        .map(|t| t.obscurity_score)
        .fold(0.0_f64, f64::max);

    assert!(
        grouper_max >= lana_max,
        "FAIL: Grouper obscurity ({:.3}) should be ≥ Lana's ({:.3}) — fewer plays = more obscure",
        grouper_max, lana_max
    );
    println!("PASS: obscurity — Grouper({:.3}) ≥ Lana({:.3})", grouper_max, lana_max);

    // ── Test 6: hunt_by_obscurity — genre filter ──────────────────────────────
    let ambient = hunt_by_obscurity(&conn, Some("Ambient"), None, 0.0, 20.0, 20).unwrap();
    assert!(
        ambient.iter().all(|t| t.genre.to_lowercase().contains("ambient")),
        "FAIL: genre filter leaked non-ambient tracks"
    );
    println!("PASS: genre filter => {} ambient tracks", ambient.len());

    // ── Test 7: hunt_with_taste_context ───────────────────────────────────────
    let taste: HashMap<String, f64> = [
        ("energy", 0.1), ("space", 0.9), ("warmth", 0.8), ("nostalgia", 0.7),
        ("valence", 0.2), ("tension", 0.2), ("density", 0.1), ("movement", 0.1),
        ("rawness", 0.2), ("complexity", 0.5),
    ]
    .iter()
    .map(|(k, v)| (k.to_string(), *v))
    .collect();

    let taste_results = hunt_with_taste_context(&conn, &taste, 10).unwrap();
    assert!(!taste_results.is_empty(), "FAIL: taste hunt returned no results");
    for t in &taste_results {
        assert!(
            t.deep_cut_rank >= 0.0,
            "FAIL: negative deep_cut_rank for {}", t.title
        );
        assert!(
            t.taste_alignment >= 0.0 && t.taste_alignment <= 1.0,
            "FAIL: taste_alignment {} out of [0,1] for {}", t.taste_alignment, t.title
        );
    }
    // Grouper/ambient tracks should rank higher for ambient taste profile
    println!(
        "PASS: hunt_with_taste_context => {} results, top: {} ({:.3})",
        taste_results.len(),
        taste_results[0].title,
        taste_results[0].deep_cut_rank
    );

    // ── Test 8: get_stats ─────────────────────────────────────────────────────
    let stats = get_stats(&conn).unwrap();
    assert_eq!(stats.total_tracks, 5, "FAIL: expected 5 total tracks, got {}", stats.total_tracks);
    assert!(stats.median_obscurity >= 0.0, "FAIL: median_obscurity must be non-negative");
    println!(
        "PASS: get_stats — total={}, median_obscurity={:.3}, high_potential={}",
        stats.total_tracks, stats.median_obscurity, stats.high_potential_count
    );

    println!("\nAll smoke_deepcut checks passed.");
}

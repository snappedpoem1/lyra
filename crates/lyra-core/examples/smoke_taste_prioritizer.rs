//! Smoke test: taste_prioritizer module.

use lyra_core::{
    db::init_database,
    taste_prioritizer::{get_next_priority_batch, prioritize_queue},
};
use rusqlite::Connection;

fn main() {
    let conn = Connection::open_in_memory().unwrap();
    init_database(&conn).unwrap();

    // ── Test 1: no taste profile → no_taste=true, no crash ───────────────────
    let stats = prioritize_queue(&conn, 0).unwrap();
    assert!(stats.no_taste, "FAIL: expected no_taste=true with empty taste_profile");
    println!("PASS: prioritize_queue with no taste profile => no_taste=true");

    // ── Seed taste profile ────────────────────────────────────────────────────
    for (dim, val) in [
        ("energy", 0.8), ("valence", 0.5), ("tension", 0.6), ("density", 0.7),
        ("warmth", 0.3), ("movement", 0.7), ("space", 0.2), ("rawness", 0.8),
        ("complexity", 0.5), ("nostalgia", 0.2),
    ] {
        conn.execute(
            "INSERT INTO taste_profile (dimension, value, confidence, last_updated)
             VALUES (?1, ?2, 1.0, '2026-01-01')",
            rusqlite::params![dim, val],
        ).unwrap();
    }

    // ── Seed acquisition_queue items ──────────────────────────────────────────
    for (artist, title, album) in [
        ("Beck",       "E-Pro",       "Guero"),
        ("Metallica",  "Enter Sandman","Black Album"),
        ("Enya",       "Orinoco Flow", "Watermark"),
        ("",           "Unknown",     ""),        // no artist → should be skipped
    ] {
        conn.execute(
            "INSERT INTO acquisition_queue (artist, title, album, status, priority_score, added_at)
             VALUES (?1, ?2, ?3, 'pending', 5.0, '2026-01-01')",
            rusqlite::params![artist, title, album],
        ).unwrap();
    }

    // ── Test 2: prioritize_queue re-scores pending items ──────────────────────
    let stats = prioritize_queue(&conn, 0).unwrap();
    assert!(!stats.no_taste, "FAIL: taste profile seeded, should not be no_taste");
    assert_eq!(stats.updated, 3, "FAIL: expected 3 updated, got {}", stats.updated);
    assert_eq!(stats.skipped, 1, "FAIL: expected 1 skipped (no artist), got {}", stats.skipped);
    println!("PASS: prioritize_queue => updated={}, skipped={}", stats.updated, stats.skipped);

    // ── Test 3: scores are in valid range ─────────────────────────────────────
    let items = get_next_priority_batch(&conn, 10, "pending").unwrap();
    assert_eq!(items.len(), 4, "FAIL: expected 4 items, got {}", items.len());
    for item in &items {
        assert!(
            item.priority_score >= 1.0 && item.priority_score <= 9.5,
            "FAIL: priority_score {} out of range [1.0, 9.5] for {}",
            item.priority_score, item.artist
        );
    }
    println!("PASS: all priority_scores in [1.0, 9.5]");

    // ── Test 4: order is descending by score ──────────────────────────────────
    let scores: Vec<f64> = items.iter().map(|i| i.priority_score).collect();
    let sorted = {
        let mut s = scores.clone();
        s.sort_by(|a, b| b.partial_cmp(a).unwrap());
        s
    };
    assert_eq!(scores, sorted, "FAIL: items not sorted by priority_score DESC");
    println!(
        "PASS: batch sorted DESC: {}",
        items.iter().map(|i| format!("{}({:.2})", i.artist, i.priority_score)).collect::<Vec<_>>().join(", ")
    );

    // ── Test 5: genre heuristic — Metallica (metal) should outscore Enya (ambient)
    //    given a taste profile biased toward high energy+rawness
    let metallica = items.iter().find(|i| i.artist == "Metallica").unwrap();
    let enya      = items.iter().find(|i| i.artist == "Enya").unwrap();
    assert!(
        metallica.priority_score >= enya.priority_score,
        "FAIL: Metallica ({:.2}) should outscore Enya ({:.2}) for high-energy taste",
        metallica.priority_score, enya.priority_score
    );
    println!(
        "PASS: genre heuristic — Metallica({:.2}) >= Enya({:.2}) for energy/rawness taste",
        metallica.priority_score, enya.priority_score
    );

    println!("\nAll smoke_taste_prioritizer checks passed.");
}

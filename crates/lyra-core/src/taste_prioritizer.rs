//! Taste-driven acquisition queue prioritizer.
//!
//! Re-scores `acquisition_queue` items by how well each artist/title aligns
//! with the current `taste_profile`.  Two-pass strategy:
//!   - Pass A: artist already exists in local library → score by average track dims
//!   - Pass B: unknown artist → score by genre-tag heuristics mapped to dimensions
//!
//! Priority scale: 0.0–10.0. Cosine similarity 1.0 → 9.5, 0.0 → 1.0.

use serde::Serialize;
use std::collections::HashMap;

use rusqlite::{params, Connection};

use crate::errors::LyraResult;

// ── Constants ────────────────────────────────────────────────────────────────

const ALL_DIMS: [&str; 10] = [
    "energy",
    "valence",
    "tension",
    "density",
    "warmth",
    "movement",
    "space",
    "rawness",
    "complexity",
    "nostalgia",
];

/// Genre keyword → dimension boosts (value replaces 0.5 base if higher).
fn genre_boost_table() -> &'static [(&'static str, &'static [(&'static str, f64)])] {
    &[
        (
            "hip-hop",
            &[("energy", 0.6), ("rawness", 0.7), ("density", 0.4)],
        ),
        (
            "rap",
            &[("energy", 0.6), ("rawness", 0.7), ("density", 0.4)],
        ),
        (
            "electronic",
            &[("energy", 0.7), ("movement", 0.8), ("tension", 0.5)],
        ),
        (
            "edm",
            &[("energy", 0.8), ("movement", 0.9), ("tension", 0.6)],
        ),
        (
            "pop",
            &[("valence", 0.7), ("warmth", 0.5), ("density", 0.3)],
        ),
        (
            "rock",
            &[("energy", 0.6), ("rawness", 0.5), ("tension", 0.4)],
        ),
        (
            "jazz",
            &[("complexity", 0.8), ("warmth", 0.6), ("nostalgia", 0.5)],
        ),
        (
            "classical",
            &[("complexity", 0.9), ("space", 0.8), ("tension", 0.3)],
        ),
        (
            "r&b",
            &[("warmth", 0.7), ("valence", 0.6), ("movement", 0.5)],
        ),
        (
            "soul",
            &[("warmth", 0.8), ("rawness", 0.4), ("nostalgia", 0.6)],
        ),
        (
            "ambient",
            &[("space", 0.9), ("energy", 0.1), ("tension", 0.1)],
        ),
        (
            "metal",
            &[("energy", 0.9), ("rawness", 0.9), ("tension", 0.8)],
        ),
        (
            "indie",
            &[("rawness", 0.5), ("nostalgia", 0.4), ("complexity", 0.4)],
        ),
        (
            "folk",
            &[("warmth", 0.7), ("nostalgia", 0.6), ("rawness", 0.4)],
        ),
        (
            "blues",
            &[("rawness", 0.6), ("warmth", 0.7), ("nostalgia", 0.7)],
        ),
    ]
}

type DimVec = HashMap<String, f64>;
type ArtistAvgRow = (
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
);

// ── Internal helpers ─────────────────────────────────────────────────────────

fn load_taste_profile(conn: &Connection) -> Option<DimVec> {
    let mut stmt = conn
        .prepare("SELECT dimension, value FROM taste_profile")
        .ok()?;
    let rows: Vec<(String, f64)> = stmt
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
        .ok()?
        .filter_map(Result::ok)
        .collect();
    if rows.is_empty() {
        return None;
    }
    Some(rows.into_iter().collect())
}

fn artist_avg_scores(conn: &Connection, artist: &str) -> Option<DimVec> {
    let row: Option<ArtistAvgRow> = conn
        .query_row(
            "SELECT AVG(ts.energy), AVG(ts.valence), AVG(ts.tension), AVG(ts.density),
                    AVG(ts.warmth), AVG(ts.movement), AVG(ts.space), AVG(ts.rawness),
                    AVG(ts.complexity), AVG(ts.nostalgia)
             FROM track_scores ts
             JOIN tracks t ON t.id = ts.track_id
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE LOWER(ar.name) LIKE LOWER(?1)
               AND (t.quarantined IS NULL OR t.quarantined = 0)
               AND ts.energy IS NOT NULL",
            params![format!("%{}%", artist)],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                    row.get(6)?,
                    row.get(7)?,
                    row.get(8)?,
                    row.get(9)?,
                ))
            },
        )
        .ok();

    let row = row?;
    // If energy (first dim) is None, artist has no scored tracks
    row.0?;

    let vals = [
        row.0, row.1, row.2, row.3, row.4, row.5, row.6, row.7, row.8, row.9,
    ];
    Some(
        ALL_DIMS
            .iter()
            .zip(vals.iter())
            .map(|(&dim, val)| (dim.to_string(), val.unwrap_or(0.5)))
            .collect(),
    )
}

fn genre_score_vector(hint: &str) -> DimVec {
    let mut base: DimVec = ALL_DIMS.iter().map(|&d| (d.to_string(), 0.5)).collect();
    let lower = hint.to_lowercase();
    for (keyword, boosts) in genre_boost_table() {
        if lower.contains(keyword) {
            for (dim, val) in *boosts {
                let entry = base.entry(dim.to_string()).or_insert(0.5);
                *entry = entry.max(*val);
            }
        }
    }
    base
}

fn cosine_similarity(a: &DimVec, b: &DimVec) -> f64 {
    let dims: Vec<&str> = ALL_DIMS
        .iter()
        .copied()
        .filter(|&d| a.contains_key(d) && b.contains_key(d))
        .collect();
    if dims.is_empty() {
        return 0.0;
    }
    let dot: f64 = dims.iter().map(|&d| a[d] * b[d]).sum();
    let mag_a: f64 = dims.iter().map(|&d| a[d].powi(2)).sum::<f64>().sqrt();
    let mag_b: f64 = dims.iter().map(|&d| b[d].powi(2)).sum::<f64>().sqrt();
    if mag_a == 0.0 || mag_b == 0.0 {
        return 0.0;
    }
    (dot / (mag_a * mag_b)).clamp(0.0, 1.0)
}

/// Map cosine similarity [0,1] → priority [1.0, 9.5].
fn compute_priority(taste: &DimVec, track_scores: &DimVec) -> f64 {
    let sim = cosine_similarity(taste, track_scores);
    (1.0 + sim * 8.5 * 100.0).round() / 100.0
}

// ── Public API ───────────────────────────────────────────────────────────────

#[derive(Debug, Default, Serialize)]
pub struct PrioritizeStats {
    pub updated: usize,
    pub skipped: usize,
    pub no_taste: bool,
}

/// Re-score all pending acquisition_queue items by taste alignment.
pub fn prioritize_queue(conn: &Connection, limit: usize) -> LyraResult<PrioritizeStats> {
    let taste = match load_taste_profile(conn) {
        Some(t) => t,
        None => {
            return Ok(PrioritizeStats {
                no_taste: true,
                ..Default::default()
            })
        }
    };

    let sql = if limit > 0 {
        format!(
            "SELECT id, artist, title, album FROM acquisition_queue WHERE status='pending' LIMIT {}",
            limit
        )
    } else {
        "SELECT id, artist, title, album FROM acquisition_queue WHERE status='pending'".into()
    };

    let items: Vec<(i64, String, String, String)> = conn
        .prepare(&sql)?
        .query_map([], |row| {
            Ok((
                row.get(0)?,
                row.get::<_, Option<String>>(1)?.unwrap_or_default(),
                row.get::<_, Option<String>>(2)?.unwrap_or_default(),
                row.get::<_, Option<String>>(3)?.unwrap_or_default(),
            ))
        })?
        .filter_map(Result::ok)
        .collect();

    let mut updated = 0usize;
    let mut skipped = 0usize;

    for (item_id, artist, title, album) in &items {
        if artist.is_empty() {
            skipped += 1;
            continue;
        }

        // Pass A: known artist → average dims from library
        let scores = artist_avg_scores(conn, artist)
            // Pass B: genre heuristic from album/title
            .unwrap_or_else(|| genre_score_vector(&format!("{} {}", album, title)));

        let new_priority = compute_priority(&taste, &scores);
        conn.execute(
            "UPDATE acquisition_queue SET priority_score=?1 WHERE id=?2",
            params![new_priority, item_id],
        )?;
        updated += 1;
    }

    Ok(PrioritizeStats {
        updated,
        skipped,
        no_taste: false,
    })
}

/// Return the next N highest-priority pending queue items.
pub fn get_next_priority_batch(
    conn: &Connection,
    limit: usize,
    status: &str,
) -> LyraResult<Vec<QueueItem>> {
    let items = conn
        .prepare(
            "SELECT id, artist, title, album, priority_score
             FROM acquisition_queue
             WHERE status = ?1
             ORDER BY priority_score DESC, id ASC
             LIMIT ?2",
        )?
        .query_map(params![status, limit as i64], |row| {
            Ok(QueueItem {
                id: row.get(0)?,
                artist: row.get::<_, Option<String>>(1)?.unwrap_or_default(),
                title: row.get::<_, Option<String>>(2)?.unwrap_or_default(),
                album: row.get::<_, Option<String>>(3)?.unwrap_or_default(),
                priority_score: row.get::<_, Option<f64>>(4)?.unwrap_or(5.0),
            })
        })?
        .filter_map(Result::ok)
        .collect();
    Ok(items)
}

#[derive(Debug, Clone, Serialize)]
pub struct QueueItem {
    pub id: i64,
    pub artist: String,
    pub title: String,
    pub album: String,
    pub priority_score: f64,
}

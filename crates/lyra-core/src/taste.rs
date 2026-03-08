use std::collections::HashMap;

use chrono::Utc;
use rusqlite::{params, Connection};

use crate::commands::TasteProfile;
use crate::errors::LyraResult;

const DIMS: &[&str] = &[
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

pub fn get_taste_profile(conn: &Connection) -> LyraResult<TasteProfile> {
    let mut stmt = conn
        .prepare("SELECT dimension, value, confidence FROM taste_profile ORDER BY dimension ASC")?;
    let rows: Vec<(String, f64, f64)> = stmt
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))?
        .filter_map(Result::ok)
        .collect();

    if rows.is_empty() {
        return Ok(TasteProfile::default());
    }

    let avg_confidence = rows.iter().map(|(_, _, c)| c).sum::<f64>() / rows.len() as f64;
    let dimensions: HashMap<String, f64> = rows.into_iter().map(|(d, v, _)| (d, v)).collect();

    let total_signals: i64 = conn
        .query_row("SELECT COUNT(*) FROM playback_history", [], |row| {
            row.get(0)
        })
        .unwrap_or(0);

    Ok(TasteProfile {
        dimensions,
        confidence: avg_confidence,
        total_signals,
        source: "learned".to_string(),
    })
}

pub fn save_taste_profile(conn: &Connection, profile: &TasteProfile) -> LyraResult<()> {
    let now = Utc::now().to_rfc3339();
    for (dim, val) in &profile.dimensions {
        let confidence = profile.confidence;
        conn.execute(
            "INSERT INTO taste_profile (dimension, value, confidence, last_updated)
             VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(dimension) DO UPDATE SET
               value=excluded.value, confidence=excluded.confidence, last_updated=excluded.last_updated",
            params![dim, val, confidence, now],
        )?;
    }
    Ok(())
}

/// Update the taste profile dimensions based on a completed or skipped playback event.
/// When `completion_rate >= 0.5`, nudge dimensions toward the track's scores (positive signal).
/// When `completion_rate < 0.1`, nudge dimensions away (negative signal / skip).
/// No-ops if the track has no score row.
pub fn update_taste_from_completion(
    conn: &Connection,
    track_id: i64,
    completion_rate: f64,
) -> LyraResult<()> {
    // Load current track scores.
    let row = conn.query_row(
        "SELECT energy, valence, tension, density, warmth, movement,
                space, rawness, complexity, nostalgia
         FROM track_scores WHERE track_id = ?1",
        params![track_id],
        |row| {
            Ok([
                row.get::<_, f64>(0)?,
                row.get::<_, f64>(1)?,
                row.get::<_, f64>(2)?,
                row.get::<_, f64>(3)?,
                row.get::<_, f64>(4)?,
                row.get::<_, f64>(5)?,
                row.get::<_, f64>(6)?,
                row.get::<_, f64>(7)?,
                row.get::<_, f64>(8)?,
                row.get::<_, f64>(9)?,
            ])
        },
    );
    let Ok(track_vals) = row else {
        return Ok(()); // no score row — skip silently
    };

    // Load existing taste profile.
    let mut stmt = conn
        .prepare("SELECT dimension, value, confidence FROM taste_profile ORDER BY dimension ASC")?;
    let existing: Vec<(String, f64, f64)> = stmt
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))?
        .filter_map(Result::ok)
        .collect();
    if existing.is_empty() {
        return Ok(()); // no profile yet — can't update
    }

    let is_positive = completion_rate >= 0.5;
    let is_skip = completion_rate < 0.1;
    if !is_positive && !is_skip {
        return Ok(()); // partial play — not enough signal
    }

    // Small EMA step: 3% toward (positive) or away (skip) from the track value.
    let alpha = 0.03_f64;
    let now = Utc::now().to_rfc3339();
    let dim_order: &[&str] = DIMS;

    let dim_vals: HashMap<String, (f64, f64)> = existing
        .into_iter()
        .map(|(d, v, c)| (d, (v, c)))
        .collect();

    for (i, &dim) in dim_order.iter().enumerate() {
        let Some(&(old_val, old_conf)) = dim_vals.get(dim) else {
            continue;
        };
        let track_val = track_vals[i];
        let target = if is_positive {
            track_val
        } else {
            1.0 - track_val // push away
        };
        let new_val = (old_val * (1.0 - alpha) + target * alpha).clamp(0.0, 1.0);
        // Confidence grows slowly (up to a ceiling of 1.0).
        let new_conf = (old_conf + 0.001).min(1.0);
        conn.execute(
            "INSERT INTO taste_profile (dimension, value, confidence, last_updated)
             VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(dimension) DO UPDATE SET
               value=excluded.value, confidence=excluded.confidence, last_updated=excluded.last_updated",
            params![dim, new_val, new_conf, now],
        )?;
    }
    Ok(())
}

pub fn import_taste_from_legacy(conn: &Connection, legacy: &Connection) -> LyraResult<usize> {
    let mut stmt = legacy.prepare("SELECT dimension, value, confidence FROM taste_profile")?;
    let rows: Vec<(String, f64, f64)> = stmt
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))?
        .filter_map(Result::ok)
        .collect();

    let now = Utc::now().to_rfc3339();
    let mut count = 0_usize;

    for (dim, val, confidence) in &rows {
        if !DIMS.contains(&dim.as_str()) {
            continue;
        }
        conn.execute(
            "INSERT INTO taste_profile (dimension, value, confidence, last_updated)
             VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(dimension) DO NOTHING",
            params![dim, val, confidence, now],
        )?;
        count += 1;
    }
    Ok(count)
}

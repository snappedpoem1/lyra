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

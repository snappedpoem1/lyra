use std::collections::HashMap;

use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};

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

    let dim_vals: HashMap<String, (f64, f64)> =
        existing.into_iter().map(|(d, v, c)| (d, (v, c))).collect();

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

/// Seed the taste profile from `spotify_history` play counts and local track scores.
///
/// The algorithm:
///   1. Join spotify_history → tracks (by lower artist + title match) → track_scores.
///   2. Weight each track by: play_count * ln(1 + total_ms_played / 30_000).
///   3. Compute a weighted average across all 10 dimensions.
///   4. Write to taste_profile with confidence = matched_tracks / (matched_tracks + 20).clamp(0,1).
///
/// `force`: if false, skips when taste_profile already has avg confidence ≥ 0.5.
/// Returns the number of tracks that contributed to the seed.
pub fn seed_taste_from_spotify_history(conn: &Connection, force: bool) -> LyraResult<usize> {
    // Guard: skip if existing profile is already confident and force is false.
    if !force {
        let avg_conf: f64 = conn
            .query_row(
                "SELECT AVG(confidence) FROM taste_profile",
                [],
                |row| row.get::<_, Option<f64>>(0),
            )
            .unwrap_or(None)
            .unwrap_or(0.0);
        if avg_conf >= 0.5 {
            return Ok(0);
        }
    }

    // Check that spotify_history exists.
    let has_table: bool = conn
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='spotify_history'",
            [],
            |_| Ok(true),
        )
        .optional()?
        .unwrap_or(false);
    if !has_table {
        return Ok(0);
    }

    // Pull play-count + total ms per artist/track combo.
    let mut stmt = conn.prepare(
        "SELECT LOWER(TRIM(sh.artist)), LOWER(TRIM(sh.track)),
                COUNT(*) AS plays, COALESCE(SUM(sh.ms_played), 0) AS total_ms
         FROM spotify_history sh
         GROUP BY LOWER(TRIM(sh.artist)), LOWER(TRIM(sh.track))
         HAVING plays >= 2
         ORDER BY plays DESC
         LIMIT 2000",
    )?;

    struct SpotifyPlay {
        artist: String,
        title: String,
        plays: i64,
        total_ms: i64,
    }

    let plays: Vec<SpotifyPlay> = stmt
        .query_map([], |row| {
            Ok(SpotifyPlay {
                artist: row.get(0)?,
                title:  row.get(1)?,
                plays:  row.get(2)?,
                total_ms: row.get(3)?,
            })
        })?
        .filter_map(Result::ok)
        .collect();

    if plays.is_empty() {
        return Ok(0);
    }

    // For each entry try to join to a scored local track.
    let mut dim_weight_sum: [f64; 10] = [0.0; 10];
    let mut total_weight = 0.0_f64;
    let mut matched = 0_usize;

    for sp in &plays {
        // Resolve track_id by fuzzy artist+title match.
        let track_id: Option<i64> = conn
            .query_row(
                "SELECT t.id
                 FROM tracks t
                 LEFT JOIN artists ar ON ar.id = t.artist_id
                 WHERE LOWER(TRIM(COALESCE(ar.name, ''))) = ?1
                   AND LOWER(TRIM(t.title)) = ?2
                 LIMIT 1",
                params![sp.artist, sp.title],
                |row| row.get(0),
            )
            .optional()?;

        let Some(tid) = track_id else { continue };

        // Load scores.
        let scores = conn.query_row(
            "SELECT energy, valence, tension, density, warmth,
                    movement, space, rawness, complexity, nostalgia
             FROM track_scores WHERE track_id = ?1",
            params![tid],
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
        let Ok(s) = scores else { continue };

        // Weight: play count × log-scaled listening time.
        let minutes = sp.total_ms as f64 / 60_000.0;
        let weight = sp.plays as f64 * (1.0 + minutes.ln().max(0.0));

        for i in 0..10 {
            dim_weight_sum[i] += s[i] * weight;
        }
        total_weight += weight;
        matched += 1;
    }

    if matched == 0 || total_weight == 0.0 {
        return Ok(0);
    }

    // Confidence proportional to matched coverage, capped at 0.85.
    let confidence = (matched as f64 / (matched as f64 + 20.0)).min(0.85);
    let now = Utc::now().to_rfc3339();

    for (i, &dim) in DIMS.iter().enumerate() {
        let value = (dim_weight_sum[i] / total_weight).clamp(0.0, 1.0);
        conn.execute(
            "INSERT INTO taste_profile (dimension, value, confidence, last_updated)
             VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(dimension) DO UPDATE SET
               value=excluded.value, confidence=excluded.confidence, last_updated=excluded.last_updated",
            params![dim, value, confidence, now],
        )?;
    }

    Ok(matched)
}

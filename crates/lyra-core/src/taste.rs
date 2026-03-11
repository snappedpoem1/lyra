use std::collections::HashMap;

use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::TasteProfile;
use crate::errors::LyraResult;

/// Detect whether the DB uses the normalized schema (has `artists` table) or legacy flat schema.
fn has_artists_table(conn: &Connection) -> bool {
    conn.query_row(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='artists'",
        [],
        |_| Ok(()),
    )
    .is_ok()
}

/// Resolve (artist_lc, title_lc) → track_id TEXT (legacy flat schema).
/// Returns None if not found or no track_scores row exists.
fn resolve_track_flat(conn: &Connection, artist_lc: &str, title_lc: &str) -> Option<[f64; 10]> {
    let track_id: Option<String> = conn
        .query_row(
            "SELECT track_id FROM tracks
             WHERE LOWER(TRIM(artist)) = ?1 AND LOWER(TRIM(title)) = ?2
             LIMIT 1",
            params![artist_lc, title_lc],
            |row| row.get(0),
        )
        .optional()
        .ok()
        .flatten();
    let tid = track_id?;
    conn.query_row(
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
    )
    .ok()
}

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
/// Matches legacy `taste_backfill.py` semantics:
///   - Skip inference: ms_played < 30 000 ms counts as a skip
///   - Signal: positive when non_skip_count > skip_count AND avg_ms >= 30 s
///   - Weight: min(log2(play_count + 1), 3.0) — log-scaled, capped
///   - Positive: EMA nudge toward track scores; Negative: nudge away
///
/// `force`: if false, skips when taste_profile already has avg confidence ≥ 0.5.
/// Returns the number of tracks that contributed to the seed.
pub fn seed_taste_from_spotify_history(conn: &Connection, force: bool) -> LyraResult<usize> {
    if !force {
        let avg_conf: f64 = conn
            .query_row("SELECT AVG(confidence) FROM taste_profile", [], |row| {
                row.get::<_, Option<f64>>(0)
            })
            .unwrap_or(None)
            .unwrap_or(0.0);
        if avg_conf >= 0.5 {
            return Ok(0);
        }
    }

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

    // Aggregate: plays, skips (ms < 30s), total_ms per artist+track.
    let mut stmt = conn.prepare(
        "SELECT LOWER(TRIM(sh.artist)), LOWER(TRIM(sh.track)),
                COUNT(*) AS plays,
                SUM(CASE WHEN sh.ms_played < 30000 THEN 1 ELSE 0 END) AS skips,
                COALESCE(SUM(sh.ms_played), 0) AS total_ms
         FROM spotify_history sh
         WHERE sh.artist IS NOT NULL AND sh.track IS NOT NULL
         GROUP BY LOWER(TRIM(sh.artist)), LOWER(TRIM(sh.track))
         HAVING plays >= 2
         ORDER BY plays DESC
         LIMIT 2000",
    )?;

    struct SpotifyPlay {
        artist: String,
        title: String,
        plays: i64,
        skips: i64,
        total_ms: i64,
    }

    let groups: Vec<SpotifyPlay> = stmt
        .query_map([], |row| {
            Ok(SpotifyPlay {
                artist: row.get(0)?,
                title: row.get(1)?,
                plays: row.get(2)?,
                skips: row.get(3)?,
                total_ms: row.get(4)?,
            })
        })?
        .filter_map(Result::ok)
        .collect();

    if groups.is_empty() {
        return Ok(0);
    }

    let flat_schema = !has_artists_table(conn);
    let mut matched = 0_usize;

    for sp in &groups {
        let s = if flat_schema {
            match resolve_track_flat(conn, &sp.artist, &sp.title) {
                Some(s) => s,
                None => continue,
            }
        } else {
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
            match conn.query_row(
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
            ) {
                Ok(s) => s,
                Err(_) => continue,
            }
        };

        let non_skips = sp.plays - sp.skips;
        let avg_ms = if sp.plays > 0 {
            sp.total_ms / sp.plays
        } else {
            0
        };
        let positive = non_skips > sp.skips && avg_ms >= 30_000;
        // log2-capped weight, matching legacy taste_backfill.py
        let weight = ((sp.plays as f64 + 1.0).log2()).min(3.0);

        apply_taste_nudge(conn, &s, positive, weight)?;
        matched += 1;
    }

    Ok(matched)
}

/// Apply a single EMA nudge to all taste dimensions toward (positive) or
/// away from (negative) the given track score vector.
/// alpha = 0.03 per nudge × weight (weight typically 1.0–3.0).
fn apply_taste_nudge(
    conn: &Connection,
    track_scores: &[f64; 10],
    positive: bool,
    weight: f64,
) -> LyraResult<()> {
    // Ensure rows exist for all dimensions.
    let now = Utc::now().to_rfc3339();
    for &dim in DIMS {
        conn.execute(
            "INSERT OR IGNORE INTO taste_profile (dimension, value, confidence, last_updated)
             VALUES (?1, 0.5, 0.0, ?2)",
            params![dim, now],
        )?;
    }

    let existing: Vec<(String, f64, f64)> = {
        let mut stmt = conn.prepare(
            "SELECT dimension, value, confidence FROM taste_profile ORDER BY dimension ASC",
        )?;
        let rows: Vec<_> = stmt
            .query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, f64>(1)?,
                    row.get::<_, f64>(2)?,
                ))
            })?
            .filter_map(Result::ok)
            .collect();
        rows
    };

    let dim_map: HashMap<String, (f64, f64)> =
        existing.into_iter().map(|(d, v, c)| (d, (v, c))).collect();

    let alpha = (0.03 * weight).min(0.12); // scale with weight, cap at 12%
    for (i, &dim) in DIMS.iter().enumerate() {
        let (old_val, old_conf) = dim_map.get(dim).copied().unwrap_or((0.5, 0.0));
        let target = if positive {
            track_scores[i]
        } else {
            1.0 - track_scores[i]
        };
        let new_val = (old_val * (1.0 - alpha) + target * alpha).clamp(0.0, 1.0);
        let new_conf = (old_conf + 0.005).min(1.0);
        conn.execute(
            "UPDATE taste_profile SET value=?1, confidence=?2, last_updated=?3
             WHERE dimension=?4",
            params![new_val, new_conf, now, dim],
        )?;
    }
    Ok(())
}

/// Pull recent scrobbles from the Last.fm API and apply them as taste signals.
///
/// Requires env vars: LASTFM_API_KEY, LASTFM_USERNAME.
/// `lookback_days`: how many days to fetch (default 7 for incremental, up to 365 for full seed).
/// Returns (fetched, matched, written).
pub fn sync_taste_from_lastfm(
    conn: &Connection,
    lookback_days: u32,
) -> LyraResult<(usize, usize, usize)> {
    let api_key = std::env::var("LASTFM_API_KEY").unwrap_or_default();
    let username = std::env::var("LASTFM_USERNAME").unwrap_or_default();
    if api_key.is_empty() || username.is_empty() {
        return Ok((0, 0, 0));
    }

    let since_ts = {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        now.saturating_sub(lookback_days as u64 * 86_400)
    };

    // Fetch pages from Last.fm user.getRecentTracks
    let mut all_plays: Vec<(String, String)> = Vec::new(); // (artist, title)
    let mut page = 1u32;
    let page_limit = 200u32;

    loop {
        let url = format!(
            "https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks\
             &user={username}&api_key={api_key}&format=json\
             &limit={page_limit}&from={since_ts}&page={page}"
        );

        let body = match ureq::get(&url).call() {
            Ok(resp) => match resp.into_string() {
                Ok(s) => s,
                Err(_) => break,
            },
            Err(_) => break,
        };

        let json: serde_json::Value = match serde_json::from_str(&body) {
            Ok(v) => v,
            Err(_) => break,
        };

        let tracks = match json["recenttracks"]["track"].as_array() {
            Some(t) => t.clone(),
            None => break,
        };
        if tracks.is_empty() {
            break;
        }

        let total_pages: u32 = json["recenttracks"]["@attr"]["totalPages"]
            .as_str()
            .and_then(|s| s.parse().ok())
            .unwrap_or(1);

        for t in &tracks {
            // Skip the currently-playing track (has @attr.nowplaying)
            if t["@attr"]["nowplaying"].as_str().is_some() {
                continue;
            }
            let artist = t["artist"]["#text"]
                .as_str()
                .unwrap_or("")
                .trim()
                .to_string();
            let title = t["name"].as_str().unwrap_or("").trim().to_string();
            if !artist.is_empty() && !title.is_empty() {
                all_plays.push((artist, title));
            }
        }

        if page >= total_pages {
            break;
        }
        page += 1;
        // Rate-limit: Last.fm allows ~5 req/s; be polite
        std::thread::sleep(std::time::Duration::from_millis(220));
    }

    let fetched = all_plays.len();
    if fetched == 0 {
        return Ok((0, 0, 0));
    }

    // Aggregate play counts per artist+title
    let mut counts: HashMap<(String, String), usize> = HashMap::new();
    for (artist, title) in all_plays {
        let key = (artist.to_lowercase(), title.to_lowercase());
        *counts.entry(key).or_insert(0) += 1;
    }

    let flat_schema = !has_artists_table(conn);
    let mut matched = 0_usize;
    let mut written = 0_usize;

    for ((artist_lc, title_lc), count) in &counts {
        let s = if flat_schema {
            match resolve_track_flat(conn, artist_lc, title_lc) {
                Some(s) => s,
                None => continue,
            }
        } else {
            let track_id: Option<i64> = conn
                .query_row(
                    "SELECT t.id
                     FROM tracks t
                     LEFT JOIN artists ar ON ar.id = t.artist_id
                     WHERE LOWER(TRIM(COALESCE(ar.name, ''))) = ?1
                       AND LOWER(TRIM(t.title)) = ?2
                     LIMIT 1",
                    params![artist_lc, title_lc],
                    |row| row.get(0),
                )
                .optional()?;
            let Some(tid) = track_id else { continue };
            match conn.query_row(
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
            ) {
                Ok(s) => s,
                Err(_) => continue,
            }
        };

        // Last.fm plays are all-positive signals (no skip data)
        let weight = ((*count as f64 + 1.0).log2()).min(3.0);
        apply_taste_nudge(conn, &s, true, weight)?;
        matched += 1;
        written += 1;
    }

    Ok((fetched, matched, written))
}

//! Deep Cut Protocol — Obscurity-weighted discovery engine.
//!
//! Surfaces tracks that are acclaimed relative to their mainstream visibility.
//! Algorithm: `obscurity = acclaim / (popularity_percentile + ε)`
//!
//! **[Last.fm DeepCut API?]** — `listeners` and `playcount` come from Last.fm
//! `track.getInfo`. Without that data the popularity is derived from local
//! `playback_history` as a proxy.
//!
//! **[Discogs DeepCut API?]** — community rating from Discogs `/releases/{id}`.
//! Without it the acclaim defaults to a neutral 0.5 prior.
//!
//! The Rust layer owns: DB queries, local-play-count percentile computation,
//! L1-distance taste alignment, obscurity math, tag building, and result ranking.

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::errors::LyraResult;

// ── Constants ─────────────────────────────────────────────────────────────────

const EPSILON: f64 = 0.05;

/// Default percentile buckets used when no Last.fm cache data is available.
/// (percentile, max_listeners_at_that_percentile)
pub const DEFAULT_LISTENER_BUCKETS: &[(f64, i64)] = &[
    (0.05,   1_000),
    (0.10,   5_000),
    (0.25,  25_000),
    (0.50, 150_000),
    (0.75, 500_000),
    (0.90, 1_500_000),
    (0.95, 5_000_000),
];

const DIM_NAMES: [&str; 10] = [
    "energy", "valence", "tension", "density",
    "warmth", "movement", "space", "rawness", "complexity", "nostalgia",
];

// ── Types ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeepCutTrack {
    pub track_id:             i64,
    pub artist:               String,
    pub title:                String,
    pub album:                String,
    pub genre:                String,
    pub path:                 String,
    pub obscurity_score:      f64,
    pub acclaim_score:        f64,
    pub popularity_percentile: f64,
    /// Local playback count (Last.fm proxy when API unavailable).
    pub local_play_count:     i64,
    /// Taste alignment (0–1); populated by `hunt_with_taste_context`.
    pub taste_alignment:      f64,
    /// Blended rank: obscurity × 0.6 + taste × 0.4.
    pub deep_cut_rank:        f64,
    pub tags:                 Vec<String>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
pub struct DeepCutStats {
    pub total_tracks:        i64,
    pub median_obscurity:    f64,
    pub high_potential_count: usize,
    pub top_5_deep_cuts:     Vec<TopDeepCut>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TopDeepCut {
    pub artist:          String,
    pub title:           String,
    pub obscurity_score: f64,
}

// ── Popularity percentile ─────────────────────────────────────────────────────

/// Map a raw listener count to a 0–1 percentile using the bucket table.
pub fn compute_popularity_percentile(
    listeners: i64,
    buckets: &[(f64, i64)],
) -> f64 {
    if listeners <= 0 {
        return 0.01; // nearly unknown
    }
    for &(pct, threshold) in buckets {
        if listeners <= threshold {
            return pct;
        }
    }
    1.0 // above highest bucket → mainstream
}

/// Compute percentile buckets from local play counts (Last.fm proxy).
///
/// Reads `playback_history` counts per track. Tracks never played get 0.
/// Returns a bucket table in the same format as `DEFAULT_LISTENER_BUCKETS`.
pub fn local_play_count_percentile_buckets(
    conn: &Connection,
) -> LyraResult<Vec<(f64, i64)>> {
    let counts: Vec<i64> = conn
        .prepare(
            "SELECT COUNT(*) as c
             FROM playback_history
             GROUP BY track_id
             ORDER BY c ASC",
        )?
        .query_map([], |row| row.get(0))?
        .filter_map(Result::ok)
        .collect();

    if counts.len() < 10 {
        // Not enough playback data — use default Last.fm-derived buckets
        return Ok(DEFAULT_LISTENER_BUCKETS.to_vec());
    }

    let n = counts.len();
    let pct_points = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95_f64];
    let buckets = pct_points
        .iter()
        .map(|&pct| {
            let idx = ((pct * n as f64) as usize).saturating_sub(1).min(n - 1);
            (pct, counts[idx])
        })
        .collect();

    Ok(buckets)
}

// ── Acclaim ───────────────────────────────────────────────────────────────────

/// Compute acclaim (0–1) from an optional Discogs community rating.
///
/// If no external rating is available, returns a neutral prior of 0.5.
/// **[Discogs DeepCut API?]** — discogs_rating is 0.0 when API is unavailable.
pub fn compute_acclaim(discogs_rating: f64) -> f64 {
    if discogs_rating > 0.0 {
        // Discogs ratings are 0–5; normalise to 0–1
        (discogs_rating / 5.0).clamp(0.0, 1.0)
    } else {
        0.5 // neutral prior
    }
}

/// Build descriptive tags for a deep cut result.
pub fn build_tags(obscurity: f64, acclaim: f64, pop_pct: f64, genre: &str) -> Vec<String> {
    let mut tags = vec!["deepcut:true".to_string()];

    tags.push(if obscurity > 1.5 {
        "tier:holy_grail"
    } else if obscurity > 1.0 {
        "tier:hidden_gem"
    } else if obscurity > 0.7 {
        "tier:deep_cut"
    } else {
        "tier:underrated"
    }.to_string());

    if pop_pct < 0.1 {
        tags.push("visibility:nearly_unknown".into());
    } else if pop_pct < 0.25 {
        tags.push("visibility:obscure".into());
    }

    if acclaim > 0.8 {
        tags.push("quality:exceptional".into());
    } else if acclaim > 0.6 {
        tags.push("quality:acclaimed".into());
    }

    if !genre.is_empty() {
        let safe = genre.to_lowercase().replace(' ', "_").replace('/', "_");
        let safe = &safe[..safe.len().min(30)];
        tags.push(format!("genre:{}", safe));
    }

    tags
}

// ── DB queries ────────────────────────────────────────────────────────────────

/// Candidate row from the library.
struct LibraryRow {
    track_id:       i64,
    artist:         String,
    title:          String,
    album:          String,
    genre:          String,
    path:           String,
    local_plays:    i64,
    taste_alignment: f64,
}

fn get_library_candidates(
    conn: &Connection,
    genre: Option<&str>,
    artist: Option<&str>,
    limit: usize,
) -> LyraResult<Vec<LibraryRow>> {
    let mut clauses: Vec<String> = vec!["(t.quarantined IS NULL OR t.quarantined = 0)".into()];
    let mut bound: Vec<Box<dyn rusqlite::types::ToSql>> = Vec::new();

    if let Some(g) = genre.filter(|s| !s.is_empty()) {
        clauses.push("LOWER(COALESCE(t.genre,'')) LIKE ?".into());
        bound.push(Box::new(format!("%{}%", g.to_lowercase())));
    }
    if let Some(a) = artist.filter(|s| !s.is_empty()) {
        clauses.push("LOWER(COALESCE(ar.name,'')) LIKE ?".into());
        bound.push(Box::new(format!("%{}%", a.to_lowercase())));
    }

    let sql = format!(
        "SELECT t.id, COALESCE(ar.name,''), COALESCE(t.title,''),
                COALESCE(al.title,''), COALESCE(t.genre,''), COALESCE(t.path,''),
                COALESCE((SELECT COUNT(*) FROM playback_history ph WHERE ph.track_id = t.id), 0)
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         LEFT JOIN albums  al ON al.id = t.album_id
         WHERE {}
         ORDER BY RANDOM()
         LIMIT ?",
        clauses.join(" AND ")
    );
    bound.push(Box::new(limit as i64));
    let refs: Vec<&dyn rusqlite::types::ToSql> = bound.iter().map(|b| b.as_ref()).collect();

    let mut stmt = conn.prepare(&sql)?;
    let rows: Vec<LibraryRow> = stmt
        .query_map(refs.as_slice(), |row| {
            Ok(LibraryRow {
                track_id:        row.get(0)?,
                artist:          row.get(1)?,
                title:           row.get(2)?,
                album:           row.get(3)?,
                genre:           row.get(4)?,
                path:            row.get(5)?,
                local_plays:     row.get(6)?,
                taste_alignment: 0.0,
            })
        })?
        .filter_map(Result::ok)
        .collect();

    Ok(rows)
}

/// Get candidates ranked by L1-distance taste alignment to a 10-dim profile.
fn get_taste_aligned_candidates(
    conn: &Connection,
    taste: &HashMap<String, f64>,
    limit: usize,
) -> LyraResult<Vec<LibraryRow>> {
    // Load all scored tracks
    let rows: Vec<(i64, String, String, String, String, String, i64,
                   Option<f64>, Option<f64>, Option<f64>, Option<f64>,
                   Option<f64>, Option<f64>, Option<f64>, Option<f64>,
                   Option<f64>, Option<f64>)> = conn
        .prepare(
            "SELECT t.id, COALESCE(ar.name,''), COALESCE(t.title,''),
                    COALESCE(al.title,''), COALESCE(t.genre,''), COALESCE(t.path,''),
                    COALESCE((SELECT COUNT(*) FROM playback_history ph WHERE ph.track_id = t.id), 0),
                    ts.energy, ts.valence, ts.tension, ts.density,
                    ts.warmth, ts.movement, ts.space, ts.rawness,
                    ts.complexity, ts.nostalgia
             FROM track_scores ts
             JOIN tracks t ON t.id = ts.track_id
             LEFT JOIN artists ar ON ar.id = t.artist_id
             LEFT JOIN albums  al ON al.id = t.album_id
             WHERE (t.quarantined IS NULL OR t.quarantined = 0)
             LIMIT 5000",
        )?
        .query_map([], |row| {
            Ok((
                row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?,
                row.get(4)?, row.get(5)?, row.get(6)?,
                row.get(7)?,  row.get(8)?,  row.get(9)?,  row.get(10)?,
                row.get(11)?, row.get(12)?, row.get(13)?, row.get(14)?,
                row.get(15)?, row.get(16)?,
            ))
        })?
        .filter_map(Result::ok)
        .collect();

    let mut scored: Vec<(f64, LibraryRow)> = rows
        .into_iter()
        .map(|r| {
            let track_dims: [Option<f64>; 10] = [
                r.7, r.8, r.9, r.10, r.11, r.12, r.13, r.14, r.15, r.16,
            ];
            let mut total_dist = 0.0_f64;
            let mut matched = 0usize;
            for (i, &dim) in DIM_NAMES.iter().enumerate() {
                if let (Some(taste_val), Some(track_val)) = (taste.get(dim), track_dims[i]) {
                    total_dist += (taste_val - track_val).abs();
                    matched += 1;
                }
            }
            let alignment = if matched == 0 {
                0.5
            } else {
                1.0 - (total_dist / matched as f64)
            };
            (alignment, LibraryRow {
                track_id:        r.0,
                artist:          r.1,
                title:           r.2,
                album:           r.3,
                genre:           r.4,
                path:            r.5,
                local_plays:     r.6,
                taste_alignment: alignment,
            })
        })
        .collect();

    scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    Ok(scored.into_iter().take(limit).map(|(_, row)| row).collect())
}

// ── Scoring ───────────────────────────────────────────────────────────────────

fn score_row(row: LibraryRow, buckets: &[(f64, i64)]) -> DeepCutTrack {
    // Use local play count as popularity proxy (Last.fm deferred)
    let pop_pct = compute_popularity_percentile(row.local_plays, buckets);
    let acclaim  = compute_acclaim(0.0); // Discogs deferred → neutral 0.5
    let obscurity = acclaim / (pop_pct + EPSILON);

    let deep_cut_rank =
        obscurity.clamp(0.0, 5.0) * 0.6 + row.taste_alignment * 0.4;

    let tags = build_tags(obscurity, acclaim, pop_pct, &row.genre);

    DeepCutTrack {
        track_id:              row.track_id,
        artist:                row.artist,
        title:                 row.title,
        album:                 row.album,
        genre:                 row.genre,
        path:                  row.path,
        obscurity_score:       (obscurity * 1000.0).round() / 1000.0,
        acclaim_score:         acclaim,
        popularity_percentile: (pop_pct * 1000.0).round() / 1000.0,
        local_play_count:      row.local_plays,
        taste_alignment:       (row.taste_alignment * 1000.0).round() / 1000.0,
        deep_cut_rank:         (deep_cut_rank * 1000.0).round() / 1000.0,
        tags,
    }
}

// ── Public API ────────────────────────────────────────────────────────────────

/// Hunt for deep cuts by genre/artist, ranked by obscurity score.
///
/// Uses local play count as popularity proxy (no Last.fm call).
/// **[Last.fm DeepCut API?]** — real listener counts would improve ranking.
pub fn hunt_by_obscurity(
    conn: &Connection,
    genre: Option<&str>,
    artist: Option<&str>,
    min_obscurity: f64,
    max_obscurity: f64,
    limit: usize,
) -> LyraResult<Vec<DeepCutTrack>> {
    let limit = limit.clamp(1, 500);
    let candidates = get_library_candidates(conn, genre, artist, limit * 5)?;

    if candidates.is_empty() {
        return Ok(vec![]);
    }

    let buckets = local_play_count_percentile_buckets(conn)?;

    let mut scored: Vec<DeepCutTrack> = candidates
        .into_iter()
        .map(|row| score_row(row, &buckets))
        .filter(|t| {
            t.obscurity_score >= min_obscurity && t.obscurity_score <= max_obscurity
        })
        .collect();

    scored.sort_by(|a, b| {
        b.obscurity_score
            .partial_cmp(&a.obscurity_score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    scored.truncate(limit);
    Ok(scored)
}

/// Hunt for deep cuts aligned with a taste profile.
///
/// Taste profile is a `HashMap<dimension, value_0_to_1>`.
/// Results ranked by `obscurity × 0.6 + taste_alignment × 0.4`.
pub fn hunt_with_taste_context(
    conn: &Connection,
    taste: &HashMap<String, f64>,
    limit: usize,
) -> LyraResult<Vec<DeepCutTrack>> {
    let limit = limit.clamp(1, 500);

    // Try taste-aligned first; fall back to random if no scored tracks
    let mut candidates = get_taste_aligned_candidates(conn, taste, limit * 5)?;
    if candidates.is_empty() {
        candidates = get_library_candidates(conn, None, None, limit * 5)?;
    }

    let buckets = local_play_count_percentile_buckets(conn)?;

    let mut scored: Vec<DeepCutTrack> = candidates
        .into_iter()
        .map(|row| score_row(row, &buckets))
        .collect();

    scored.sort_by(|a, b| {
        b.deep_cut_rank
            .partial_cmp(&a.deep_cut_rank)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    scored.truncate(limit);
    Ok(scored)
}

/// Return summary statistics for the deep cut engine.
pub fn get_stats(conn: &Connection) -> LyraResult<DeepCutStats> {
    let total: i64 =
        conn.query_row("SELECT COUNT(*) FROM tracks", [], |r| r.get(0))?;

    let buckets = local_play_count_percentile_buckets(conn)?;

    // Sample up to 500 tracks to compute stats without full scan
    let candidates = get_library_candidates(conn, None, None, 500)?;
    let scores: Vec<f64> = candidates
        .into_iter()
        .map(|row| score_row(row, &buckets).obscurity_score)
        .collect();

    let median = if scores.is_empty() {
        0.0
    } else {
        let mut s = scores.clone();
        s.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        s[s.len() / 2]
    };

    let high_potential_count = scores.iter().filter(|&&s| s > 0.8).count();

    // Top 5 by obscurity (re-score same sample, already have scores)
    let mut all_buckets2 = local_play_count_percentile_buckets(conn)?;
    let top5_candidates = get_library_candidates(conn, None, None, 500)?;
    let mut top5: Vec<TopDeepCut> = top5_candidates
        .into_iter()
        .map(|row| {
            let t = score_row(row, &all_buckets2);
            TopDeepCut {
                artist:          t.artist,
                title:           t.title,
                obscurity_score: t.obscurity_score,
            }
        })
        .collect();
    top5.sort_by(|a, b| {
        b.obscurity_score
            .partial_cmp(&a.obscurity_score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    top5.truncate(5);

    Ok(DeepCutStats {
        total_tracks: total,
        median_obscurity: (median * 1000.0).round() / 1000.0,
        high_potential_count,
        top_5_deep_cuts: top5,
    })
}

//! Library search — metadata text search, remix finder, and hybrid filter/sort.
//!
//! **[CLAP Semantic Search?]** — `search()` and the semantic candidate pass
//! of `hybrid_search()` require the PyTorch/ROCm CLAP embedder and ChromaDB
//! Python client. That path stays in Python (`oracle/search.py`). The Rust
//! layer owns the deterministic filter/sort/dimensional layer that runs on top
//! of any candidate set.

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::errors::LyraResult;

// ── Types ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub rank:            usize,
    pub track_id:        i64,
    pub artist:          String,
    pub title:           String,
    pub album:           String,
    pub year:            Option<i32>,
    pub genre:           String,
    pub path:            String,
    pub duration:        Option<f64>,
    pub version_type:    Option<String>,
    pub confidence:      Option<f64>,
    pub bpm:             Option<f64>,
    pub score:           f64,
    /// Dimension scores from track_scores table (may be empty).
    pub scores:          std::collections::HashMap<String, f64>,
    pub played_count:    i64,
    pub fallback_reason: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SearchFilters {
    pub artist:       Option<String>,
    pub title:        Option<String>,
    pub album:        Option<String>,
    pub genre:        Option<String>,
    pub version_type: Option<String>,
    pub exclude_remix: bool,
    pub year_min:     Option<i32>,
    pub year_max:     Option<i32>,
    pub bpm_min:      Option<f64>,
    pub bpm_max:      Option<f64>,
    pub duration_min: Option<f64>,
    pub duration_max: Option<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SortBy {
    Relevance,
    Artist,
    Title,
    Year,
    Bpm,
    Duration,
    MostPlayed,
    LeastPlayed,
    RecentlyAdded,
    Random,
    /// Dimensional sort — e.g. energy, valence, tension…
    Dimension,
}

impl SortBy {
    pub fn from_str(s: &str) -> Self {
        match s.trim().to_lowercase().as_str() {
            "artist"                       => Self::Artist,
            "title"                        => Self::Title,
            "year"                         => Self::Year,
            "bpm"                          => Self::Bpm,
            "duration"                     => Self::Duration,
            "played" | "most_played"       => Self::MostPlayed,
            "least_played"                 => Self::LeastPlayed,
            "added" | "recently_added"     => Self::RecentlyAdded,
            "random"                       => Self::Random,
            _                              => Self::Relevance,
        }
    }
}

const DIM_NAMES: [&str; 10] = [
    "energy", "valence", "tension", "density",
    "warmth", "movement", "space", "rawness", "complexity", "nostalgia",
];

const REMIX_HINT_TOKENS: [&str; 8] = [
    "remix", "edit", "rework", "bootleg", "vip", "mashup", "flip", "mix",
];

// ── Fallback metadata text search ────────────────────────────────────────────

/// Token-scored metadata search against artist, title, album.
/// Used when semantic search (CLAP/ChromaDB) is unavailable.
pub fn fallback_text_search(
    conn: &Connection,
    query: &str,
    limit: usize,
) -> LyraResult<Vec<SearchResult>> {
    let limit = limit.max(1);
    let terms: Vec<String> = query
        .to_lowercase()
        .split(|c: char| !c.is_alphanumeric())
        .filter(|t| !t.is_empty())
        .take(8)
        .map(String::from)
        .collect();

    // Build candidate SQL
    let rows: Vec<(i64, String, String, String, Option<i32>, String, String, Option<f64>, Option<String>, Option<f64>, Option<f64>)> = if terms.is_empty() {
        conn.prepare(
            "SELECT t.id, COALESCE(ar.name,''), COALESCE(t.title,''),
                    COALESCE(al.title,''), CAST(t.year AS INTEGER), COALESCE(t.genre,''),
                    t.path, t.duration_seconds, t.version_type, NULL, t.bpm
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             LEFT JOIN albums  al ON al.id = t.album_id
             WHERE (t.quarantined IS NULL OR t.quarantined = 0)
             ORDER BY t.imported_at DESC
             LIMIT ?1",
        )?
        .query_map(params![limit as i64 * 5], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?,
                row.get(4)?, row.get(5)?, row.get(6)?, row.get(7)?,
                row.get(8)?, row.get(9)?, row.get(10)?))
        })?
        .filter_map(Result::ok)
        .collect()
    } else {
        // Build LIKE conditions for each term across artist/title/album
        let like_clause: String = terms
            .iter()
            .map(|_| "(LOWER(ar.name) LIKE ?1 OR LOWER(t.title) LIKE ?1 OR LOWER(al.title) LIKE ?1)")
            .collect::<Vec<_>>()
            .join(" OR ");

        // rusqlite doesn't support repeating params by index in user SQL, so
        // we build a flat param list (3 copies per term × n terms)
        let mut flat_params: Vec<String> = Vec::new();
        let mut clauses: Vec<String> = Vec::new();
        for term in &terms {
            let like = format!("%{}%", term);
            clauses.push(
                "(LOWER(ar.name) LIKE ? OR LOWER(t.title) LIKE ? OR LOWER(al.title) LIKE ?)".into(),
            );
            flat_params.push(like.clone());
            flat_params.push(like.clone());
            flat_params.push(like);
        }
        let where_clause = clauses.join(" OR ");
        let sql = format!(
            "SELECT t.id, COALESCE(ar.name,''), COALESCE(t.title,''),
                    COALESCE(al.title,''), CAST(t.year AS INTEGER), COALESCE(t.genre,''),
                    t.path, t.duration_seconds, t.version_type, NULL, t.bpm
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             LEFT JOIN albums  al ON al.id = t.album_id
             WHERE (t.quarantined IS NULL OR t.quarantined = 0)
               AND ({})
             ORDER BY ar.name COLLATE NOCASE, al.title COLLATE NOCASE, t.title COLLATE NOCASE
             LIMIT ?",
            where_clause
        );
        let fetch_limit = (limit * 25).max(100) as i64;
        let mut bound: Vec<Box<dyn rusqlite::types::ToSql>> =
            flat_params.iter().map(|s| -> Box<dyn rusqlite::types::ToSql> { Box::new(s.clone()) }).collect();
        bound.push(Box::new(fetch_limit));
        let refs: Vec<&dyn rusqlite::types::ToSql> = bound.iter().map(|b| b.as_ref()).collect();
        let mut stmt = conn.prepare(&sql)?;
        let rows_collected: Vec<_> = stmt.query_map(refs.as_slice(), |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?,
                row.get(4)?, row.get(5)?, row.get(6)?, row.get(7)?,
                row.get(8)?, row.get(9)?, row.get(10)?))
        })?
        .filter_map(Result::ok)
        .collect();
        rows_collected
    };

    // Score + sort
    let query_lower = query.to_lowercase();
    let mut scored: Vec<(f64, (i64, String, String, String, Option<i32>, String, String, Option<f64>, Option<String>, Option<f64>, Option<f64>))> = rows
        .into_iter()
        .map(|row| {
            let blob = format!("{} {} {}", row.1, row.2, row.3).to_lowercase();
            let token_hits = terms.iter().filter(|t| blob.contains(t.as_str())).count();
            let exact_bonus = if !query_lower.is_empty() && blob.contains(&query_lower) { 1.0 } else { 0.0 };
            let score = if terms.is_empty() {
                0.0
            } else {
                token_hits as f64 / terms.len() as f64 + exact_bonus
            };
            (score, row)
        })
        .collect();

    scored.sort_by(|a, b| {
        b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal)
            .then(a.1.1.to_lowercase().cmp(&b.1.1.to_lowercase()))
            .then(a.1.3.to_lowercase().cmp(&b.1.3.to_lowercase()))
            .then(a.1.2.to_lowercase().cmp(&b.1.2.to_lowercase()))
    });

    let reason = if terms.is_empty() { Some("metadata fallback".into()) } else { None };
    Ok(scored
        .into_iter()
        .take(limit)
        .enumerate()
        .map(|(i, (score, row))| SearchResult {
            rank: i + 1,
            track_id: row.0,
            artist: row.1,
            title: row.2,
            album: row.3,
            year: row.4,
            genre: row.5,
            path: row.6,
            duration: row.7,
            version_type: row.8,
            confidence: row.9,
            bpm: row.10,
            score,
            scores: std::collections::HashMap::new(),
            played_count: 0,
            fallback_reason: reason.clone(),
        })
        .collect())
}

// ── Remix finder ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemixResult {
    pub track_id:      i64,
    pub artist:        String,
    pub title:         String,
    pub album:         String,
    pub year:          Option<i32>,
    pub version_type:  Option<String>,
    pub confidence:    Option<f64>,
    pub path:          String,
    pub is_strict:     bool,
    pub match_type:    String,
    pub matched_tokens: Vec<String>,
}

pub fn find_remixes(
    conn: &Connection,
    artist: Option<&str>,
    album: Option<&str>,
    track: Option<&str>,
    limit: usize,
    include_candidates: bool,
    sort_by: &str,
) -> LyraResult<Vec<RemixResult>> {
    let limit = limit.clamp(1, 1000);
    let mut conditions: Vec<String> = vec!["(t.quarantined IS NULL OR t.quarantined = 0)".into()];
    let mut param_values: Vec<String> = Vec::new();

    if let Some(a) = artist.filter(|s| !s.is_empty()) {
        let like = format!("%{}%", a.to_lowercase());
        conditions.push("(LOWER(ar.name) LIKE ? OR LOWER(t.title) LIKE ?)".into());
        param_values.push(like.clone());
        param_values.push(like);
    }
    if let Some(al) = album.filter(|s| !s.is_empty()) {
        conditions.push("LOWER(COALESCE(alb.title,'')) LIKE ?".into());
        param_values.push(format!("%{}%", al.to_lowercase()));
    }
    if let Some(tr) = track.filter(|s| !s.is_empty()) {
        conditions.push("LOWER(t.title) LIKE ?".into());
        param_values.push(format!("%{}%", tr.to_lowercase()));
    }

    // Remix predicate: version_type='remix' OR hint tokens in title/album
    let mut remix_preds = vec!["LOWER(COALESCE(t.version_type,'')) = 'remix'".to_string()];
    if include_candidates {
        for tok in &REMIX_HINT_TOKENS {
            remix_preds.push("LOWER(t.title) LIKE ?".into());
            param_values.push(format!("%{}%", tok));
            remix_preds.push("LOWER(COALESCE(alb.title,'')) LIKE ?".into());
            param_values.push(format!("%{}%", tok));
        }
    }
    conditions.push(format!("({})", remix_preds.join(" OR ")));

    let order = match sort_by.to_lowercase().as_str() {
        "confidence" | "score" => "NULL DESC, t.imported_at DESC",
        "artist"               => "LOWER(ar.name) ASC, LOWER(t.title) ASC",
        "title" | "track"      => "LOWER(t.title) ASC, LOWER(ar.name) ASC",
        _                      => "t.imported_at DESC",
    };

    let sql = format!(
        "SELECT t.id, COALESCE(ar.name,''), t.title, COALESCE(alb.title,''),
                CAST(t.year AS INTEGER), t.version_type, NULL, t.path
         FROM tracks t
         LEFT JOIN artists ar  ON ar.id = t.artist_id
         LEFT JOIN albums  alb ON alb.id = t.album_id
         WHERE {}
         ORDER BY {}
         LIMIT ?",
        conditions.join(" AND "),
        order
    );

    let mut bound: Vec<Box<dyn rusqlite::types::ToSql>> =
        param_values.iter().map(|s| -> Box<dyn rusqlite::types::ToSql> { Box::new(s.clone()) }).collect();
    bound.push(Box::new(limit as i64));
    let refs: Vec<&dyn rusqlite::types::ToSql> = bound.iter().map(|b| b.as_ref()).collect();
    let mut stmt = conn.prepare(&sql)?;
    let rows: Vec<RemixResult> = stmt
        .query_map(refs.as_slice(), |row| {
            let title: String    = row.get::<_, Option<String>>(2)?.unwrap_or_default();
            let album_name: String = row.get::<_, Option<String>>(3)?.unwrap_or_default();
            let version_type: Option<String> = row.get(5)?;
            let is_strict = version_type.as_deref().map(|v| v == "remix").unwrap_or(false);
            let blob = format!("{} {}", title, album_name).to_lowercase();
            let matched: Vec<String> = REMIX_HINT_TOKENS.iter()
                .filter(|&&t| blob.contains(t))
                .map(|&t| t.to_string())
                .collect();
            Ok(RemixResult {
                track_id:     row.get(0)?,
                artist:       row.get::<_, Option<String>>(1)?.unwrap_or_default(),
                title,
                album:        album_name,
                year:         row.get(4)?,
                version_type,
                confidence:   row.get(6)?,
                path:         row.get::<_, Option<String>>(7)?.unwrap_or_default(),
                match_type:   if is_strict { "classified".into() } else { "candidate".into() },
                is_strict,
                matched_tokens: matched,
            })
        })?
        .filter_map(Result::ok)
        .collect();
    Ok(rows)
}

// ── Hybrid search (DB-side filter + dimensional range + sort) ─────────────────

/// Apply metadata filters + dimensional ranges to a pre-built candidate list.
/// When `candidate_ids` is empty, loads the most recent N tracks from DB.
/// Semantic ranking (**[CLAP Semantic Search?]**) is handled by the Python
/// layer; pass pre-ranked IDs here when available.
pub fn hybrid_search(
    conn: &Connection,
    candidate_ids: &[i64],
    filters: &SearchFilters,
    dimension_ranges: &std::collections::HashMap<String, (f64, f64)>,
    sort_by: SortBy,
    sort_dim: Option<&str>,
    descending: bool,
    top_k: usize,
) -> LyraResult<Vec<SearchResult>> {
    let top_k = top_k.clamp(1, 500);

    // If no candidates provided, pull from DB
    let ids: Vec<i64> = if candidate_ids.is_empty() {
        conn.prepare(
            "SELECT id FROM tracks WHERE (quarantined IS NULL OR quarantined = 0)
             ORDER BY imported_at DESC LIMIT ?1",
        )?
        .query_map(params![(top_k * 8) as i64], |row| row.get(0))?
        .filter_map(Result::ok)
        .collect()
    } else {
        candidate_ids.to_vec()
    };

    if ids.is_empty() {
        return Ok(vec![]);
    }

    // Fetch tracks
    let placeholders = ids.iter().map(|_| "?").collect::<Vec<_>>().join(",");
    let sql = format!(
        "SELECT t.id, COALESCE(ar.name,''), COALESCE(t.title,''),
                COALESCE(al.title,''), CAST(t.year AS INTEGER), COALESCE(t.genre,''),
                t.path, t.duration_seconds, t.version_type, NULL, t.bpm
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         LEFT JOIN albums  al ON al.id = t.album_id
         WHERE t.id IN ({}) AND (t.quarantined IS NULL OR t.quarantined = 0)",
        placeholders
    );
    let id_params: Vec<Box<dyn rusqlite::types::ToSql>> =
        ids.iter().map(|&id| -> Box<dyn rusqlite::types::ToSql> { Box::new(id) }).collect();
    let id_refs: Vec<&dyn rusqlite::types::ToSql> = id_params.iter().map(|b| b.as_ref()).collect();
    let mut stmt = conn.prepare(&sql)?;
    let mut tracks: Vec<SearchResult> = stmt
        .query_map(id_refs.as_slice(), |row| {
            Ok(SearchResult {
                rank: 0,
                track_id:     row.get(0)?,
                artist:       row.get(1)?,
                title:        row.get(2)?,
                album:        row.get(3)?,
                year:         row.get(4)?,
                genre:        row.get(5)?,
                path:         row.get::<_, Option<String>>(6)?.unwrap_or_default(),
                duration:     row.get(7)?,
                version_type: row.get(8)?,
                confidence:   row.get(9)?,
                bpm:          row.get(10)?,
                score: 0.0,
                scores: std::collections::HashMap::new(),
                played_count: 0,
                fallback_reason: None,
            })
        })?
        .filter_map(Result::ok)
        .collect();

    // Load dimension scores
    if !dimension_ranges.is_empty() || matches!(sort_by, SortBy::Dimension) {
        let score_sql = format!(
            "SELECT track_id, energy, valence, tension, density,
                    warmth, movement, space, rawness, complexity, nostalgia
             FROM track_scores WHERE track_id IN ({})",
            placeholders
        );
        if let Ok(mut score_stmt) = conn.prepare(&score_sql) {
            let score_refs: Vec<&dyn rusqlite::types::ToSql> = id_params.iter().map(|b| b.as_ref()).collect();
            let score_rows: Vec<(i64, [Option<f64>; 10])> = score_stmt
                .query_map(score_refs.as_slice(), |row| {
                    Ok((row.get(0)?, [
                        row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?,
                        row.get(5)?, row.get(6)?, row.get(7)?, row.get(8)?,
                        row.get(9)?, row.get(10)?,
                    ]))
                })?
                .filter_map(Result::ok)
                .collect();
            let score_map: std::collections::HashMap<i64, std::collections::HashMap<String, f64>> = score_rows
                .into_iter()
                .map(|(id, vals)| {
                    let m: std::collections::HashMap<String, f64> = DIM_NAMES.iter()
                        .zip(vals.iter())
                        .filter_map(|(&name, &val)| val.map(|v| (name.to_string(), v)))
                        .collect();
                    (id, m)
                })
                .collect();
            for t in &mut tracks {
                if let Some(s) = score_map.get(&t.track_id) {
                    t.scores = s.clone();
                }
            }
        }
    }

    // Load play counts
    {
        let pc_sql = format!(
            "SELECT track_id, COUNT(*) FROM playback_history WHERE track_id IN ({}) GROUP BY track_id",
            placeholders
        );
        if let Ok(mut pc_stmt) = conn.prepare(&pc_sql) {
            let pc_refs: Vec<&dyn rusqlite::types::ToSql> = id_params.iter().map(|b| b.as_ref()).collect();
            let counts: Vec<(i64, i64)> = pc_stmt
                .query_map(pc_refs.as_slice(), |row| Ok((row.get(0)?, row.get(1)?)))?
                .filter_map(Result::ok)
                .collect();
            let pc_map: std::collections::HashMap<i64, i64> = counts.into_iter().collect();
            for t in &mut tracks {
                t.played_count = pc_map.get(&t.track_id).copied().unwrap_or(0);
            }
        }
    }

    // Apply metadata filters
    let norm = |s: &str| s.trim().to_lowercase();
    tracks.retain(|t| {
        if let Some(a) = &filters.artist {
            if !norm(&t.artist).contains(&norm(a)) { return false; }
        }
        if let Some(ti) = &filters.title {
            if !norm(&t.title).contains(&norm(ti)) { return false; }
        }
        if let Some(al) = &filters.album {
            if !norm(&t.album).contains(&norm(al)) { return false; }
        }
        if let Some(g) = &filters.genre {
            if !norm(&t.genre).contains(&norm(g)) { return false; }
        }
        if let Some(vt) = &filters.version_type {
            if norm(t.version_type.as_deref().unwrap_or("")) != norm(vt) { return false; }
        }
        if filters.exclude_remix {
            if norm(t.version_type.as_deref().unwrap_or("")).contains("remix") { return false; }
        }
        if let Some(yr) = filters.year_min {
            if t.year.map(|y| y < yr).unwrap_or(true) { return false; }
        }
        if let Some(yr) = filters.year_max {
            if t.year.map(|y| y > yr).unwrap_or(true) { return false; }
        }
        if let Some(bmin) = filters.bpm_min {
            if t.bpm.map(|b| b < bmin).unwrap_or(true) { return false; }
        }
        if let Some(bmax) = filters.bpm_max {
            if t.bpm.map(|b| b > bmax).unwrap_or(true) { return false; }
        }
        if let Some(dmin) = filters.duration_min {
            if t.duration.map(|d| d < dmin).unwrap_or(true) { return false; }
        }
        if let Some(dmax) = filters.duration_max {
            if t.duration.map(|d| d > dmax).unwrap_or(true) { return false; }
        }
        true
    });

    // Apply dimensional ranges
    if !dimension_ranges.is_empty() {
        tracks.retain(|t| {
            for (dim, &(lo, hi)) in dimension_ranges {
                match t.scores.get(dim) {
                    Some(&v) if v >= lo && v <= hi => {}
                    _ => return false,
                }
            }
            true
        });
    }

    // Sort
    match sort_by {
        SortBy::Artist => tracks.sort_by(|a, b| {
            let o = a.artist.to_lowercase().cmp(&b.artist.to_lowercase());
            if descending { o.reverse() } else { o }
        }),
        SortBy::Title => tracks.sort_by(|a, b| {
            let o = a.title.to_lowercase().cmp(&b.title.to_lowercase());
            if descending { o.reverse() } else { o }
        }),
        SortBy::Year => tracks.sort_by(|a, b| {
            let o = a.year.cmp(&b.year);
            if descending { o.reverse() } else { o }
        }),
        SortBy::Bpm => tracks.sort_by(|a, b| {
            a.bpm.partial_cmp(&b.bpm).unwrap_or(std::cmp::Ordering::Equal)
        }),
        SortBy::Duration => tracks.sort_by(|a, b| {
            a.duration.partial_cmp(&b.duration).unwrap_or(std::cmp::Ordering::Equal)
        }),
        SortBy::MostPlayed => tracks.sort_by(|a, b| b.played_count.cmp(&a.played_count)),
        SortBy::LeastPlayed => tracks.sort_by(|a, b| a.played_count.cmp(&b.played_count)),
        SortBy::Random => {
            use std::collections::hash_map::DefaultHasher;
            use std::hash::{Hash, Hasher};
            let seed = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.subsec_nanos())
                .unwrap_or(42);
            tracks.sort_by_key(|t| {
                let mut h = DefaultHasher::new();
                t.track_id.hash(&mut h);
                seed.hash(&mut h);
                h.finish()
            });
        }
        SortBy::Dimension => {
            if let Some(dim) = sort_dim {
                let d = dim.to_string();
                tracks.sort_by(|a, b| {
                    let va = a.scores.get(&d).copied().unwrap_or(0.0);
                    let vb = b.scores.get(&d).copied().unwrap_or(0.0);
                    let o = va.partial_cmp(&vb).unwrap_or(std::cmp::Ordering::Equal);
                    if descending { o.reverse() } else { o }
                });
            }
        }
        SortBy::Relevance | SortBy::RecentlyAdded => {
            // Keep candidate order (semantic rank or recency from DB)
        }
    }

    // Assign final ranks
    let result: Vec<SearchResult> = tracks
        .into_iter()
        .take(top_k)
        .enumerate()
        .map(|(i, mut t)| { t.rank = i + 1; t })
        .collect();

    Ok(result)
}

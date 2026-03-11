//! Library search — metadata text search, remix finder, and hybrid filter/sort.
//!
//! **[CLAP Semantic Search?]** — `search()` and the semantic candidate pass
//! of `hybrid_search()` require the PyTorch/ROCm CLAP embedder and ChromaDB
//! Python client. That path stays in Python (`oracle/search.py`). The Rust
//! layer owns the deterministic filter/sort/dimensional layer that runs on top
//! of any candidate set.

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use crate::errors::LyraResult;

// ── Types ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub rank: usize,
    pub track_id: i64,
    pub artist: String,
    pub title: String,
    pub album: String,
    pub year: Option<i32>,
    pub genre: String,
    pub path: String,
    pub duration: Option<f64>,
    pub version_type: Option<String>,
    pub confidence: Option<f64>,
    pub bpm: Option<f64>,
    pub score: f64,
    /// Dimension scores from track_scores table (may be empty).
    pub scores: std::collections::HashMap<String, f64>,
    pub played_count: i64,
    pub fallback_reason: Option<String>,
}

type SearchDbRow = (
    i64,
    String,
    String,
    String,
    Option<i32>,
    String,
    String,
    Option<f64>,
    Option<String>,
    Option<f64>,
    Option<f64>,
);
type ScoredSearchRow = (f64, SearchDbRow);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchFacetBucket {
    pub value: String,
    pub count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchExcavationResult {
    pub query: String,
    pub tracks: Vec<SearchResult>,
    pub top_artists: Vec<SearchFacetBucket>,
    pub top_albums: Vec<SearchFacetBucket>,
    pub route_hints: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchSemanticCapability {
    pub provider_key: String,
    pub status: String, // ready | not_configured | unavailable_*
    pub detail: String,
    pub supports_query: bool,
    pub supports_indexing: bool,
}

pub trait SemanticSearchProvider: Send + Sync {
    fn provider_key(&self) -> &'static str;
    fn capability(&self) -> SearchSemanticCapability;
}

#[derive(Debug, Clone)]
struct NoopSemanticProvider;

impl SemanticSearchProvider for NoopSemanticProvider {
    fn provider_key(&self) -> &'static str {
        "none"
    }

    fn capability(&self) -> SearchSemanticCapability {
        SearchSemanticCapability {
            provider_key: self.provider_key().to_string(),
            status: "not_configured".to_string(),
            detail: "Semantic provider is disabled. Set LYRA_SEMANTIC_PROVIDER=clap after Rust-native CLAP runtime support lands."
                .to_string(),
            supports_query: false,
            supports_indexing: false,
        }
    }
}

#[derive(Debug, Clone)]
struct ClapSemanticProvider;

impl SemanticSearchProvider for ClapSemanticProvider {
    fn provider_key(&self) -> &'static str {
        "clap"
    }

    fn capability(&self) -> SearchSemanticCapability {
        SearchSemanticCapability {
            provider_key: self.provider_key().to_string(),
            status: "unavailable".to_string(),
            detail:
                "CLAP semantic search is configured but Rust-native provider runtime is not wired yet; metadata fallback search remains active."
                    .to_string(),
            supports_query: false,
            supports_indexing: false,
        }
    }
}

fn configured_semantic_provider_from(setting: &str) -> Box<dyn SemanticSearchProvider> {
    match setting.trim().to_ascii_lowercase().as_str() {
        "" | "none" | "disabled" => Box::new(NoopSemanticProvider),
        "clap" => Box::new(ClapSemanticProvider),
        _ => Box::new(NoopSemanticProvider),
    }
}

fn configured_semantic_provider(conn: &Connection) -> Box<dyn SemanticSearchProvider> {
    if let Ok(configured) = std::env::var("LYRA_SEMANTIC_PROVIDER") {
        return configured_semantic_provider_from(&configured);
    }

    let clap_enabled = conn
        .query_row(
            "SELECT enabled FROM provider_configs WHERE provider_key = ?1",
            params!["clap"],
            |row| row.get::<_, i64>(0),
        )
        .ok()
        .is_some_and(|enabled| enabled != 0);

    if clap_enabled {
        Box::new(ClapSemanticProvider)
    } else {
        Box::new(NoopSemanticProvider)
    }
}

fn clap_model_name() -> String {
    std::env::var("LYRA_CLAP_MODEL").unwrap_or_else(|_| "laion/larger_clap_music".to_string())
}

fn clap_model_cache_key(model_name: &str) -> String {
    let normalized = model_name.trim().replace('/', "--");
    format!("models--{normalized}")
}

fn clap_cache_roots(app_data_dir: Option<&Path>) -> Vec<PathBuf> {
    let mut roots: Vec<PathBuf> = Vec::new();
    if let Ok(value) = std::env::var("HUGGINGFACE_HUB_CACHE") {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            roots.push(PathBuf::from(trimmed));
        }
    }
    if let Ok(value) = std::env::var("HF_HOME") {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            let path = PathBuf::from(trimmed);
            roots.push(path.join("hub"));
            roots.push(path);
        }
    }
    if let Ok(value) = std::env::var("LYRA_MODEL_CACHE_ROOT") {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            let path = PathBuf::from(trimmed);
            roots.push(path.join("hub"));
            roots.push(path);
        }
    }
    if let Some(app_data_dir) = app_data_dir {
        let legacy_style = app_data_dir.join("cache").join("hf");
        roots.push(legacy_style.join("hub"));
        roots.push(legacy_style);
    }
    roots.push(PathBuf::from("hf_cache").join("hub"));
    roots.push(PathBuf::from("hf_cache"));

    let mut deduped: Vec<PathBuf> = Vec::new();
    for root in roots {
        if !deduped.iter().any(|existing| existing == &root) {
            deduped.push(root);
        }
    }
    deduped
}

fn clap_model_cached_in_roots(cache_roots: &[PathBuf], model_name: &str) -> bool {
    let model_key = clap_model_cache_key(model_name);
    cache_roots.iter().any(|root| {
        let model_root = root.join(&model_key);
        let snapshots = model_root.join("snapshots");
        if !snapshots.is_dir() {
            return false;
        }
        let Ok(entries) = std::fs::read_dir(snapshots) else {
            return false;
        };
        entries.flatten().any(|entry| {
            entry.path().is_dir()
                && std::fs::read_dir(entry.path())
                    .map(|mut dir| dir.next().is_some())
                    .unwrap_or(false)
        })
    })
}

pub fn semantic_search_capability(
    conn: &Connection,
    app_data_dir: Option<&Path>,
) -> SearchSemanticCapability {
    let mut capability = configured_semantic_provider(conn).capability();
    if capability.provider_key != "clap" {
        return capability;
    }

    let model_name = clap_model_name();
    let cache_roots = clap_cache_roots(app_data_dir);
    if clap_model_cached_in_roots(&cache_roots, &model_name) {
        capability.status = "ready".to_string();
        capability.detail = "CLAP is configured and cache-ready. Rust semantic-lite candidate search is active; full CLAP embedding parity is still pending.".to_string();
        capability.supports_query = true;
        capability.supports_indexing = false;
    } else {
        capability.status = "unavailable_model_missing".to_string();
        let first_root = cache_roots
            .first()
            .map(|path| path.display().to_string())
            .unwrap_or_else(|| "<unknown>".to_string());
        capability.detail = format!(
            "CLAP is configured but model cache for {model_name} was not found. Legacy runtime expected HF cache roots such as {first_root}."
        );
    }
    capability
}

fn query_semantic_targets(query: &str) -> std::collections::HashMap<&'static str, f64> {
    let mut targets: std::collections::HashMap<&'static str, (f64, f64)> =
        std::collections::HashMap::new();
    let q = query.to_ascii_lowercase();
    let mut bump = |dim: &'static str, target: f64, weight: f64| {
        let entry = targets.entry(dim).or_insert((0.0, 0.0));
        entry.0 += target * weight;
        entry.1 += weight;
    };

    for token in q.split(|c: char| !c.is_alphanumeric()) {
        if token.is_empty() {
            continue;
        }
        match token {
            "energy" | "energetic" | "driving" | "intense" | "hype" => bump("energy", 0.85, 1.0),
            "calm" | "soft" | "gentle" | "ambient" => bump("energy", 0.25, 1.0),
            "happy" | "bright" | "uplift" | "joy" => bump("valence", 0.82, 1.0),
            "sad" | "melancholy" | "dark" | "bleak" => bump("valence", 0.2, 1.0),
            "tense" | "aggressive" | "anxious" | "chaotic" => bump("tension", 0.84, 1.0),
            "relaxed" | "smooth" | "easy" => bump("tension", 0.25, 1.0),
            "dense" | "heavy" | "layered" => bump("density", 0.82, 1.0),
            "minimal" | "sparse" | "stripped" => bump("density", 0.22, 1.0),
            "warm" | "analog" | "cozy" | "human" => bump("warmth", 0.8, 1.0),
            "cold" | "digital" | "icy" | "clinical" => bump("warmth", 0.2, 1.0),
            "drift" | "flow" | "movement" | "groove" => bump("movement", 0.78, 1.0),
            "still" | "static" | "frozen" => bump("movement", 0.2, 1.0),
            "wide" | "airy" | "spacious" | "cinematic" => bump("space", 0.84, 1.0),
            "close" | "tight" | "compressed" => bump("space", 0.24, 1.0),
            "raw" | "rough" | "gritty" | "lofi" => bump("rawness", 0.82, 1.0),
            "clean" | "polished" | "glossy" => bump("rawness", 0.24, 1.0),
            "complex" | "intricate" | "progressive" => bump("complexity", 0.82, 1.0),
            "simple" | "plain" | "direct" => bump("complexity", 0.25, 1.0),
            "nostalgic" | "nostalgia" | "retro" | "vintage" => bump("nostalgia", 0.86, 1.0),
            "modern" | "futuristic" | "current" => bump("nostalgia", 0.2, 1.0),
            _ => {}
        }
    }

    targets
        .into_iter()
        .filter_map(|(dim, (sum, weight))| {
            if weight > 0.0 {
                Some((dim, (sum / weight).clamp(0.0, 1.0)))
            } else {
                None
            }
        })
        .collect()
}

fn semantic_proxy_rerank(
    conn: &Connection,
    query: &str,
    limit: usize,
) -> LyraResult<Vec<SearchResult>> {
    let pool = fallback_text_search(conn, query, (limit.max(10) * 12).min(240))?;
    let targets = query_semantic_targets(query);
    if targets.is_empty() {
        return Ok(pool.into_iter().take(limit).collect());
    }

    let ids: Vec<i64> = pool.iter().map(|row| row.track_id).collect();
    if ids.is_empty() {
        return Ok(vec![]);
    }
    let placeholders = ids.iter().map(|_| "?").collect::<Vec<_>>().join(",");
    let sql = format!(
        "SELECT track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia
         FROM track_scores
         WHERE track_id IN ({placeholders})"
    );
    let id_params: Vec<Box<dyn rusqlite::types::ToSql>> = ids
        .iter()
        .map(|&id| -> Box<dyn rusqlite::types::ToSql> { Box::new(id) })
        .collect();
    let id_refs: Vec<&dyn rusqlite::types::ToSql> = id_params.iter().map(|b| b.as_ref()).collect();
    let mut stmt = conn.prepare(&sql)?;
    let score_rows: Vec<(i64, std::collections::HashMap<&'static str, f64>)> = stmt
        .query_map(id_refs.as_slice(), |row| {
            let mut m: std::collections::HashMap<&'static str, f64> =
                std::collections::HashMap::new();
            let values: [Option<f64>; 10] = [
                row.get(1)?,
                row.get(2)?,
                row.get(3)?,
                row.get(4)?,
                row.get(5)?,
                row.get(6)?,
                row.get(7)?,
                row.get(8)?,
                row.get(9)?,
                row.get(10)?,
            ];
            for (idx, value) in values.iter().enumerate() {
                if let Some(v) = value {
                    m.insert(DIM_NAMES[idx], *v);
                }
            }
            Ok((row.get(0)?, m))
        })?
        .filter_map(Result::ok)
        .collect();
    let dim_by_track: std::collections::HashMap<i64, std::collections::HashMap<&'static str, f64>> =
        score_rows.into_iter().collect();

    let mut reranked: Vec<SearchResult> = pool
        .into_iter()
        .map(|mut row| {
            let text_score = row.score.clamp(0.0, 1.0);
            let dim_score = dim_by_track
                .get(&row.track_id)
                .map(|dims| {
                    let mut hits = 0.0;
                    let mut count = 0.0;
                    for (dim, target) in &targets {
                        if let Some(actual) = dims.get(dim) {
                            hits += 1.0 - (actual - target).abs();
                            count += 1.0;
                        }
                    }
                    if count > 0.0 {
                        (hits / count).clamp(0.0, 1.0)
                    } else {
                        0.4
                    }
                })
                .unwrap_or(0.4);
            row.score = ((text_score * 0.45) + (dim_score * 0.55)).clamp(0.0, 1.0);
            row.fallback_reason = Some("semantic-lite clap proxy".to_string());
            row
        })
        .collect();

    reranked.sort_by(|left, right| {
        right
            .score
            .partial_cmp(&left.score)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| left.artist.to_lowercase().cmp(&right.artist.to_lowercase()))
            .then_with(|| left.album.to_lowercase().cmp(&right.album.to_lowercase()))
            .then_with(|| left.title.to_lowercase().cmp(&right.title.to_lowercase()))
    });
    for (index, row) in reranked.iter_mut().enumerate() {
        row.rank = index + 1;
    }
    Ok(reranked.into_iter().take(limit).collect())
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SearchFilters {
    pub artist: Option<String>,
    pub title: Option<String>,
    pub album: Option<String>,
    pub genre: Option<String>,
    pub version_type: Option<String>,
    pub exclude_remix: bool,
    pub year_min: Option<i32>,
    pub year_max: Option<i32>,
    pub bpm_min: Option<f64>,
    pub bpm_max: Option<f64>,
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

impl std::str::FromStr for SortBy {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Ok(match s.trim().to_lowercase().as_str() {
            "artist" => Self::Artist,
            "title" => Self::Title,
            "year" => Self::Year,
            "bpm" => Self::Bpm,
            "duration" => Self::Duration,
            "played" | "most_played" => Self::MostPlayed,
            "least_played" => Self::LeastPlayed,
            "added" | "recently_added" => Self::RecentlyAdded,
            "random" => Self::Random,
            _ => Self::Relevance,
        })
    }
}

const DIM_NAMES: [&str; 10] = [
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
    let rows: Vec<SearchDbRow> = if terms.is_empty() {
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
                row.get(10)?,
            ))
        })?
        .filter_map(Result::ok)
        .collect()
    } else {
        // Build LIKE conditions for each term across artist/title/album
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
        let mut bound: Vec<Box<dyn rusqlite::types::ToSql>> = flat_params
            .iter()
            .map(|s| -> Box<dyn rusqlite::types::ToSql> { Box::new(s.clone()) })
            .collect();
        bound.push(Box::new(fetch_limit));
        let refs: Vec<&dyn rusqlite::types::ToSql> = bound.iter().map(|b| b.as_ref()).collect();
        let mut stmt = conn.prepare(&sql)?;
        let rows_collected: Vec<_> = stmt
            .query_map(refs.as_slice(), |row| {
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
                    row.get(10)?,
                ))
            })?
            .filter_map(Result::ok)
            .collect();
        rows_collected
    };

    // Score + sort
    let query_lower = query.to_lowercase();
    let mut scored: Vec<ScoredSearchRow> = rows
        .into_iter()
        .map(|row| {
            let blob = format!("{} {} {}", row.1, row.2, row.3).to_lowercase();
            let token_hits = terms.iter().filter(|t| blob.contains(t.as_str())).count();
            let exact_bonus = if !query_lower.is_empty() && blob.contains(&query_lower) {
                1.0
            } else {
                0.0
            };
            let score = if terms.is_empty() {
                0.0
            } else {
                token_hits as f64 / terms.len() as f64 + exact_bonus
            };
            (score, row)
        })
        .collect();

    scored.sort_by(|a, b| {
        b.0.partial_cmp(&a.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.1 .1.to_lowercase().cmp(&b.1 .1.to_lowercase()))
            .then(a.1 .3.to_lowercase().cmp(&b.1 .3.to_lowercase()))
            .then(a.1 .2.to_lowercase().cmp(&b.1 .2.to_lowercase()))
    });

    let reason = if terms.is_empty() {
        Some("metadata fallback".into())
    } else {
        None
    };
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

/// Canonical search excavation surface:
/// metadata fallback tracks + compact artist/album facets + route hints.
pub fn search_excavation_surface(
    conn: &Connection,
    query: &str,
    limit: usize,
    app_data_dir: Option<&Path>,
) -> LyraResult<SearchExcavationResult> {
    let semantic = semantic_search_capability(conn, app_data_dir);
    let tracks = if semantic.supports_query {
        semantic_proxy_rerank(conn, query, limit.max(5))?
    } else {
        fallback_text_search(conn, query, limit.max(5))?
    };
    let mut artist_counts: std::collections::HashMap<String, i64> =
        std::collections::HashMap::new();
    let mut album_counts: std::collections::HashMap<String, i64> = std::collections::HashMap::new();
    let mut genre_counts: std::collections::HashMap<String, i64> = std::collections::HashMap::new();

    for track in &tracks {
        *artist_counts.entry(track.artist.clone()).or_insert(0) += 1;
        if !track.album.trim().is_empty() {
            *album_counts.entry(track.album.clone()).or_insert(0) += 1;
        }
        if !track.genre.trim().is_empty() {
            *genre_counts.entry(track.genre.clone()).or_insert(0) += 1;
        }
    }

    fn rank_counts(
        counts: std::collections::HashMap<String, i64>,
        max: usize,
    ) -> Vec<SearchFacetBucket> {
        let mut ranked: Vec<SearchFacetBucket> = counts
            .into_iter()
            .map(|(value, count)| SearchFacetBucket { value, count })
            .collect();
        ranked.sort_by(|left, right| {
            right
                .count
                .cmp(&left.count)
                .then_with(|| left.value.to_lowercase().cmp(&right.value.to_lowercase()))
        });
        ranked.into_iter().take(max).collect()
    }

    let top_artists = rank_counts(artist_counts, 5);
    let top_albums = rank_counts(album_counts, 5);
    let top_genres = rank_counts(genre_counts, 3);
    let mut route_hints: Vec<String> = Vec::new();
    if let Some(artist) = top_artists.first() {
        route_hints.push(format!(
            "Bridge from {} into something adjacent but less obvious.",
            artist.value
        ));
    }
    if let Some(genre) = top_genres.first() {
        route_hints.push(format!(
            "Keep the {} pulse, but move one room sideways.",
            genre.value
        ));
    }
    if let Some(album) = top_albums.first() {
        route_hints.push(format!(
            "Use {} as a hinge and search for the rewarding risk around it.",
            album.value
        ));
    }

    Ok(SearchExcavationResult {
        query: query.trim().to_string(),
        tracks: tracks.into_iter().take(limit.max(5)).collect(),
        top_artists,
        top_albums,
        route_hints,
    })
}

// ── Remix finder ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemixResult {
    pub track_id: i64,
    pub artist: String,
    pub title: String,
    pub album: String,
    pub year: Option<i32>,
    pub version_type: Option<String>,
    pub confidence: Option<f64>,
    pub path: String,
    pub is_strict: bool,
    pub match_type: String,
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
        "artist" => "LOWER(ar.name) ASC, LOWER(t.title) ASC",
        "title" | "track" => "LOWER(t.title) ASC, LOWER(ar.name) ASC",
        _ => "t.imported_at DESC",
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

    let mut bound: Vec<Box<dyn rusqlite::types::ToSql>> = param_values
        .iter()
        .map(|s| -> Box<dyn rusqlite::types::ToSql> { Box::new(s.clone()) })
        .collect();
    bound.push(Box::new(limit as i64));
    let refs: Vec<&dyn rusqlite::types::ToSql> = bound.iter().map(|b| b.as_ref()).collect();
    let mut stmt = conn.prepare(&sql)?;
    let rows: Vec<RemixResult> = stmt
        .query_map(refs.as_slice(), |row| {
            let title: String = row.get::<_, Option<String>>(2)?.unwrap_or_default();
            let album_name: String = row.get::<_, Option<String>>(3)?.unwrap_or_default();
            let version_type: Option<String> = row.get(5)?;
            let is_strict = version_type
                .as_deref()
                .map(|v| v == "remix")
                .unwrap_or(false);
            let blob = format!("{} {}", title, album_name).to_lowercase();
            let matched: Vec<String> = REMIX_HINT_TOKENS
                .iter()
                .filter(|&&t| blob.contains(t))
                .map(|&t| t.to_string())
                .collect();
            Ok(RemixResult {
                track_id: row.get(0)?,
                artist: row.get::<_, Option<String>>(1)?.unwrap_or_default(),
                title,
                album: album_name,
                year: row.get(4)?,
                version_type,
                confidence: row.get(6)?,
                path: row.get::<_, Option<String>>(7)?.unwrap_or_default(),
                match_type: if is_strict {
                    "classified".into()
                } else {
                    "candidate".into()
                },
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
#[allow(clippy::too_many_arguments)]
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
    let id_params: Vec<Box<dyn rusqlite::types::ToSql>> = ids
        .iter()
        .map(|&id| -> Box<dyn rusqlite::types::ToSql> { Box::new(id) })
        .collect();
    let id_refs: Vec<&dyn rusqlite::types::ToSql> = id_params.iter().map(|b| b.as_ref()).collect();
    let mut stmt = conn.prepare(&sql)?;
    let mut tracks: Vec<SearchResult> = stmt
        .query_map(id_refs.as_slice(), |row| {
            Ok(SearchResult {
                rank: 0,
                track_id: row.get(0)?,
                artist: row.get(1)?,
                title: row.get(2)?,
                album: row.get(3)?,
                year: row.get(4)?,
                genre: row.get(5)?,
                path: row.get::<_, Option<String>>(6)?.unwrap_or_default(),
                duration: row.get(7)?,
                version_type: row.get(8)?,
                confidence: row.get(9)?,
                bpm: row.get(10)?,
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
            let score_refs: Vec<&dyn rusqlite::types::ToSql> =
                id_params.iter().map(|b| b.as_ref()).collect();
            let score_rows: Vec<(i64, [Option<f64>; 10])> = score_stmt
                .query_map(score_refs.as_slice(), |row| {
                    Ok((
                        row.get(0)?,
                        [
                            row.get(1)?,
                            row.get(2)?,
                            row.get(3)?,
                            row.get(4)?,
                            row.get(5)?,
                            row.get(6)?,
                            row.get(7)?,
                            row.get(8)?,
                            row.get(9)?,
                            row.get(10)?,
                        ],
                    ))
                })?
                .filter_map(Result::ok)
                .collect();
            let score_map: std::collections::HashMap<i64, std::collections::HashMap<String, f64>> =
                score_rows
                    .into_iter()
                    .map(|(id, vals)| {
                        let m: std::collections::HashMap<String, f64> = DIM_NAMES
                            .iter()
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
            let pc_refs: Vec<&dyn rusqlite::types::ToSql> =
                id_params.iter().map(|b| b.as_ref()).collect();
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
            if !norm(&t.artist).contains(&norm(a)) {
                return false;
            }
        }
        if let Some(ti) = &filters.title {
            if !norm(&t.title).contains(&norm(ti)) {
                return false;
            }
        }
        if let Some(al) = &filters.album {
            if !norm(&t.album).contains(&norm(al)) {
                return false;
            }
        }
        if let Some(g) = &filters.genre {
            if !norm(&t.genre).contains(&norm(g)) {
                return false;
            }
        }
        if let Some(vt) = &filters.version_type {
            if norm(t.version_type.as_deref().unwrap_or("")) != norm(vt) {
                return false;
            }
        }
        if filters.exclude_remix && norm(t.version_type.as_deref().unwrap_or("")).contains("remix")
        {
            return false;
        }
        if let Some(yr) = filters.year_min {
            if t.year.map(|y| y < yr).unwrap_or(true) {
                return false;
            }
        }
        if let Some(yr) = filters.year_max {
            if t.year.map(|y| y > yr).unwrap_or(true) {
                return false;
            }
        }
        if let Some(bmin) = filters.bpm_min {
            if t.bpm.map(|b| b < bmin).unwrap_or(true) {
                return false;
            }
        }
        if let Some(bmax) = filters.bpm_max {
            if t.bpm.map(|b| b > bmax).unwrap_or(true) {
                return false;
            }
        }
        if let Some(dmin) = filters.duration_min {
            if t.duration.map(|d| d < dmin).unwrap_or(true) {
                return false;
            }
        }
        if let Some(dmax) = filters.duration_max {
            if t.duration.map(|d| d > dmax).unwrap_or(true) {
                return false;
            }
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
            if descending {
                o.reverse()
            } else {
                o
            }
        }),
        SortBy::Title => tracks.sort_by(|a, b| {
            let o = a.title.to_lowercase().cmp(&b.title.to_lowercase());
            if descending {
                o.reverse()
            } else {
                o
            }
        }),
        SortBy::Year => tracks.sort_by(|a, b| {
            let o = a.year.cmp(&b.year);
            if descending {
                o.reverse()
            } else {
                o
            }
        }),
        SortBy::Bpm => tracks.sort_by(|a, b| {
            a.bpm
                .partial_cmp(&b.bpm)
                .unwrap_or(std::cmp::Ordering::Equal)
        }),
        SortBy::Duration => tracks.sort_by(|a, b| {
            a.duration
                .partial_cmp(&b.duration)
                .unwrap_or(std::cmp::Ordering::Equal)
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
                    if descending {
                        o.reverse()
                    } else {
                        o
                    }
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
        .map(|(i, mut t)| {
            t.rank = i + 1;
            t
        })
        .collect();

    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::{
        clap_model_cached_in_roots, configured_semantic_provider_from, search_excavation_surface,
        semantic_search_capability,
    };
    use rusqlite::{params, Connection};
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn search_excavation_surface_returns_facets_and_route_hints() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE artists (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE albums (
              id INTEGER PRIMARY KEY,
              title TEXT NOT NULL
            );
            CREATE TABLE tracks (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              album_id INTEGER,
              title TEXT NOT NULL,
              path TEXT NOT NULL,
              year TEXT,
              genre TEXT,
              duration_seconds REAL,
              version_type TEXT,
              bpm REAL,
              quarantined INTEGER DEFAULT 0,
              imported_at TEXT
            );
            ",
        )
        .expect("schema");

        conn.execute(
            "INSERT INTO artists (id, name) VALUES (1, 'Artist One')",
            [],
        )
        .expect("artist one");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (2, 'Artist Two')",
            [],
        )
        .expect("artist two");
        conn.execute(
            "INSERT INTO albums (id, title) VALUES (1, 'Echo Chamber')",
            [],
        )
        .expect("album one");
        conn.execute(
            "INSERT INTO albums (id, title) VALUES (2, 'Echo Drift')",
            [],
        )
        .expect("album two");

        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, genre, quarantined)
             VALUES (1, 1, 1, 'Echo Lines', 'C:/tmp/echo1.mp3', 'indie', 0)",
            [],
        )
        .expect("track 1");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, genre, quarantined)
             VALUES (2, 1, 2, 'After Echo', 'C:/tmp/echo2.mp3', 'indie', 0)",
            [],
        )
        .expect("track 2");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, genre, quarantined)
             VALUES (3, 2, 2, 'Echo Ruins', 'C:/tmp/echo3.mp3', 'post-rock', 0)",
            [],
        )
        .expect("track 3");

        let surface = search_excavation_surface(&conn, "echo", 10, None).expect("search surface");
        assert!(!surface.tracks.is_empty());
        assert!(!surface.top_artists.is_empty());
        assert!(!surface.top_albums.is_empty());
        assert!(!surface.route_hints.is_empty());
        assert_eq!(surface.top_artists[0].value, "Artist One");
        assert_eq!(surface.top_artists[0].count, 2);
    }

    #[test]
    fn semantic_search_capability_reports_provider_status() {
        let capability = configured_semantic_provider_from("clap").capability();
        assert_eq!(capability.provider_key, "clap");
        assert_eq!(capability.status, "unavailable");
        assert!(!capability.supports_query);
        assert!(capability.detail.to_lowercase().contains("rust-native"));
    }

    #[test]
    fn semantic_search_capability_uses_provider_configs_when_env_is_absent() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE provider_configs (
              provider_key TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 0,
              config_json TEXT NOT NULL DEFAULT '{}',
              updated_at TEXT NOT NULL
            );
            ",
        )
        .expect("provider schema");

        conn.execute(
            "INSERT INTO provider_configs (provider_key, display_name, enabled, config_json, updated_at)
             VALUES (?1, ?2, ?3, ?4, datetime('now'))",
            params!["clap", "CLAP Semantic", 1_i64, "{}"],
        )
        .expect("insert clap provider row");

        let app_data_dir = std::env::temp_dir().join(format!(
            "lyra-semantic-test-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock")
                .as_nanos()
        ));
        std::fs::create_dir_all(&app_data_dir).expect("create app-data dir");

        let capability = semantic_search_capability(&conn, Some(&app_data_dir));
        assert_eq!(capability.provider_key, "clap");
        assert!(capability.status.starts_with("unavailable_"));
        assert!(!capability.supports_query);
    }

    #[test]
    fn clap_model_cached_in_roots_detects_hf_layout() {
        let root = std::env::temp_dir().join(format!(
            "lyra-semantic-cache-test-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock")
                .as_nanos()
        ));
        let snapshot_dir = root
            .join("hub")
            .join("models--laion--larger_clap_music")
            .join("snapshots")
            .join("abc123");
        std::fs::create_dir_all(&snapshot_dir).expect("create snapshot dir");
        std::fs::write(snapshot_dir.join("config.json"), "{}").expect("write marker");

        let present = clap_model_cached_in_roots(
            &[root.join("hub"), PathBuf::from("unused")],
            "laion/larger_clap_music",
        );
        assert!(present);
    }

    #[test]
    fn search_excavation_surface_uses_semantic_proxy_when_clap_cache_ready() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE provider_configs (
              provider_key TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 0,
              config_json TEXT NOT NULL DEFAULT '{}',
              updated_at TEXT NOT NULL
            );
            CREATE TABLE artists (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE albums (
              id INTEGER PRIMARY KEY,
              title TEXT NOT NULL
            );
            CREATE TABLE tracks (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              album_id INTEGER,
              title TEXT NOT NULL,
              path TEXT NOT NULL,
              year TEXT,
              genre TEXT,
              duration_seconds REAL,
              version_type TEXT,
              bpm REAL,
              quarantined INTEGER DEFAULT 0,
              imported_at TEXT
            );
            CREATE TABLE track_scores (
              track_id INTEGER PRIMARY KEY,
              energy REAL,
              valence REAL,
              tension REAL,
              density REAL,
              warmth REAL,
              movement REAL,
              space REAL,
              rawness REAL,
              complexity REAL,
              nostalgia REAL,
              bpm REAL,
              key_signature TEXT,
              scored_at TEXT NOT NULL,
              score_version INTEGER NOT NULL DEFAULT 2
            );
            ",
        )
        .expect("schema");
        conn.execute(
            "INSERT INTO provider_configs (provider_key, display_name, enabled, config_json, updated_at)
             VALUES (?1, ?2, ?3, ?4, datetime('now'))",
            params!["clap", "CLAP Semantic", 1_i64, "{}"],
        )
        .expect("provider row");
        conn.execute("INSERT INTO artists (id, name) VALUES (1, 'A1')", [])
            .expect("artist");
        conn.execute("INSERT INTO albums (id, title) VALUES (1, 'Worlds')", [])
            .expect("album");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, genre, quarantined)
             VALUES (1, 1, 1, 'Warm Echo', 'C:/tmp/warm.mp3', 'ambient', 0)",
            [],
        )
        .expect("track1");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, genre, quarantined)
             VALUES (2, 1, 1, 'Nostalgic Glow', 'C:/tmp/nostalgic.mp3', 'ambient', 0)",
            [],
        )
        .expect("track2");
        conn.execute(
            "INSERT INTO track_scores (track_id, warmth, nostalgia, scored_at)
             VALUES (1, 0.95, 0.10, datetime('now'))",
            [],
        )
        .expect("scores1");
        conn.execute(
            "INSERT INTO track_scores (track_id, warmth, nostalgia, scored_at)
             VALUES (2, 0.88, 0.92, datetime('now'))",
            [],
        )
        .expect("scores2");

        let app_data_dir = std::env::temp_dir().join(format!(
            "lyra-semantic-ready-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock")
                .as_nanos()
        ));
        let snapshot_dir = app_data_dir
            .join("cache")
            .join("hf")
            .join("hub")
            .join("models--laion--larger_clap_music")
            .join("snapshots")
            .join("abc123");
        std::fs::create_dir_all(&snapshot_dir).expect("create snapshot dir");
        std::fs::write(snapshot_dir.join("config.json"), "{}").expect("write marker");

        let surface = search_excavation_surface(&conn, "warm nostalgic", 5, Some(&app_data_dir))
            .expect("excavation");
        assert!(!surface.tracks.is_empty());
        assert_eq!(surface.tracks[0].track_id, 2);
        assert_eq!(
            surface.tracks[0].fallback_reason.as_deref(),
            Some("semantic-lite clap proxy")
        );
    }
}

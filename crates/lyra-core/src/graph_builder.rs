//! Artist relationship graph builder — Rust port of oracle/graph_builder.py.
//!
//! Two edge types are supported:
//!
//! **dimension_affinity** (local-only, no API):
//!   Artists whose track_scores centroids are cosine-similar (z-score-normalised).
//!   Implemented in `oracle::build_dimension_affinity` and re-exported here.
//!
//! **similar** (Last.fm community data):
//!   Uses `artist.getSimilar` to surface artists that fans of each library artist
//!   also listen to.  Requires a Last.fm API key stored in provider_configs.
//!
//! **[Lore Lineage?]** — MusicBrainz member_of / influence / lineage edges depend
//! on the Python Lore module and are deferred.
//!
//! Incremental builds track progress via the `settings` KV table
//! (key = `graph_builder_last_run_ts`).

use std::collections::{HashMap, HashSet};

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{errors::LyraResult, oracle::build_dimension_affinity};

// ── Constants ─────────────────────────────────────────────────────────────────

const LASTFM_BASE: &str = "https://ws.audioscrobbler.com/2.0";
const LASTFM_RATE_MS: u64 = 250; // ~4 req/s, well within 5/s limit
const META_KEY_LAST_RUN: &str = "graph_builder_last_run_ts";

// ── Public types ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphEdge {
    pub source: String,
    pub target: String,
    pub edge_type: String,
    pub weight: f64,
    pub evidence: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct GraphBuildResult {
    /// Number of new edge pairs (bidirectional) inserted.
    pub new_pairs: usize,
    pub dimension_pairs: usize,
    pub lastfm_pairs: usize,
    pub artists_processed: usize,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct GraphStats {
    pub total_artists: usize,
    pub total_connections: usize,
    pub last_run_ts: f64,
    pub top_connected: Vec<GraphNode>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct GraphNode {
    pub artist: String,
    pub connections: usize,
}

// ── Credential helpers ────────────────────────────────────────────────────────

pub fn load_lastfm_api_key(conn: &Connection) -> Option<String> {
    conn.query_row(
        "SELECT config_json FROM provider_configs WHERE provider_key = 'lastfm'",
        [],
        |row| row.get::<_, String>(0),
    )
    .ok()
    .and_then(|j| serde_json::from_str::<Value>(&j).ok())
    .and_then(|v| {
        v.get("lastfm_api_key")
            .or_else(|| v.get("LASTFM_API_KEY"))
            .and_then(Value::as_str)
            .map(String::from)
    })
    .filter(|s| !s.is_empty())
}

// ── Meta KV helpers ───────────────────────────────────────────────────────────

fn get_last_run_ts(conn: &Connection) -> f64 {
    conn.query_row(
        "SELECT value_json FROM settings WHERE key = ?1",
        params![META_KEY_LAST_RUN],
        |row| row.get::<_, String>(0),
    )
    .ok()
    .and_then(|s| s.trim_matches('"').parse::<f64>().ok())
    .unwrap_or(0.0)
}

fn set_last_run_ts(conn: &Connection, ts: f64) {
    let _ = conn.execute(
        "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?1, ?2)",
        params![META_KEY_LAST_RUN, ts.to_string()],
    );
}

// ── Last.fm similar-artist API ────────────────────────────────────────────────

#[derive(Debug)]
struct SimilarArtist {
    name: String,
    match_score: f64,
}

/// Call Last.fm `artist.getSimilar` for a single artist.
/// Returns up to `top_k` similar artists with match score ≥ 0.05.
fn fetch_lastfm_similar(api_key: &str, artist: &str, top_k: usize) -> Vec<SimilarArtist> {
    std::thread::sleep(std::time::Duration::from_millis(LASTFM_RATE_MS));

    let data: Value = match ureq::get(LASTFM_BASE)
        .query("method", "artist.getSimilar")
        .query("artist", artist)
        .query("api_key", api_key)
        .query("format", "json")
        .query("limit", &top_k.to_string())
        .call()
    {
        Ok(r) => r.into_json().unwrap_or(Value::Null),
        Err(_) => return vec![],
    };

    data.pointer("/similarartists/artist")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|entry| {
                    let name = entry.get("name").and_then(Value::as_str)?.to_string();
                    // Last.fm returns match as a string like "0.999"
                    let match_score = entry
                        .get("match")
                        .and_then(Value::as_str)
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0);
                    if match_score >= 0.05 {
                        Some(SimilarArtist { name, match_score })
                    } else {
                        None
                    }
                })
                .collect()
        })
        .unwrap_or_default()
}

// ── Last.fm similarity edge builder ──────────────────────────────────────────

/// Build `similar` edges from Last.fm community data.
///
/// For each library artist calls `artist.getSimilar` and inserts bidirectional
/// edges.  When `local_targets_only = true` only connects to artists already in
/// the local library (avoids inflating the graph with unowned artists).
///
/// Returns the number of new unique edge pairs inserted.
pub fn build_lastfm_similarity_edges(
    conn: &Connection,
    api_key: &str,
    top_k: usize,
    local_targets_only: bool,
    limit_artists: Option<usize>,
) -> LyraResult<usize> {
    let top_k = top_k.clamp(1, 50);

    // Load library artists
    let library_artists: Vec<String> = {
        let mut stmt = conn.prepare(
            "SELECT DISTINCT ar.name
             FROM artists ar
             JOIN tracks t ON t.artist_id = ar.id
             WHERE trim(COALESCE(ar.name,'')) != ''
               AND (t.quarantined IS NULL OR t.quarantined = 0)
             ORDER BY ar.name",
        )?;
        let all: Vec<String> = stmt
            .query_map([], |row| row.get(0))?
            .filter_map(Result::ok)
            .collect();
        match limit_artists {
            Some(n) => all.into_iter().take(n).collect(),
            None => all,
        }
    };

    let library_set: HashSet<String> = library_artists.iter().cloned().collect();

    // Load existing similar edges to skip duplicates
    let existing: HashSet<(String, String)> = {
        let mut stmt =
            conn.prepare("SELECT source, target FROM connections WHERE type = 'similar'")?;
        let rows_collected: Vec<(String, String)> = stmt
            .query_map([], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            })?
            .filter_map(Result::ok)
            .collect();
        rows_collected.into_iter().collect()
    };

    let mut seen_pairs: HashSet<(String, String)> = HashSet::new();
    let mut new_edges: Vec<GraphEdge> = Vec::new();

    for artist_name in &library_artists {
        let similar = fetch_lastfm_similar(api_key, artist_name, top_k);

        for s in similar {
            if s.name.is_empty() || s.name == *artist_name {
                continue;
            }
            if local_targets_only && !library_set.contains(&s.name) {
                continue;
            }
            let lo = if artist_name < &s.name {
                artist_name.clone()
            } else {
                s.name.clone()
            };
            let hi = if artist_name < &s.name {
                s.name.clone()
            } else {
                artist_name.clone()
            };
            let pair = (lo.clone(), hi.clone());
            if seen_pairs.contains(&pair) {
                continue;
            }
            if existing.contains(&(artist_name.clone(), s.name.clone()))
                || existing.contains(&(s.name.clone(), artist_name.clone()))
            {
                continue;
            }
            seen_pairs.insert(pair);

            let weight = (s.match_score * 0.9).clamp(0.0, 1.0);
            let evidence = format!(
                r#"{{"match":{:.4},"source":"lastfm_similar"}}"#,
                s.match_score
            );
            new_edges.push(GraphEdge {
                source: artist_name.clone(),
                target: s.name.clone(),
                edge_type: "similar".to_string(),
                weight,
                evidence: evidence.clone(),
            });
            new_edges.push(GraphEdge {
                source: s.name.clone(),
                target: artist_name.clone(),
                edge_type: "similar".to_string(),
                weight,
                evidence,
            });
        }
    }

    if new_edges.is_empty() {
        return Ok(0);
    }

    let now = chrono::Utc::now().to_rfc3339();
    let mut inserted = 0usize;
    for e in &new_edges {
        let ok = conn.execute(
            "INSERT OR IGNORE INTO connections
             (source, target, type, weight, evidence, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![e.source, e.target, e.edge_type, e.weight, e.evidence, now],
        );
        if ok.is_ok() {
            inserted += 1;
        }
    }

    Ok(inserted / 2) // bidirectional pairs
}

// ── Full / incremental build ──────────────────────────────────────────────────

/// Build dimension-affinity + Last.fm similar edges for artists added since the
/// last build run.  Tracks progress in the `settings` table.
///
/// Returns counts of new edge pairs per type.
pub fn build_incremental(
    conn: &Connection,
    top_k_lastfm: usize,
    local_targets_only: bool,
) -> LyraResult<GraphBuildResult> {
    let dim_pairs = build_dimension_affinity(conn);
    let lfm_pairs = match load_lastfm_api_key(conn) {
        Some(key) => {
            build_lastfm_similarity_edges(conn, &key, top_k_lastfm, local_targets_only, None)?
        }
        None => 0,
    };

    set_last_run_ts(conn, chrono::Utc::now().timestamp() as f64);

    // Count artists that were processed (those present in library)
    let artists_processed: i64 = conn
        .query_row(
            "SELECT COUNT(DISTINCT ar.id) FROM artists ar
             JOIN tracks t ON t.artist_id = ar.id
             WHERE (t.quarantined IS NULL OR t.quarantined = 0)",
            [],
            |r| r.get(0),
        )
        .unwrap_or(0);

    Ok(GraphBuildResult {
        new_pairs: dim_pairs + lfm_pairs,
        dimension_pairs: dim_pairs,
        lastfm_pairs: lfm_pairs,
        artists_processed: artists_processed as usize,
    })
}

/// Full rebuild — same as incremental but ignores last-run timestamp.
pub fn build_full(
    conn: &Connection,
    top_k_lastfm: usize,
    local_targets_only: bool,
) -> LyraResult<GraphBuildResult> {
    // Reset timestamp so incremental logic processes everything
    set_last_run_ts(conn, 0.0);
    build_incremental(conn, top_k_lastfm, local_targets_only)
}

// ── Stats ─────────────────────────────────────────────────────────────────────

pub fn graph_stats(conn: &Connection) -> LyraResult<GraphStats> {
    let total_artists: i64 = conn
        .query_row("SELECT COUNT(DISTINCT source) FROM connections", [], |r| {
            r.get(0)
        })
        .unwrap_or(0);

    let total_connections: i64 = conn
        .query_row("SELECT COUNT(*) FROM connections", [], |r| r.get(0))
        .unwrap_or(0);

    let top_connected: Vec<GraphNode> = {
        let mut stmt = conn.prepare(
            "SELECT source, COUNT(*) AS cnt FROM connections
             GROUP BY source ORDER BY cnt DESC LIMIT 5",
        )?;
        let rows_collected: Vec<GraphNode> = stmt
            .query_map([], |row| {
                Ok(GraphNode {
                    artist: row.get(0)?,
                    connections: row.get::<_, i64>(1)? as usize,
                })
            })?
            .filter_map(Result::ok)
            .collect();
        rows_collected
    };

    Ok(GraphStats {
        total_artists: total_artists as usize,
        total_connections: total_connections as usize,
        last_run_ts: get_last_run_ts(conn),
        top_connected,
    })
}

// ── Neighbourhood query ───────────────────────────────────────────────────────

/// Return all direct neighbours of `artist` in the connections table,
/// optionally filtered by edge type.
pub fn get_neighbours(
    conn: &Connection,
    artist: &str,
    edge_type: Option<&str>,
    limit: usize,
) -> LyraResult<Vec<GraphEdge>> {
    let limit = limit.clamp(1, 500);

    let (sql, params_box): (String, Vec<Box<dyn rusqlite::types::ToSql>>) = match edge_type {
        Some(et) => (
            format!(
                "SELECT source, target, type, weight, COALESCE(evidence,'')
                 FROM connections WHERE source = ?1 AND type = ?2
                 ORDER BY weight DESC LIMIT {limit}"
            ),
            vec![Box::new(artist.to_string()), Box::new(et.to_string())],
        ),
        None => (
            format!(
                "SELECT source, target, type, weight, COALESCE(evidence,'')
                 FROM connections WHERE source = ?1
                 ORDER BY weight DESC LIMIT {limit}"
            ),
            vec![Box::new(artist.to_string())],
        ),
    };

    let refs: Vec<&dyn rusqlite::types::ToSql> = params_box.iter().map(|b| b.as_ref()).collect();
    let mut stmt = conn.prepare(&sql)?;
    let edges: Vec<GraphEdge> = stmt
        .query_map(refs.as_slice(), |row| {
            Ok(GraphEdge {
                source: row.get(0)?,
                target: row.get(1)?,
                edge_type: row.get(2)?,
                weight: row.get(3)?,
                evidence: row.get(4)?,
            })
        })?
        .filter_map(Result::ok)
        .collect();

    Ok(edges)
}

// ── Edge type frequency map ───────────────────────────────────────────────────

/// Return a map of edge_type → count across all connections.
pub fn edge_type_counts(conn: &Connection) -> LyraResult<HashMap<String, usize>> {
    let mut stmt = conn.prepare("SELECT type, COUNT(*) FROM connections GROUP BY type")?;
    let map: HashMap<String, usize> = stmt
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)? as usize))
        })?
        .filter_map(Result::ok)
        .collect();
    Ok(map)
}

//! Cross-genre discovery — local-library bridge-artist and mood-based surfacing.
//!
//! Local pass: DB query for artists spanning two genre buckets.
//! Discogs fallback: when local library has no bridge artists, queries the
//! Discogs `/database/search` API for artists tagged with both genres.

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

use crate::errors::LyraResult;

// ── Mood → Genre mapping ──────────────────────────────────────────────────────

/// Static mood keyword → genre list table.
fn mood_genre_map() -> &'static [(&'static str, &'static [&'static str])] {
    &[
        ("aggressive",    &["Punk", "Hardcore", "Metal", "Industrial"]),
        ("euphoric",      &["Trance", "Progressive House", "Uplifting"]),
        ("melancholic",   &["Post-Rock", "Ambient", "Shoegaze", "Slowcore"]),
        ("energetic",     &["Drum and Bass", "Breakcore", "Techno"]),
        ("dark",          &["Darkwave", "EBM", "Dark Ambient", "Witch House"]),
        ("rebellious",    &["Punk", "Garage Rock", "Grunge"]),
        ("introspective", &["Indie Folk", "Singer-Songwriter", "Chamber Pop"]),
        ("chill",         &["Lo-fi", "Chillhop", "Downtempo", "Ambient"]),
        ("romantic",      &["Soul", "R&B", "Jazz", "Bossa Nova"]),
        ("nostalgic",     &["Classic Rock", "Oldies", "Blues", "Folk"]),
        ("focused",       &["Classical", "Minimalism", "Ambient", "Post-Rock"]),
        ("party",         &["Electronic", "EDM", "Hip-Hop", "Pop"]),
    ]
}

/// Map a mood string to genre keywords (may overlap across keys).
pub fn mood_to_genres(mood: &str) -> Vec<String> {
    let lower = mood.to_lowercase();
    let mut genres: Vec<String> = Vec::new();
    for (keyword, genre_list) in mood_genre_map() {
        if lower.contains(keyword) {
            for g in *genre_list {
                if !genres.iter().any(|x: &String| x.eq_ignore_ascii_case(g)) {
                    genres.push(g.to_string());
                }
            }
        }
    }
    // Fallback: treat mood itself as a genre hint
    if genres.is_empty() {
        genres.push(mood.to_string());
    }
    genres
}

// ── Types ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeArtist {
    pub name:         String,
    pub genre_a:      String,
    pub genre_b:      String,
    pub track_count:  i64,
    /// "local" = found in library; "discogs" = from Discogs API (deferred)
    pub source:       String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoutTarget {
    pub artist:       String,
    pub title:        String,
    pub album:        String,
    pub year:         Option<i32>,
    pub genre:        String,
    pub path:         String,
    pub tags:         Vec<String>,
    pub priority:     f64,
}

#[derive(Debug, Default, Serialize, Deserialize)]
pub struct MoodSearchResult {
    pub track_id:  i64,
    pub artist:    String,
    pub title:     String,
    pub album:     String,
    pub genre:     String,
    pub path:      String,
    pub source:    String,
}

// ── Credential loading ────────────────────────────────────────────────────────

fn load_discogs_token(conn: &Connection) -> Option<String> {
    conn.query_row(
        "SELECT config_json FROM provider_configs WHERE provider_key = 'discogs'",
        [], |row| row.get::<_, String>(0),
    )
    .ok()
    .and_then(|j| serde_json::from_str::<Value>(&j).ok())
    .and_then(|v| {
        v.get("discogs_token")
            .or_else(|| v.get("DISCOGS_TOKEN"))
            .and_then(Value::as_str)
            .map(String::from)
    })
    .filter(|s| !s.is_empty())
}

// ── Discogs bridge artist API ─────────────────────────────────────────────────

const DISCOGS_BASE:    &str = "https://api.discogs.com";
const DISCOGS_UA:      &str = "Lyra/0.1 +https://github.com/snappedpoem1/lyra";
const DISCOGS_RATE_MS: u64  = 1100;

/// Query Discogs for artists tagged with both genres.
/// Returns up to 50 candidates sourced as "discogs".
pub fn fetch_discogs_bridge_artists(
    token: &str,
    genre_a: &str,
    genre_b: &str,
) -> Vec<BridgeArtist> {
    std::thread::sleep(std::time::Duration::from_millis(DISCOGS_RATE_MS));

    let data: Value = match ureq::get(&format!("{}/database/search", DISCOGS_BASE))
        .set("User-Agent", DISCOGS_UA)
        .set("Authorization", &format!("Discogs token={}", token))
        .query("type", "artist")
        .query("style", &format!("{},{}", genre_a, genre_b))
        .query("per_page", "50")
        .call()
    {
        Ok(r)  => r.into_json().unwrap_or(Value::Null),
        Err(_) => return vec![],
    };

    data.get("results")
        .and_then(|r| r.as_array())
        .map(|results| {
            results
                .iter()
                .filter_map(|r| r.get("title").and_then(Value::as_str))
                .map(|name| BridgeArtist {
                    name:        name.to_string(),
                    genre_a:     genre_a.to_string(),
                    genre_b:     genre_b.to_string(),
                    track_count: 0,
                    source:      "discogs".to_string(),
                })
                .collect()
        })
        .unwrap_or_default()
}

// ── Bridge artist discovery ───────────────────────────────────────────────────

/// Find artists in the local library whose tracks span both genre strings.
///
/// Uses a substring match on the `genre` column — broad but fast.
/// Requires at least 2 distinct genre values containing the respective keywords.
pub fn find_local_bridge_artists(
    conn: &Connection,
    genre_a: &str,
    genre_b: &str,
) -> LyraResult<Vec<BridgeArtist>> {
    let like_a = format!("%{}%", genre_a.to_lowercase());
    let like_b = format!("%{}%", genre_b.to_lowercase());

    // Artists that have at least one track matching genre A and one matching genre B
    let sql = "
        SELECT ar.name,
               COUNT(DISTINCT t.id) AS cnt
        FROM tracks t
        LEFT JOIN artists ar ON ar.id = t.artist_id
        WHERE ar.name IS NOT NULL
          AND (t.quarantined IS NULL OR t.quarantined = 0)
          AND ar.id IN (
              SELECT t2.artist_id FROM tracks t2
              WHERE LOWER(COALESCE(t2.genre,'')) LIKE ?1
                AND (t2.quarantined IS NULL OR t2.quarantined = 0)
          )
          AND ar.id IN (
              SELECT t3.artist_id FROM tracks t3
              WHERE LOWER(COALESCE(t3.genre,'')) LIKE ?2
                AND (t3.quarantined IS NULL OR t3.quarantined = 0)
          )
        GROUP BY ar.id, ar.name
        ORDER BY cnt DESC
        LIMIT 50";

    let artists = conn
        .prepare(sql)?
        .query_map(params![like_a, like_b], |row| {
            Ok(BridgeArtist {
                name:        row.get::<_, String>(0)?,
                genre_a:     genre_a.to_string(),
                genre_b:     genre_b.to_string(),
                track_count: row.get(1)?,
                source:      "local".to_string(),
            })
        })?
        .filter_map(Result::ok)
        .collect();

    Ok(artists)
}

/// Cross-genre hunt — returns local library tracks by bridge artists.
///
/// Local pass first. If the library has no bridge artists AND a Discogs token
/// is configured, falls back to Discogs API to find bridge artist names, then
/// surfaces any matching tracks from the local library.
pub fn cross_genre_hunt(
    conn: &Connection,
    genre_a: &str,
    genre_b: &str,
    limit: usize,
) -> LyraResult<Vec<ScoutTarget>> {
    let limit = limit.clamp(1, 500);
    let mut bridge_artists = find_local_bridge_artists(conn, genre_a, genre_b)?;

    // Discogs fallback when local library has no bridge artists
    if bridge_artists.is_empty() {
        if let Some(token) = load_discogs_token(conn) {
            bridge_artists = fetch_discogs_bridge_artists(&token, genre_a, genre_b);
        }
    }

    if bridge_artists.is_empty() {
        return Ok(vec![]);
    }

    let artist_names: Vec<String> = bridge_artists
        .iter()
        .take(20)
        .map(|a| a.name.clone())
        .collect();

    let mut results: Vec<ScoutTarget> = Vec::new();

    for name in &artist_names {
        let like_name = format!("%{}%", name.to_lowercase());
        let like_a    = format!("%{}%", genre_a.to_lowercase());
        let like_b    = format!("%{}%", genre_b.to_lowercase());

        let tracks: Vec<ScoutTarget> = conn
            .prepare(
                "SELECT t.id, COALESCE(ar.name,''), COALESCE(t.title,''),
                        COALESCE(al.title,''), CAST(t.year AS INTEGER),
                        COALESCE(t.genre,''), COALESCE(t.path,'')
                 FROM tracks t
                 LEFT JOIN artists ar ON ar.id = t.artist_id
                 LEFT JOIN albums  al ON al.id = t.album_id
                 WHERE LOWER(COALESCE(ar.name,'')) LIKE ?1
                   AND (LOWER(COALESCE(t.genre,'')) LIKE ?2
                        OR LOWER(COALESCE(t.genre,'')) LIKE ?3)
                   AND (t.quarantined IS NULL OR t.quarantined = 0)
                 LIMIT 10",
            )?
            .query_map(params![like_name, like_a, like_b], |row| {
                let year: Option<i32> = row.get(4)?;
                let genre: String = row.get(5)?;
                let priority = compute_scout_priority(year, &genre, genre_a, genre_b);
                Ok(ScoutTarget {
                    artist: row.get(1)?,
                    title:  row.get(2)?,
                    album:  row.get(3)?,
                    year,
                    genre:  genre.clone(),
                    path:   row.get(6)?,
                    tags:   vec![
                        format!("fusion:{}_{}", genre_a.to_lowercase(), genre_b.to_lowercase()),
                        "context:bridge".into(),
                        "scout:cross_genre".into(),
                    ],
                    priority,
                })
            })?
            .filter_map(Result::ok)
            .collect();

        results.extend(tracks);
        if results.len() >= limit {
            break;
        }
    }

    results.sort_by(|a, b| b.priority.partial_cmp(&a.priority).unwrap_or(std::cmp::Ordering::Equal));
    results.truncate(limit);
    Ok(results)
}

/// Priority heuristic matching the Python `_calculate_priority` logic.
fn compute_scout_priority(year: Option<i32>, genre: &str, genre_a: &str, genre_b: &str) -> f64 {
    let mut score = 0.5_f64;
    let genre_lower = genre.to_lowercase();

    // Both genre signals present
    if genre_lower.contains(&genre_a.to_lowercase())
        && genre_lower.contains(&genre_b.to_lowercase())
    {
        score += 0.3;
    }

    // Recency bonus
    match year {
        Some(y) if y >= 2010 => score += 0.2,
        Some(y) if y >= 2000 => score += 0.1,
        _ => {}
    }

    score.clamp(0.0, 1.0)
}

// ── Mood-based discovery ──────────────────────────────────────────────────────

/// Mood-to-genre discovery against the local library.
///
/// Maps abstract mood keywords to genre lists (see `mood_to_genres`), then
/// queries tracks whose `genre` column contains any of those genres.
pub fn discover_by_mood(
    conn: &Connection,
    mood: &str,
    limit: usize,
) -> LyraResult<Vec<MoodSearchResult>> {
    let limit = limit.clamp(1, 500);
    let genres = mood_to_genres(mood);

    if genres.is_empty() {
        return Ok(vec![]);
    }

    // Build flat param list: one LIKE per genre
    let clauses: Vec<String> = genres
        .iter()
        .map(|_| "LOWER(COALESCE(t.genre,'')) LIKE ?".to_string())
        .collect();
    let where_str = clauses.join(" OR ");

    let sql = format!(
        "SELECT t.id, COALESCE(ar.name,''), COALESCE(t.title,''),
                COALESCE(al.title,''), COALESCE(t.genre,''), COALESCE(t.path,'')
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         LEFT JOIN albums  al ON al.id = t.album_id
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
           AND ({})
         ORDER BY RANDOM()
         LIMIT ?",
        where_str
    );

    let mut bound: Vec<Box<dyn rusqlite::types::ToSql>> = genres
        .iter()
        .map(|g| -> Box<dyn rusqlite::types::ToSql> {
            Box::new(format!("%{}%", g.to_lowercase()))
        })
        .collect();
    bound.push(Box::new(limit as i64));
    let refs: Vec<&dyn rusqlite::types::ToSql> = bound.iter().map(|b| b.as_ref()).collect();

    let mut stmt = conn.prepare(&sql)?;
    let results: Vec<MoodSearchResult> = stmt
        .query_map(refs.as_slice(), |row| {
            Ok(MoodSearchResult {
                track_id: row.get(0)?,
                artist:   row.get(1)?,
                title:    row.get(2)?,
                album:    row.get(3)?,
                genre:    row.get(4)?,
                path:     row.get(5)?,
                source:   "local".to_string(),
            })
        })?
        .filter_map(Result::ok)
        .collect();

    Ok(results)
}

// ── Genre tag stats ───────────────────────────────────────────────────────────

/// Return a frequency map of genre substrings found in the library.
/// Useful for surfacing available genre tokens for the cross-genre hunt.
pub fn genre_frequency_map(conn: &Connection) -> LyraResult<HashMap<String, usize>> {
    let genres: Vec<String> = conn
        .prepare(
            "SELECT DISTINCT LOWER(COALESCE(genre,''))
             FROM tracks
             WHERE genre IS NOT NULL AND genre != ''
               AND (quarantined IS NULL OR quarantined = 0)",
        )?
        .query_map([], |row| row.get(0))?
        .filter_map(Result::ok)
        .collect();

    let mut freq: HashMap<String, usize> = HashMap::new();
    for g in genres {
        *freq.entry(g).or_insert(0) += 1;
    }
    Ok(freq)
}

use std::cmp::Ordering;
use std::collections::HashMap;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::commands::{DiscoveryInteraction, DiscoverySession, ExplainPayload, RelatedArtist, TasteProfile, TrackScores};

const DIMENSIONS: &[&str] = &[
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

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MoodInterpreter;

impl MoodInterpreter {
    pub fn label(&self, dimensions: &HashMap<String, f64>) -> String {
        let energy = *dimensions.get("energy").unwrap_or(&0.5);
        let valence = *dimensions.get("valence").unwrap_or(&0.5);
        let tension = *dimensions.get("tension").unwrap_or(&0.5);
        let warmth = *dimensions.get("warmth").unwrap_or(&0.5);
        let space = *dimensions.get("space").unwrap_or(&0.5);
        let density = *dimensions.get("density").unwrap_or(&0.5);
        let rawness = *dimensions.get("rawness").unwrap_or(&0.5);

        let labels = vec![
            describe_energy(energy).to_string(),
            describe_tone(valence, tension, warmth).to_string(),
            describe_texture(space, density, rawness).to_string(),
        ];

        let labels: Vec<String> = labels
            .into_iter()
            .filter(|label| !label.is_empty())
            .collect();

        if labels.iter().all(|label| label == "balanced") {
            "balanced".to_string()
        } else {
            labels.join("/")
        }
    }
}

// ExplainPayload is defined in commands.rs and re-exported here for callers.

pub struct RecommendationBroker<'conn> {
    conn: &'conn Connection,
}

impl<'conn> RecommendationBroker<'conn> {
    pub fn new(conn: &'conn Connection) -> Self {
        Self { conn }
    }

    pub fn recommend(&self, taste: &TasteProfile, limit: usize) -> Vec<i64> {
        if taste.dimensions.is_empty() || limit == 0 {
            return Vec::new();
        }

        let Ok(mut stmt) = self.conn.prepare(
            "SELECT track_id, energy, valence, tension, density, warmth, movement,
                    space, rawness, complexity, nostalgia, bpm, key_signature,
                    scored_at, score_version
             FROM track_scores",
        ) else {
            return Vec::new();
        };

        let rows = match stmt.query_map([], |row| {
            Ok(TrackScores {
                track_id: row.get(0)?,
                energy: row.get(1)?,
                valence: row.get(2)?,
                tension: row.get(3)?,
                density: row.get(4)?,
                warmth: row.get(5)?,
                movement: row.get(6)?,
                space: row.get(7)?,
                rawness: row.get(8)?,
                complexity: row.get(9)?,
                nostalgia: row.get(10)?,
                bpm: row.get(11)?,
                key_signature: row.get(12)?,
                scored_at: row.get(13)?,
                score_version: row.get(14)?,
            })
        }) {
            Ok(rows) => rows,
            Err(_) => return Vec::new(),
        };

        let mut scored: Vec<(i64, f64)> = rows
            .filter_map(Result::ok)
            .map(|scores| {
                let score_map = scores_to_map(&scores);
                let similarity = cosine_similarity(&taste.dimensions, &score_map);
                let overlap = mean_overlap(&taste.dimensions, &score_map);
                let weighted_score =
                    (similarity * 0.85 + overlap * 0.15) * taste.confidence.max(0.35);
                (scores.track_id, weighted_score.clamp(0.0, 1.0))
            })
            .filter(|(_, similarity)| *similarity >= 0.15)
            .collect();

        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(Ordering::Equal));
        scored
            .into_iter()
            .take(limit)
            .map(|(track_id, _)| track_id)
            .collect()
    }

    /// Like `recommend` but returns (track_id, score) pairs.
    pub fn recommend_scored(&self, taste: &TasteProfile, limit: usize) -> Vec<(i64, f64)> {
        if taste.dimensions.is_empty() || limit == 0 {
            return Vec::new();
        }

        let Ok(mut stmt) = self.conn.prepare(
            "SELECT track_id, energy, valence, tension, density, warmth, movement,
                    space, rawness, complexity, nostalgia, bpm, key_signature,
                    scored_at, score_version
             FROM track_scores",
        ) else {
            return Vec::new();
        };

        let rows = match stmt.query_map([], |row| {
            Ok(TrackScores {
                track_id: row.get(0)?,
                energy: row.get(1)?,
                valence: row.get(2)?,
                tension: row.get(3)?,
                density: row.get(4)?,
                warmth: row.get(5)?,
                movement: row.get(6)?,
                space: row.get(7)?,
                rawness: row.get(8)?,
                complexity: row.get(9)?,
                nostalgia: row.get(10)?,
                bpm: row.get(11)?,
                key_signature: row.get(12)?,
                scored_at: row.get(13)?,
                score_version: row.get(14)?,
            })
        }) {
            Ok(rows) => rows,
            Err(_) => return Vec::new(),
        };

        let mut scored: Vec<(i64, f64)> = rows
            .filter_map(Result::ok)
            .map(|scores| {
                let score_map = scores_to_map(&scores);
                let similarity = cosine_similarity(&taste.dimensions, &score_map);
                let overlap = mean_overlap(&taste.dimensions, &score_map);
                let weighted_score =
                    (similarity * 0.85 + overlap * 0.15) * taste.confidence.max(0.35);
                (scores.track_id, weighted_score.clamp(0.0, 1.0))
            })
            .filter(|(_, similarity)| *similarity >= 0.15)
            .collect();

        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(Ordering::Equal));
        scored.into_iter().take(limit).collect()
    }
}

pub fn explain_track(conn: &Connection, track_id: i64, taste: &TasteProfile) -> ExplainPayload {
    let source = "rust-sqlite".to_string();

    let track_title = conn
        .query_row(
            "SELECT title FROM tracks WHERE id = ?1",
            params![track_id],
            |row| row.get::<_, String>(0),
        )
        .ok();

    let track_scores = conn
        .query_row(
            "SELECT track_id, energy, valence, tension, density, warmth, movement,
                    space, rawness, complexity, nostalgia, bpm, key_signature,
                    scored_at, score_version
             FROM track_scores
             WHERE track_id = ?1",
            params![track_id],
            |row| {
                Ok(TrackScores {
                    track_id: row.get(0)?,
                    energy: row.get(1)?,
                    valence: row.get(2)?,
                    tension: row.get(3)?,
                    density: row.get(4)?,
                    warmth: row.get(5)?,
                    movement: row.get(6)?,
                    space: row.get(7)?,
                    rawness: row.get(8)?,
                    complexity: row.get(9)?,
                    nostalgia: row.get(10)?,
                    bpm: row.get(11)?,
                    key_signature: row.get(12)?,
                    scored_at: row.get(13)?,
                    score_version: row.get(14)?,
                })
            },
        )
        .ok();

    let Some(track_scores) = track_scores else {
        return ExplainPayload {
            track_id,
            reasons: vec!["No local track_scores row exists for this track yet.".to_string()],
            confidence: 0.0,
            source,
        };
    };

    let score_map = scores_to_map(&track_scores);
    let interpreter = MoodInterpreter;
    let similarity = cosine_similarity(&taste.dimensions, &score_map);
    let overlap = mean_overlap(&taste.dimensions, &score_map);
    let mood_label = interpreter.label(&score_map);
    let taste_label = interpreter.label(&taste.dimensions);
    let shared_dimensions = strongest_dimension_matches(&taste.dimensions, &score_map);

    let mut reasons = Vec::new();
    if let Some(title) = track_title {
        reasons.push(format!("{title} resolves to a {mood_label} profile."));
    } else {
        reasons.push(format!("This track resolves to a {mood_label} profile."));
    }

    if !shared_dimensions.is_empty() {
        reasons.push(format!(
            "Strongest taste overlap: {}.",
            shared_dimensions.join(", ")
        ));
    }

    reasons.push(format!(
        "Taste profile currently reads as {taste_label}; cosine similarity is {:.2} with mean overlap {:.2}.",
        similarity, overlap
    ));

    if let Some(bpm) = track_scores.bpm {
        reasons.push(format!("Tempo signal sits at roughly {:.0} BPM.", bpm));
    }

    if let Some(key_signature) = &track_scores.key_signature {
        if !key_signature.trim().is_empty() {
            reasons.push(format!(
                "Local structure metadata includes key {key_signature}."
            ));
        }
    }

    ExplainPayload {
        track_id,
        reasons,
        confidence: ((similarity * 0.7 + overlap * 0.3) * taste.confidence.max(0.25))
            .clamp(0.0, 1.0),
        source,
    }
}

/// Build dimension-affinity edges between artists based on their track_scores centroids.
/// Ports graph_builder.py build_dimension_edges() — pure local DB computation.
/// Returns the count of new edge pairs inserted.
pub fn build_dimension_affinity(conn: &Connection) -> usize {
    // Load per-artist average score vectors
    let dim_cols: Vec<String> = DIMENSIONS.iter().map(|d| format!("AVG(ts.{})", d)).collect();
    let select_cols = dim_cols.join(", ");
    let sql = format!(
        "SELECT ar.name, {select_cols}
         FROM track_scores ts
         JOIN tracks t ON t.id = ts.track_id
         JOIN artists ar ON ar.id = t.artist_id
         WHERE trim(COALESCE(ar.name, '')) != ''
         GROUP BY ar.name
         HAVING COUNT(ts.track_id) >= 2"
    );
    let rows: Vec<(String, [f64; 10])> = {
        let mut stmt = match conn.prepare(&sql) {
            Ok(s) => s,
            Err(_) => return 0,
        };
        let raw: Vec<(String, Vec<f64>)> = stmt
            .query_map([], |row| {
                let name: String = row.get(0)?;
                let vals: Vec<f64> = (1..=10)
                    .map(|i| row.get::<_, f64>(i).unwrap_or(0.0))
                    .collect();
                Ok((name, vals))
            })
            .map(|rows| rows.filter_map(Result::ok).collect())
            .unwrap_or_default();
        raw.into_iter()
            .filter_map(|(name, v)| {
                if v.len() == 10 {
                    let mut arr = [0f64; 10];
                    arr.copy_from_slice(&v);
                    Some((name, arr))
                } else {
                    None
                }
            })
            .collect()
    };

    let n = rows.len();
    if n < 2 {
        return 0;
    }

    // Z-score standardise each dimension across all artists
    let mut means = [0f64; 10];
    let mut stds = [0f64; 10];
    for (_, v) in &rows {
        for i in 0..10 {
            means[i] += v[i];
        }
    }
    for m in &mut means {
        *m /= n as f64;
    }
    for (_, v) in &rows {
        for i in 0..10 {
            let d = v[i] - means[i];
            stds[i] += d * d;
        }
    }
    for s in &mut stds {
        *s = (*s / n as f64).sqrt();
        if *s < 1e-9 {
            *s = 1.0;
        }
    }

    // Build normalised z-score vectors
    let mut z_vecs: Vec<[f64; 10]> = rows
        .iter()
        .map(|(_, v)| {
            let mut z = [0f64; 10];
            for i in 0..10 {
                z[i] = (v[i] - means[i]) / stds[i];
            }
            // L2 normalise
            let norm: f64 = z.iter().map(|x| x * x).sum::<f64>().sqrt().max(1e-9);
            z.iter_mut().for_each(|x| *x /= norm);
            z
        })
        .collect();
    let _ = &mut z_vecs; // suppress lint

    // Compute pairwise cosine similarity and collect edges above threshold
    const THRESHOLD: f64 = 0.60;
    const TOP_K: usize = 8;
    let artists: Vec<&str> = rows.iter().map(|(name, _)| name.as_str()).collect();
    let norm_vecs = &z_vecs;

    // Load existing pairs to avoid duplicates
    let existing: std::collections::HashSet<(String, String)> = {
        let mut stmt = conn
            .prepare("SELECT source, target FROM connections WHERE type = 'dimension_affinity'")
            .unwrap_or_else(|_| conn.prepare("SELECT '' AS source, '' AS target WHERE 0").unwrap());
        stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })
        .map(|rows| rows.filter_map(Result::ok).collect())
        .unwrap_or_default()
    };

    let mut new_edges: Vec<(String, String, f64)> = Vec::new();
    let mut seen: std::collections::HashSet<(usize, usize)> = std::collections::HashSet::new();

    for i in 0..n {
        // Compute similarities for artist i against all others
        let mut sims: Vec<(usize, f64)> = (0..n)
            .filter(|&j| j != i)
            .map(|j| {
                let sim: f64 = norm_vecs[i]
                    .iter()
                    .zip(norm_vecs[j].iter())
                    .map(|(a, b)| a * b)
                    .sum();
                (j, sim)
            })
            .collect();
        sims.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        for (j, sim) in sims.into_iter().take(TOP_K) {
            if sim < THRESHOLD {
                continue;
            }
            let lo = i.min(j);
            let hi = i.max(j);
            if seen.contains(&(lo, hi)) {
                continue;
            }
            let a = artists[i].to_string();
            let b = artists[j].to_string();
            if existing.contains(&(a.clone(), b.clone())) || existing.contains(&(b.clone(), a.clone())) {
                continue;
            }
            seen.insert((lo, hi));
            new_edges.push((a, b, sim));
        }
    }

    if new_edges.is_empty() {
        return 0;
    }

    let now = chrono::Utc::now().to_rfc3339();
    let mut inserted = 0usize;
    for (a, b, sim) in &new_edges {
        let weight = (*sim).clamp(0.0, 1.0);
        let evidence = format!(r#"{{"similarity":{:.4},"type":"dimension_affinity"}}"#, weight);
        let r1 = conn.execute(
            "INSERT OR IGNORE INTO connections (source, target, type, weight, evidence, updated_at) VALUES (?1, ?2, 'dimension_affinity', ?3, ?4, ?5)",
            params![a, b, weight, evidence, now],
        );
        let r2 = conn.execute(
            "INSERT OR IGNORE INTO connections (source, target, type, weight, evidence, updated_at) VALUES (?1, ?2, 'dimension_affinity', ?3, ?4, ?5)",
            params![b, a, weight, evidence, now],
        );
        if r1.is_ok() && r2.is_ok() {
            inserted += 1;
        }
    }
    inserted
}

/// Find related artists — checks connections table first, then falls back to co-play/genre.
pub fn get_related_artists(
    artist_name: &str,
    limit: usize,
    conn: &Connection,
) -> Vec<RelatedArtist> {
    let mut results: Vec<RelatedArtist> = Vec::new();

    // First: query dimension_affinity + similar edges from connections table
    if let Ok(mut stmt) = conn.prepare(
        "SELECT target, weight, type FROM connections
         WHERE lower(trim(source)) = lower(trim(?1))
         ORDER BY weight DESC LIMIT ?2",
    ) {
        let rows = stmt.query_map(params![artist_name, limit as i64], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, f64>(1)?,
                row.get::<_, String>(2)?,
            ))
        });
        if let Ok(rows) = rows {
            for row in rows.filter_map(Result::ok) {
                let (name, weight, conn_type) = row;
                let local_count: i64 = conn
                    .query_row(
                        "SELECT COUNT(*) FROM tracks t LEFT JOIN artists ar ON ar.id = t.artist_id
                         WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
                        params![name.as_str()],
                        |r| r.get(0),
                    )
                    .unwrap_or(0);
                results.push(RelatedArtist {
                    name,
                    connection_strength: weight as f32,
                    connection_type: conn_type,
                    local_track_count: local_count as usize,
                });
            }
        }
    }

    if !results.is_empty() {
        return results;
    }

    // Fallback: co-play connections from playback_history
    let co_play_result = conn.prepare(
        "SELECT COALESCE(ar2.name, '') AS related, COUNT(*) AS strength
         FROM playback_history p1
         JOIN playback_history p2
           ON p1.id != p2.id
          AND abs(strftime('%s', p1.ts) - strftime('%s', p2.ts)) <= 1800
         JOIN tracks t1 ON t1.id = p1.track_id
         LEFT JOIN artists ar1 ON ar1.id = t1.artist_id
         JOIN tracks t2 ON t2.id = p2.track_id
         LEFT JOIN artists ar2 ON ar2.id = t2.artist_id
         WHERE lower(trim(COALESCE(ar1.name, ''))) = lower(trim(?1))
           AND lower(trim(COALESCE(ar2.name, ''))) != lower(trim(?1))
           AND trim(COALESCE(ar2.name, '')) != ''
         GROUP BY ar2.name
         ORDER BY strength DESC
         LIMIT ?2",
    );

    if let Ok(mut stmt) = co_play_result {
        let rows = stmt.query_map(params![artist_name, limit as i64], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        });
        if let Ok(rows) = rows {
            for row in rows.filter_map(Result::ok) {
                let (name, strength) = row;
                let local_count: i64 = conn
                    .query_row(
                        "SELECT COUNT(*) FROM tracks t LEFT JOIN artists ar ON ar.id = t.artist_id
                         WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
                        params![name.as_str()],
                        |r| r.get(0),
                    )
                    .unwrap_or(0);
                let connection_strength = (strength as f32 / 100_f32).min(1.0);
                results.push(RelatedArtist {
                    name,
                    connection_strength,
                    connection_type: "co_play".to_string(),
                    local_track_count: local_count as usize,
                });
            }
        }
    }

    if results.is_empty() {
        // Final fallback: shared genre
        let genre_result = conn.prepare(
            "SELECT COALESCE(ar2.name, ''), COUNT(*) AS cnt
             FROM tracks t1
             LEFT JOIN artists ar1 ON ar1.id = t1.artist_id
             JOIN tracks t2 ON t2.genre = t1.genre AND t2.artist_id != t1.artist_id
             LEFT JOIN artists ar2 ON ar2.id = t2.artist_id
             WHERE lower(trim(COALESCE(ar1.name, ''))) = lower(trim(?1))
               AND t1.genre IS NOT NULL AND trim(t1.genre) != ''
               AND trim(COALESCE(ar2.name, '')) != ''
             GROUP BY ar2.name
             ORDER BY cnt DESC
             LIMIT ?2",
        );
        if let Ok(mut stmt) = genre_result {
            let rows = stmt.query_map(params![artist_name, limit as i64], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
            });
            if let Ok(rows) = rows {
                for row in rows.filter_map(Result::ok) {
                    let (name, cnt) = row;
                    let local_count: i64 = conn
                        .query_row(
                            "SELECT COUNT(*) FROM tracks t LEFT JOIN artists ar ON ar.id = t.artist_id
                             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
                            params![name.as_str()],
                            |r| r.get(0),
                        )
                        .unwrap_or(0);
                    results.push(RelatedArtist {
                        name,
                        connection_strength: (cnt as f32 / 50.0).min(1.0),
                        connection_type: "genre".to_string(),
                        local_track_count: local_count as usize,
                    });
                }
            }
        }
    }

    results
}

/// Return track IDs from related artists, sorted by recommendation score.
pub fn play_similar_to_artist(
    artist_name: &str,
    limit: usize,
    conn: &Connection,
) -> Vec<i64> {
    use std::cmp::Ordering;

    let related = get_related_artists(artist_name, 5, conn);
    if related.is_empty() {
        return Vec::new();
    }

    let related_names: Vec<String> = related.iter().map(|r| r.name.clone()).collect();

    // Gather scored tracks from related artists
    let mut scored: Vec<(i64, f64)> = Vec::new();
    for name in &related_names {
        let track_result = conn.prepare(
            "SELECT ts.track_id, ts.energy + ts.valence + ts.movement AS composite_score
             FROM track_scores ts
             JOIN tracks t ON t.id = ts.track_id
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
             ORDER BY composite_score DESC
             LIMIT 20",
        );
        if let Ok(mut stmt) = track_result {
            let rows = stmt.query_map(params![name.as_str()], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, f64>(1)?))
            });
            if let Ok(rows) = rows {
                scored.extend(rows.filter_map(Result::ok));
            }
        }
    }

    scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(Ordering::Equal));
    scored.dedup_by_key(|s| s.0);
    scored.into_iter().take(limit).map(|(id, _)| id).collect()
}

/// Record a discovery interaction.
pub fn record_discovery_interaction(
    artist_name: &str,
    action: &str,
    conn: &Connection,
) {
    let now = chrono::Utc::now().to_rfc3339();
    let _ = conn.execute(
        "INSERT INTO discovery_sessions (artist_name, action, created_at) VALUES (?1, ?2, ?3)",
        params![artist_name, action, now],
    );
}

/// Return the last N discovery interactions.
pub fn get_discovery_session(conn: &Connection) -> DiscoverySession {
    let result = conn.prepare(
        "SELECT artist_name, action, created_at FROM discovery_sessions
         ORDER BY created_at DESC LIMIT 10",
    );
    let recent = match result {
        Ok(mut stmt) => stmt
            .query_map([], |row| {
                Ok(DiscoveryInteraction {
                    artist_name: row.get(0)?,
                    action: row.get(1)?,
                    created_at: row.get(2)?,
                })
            })
            .map(|rows| rows.filter_map(Result::ok).collect())
            .unwrap_or_default(),
        Err(_) => Vec::new(),
    };
    DiscoverySession { recent }
}

fn scores_to_map(scores: &TrackScores) -> HashMap<String, f64> {
    HashMap::from([
        ("energy".to_string(), scores.energy),
        ("valence".to_string(), scores.valence),
        ("tension".to_string(), scores.tension),
        ("density".to_string(), scores.density),
        ("warmth".to_string(), scores.warmth),
        ("movement".to_string(), scores.movement),
        ("space".to_string(), scores.space),
        ("rawness".to_string(), scores.rawness),
        ("complexity".to_string(), scores.complexity),
        ("nostalgia".to_string(), scores.nostalgia),
    ])
}

fn strongest_dimension_matches(
    taste_dimensions: &HashMap<String, f64>,
    track_dimensions: &HashMap<String, f64>,
) -> Vec<String> {
    let mut matches: Vec<(String, f64)> = DIMENSIONS
        .iter()
        .filter_map(|dimension| {
            let taste_value = taste_dimensions.get(*dimension)?;
            let track_value = track_dimensions.get(*dimension)?;
            Some((
                dimension.to_string(),
                1.0 - (taste_value - track_value).abs(),
            ))
        })
        .collect();

    matches.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(Ordering::Equal));
    matches
        .into_iter()
        .take(2)
        .map(|(dimension, alignment)| format!("{dimension} ({alignment:.2})"))
        .collect()
}

fn cosine_similarity(left: &HashMap<String, f64>, right: &HashMap<String, f64>) -> f64 {
    let mut dot = 0.0;
    let mut left_norm = 0.0;
    let mut right_norm = 0.0;

    for dimension in DIMENSIONS {
        let left_value = *left.get(*dimension).unwrap_or(&0.0);
        let right_value = *right.get(*dimension).unwrap_or(&0.0);
        dot += left_value * right_value;
        left_norm += left_value * left_value;
        right_norm += right_value * right_value;
    }

    if left_norm <= f64::EPSILON || right_norm <= f64::EPSILON {
        return 0.0;
    }

    (dot / (left_norm.sqrt() * right_norm.sqrt())).clamp(0.0, 1.0)
}

fn mean_overlap(left: &HashMap<String, f64>, right: &HashMap<String, f64>) -> f64 {
    let mut total = 0.0;
    let mut count = 0.0;

    for dimension in DIMENSIONS {
        if let (Some(left_value), Some(right_value)) = (left.get(*dimension), right.get(*dimension))
        {
            total += 1.0 - (left_value - right_value).abs();
            count += 1.0;
        }
    }

    if count <= f64::EPSILON {
        return 0.0;
    }

    (total / count).clamp(0.0, 1.0)
}

fn describe_energy(energy: f64) -> &'static str {
    if energy >= 0.66 {
        "high-energy"
    } else if energy <= 0.34 {
        "low-energy"
    } else {
        "mid-energy"
    }
}

fn describe_tone(valence: f64, tension: f64, warmth: f64) -> &'static str {
    if valence >= 0.62 && tension <= 0.45 {
        "bright"
    } else if valence <= 0.4 && tension >= 0.58 {
        "dark"
    } else if warmth >= 0.62 {
        "warm"
    } else if tension <= 0.38 {
        "calm"
    } else {
        "balanced"
    }
}

fn describe_texture(space: f64, density: f64, rawness: f64) -> &'static str {
    if space >= 0.62 && density <= 0.48 {
        "spacious"
    } else if density >= 0.62 {
        "dense"
    } else if rawness >= 0.62 {
        "raw"
    } else if space <= 0.4 {
        "close"
    } else {
        "balanced"
    }
}

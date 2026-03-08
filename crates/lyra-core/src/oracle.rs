use std::cmp::Ordering;
use std::collections::HashMap;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::commands::{ExplainPayload, TasteProfile, TrackScores};

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

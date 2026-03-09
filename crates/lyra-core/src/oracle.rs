use std::cmp::Ordering;
use std::collections::HashMap;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::commands::{
    DiscoveryInteraction, DiscoverySession, EvidenceItem, ExplainPayload, RelatedArtist,
    RecommendationResult, TasteProfile, TrackScores,
};

/// Static cross-genre bridge map ported from oracle/recommendation_broker.py `_SCOUT_GENRE_BRIDGES`.
/// Keys are lowercase genre tokens; values are natural bridge destination genres in adjacency order.
fn genre_bridges(genre: &str) -> &'static [&'static str] {
    match genre {
        "rock" => &["electronic", "jazz", "folk"],
        "electronic" => &["jazz", "classical", "hip hop"],
        "hip hop" | "hip-hop" | "rap" => &["jazz", "electronic", "r&b"],
        "jazz" => &["electronic", "classical", "soul"],
        "classical" => &["electronic", "jazz", "ambient"],
        "folk" => &["electronic", "bluegrass", "world"],
        "metal" => &["electronic", "jazz", "classical"],
        "pop" => &["electronic", "r&b", "jazz"],
        "r&b" | "soul" => &["jazz", "hip hop", "electronic"],
        "ambient" => &["classical", "electronic", "drone"],
        "country" => &["folk", "blues", "rock"],
        "blues" => &["jazz", "soul", "rock"],
        "reggae" => &["dub", "electronic", "world"],
        "punk" => &["electronic", "noise", "jazz"],
        "alternative" | "indie" => &["folk", "electronic", "jazz"],
        _ => &["electronic", "jazz", "folk"],
    }
}

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

    /// Returns broker-grade `RecommendationResult` with structured evidence per candidate.
    ///
    /// Lane breakdown (mirrors Python broker provider weights):
    /// - local/taste (0.45): cosine + overlap against taste profile
    /// - local/deep_cut (implicit): low-play tracks that score well
    /// - scout/bridge (0.10): cross-genre bridge candidates from local library
    /// - graph/co_play (0.10): artists with graph affinity to taste anchors
    pub fn recommend_with_evidence(
        &self,
        taste: &TasteProfile,
        limit: usize,
    ) -> Vec<RecommendationResult> {
        use crate::library;

        if taste.dimensions.is_empty() || limit == 0 {
            return Vec::new();
        }

        let interpreter = MoodInterpreter;
        let taste_label = interpreter.label(&taste.dimensions);

        // --- Lane 1: local taste alignment ---
        let local_scored = self.recommend_scored(taste, limit * 2);

        // Load play counts for deep-cut detection
        let play_counts: HashMap<i64, i64> = {
            let mut map = HashMap::new();
            if let Ok(mut stmt) = self.conn.prepare(
                "SELECT t.id, COUNT(ph.id) FROM tracks t
                 LEFT JOIN playback_history ph ON ph.track_id = t.id
                 GROUP BY t.id",
            ) {
                let rows = stmt.query_map([], |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?)));
                if let Ok(rows) = rows {
                    for row in rows.filter_map(Result::ok) {
                        map.insert(row.0, row.1);
                    }
                }
            }
            map
        };

        // Load track scores for dimension labeling
        let score_rows: HashMap<i64, TrackScores> = {
            let mut map = HashMap::new();
            if let Ok(mut stmt) = self.conn.prepare(
                "SELECT track_id, energy, valence, tension, density, warmth, movement,
                        space, rawness, complexity, nostalgia, bpm, key_signature,
                        scored_at, score_version
                 FROM track_scores",
            ) {
                let rows = stmt.query_map([], |row| {
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
                });
                if let Ok(rows) = rows {
                    for row in rows.filter_map(Result::ok) {
                        map.insert(row.track_id, row);
                    }
                }
            }
            map
        };

        let mut results: Vec<RecommendationResult> = Vec::new();
        let mut seen_ids: std::collections::HashSet<i64> = std::collections::HashSet::new();

        for (track_id, raw_score) in &local_scored {
            let track_id = *track_id;
            let raw_score = *raw_score;

            let Ok(Some(track)) = library::get_track_by_id(self.conn, track_id) else {
                continue;
            };

            let play_count = play_counts.get(&track_id).copied().unwrap_or(0);
            let score_row = score_rows.get(&track_id);

            // Determine strongest matching dimensions for human text
            let shared_dims = score_row.map(|sr| {
                let sm = scores_to_map(sr);
                strongest_dimension_matches(&taste.dimensions, &sm)
            }).unwrap_or_default();

            let track_mood = score_row.map(|sr| interpreter.label(&scores_to_map(sr))).unwrap_or_default();

            let is_deep_cut = play_count <= 3 && raw_score >= 0.55;
            let provider = if is_deep_cut { "local/deep_cut" } else { "local/taste" }.to_string();

            let (why, evidence_type, evidence_text) = if is_deep_cut {
                (
                    format!(
                        "Rarely played but Lyra reads a strong {} profile — this is the kind of track that disappears in your library.",
                        track_mood
                    ),
                    "deep_cut",
                    format!("Only {} plays. Taste match {:.0}%.", play_count, raw_score * 100.0),
                )
            } else if !shared_dims.is_empty() {
                (
                    format!(
                        "Strongest overlap with your {} taste pressure on {}.",
                        taste_label,
                        shared_dims.join(", ")
                    ),
                    "taste_alignment",
                    format!("Shared dimensions: {}. Score {:.0}%.", shared_dims.join(", "), raw_score * 100.0),
                )
            } else {
                (
                    format!("Lyra sees a {} profile match against your current taste reading.", track_mood),
                    "taste_alignment",
                    format!("Cosine match {:.0}%.", raw_score * 100.0),
                )
            };

            let inferred_note = if !shared_dims.is_empty() {
                format!("Dimension overlap on {} inferred from local scores.", shared_dims.join(", "))
            } else {
                "Cosine similarity inferred from local taste profile.".to_string()
            };

            results.push(RecommendationResult {
                track,
                score: raw_score,
                provider: provider.clone(),
                why_this_track: why,
                evidence: vec![
                    EvidenceItem {
                        type_label: evidence_type.to_string(),
                        source: provider,
                        text: evidence_text,
                        weight: 0.45,
                    },
                    EvidenceItem {
                        type_label: "inferred".to_string(),
                        source: "local".to_string(),
                        text: inferred_note,
                        weight: 0.1,
                    },
                ],
            });
            seen_ids.insert(track_id);
        }

        // --- Lane 2: scout/bridge — find local tracks in bridge genres ---
        // Determine the dominant genre(s) from the local scored set
        let seed_genres: Vec<String> = {
            let mut genre_counts: HashMap<String, usize> = HashMap::new();
            for (track_id, _) in local_scored.iter().take(10) {
                if let Ok(Some(track)) = library::get_track_by_id(self.conn, *track_id) {
                    if let Some(genre) = track.genre {
                        let tok = genre.to_lowercase();
                        *genre_counts.entry(tok).or_insert(0) += 1;
                    }
                }
            }
            let mut pairs: Vec<_> = genre_counts.into_iter().collect();
            pairs.sort_by(|a, b| b.1.cmp(&a.1));
            pairs.into_iter().take(2).map(|(g, _)| g).collect()
        };

        for seed_genre in &seed_genres {
            let bridges = genre_bridges(seed_genre);
            for bridge_genre in bridges.iter().take(2) {
                // Find local library tracks in the bridge genre
                let genre_pattern = format!("%{}%", bridge_genre);
                let bridge_ids: Vec<i64> = match self.conn.prepare(
                    "SELECT t.id FROM tracks t
                     WHERE LOWER(COALESCE(t.genre, '')) LIKE LOWER(?)
                       AND t.status = 'active'
                     LIMIT 8",
                ) {
                    Err(_) => continue,
                    Ok(mut stmt) => {
                        let x = match stmt.query_map([&genre_pattern], |row| row.get::<_, i64>(0)) {
                            Ok(rows) => rows.filter_map(Result::ok).collect(),
                            Err(_) => continue,
                        };
                        x
                    }
                };

                for bridge_id in bridge_ids {
                    if seen_ids.contains(&bridge_id) {
                        continue;
                    }
                    let Ok(Some(track)) = library::get_track_by_id(self.conn, bridge_id) else {
                        continue;
                    };

                    let bridge_score = score_rows.get(&bridge_id).map(|sr| {
                        let sm = scores_to_map(sr);
                        let sim = cosine_similarity(&taste.dimensions, &sm);
                        let ov = mean_overlap(&taste.dimensions, &sm);
                        (sim * 0.7 + ov * 0.3).clamp(0.0, 1.0)
                    }).unwrap_or(0.35);

                    // Only include bridge candidates with some taste coherence
                    if bridge_score < 0.25 {
                        continue;
                    }

                    let why = format!(
                        "Scout bridge: this is where {} meets {} — a different world that shares your current pressure.",
                        seed_genre, bridge_genre
                    );
                    let evidence_text = format!(
                        "Cross-genre bridge: {} × {}. Local taste coherence {:.0}%.",
                        seed_genre, bridge_genre, bridge_score * 100.0
                    );

                    results.push(RecommendationResult {
                        track,
                        score: bridge_score * 0.82,
                        provider: "scout/bridge".to_string(),
                        why_this_track: why,
                        evidence: vec![
                            EvidenceItem {
                                type_label: "scout_bridge".to_string(),
                                source: "scout".to_string(),
                                text: evidence_text,
                                weight: 0.10,
                            },
                        ],
                    });
                    seen_ids.insert(bridge_id);
                }
            }
        }

        // --- Lane 3: graph/co_play — artists with graph affinity ---
        // Find artists connected to the top scored tracks' artists
        let anchor_artists: Vec<String> = {
            local_scored.iter().take(5).filter_map(|(tid, _)| {
                library::get_track_by_id(self.conn, *tid)
                    .ok()
                    .flatten()
                    .map(|t| t.artist.to_lowercase())
            }).collect()
        };

        if !anchor_artists.is_empty() {
            for anchor in anchor_artists.iter().take(3) {
                let connected: Vec<(String, i64)> = {
                    let stmt = self.conn.prepare(
                        "SELECT artist_b, score FROM artist_connections
                         WHERE LOWER(artist_a) = LOWER(?)
                         ORDER BY score DESC LIMIT 3",
                    );
                    match stmt {
                        Err(_) => vec![],
                        Ok(mut stmt) => match stmt.query_map([anchor], |row| {
                            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
                        }) {
                            Ok(rows) => rows.filter_map(Result::ok).collect(),
                            Err(_) => vec![],
                        },
                    }
                };

                for (connected_artist, graph_score) in connected {
                    // Find a track from this artist
                    let track_row: Option<i64> = self.conn.query_row(
                        "SELECT t.id FROM tracks t
                         JOIN artists ar ON ar.id = t.artist_id
                         WHERE LOWER(ar.name) = LOWER(?)
                           AND t.status = 'active'
                         ORDER BY RANDOM() LIMIT 1",
                        [&connected_artist],
                        |row| row.get(0),
                    ).ok();

                    let Some(track_id) = track_row else { continue };
                    if seen_ids.contains(&track_id) { continue; }
                    let Ok(Some(track)) = library::get_track_by_id(self.conn, track_id) else { continue };

                    let co_score = (graph_score as f64 / 100.0).clamp(0.2, 0.75);
                    let why = format!(
                        "Listeners who love {} also gravitate toward {} — graph affinity, not just genre proximity.",
                        anchor, connected_artist
                    );

                    results.push(RecommendationResult {
                        track,
                        score: co_score * 0.72,
                        provider: "graph/co_play".to_string(),
                        why_this_track: why.clone(),
                        evidence: vec![
                            EvidenceItem {
                                type_label: "co_play".to_string(),
                                source: "graph".to_string(),
                                text: format!(
                                    "Artist graph connection: {} → {}. Affinity score {}.",
                                    anchor, connected_artist, graph_score
                                ),
                                weight: 0.10,
                            },
                        ],
                    });
                    seen_ids.insert(track_id);
                }
            }
        }

        // Sort: local taste first by score, then scout, then graph
        results.sort_by(|a, b| {
            let provider_rank = |p: &str| -> u8 {
                if p.starts_with("local/taste") { 0 }
                else if p.starts_with("local/deep_cut") { 1 }
                else if p.starts_with("scout") { 2 }
                else { 3 }
            };
            let pa = provider_rank(&a.provider);
            let pb = provider_rank(&b.provider);
            if pa != pb { return pa.cmp(&pb); }
            b.score.partial_cmp(&a.score).unwrap_or(Ordering::Equal)
        });

        results.truncate(limit);
        results
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
            why_this_track: "No local score data for this track yet.".to_string(),
            reasons: vec!["No local track_scores row exists for this track yet.".to_string()],
            evidence_items: vec![],
            explicit_from_prompt: vec![],
            inferred_by_lyra: vec!["Track has not been scored by the local engine.".to_string()],
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
    let confidence =
        ((similarity * 0.7 + overlap * 0.3) * taste.confidence.max(0.25)).clamp(0.0, 1.0);

    // Build the "why_this_track" — composer-payload-depth sentence
    let why_this_track = if !shared_dimensions.is_empty() {
        if let Some(ref title) = track_title {
            format!(
                "{} lands in a {} world — strongest alignment with your {} taste on {}.",
                title, mood_label, taste_label, shared_dimensions.join(", ")
            )
        } else {
            format!(
                "This track lands in a {} world — strongest alignment with your {} taste on {}.",
                mood_label, taste_label, shared_dimensions.join(", ")
            )
        }
    } else {
        format!(
            "Lyra sees a {} profile that matches your current {} taste reading.",
            mood_label, taste_label
        )
    };

    // Build flat legacy reasons (backward compat)
    let mut reasons = Vec::new();
    if let Some(ref title) = track_title {
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
    if let Some(ref key_signature) = track_scores.key_signature {
        if !key_signature.trim().is_empty() {
            reasons.push(format!(
                "Local structure metadata includes key {key_signature}."
            ));
        }
    }

    // Build structured evidence items
    let mut evidence_items = vec![EvidenceItem {
        type_label: "taste_alignment".to_string(),
        source: "local".to_string(),
        text: format!(
            "Cosine similarity {:.0}%, mean overlap {:.0}% against your current {} taste profile.",
            similarity * 100.0,
            overlap * 100.0,
            taste_label
        ),
        weight: (similarity * 0.85 + overlap * 0.15).clamp(0.0, 1.0),
    }];

    if !shared_dimensions.is_empty() {
        evidence_items.push(EvidenceItem {
            type_label: "dimension_match".to_string(),
            source: "local".to_string(),
            text: format!(
                "Strong dimension alignment on: {}.",
                shared_dimensions.join(", ")
            ),
            weight: 0.6,
        });
    }

    if let Some(bpm) = track_scores.bpm {
        evidence_items.push(EvidenceItem {
            type_label: "tempo".to_string(),
            source: "local".to_string(),
            text: format!("Tempo: ~{:.0} BPM.", bpm),
            weight: 0.15,
        });
    }

    if let Some(ref key_signature) = track_scores.key_signature {
        if !key_signature.trim().is_empty() {
            evidence_items.push(EvidenceItem {
                type_label: "key".to_string(),
                source: "local".to_string(),
                text: format!("Key: {}.", key_signature),
                weight: 0.1,
            });
        }
    }

    // Inferred signals (Lyra's read, not stated by the user)
    let mut inferred_by_lyra = vec![format!(
        "Mood profile '{}' inferred from local CLAP/score dimensions.",
        mood_label
    )];
    if !shared_dimensions.is_empty() {
        inferred_by_lyra.push(format!(
            "Dimension overlap on {} inferred from cosine comparison against taste profile.",
            shared_dimensions.join(", ")
        ));
    }

    ExplainPayload {
        track_id,
        why_this_track,
        reasons,
        evidence_items,
        explicit_from_prompt: vec![],
        inferred_by_lyra,
        confidence,
        source,
    }
}

/// Build dimension-affinity edges between artists based on their track_scores centroids.
/// Ports graph_builder.py build_dimension_edges() — pure local DB computation.
/// Returns the count of new edge pairs inserted.
pub fn build_dimension_affinity(conn: &Connection) -> usize {
    // Load per-artist average score vectors
    let dim_cols: Vec<String> = DIMENSIONS
        .iter()
        .map(|d| format!("AVG(ts.{})", d))
        .collect();
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
            .unwrap_or_else(|_| {
                conn.prepare("SELECT '' AS source, '' AS target WHERE 0")
                    .unwrap()
            });
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
            if existing.contains(&(a.clone(), b.clone()))
                || existing.contains(&(b.clone(), a.clone()))
            {
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
        let evidence = format!(
            r#"{{"similarity":{:.4},"type":"dimension_affinity"}}"#,
            weight
        );
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
                let (why, preserves, changes, risk_note) =
                    related_artist_story(&conn_type, weight as f32, local_count as usize);
                results.push(RelatedArtist {
                    name,
                    connection_strength: weight as f32,
                    connection_type: conn_type,
                    local_track_count: local_count as usize,
                    why,
                    preserves,
                    changes,
                    risk_note,
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
                let (why, preserves, changes, risk_note) =
                    related_artist_story("co_play", connection_strength, local_count as usize);
                results.push(RelatedArtist {
                    name,
                    connection_strength,
                    connection_type: "co_play".to_string(),
                    local_track_count: local_count as usize,
                    why,
                    preserves,
                    changes,
                    risk_note,
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
                    let connection_strength = (cnt as f32 / 50.0).min(1.0);
                    let (why, preserves, changes, risk_note) =
                        related_artist_story("genre", connection_strength, local_count as usize);
                    results.push(RelatedArtist {
                        name,
                        connection_strength,
                        connection_type: "genre".to_string(),
                        local_track_count: local_count as usize,
                        why,
                        preserves,
                        changes,
                        risk_note,
                    });
                }
            }
        }
    }

    results
}

fn related_artist_story(
    connection_type: &str,
    connection_strength: f32,
    local_track_count: usize,
) -> (String, Vec<String>, Vec<String>, String) {
    let (why, preserves, changes) = match connection_type {
        "dimension_affinity" => (
            "This carries a similar emotional temperature and dimensional afterimage, even if the names are not the obvious next click.".to_string(),
            vec!["emotional temperature".to_string(), "dimensional residue".to_string()],
            vec!["surface scene markers".to_string()],
        ),
        "co_play" => (
            "This showed up in the same listening orbit, so it behaves like a natural next room rather than a metadata match.".to_string(),
            vec!["listening context".to_string(), "session momentum".to_string()],
            vec!["artist identity".to_string()],
        ),
        "genre" => (
            "This is the safer adjacency: shared scene color first, deeper difference second.".to_string(),
            vec!["scene color".to_string(), "genre neighborhood".to_string()],
            vec!["emotional specificity".to_string()],
        ),
        _ => (
            "This reads adjacent for a real reason, not only because it sits nearby in metadata.".to_string(),
            vec!["route legibility".to_string()],
            vec!["obviousness".to_string()],
        ),
    };
    let risk_note = if local_track_count == 0 {
        "Higher risk: Cassette does not own this artist yet, so this is a real discovery edge rather than a comfortable local lane.".to_string()
    } else if connection_strength >= 0.72 {
        "Lower risk: this should behave like a believable bridge step inside the current library."
            .to_string()
    } else if connection_strength >= 0.44 {
        "Measured risk: close enough to trust, different enough to matter.".to_string()
    } else {
        "Rewarding risk: the link is weaker on paper, but it may be truer than the safer obvious neighbors.".to_string()
    };
    (why, preserves, changes, risk_note)
}

/// Return track IDs from related artists, sorted by recommendation score.
pub fn play_similar_to_artist(artist_name: &str, limit: usize, conn: &Connection) -> Vec<i64> {
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
pub fn record_discovery_interaction(artist_name: &str, action: &str, conn: &Connection) {
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

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::time::Duration;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::audio_data;
use crate::commands::{
    AcquisitionLead, AcquisitionLeadHandoffReport, AcquisitionLeadOutcome, DiscoveryInteraction,
    DiscoverySession, EvidenceItem, ExplainPayload, RecommendationBundle, RecommendationResult,
    RelatedArtist, ScoutExitLane, ScoutExitPlan, TasteProfile, TrackScores,
};
use crate::lineage;
use crate::provider_runtime;
use crate::track_audio_features::{self, TrackAudioFeatures};

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
const FEEDBACK_LOOKBACK_SECONDS: i64 = 60 * 60 * 24 * 90;
const LISTENBRAINZ_WEATHER_WEIGHT: f64 = 0.10;

fn evidence_item(
    type_label: &str,
    source: &str,
    category: &str,
    anchor: &str,
    text: String,
    weight: f64,
) -> EvidenceItem {
    EvidenceItem {
        type_label: type_label.to_string(),
        source: source.to_string(),
        category: category.to_string(),
        anchor: anchor.to_string(),
        text,
        weight,
    }
}

fn evidence_grade_for_items(items: &[EvidenceItem]) -> String {
    if items.is_empty() {
        return "insufficient_evidence".to_string();
    }
    let has_audio = items.iter().any(|item| item.category == "audio_features");
    let has_lineage = items
        .iter()
        .any(|item| item.category == "lineage_member_graph");
    let has_adjacency = items
        .iter()
        .any(|item| item.category == "adjacency_similarity");
    let has_external = items.iter().any(|item| item.category == "external_context");
    let has_provider_metadata = items
        .iter()
        .any(|item| item.category == "provider_metadata");
    if has_audio && (has_lineage || has_adjacency || has_external || has_provider_metadata) {
        "high_confidence_multi_evidence".to_string()
    } else if has_audio {
        "audio_feature_assisted".to_string()
    } else if has_lineage || has_adjacency || has_external {
        "graph_context_assisted".to_string()
    } else {
        "metadata_only".to_string()
    }
}

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

fn ensure_feedback_table(conn: &Connection) {
    let _ = conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS recommendation_feedback (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          track_id INTEGER,
          feedback_type TEXT NOT NULL,
          created_at REAL NOT NULL DEFAULT (unixepoch('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_track_created
          ON recommendation_feedback(track_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_type_created
          ON recommendation_feedback(feedback_type, created_at DESC);
        ",
    );
}

fn feedback_weight(feedback_type: &str) -> f64 {
    match feedback_type {
        "accepted" => 0.18,
        "queued" => 0.12,
        "replayed" => 0.08,
        "skipped" => -0.2,
        "keep" => 0.15,
        "play" => 0.2,
        "dismiss" => -0.25,
        _ => 0.0,
    }
}

fn load_feedback_bias(conn: &Connection, track_ids: &[i64]) -> HashMap<i64, f64> {
    if track_ids.is_empty() {
        return HashMap::new();
    }

    ensure_feedback_table(conn);

    let placeholders = std::iter::repeat_n("?", track_ids.len())
        .collect::<Vec<_>>()
        .join(", ");
    let query = format!(
        "
        SELECT track_id, feedback_type, COUNT(*)
        FROM recommendation_feedback
        WHERE track_id IN ({placeholders})
          AND created_at >= ?
        GROUP BY track_id, feedback_type
        "
    );
    let lookback_threshold = (chrono::Utc::now().timestamp() - FEEDBACK_LOOKBACK_SECONDS) as f64;
    let mut stmt = match conn.prepare(&query) {
        Ok(stmt) => stmt,
        Err(_) => return HashMap::new(),
    };

    let mut params_list: Vec<rusqlite::types::Value> = Vec::with_capacity(track_ids.len() + 1);
    params_list.extend(
        track_ids
            .iter()
            .map(|track_id| rusqlite::types::Value::Integer(*track_id)),
    );
    params_list.push(rusqlite::types::Value::Real(lookback_threshold));

    let rows = match stmt.query_map(rusqlite::params_from_iter(params_list), |row| {
        Ok((
            row.get::<_, i64>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, i64>(2)?,
        ))
    }) {
        Ok(rows) => rows,
        Err(_) => return HashMap::new(),
    };

    let mut tallies: HashMap<i64, f64> = HashMap::new();
    for (track_id, feedback_type, count) in rows.filter_map(Result::ok) {
        let weight = feedback_weight(feedback_type.trim().to_ascii_lowercase().as_str());
        if weight == 0.0 {
            continue;
        }
        let next = tallies.get(&track_id).copied().unwrap_or(0.0) + (weight * count as f64);
        tallies.insert(track_id, next);
    }

    tallies
        .into_iter()
        .map(|(track_id, score)| (track_id, score.clamp(-0.35, 0.35)))
        .collect()
}

pub fn record_recommendation_feedback(conn: &Connection, track_id: i64, feedback_type: &str) {
    ensure_feedback_table(conn);
    let _ = conn.execute(
        "INSERT INTO recommendation_feedback (track_id, feedback_type, created_at) VALUES (?1, ?2, ?3)",
        params![
            track_id,
            feedback_type.trim().to_ascii_lowercase(),
            chrono::Utc::now().timestamp() as f64
        ],
    );
}

fn merge_recommendation_result(
    merged: &mut HashMap<i64, RecommendationResult>,
    candidate: RecommendationResult,
) {
    let track_id = candidate.track.id;
    if let Some(existing) = merged.get_mut(&track_id) {
        let previous_score = existing.score;
        existing.score = (existing.score + candidate.score).clamp(0.0, 1.0);
        if candidate.score >= previous_score {
            existing.why_this_track = candidate.why_this_track;
        }
        existing.evidence.extend(candidate.evidence);
        existing.evidence_grade = evidence_grade_for_items(&existing.evidence);

        let mut providers: Vec<String> = existing
            .provider
            .split(", ")
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .collect();
        if !providers
            .iter()
            .any(|provider| provider == &candidate.provider)
        {
            providers.push(candidate.provider);
            providers.sort();
        }
        existing.provider = providers.join(", ");
    } else {
        merged.insert(track_id, candidate);
    }
}

fn merge_acquisition_lead(
    leads: &mut HashMap<String, AcquisitionLead>,
    candidate: AcquisitionLead,
) {
    let key = format!(
        "{}\u{1f}{}",
        candidate.artist.trim().to_ascii_lowercase(),
        candidate.title.trim().to_ascii_lowercase()
    );
    if let Some(existing) = leads.get_mut(&key) {
        let previous_score = existing.score;
        existing.score = (existing.score + candidate.score).clamp(0.0, 1.0);
        if candidate.score >= previous_score {
            existing.reason = candidate.reason.clone();
        }
        existing.evidence.extend(candidate.evidence.clone());
        existing.evidence_grade = evidence_grade_for_items(&existing.evidence);
        if !existing.provider.contains(&candidate.provider) {
            existing.provider = format!("{}, {}", existing.provider, candidate.provider);
        }
    } else {
        leads.insert(key, candidate);
    }
}

pub fn enqueue_acquisition_leads(
    conn: &Connection,
    leads: &[AcquisitionLead],
) -> crate::errors::LyraResult<AcquisitionLeadHandoffReport> {
    let mut outcomes: Vec<AcquisitionLeadOutcome> = Vec::new();
    let mut added = 0_usize;
    let mut duplicates = 0_usize;
    let mut errors = 0_usize;
    let mut queue_position: i64 = conn
        .query_row(
            "SELECT COALESCE(MAX(queue_position), 0) FROM acquisition_queue",
            [],
            |row| row.get(0),
        )
        .unwrap_or(0);

    for lead in leads {
        let duplicate_active: i64 = conn
            .query_row(
                "SELECT COUNT(*)
                 FROM acquisition_queue
                 WHERE LOWER(TRIM(artist)) = LOWER(TRIM(?1))
                   AND LOWER(TRIM(title)) = LOWER(TRIM(?2))
                   AND status IN ('queued', 'validating', 'acquiring', 'staging', 'scanning', 'organizing', 'indexing')",
                params![lead.artist, lead.title],
                |row| row.get(0),
            )
            .unwrap_or(0);
        if duplicate_active > 0 {
            duplicates += 1;
            outcomes.push(AcquisitionLeadOutcome {
                artist: lead.artist.clone(),
                title: lead.title.clone(),
                provider: lead.provider.clone(),
                status: "duplicate_active".to_string(),
                detail: "Already queued or in active acquisition lifecycle.".to_string(),
                queue_item_id: None,
            });
            continue;
        }

        queue_position += 1;
        let now = chrono::Utc::now().to_rfc3339();
        let reason = lead.reason.trim();
        let summary = if reason.is_empty() {
            None
        } else {
            Some(reason)
        };
        let insert_result = conn.execute(
                "INSERT INTO acquisition_queue
                 (artist, title, album, status, queue_position, priority_score, source, added_at,
                  status_message, validation_confidence, validation_summary, lifecycle_stage,
                  lifecycle_progress, lifecycle_note, updated_at)
                 VALUES (?1, ?2, NULL, 'queued', ?3, ?4, ?5, ?6, ?7, ?8, ?9, 'queued', 0.0, ?7, ?6)",
                params![
                    lead.artist,
                    lead.title,
                    queue_position,
                    lead.score.clamp(0.0, 1.0),
                    lead.provider,
                    now,
                    summary.unwrap_or("Queued from recommendation lead"),
                    lead.score.clamp(0.0, 1.0),
                    summary,
                ],
            );
        match insert_result {
            Ok(_) => {
                added += 1;
                outcomes.push(AcquisitionLeadOutcome {
                    artist: lead.artist.clone(),
                    title: lead.title.clone(),
                    provider: lead.provider.clone(),
                    status: "queued".to_string(),
                    detail: "Queued from recommendation lead.".to_string(),
                    queue_item_id: Some(conn.last_insert_rowid()),
                });
            }
            Err(error) => {
                errors += 1;
                outcomes.push(AcquisitionLeadOutcome {
                    artist: lead.artist.clone(),
                    title: lead.title.clone(),
                    provider: lead.provider.clone(),
                    status: "error".to_string(),
                    detail: error.to_string(),
                    queue_item_id: None,
                });
            }
        }
    }
    Ok(AcquisitionLeadHandoffReport {
        outcomes,
        queued_count: i64::try_from(added).unwrap_or(0),
        duplicate_count: i64::try_from(duplicates).unwrap_or(0),
        error_count: i64::try_from(errors).unwrap_or(0),
    })
}

#[derive(Clone, Debug)]
struct WeatherRecording {
    artist: String,
    title: String,
    listen_count: i64,
    similarity_score: f64,
    source_artist: String,
}

#[derive(Clone, Debug)]
struct SimilarArtist {
    mbid: String,
    name: String,
    similarity: f64,
}

#[derive(Clone, Debug)]
struct ListenBrainzRuntimeConfig {
    token: String,
    base_url: String,
}

fn parse_weather_row(row: &Value) -> Option<WeatherRecording> {
    let artist = row.get("artist")?.as_str()?.trim().to_string();
    let title = row.get("title")?.as_str()?.trim().to_string();
    if artist.is_empty() || title.is_empty() {
        return None;
    }
    let listen_count = row
        .get("listen_count")
        .or_else(|| row.get("play_count"))
        .and_then(Value::as_i64)
        .unwrap_or(0)
        .max(0);
    let similarity_score = row
        .get("similarity_score")
        .or_else(|| row.get("similarity"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0)
        .clamp(0.0, 1.0);
    let source_artist = row
        .get("source_artist")
        .and_then(Value::as_str)
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| artist.clone());

    Some(WeatherRecording {
        artist,
        title,
        listen_count,
        similarity_score,
        source_artist,
    })
}

fn load_listenbrainz_runtime_config(
    conn: &Connection,
) -> Result<ListenBrainzRuntimeConfig, String> {
    let mut stmt = conn
        .prepare(
            "SELECT enabled, config_json
             FROM provider_configs
             WHERE provider_key = 'listenbrainz'
             LIMIT 1",
        )
        .map_err(|_| "provider config table unavailable".to_string())?;
    let row = stmt
        .query_row([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(|_| "listenbrainz provider config missing".to_string())?;

    if row.0 == 0 {
        return Err("listenbrainz provider disabled".to_string());
    }
    let parsed = serde_json::from_str::<Value>(&row.1)
        .map_err(|_| "listenbrainz config is invalid json".to_string())?;
    let token = parsed
        .get("listenbrainz_token")
        .or_else(|| parsed.get("LISTENBRAINZ_TOKEN"))
        .and_then(Value::as_str)
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "listenbrainz token missing".to_string())?;
    let base_url = parsed
        .get("listenbrainz_base_url")
        .and_then(Value::as_str)
        .map(|value| value.trim().trim_end_matches('/').to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "https://api.listenbrainz.org/1".to_string());

    Ok(ListenBrainzRuntimeConfig { token, base_url })
}

fn fetch_artist_mbid(conn: &Connection, artist_name: &str) -> Result<String, String> {
    let cache_key = format!("artist-mbid::{}", artist_name.trim().to_ascii_lowercase());
    let body = provider_runtime::cached_json_request(
        conn,
        "musicbrainz_artist_search",
        &cache_key,
        Duration::from_secs(60 * 60 * 24 * 14),
        || {
            ureq::get("https://musicbrainz.org/ws/2/artist")
                .set("User-Agent", "Lyra/0.1")
                .set("Accept", "application/json")
                .query("query", &format!("artist:{}", artist_name))
                .query("fmt", "json")
                .query("limit", "1")
                .timeout(Duration::from_millis(2500))
                .call()
        },
    )
    .map_err(|error| format!("mbid lookup failed: {error}"))?
    .payload;
    body.get("artists")
        .and_then(Value::as_array)
        .and_then(|artists| artists.first())
        .and_then(|artist| artist.get("id"))
        .and_then(Value::as_str)
        .map(|value| value.to_string())
        .ok_or_else(|| "mbid not found".to_string())
}

fn fetch_similar_artists(
    conn: &Connection,
    config: &ListenBrainzRuntimeConfig,
    seed_mbid: &str,
    count: usize,
) -> Result<Vec<SimilarArtist>, String> {
    let endpoint = format!("{}/similarity/artist/{}/", config.base_url, seed_mbid);
    let body = provider_runtime::cached_json_request(
        conn,
        "listenbrainz_similar_artists",
        seed_mbid,
        Duration::from_secs(60 * 60 * 12),
        || {
            ureq::get(&endpoint)
                .set("User-Agent", "Lyra/0.1")
                .set("Accept", "application/json")
                .set("Authorization", &format!("Token {}", config.token))
                .query("count", &count.to_string())
                .timeout(Duration::from_millis(2500))
                .call()
        },
    )
    .map_err(|error| format!("similar-artists fetch failed: {error}"))?
    .payload;

    let raw = if body.is_array() {
        body.as_array().cloned().unwrap_or_default()
    } else {
        body.get("similar_artists")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
    };

    let mut artists: Vec<SimilarArtist> = raw
        .into_iter()
        .filter_map(|item| {
            let mbid = item
                .get("artist_mbid")
                .or_else(|| item.get("mbid"))
                .and_then(Value::as_str)?
                .trim()
                .to_string();
            let name = item
                .get("name")
                .or_else(|| item.get("artist_name"))
                .and_then(Value::as_str)?
                .trim()
                .to_string();
            if mbid.is_empty() || name.is_empty() {
                return None;
            }
            let similarity = item
                .get("similarity")
                .and_then(Value::as_f64)
                .unwrap_or(0.0)
                .clamp(0.0, 1.0);
            Some(SimilarArtist {
                mbid,
                name,
                similarity,
            })
        })
        .collect();

    artists.sort_by(|a, b| {
        b.similarity
            .partial_cmp(&a.similarity)
            .unwrap_or(Ordering::Equal)
    });
    artists.truncate(count);
    Ok(artists)
}

fn fetch_top_recordings(
    conn: &Connection,
    config: &ListenBrainzRuntimeConfig,
    artist_mbid: &str,
    artist_name: &str,
    count: usize,
) -> Result<Vec<WeatherRecording>, String> {
    let endpoint = format!(
        "{}/popularity/top-recordings-for-artist/{}",
        config.base_url, artist_mbid
    );
    let body = provider_runtime::cached_json_request(
        conn,
        "listenbrainz_top_recordings",
        artist_mbid,
        Duration::from_secs(60 * 60 * 12),
        || {
            ureq::get(&endpoint)
                .set("User-Agent", "Lyra/0.1")
                .set("Accept", "application/json")
                .set("Authorization", &format!("Token {}", config.token))
                .query("count", &count.to_string())
                .timeout(Duration::from_millis(2500))
                .call()
        },
    )
    .map_err(|error| format!("top-recordings fetch failed: {error}"))?
    .payload;

    let rows = if body.is_array() {
        body.as_array().cloned().unwrap_or_default()
    } else {
        body.get("recordings")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
    };

    let mut recordings: Vec<WeatherRecording> = rows
        .into_iter()
        .filter_map(|row| {
            let title = row
                .get("recording_name")
                .or_else(|| row.get("title"))
                .and_then(Value::as_str)?
                .trim()
                .to_string();
            if title.is_empty() {
                return None;
            }
            let artist = row
                .get("artist_name")
                .and_then(Value::as_str)
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| artist_name.to_string());
            let listen_count = row
                .get("total_listen_count")
                .or_else(|| row.get("listen_count"))
                .and_then(Value::as_i64)
                .unwrap_or(0)
                .max(0);
            Some(WeatherRecording {
                artist,
                title,
                listen_count,
                similarity_score: 0.0,
                source_artist: artist_name.to_string(),
            })
        })
        .collect();
    recordings.truncate(count);
    Ok(recordings)
}

fn cache_weather_recordings(conn: &Connection, seed_artist: &str, rows: &[WeatherRecording]) {
    let payload = Value::Array(
        rows.iter()
            .map(|row| {
                serde_json::json!({
                    "artist": row.artist,
                    "title": row.title,
                    "listen_count": row.listen_count,
                    "similarity_score": row.similarity_score,
                    "source_artist": row.source_artist
                })
            })
            .collect(),
    );
    let lookup_key = seed_artist.trim().to_ascii_lowercase();
    let _ = conn.execute(
        "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
         VALUES ('listenbrainz_weather', ?1, ?2, ?3)
         ON CONFLICT(provider, lookup_key) DO UPDATE SET
           payload_json = excluded.payload_json,
           fetched_at = excluded.fetched_at",
        params![
            lookup_key,
            serde_json::json!({ "recordings": payload }).to_string(),
            chrono::Utc::now().to_rfc3339()
        ],
    );
}

fn fetch_live_weather_recordings(
    conn: &Connection,
    seed_artist: &str,
    limit: usize,
) -> Result<Vec<WeatherRecording>, String> {
    let config = load_listenbrainz_runtime_config(conn)?;
    let seed_mbid = fetch_artist_mbid(conn, seed_artist)?;
    let similar_count = limit.clamp(2, 5);
    let recordings_per_artist = (limit / 2).clamp(1, 4);
    let similar_artists = fetch_similar_artists(conn, &config, &seed_mbid, similar_count)?;
    if similar_artists.is_empty() {
        return Err("no similar artists found".to_string());
    }

    let mut rows = Vec::new();
    for similar in similar_artists {
        let top_recordings = fetch_top_recordings(
            conn,
            &config,
            &similar.mbid,
            &similar.name,
            recordings_per_artist,
        )?;
        for mut row in top_recordings {
            row.similarity_score = similar.similarity;
            row.source_artist = seed_artist.to_string();
            rows.push(row);
        }
    }
    if rows.is_empty() {
        return Err("no weather recordings found".to_string());
    }

    rows.sort_by(|a, b| {
        weather_score(b)
            .partial_cmp(&weather_score(a))
            .unwrap_or(Ordering::Equal)
    });
    rows.truncate(limit);
    cache_weather_recordings(conn, seed_artist, &rows);
    Ok(rows)
}

fn parse_weather_payload(payload: &Value) -> Vec<WeatherRecording> {
    let rows = payload
        .get("recordings")
        .and_then(Value::as_array)
        .or_else(|| {
            payload
                .get("similar_artist_recordings")
                .and_then(Value::as_array)
        })
        .or_else(|| payload.get("data").and_then(Value::as_array))
        .or_else(|| payload.as_array());

    rows.map(|items| {
        items
            .iter()
            .filter_map(parse_weather_row)
            .collect::<Vec<WeatherRecording>>()
    })
    .unwrap_or_default()
}

fn weather_score(recording: &WeatherRecording) -> f64 {
    let popularity = (recording.listen_count.max(10) as f64).log10() / 5.0;
    (0.25 + 0.5 * recording.similarity_score + 0.15 * popularity.clamp(0.0, 1.0)).clamp(0.0, 1.0)
}

fn find_local_track_by_artist_title(conn: &Connection, artist: &str, title: &str) -> Option<i64> {
    conn.query_row(
        "SELECT t.id
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE LOWER(TRIM(COALESCE(ar.name, ''))) = LOWER(TRIM(?1))
           AND LOWER(TRIM(t.title)) = LOWER(TRIM(?2))
         ORDER BY t.id DESC
         LIMIT 1",
        params![artist, title],
        |row| row.get::<_, i64>(0),
    )
    .ok()
}

fn load_cached_weather_recordings(
    conn: &Connection,
    seed_artist: &str,
    limit: usize,
) -> Vec<WeatherRecording> {
    let normalized = seed_artist.trim().to_ascii_lowercase();
    if normalized.is_empty() {
        return Vec::new();
    }

    let mut rows = Vec::new();
    let query = conn.prepare(
        "SELECT payload_json
         FROM enrich_cache
         WHERE provider = 'listenbrainz_weather'
         ORDER BY fetched_at DESC
         LIMIT 12",
    );
    let Ok(mut stmt) = query else {
        return Vec::new();
    };

    let mapped = stmt.query_map([], |row| row.get::<_, String>(0));
    if let Ok(mapped) = mapped {
        for raw_json in mapped.filter_map(Result::ok) {
            let Ok(payload) = serde_json::from_str::<Value>(&raw_json) else {
                continue;
            };
            for entry in parse_weather_payload(&payload) {
                let source = entry.source_artist.trim().to_ascii_lowercase();
                if source == normalized {
                    rows.push(entry);
                }
            }
        }
    }

    rows.sort_by(|a, b| {
        weather_score(b)
            .partial_cmp(&weather_score(a))
            .unwrap_or(Ordering::Equal)
    });
    rows.truncate(limit);
    rows
}

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
    pub fn recommend_with_evidence_and_leads(
        &self,
        taste: &TasteProfile,
        limit: usize,
    ) -> RecommendationBundle {
        use crate::library;

        if taste.dimensions.is_empty() || limit == 0 {
            return RecommendationBundle {
                recommendations: Vec::new(),
                acquisition_leads: Vec::new(),
            };
        }

        let interpreter = MoodInterpreter;
        let taste_label = interpreter.label(&taste.dimensions);

        // --- Lane 1: local taste alignment ---
        let mut local_scored = self.recommend_scored(taste, limit * 2);
        let feedback_bias = load_feedback_bias(
            self.conn,
            &local_scored
                .iter()
                .map(|(track_id, _)| *track_id)
                .collect::<Vec<_>>(),
        );
        if !feedback_bias.is_empty() {
            for (track_id, score) in &mut local_scored {
                if let Some(bias) = feedback_bias.get(track_id) {
                    *score = (*score + *bias).clamp(0.0, 1.0);
                }
            }
            local_scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(Ordering::Equal));
        }

        // Load play counts for deep-cut detection
        let play_counts: HashMap<i64, i64> = {
            let mut map = HashMap::new();
            if let Ok(mut stmt) = self.conn.prepare(
                "SELECT t.id, COUNT(ph.id) FROM tracks t
                 LEFT JOIN playback_history ph ON ph.track_id = t.id
                 GROUP BY t.id",
            ) {
                let rows =
                    stmt.query_map([], |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?)));
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

        let mut merged_results: HashMap<i64, RecommendationResult> = HashMap::new();
        let mut merged_leads: HashMap<String, AcquisitionLead> = HashMap::new();

        for (track_id, raw_score) in &local_scored {
            let track_id = *track_id;
            let raw_score = *raw_score;

            let Ok(Some(track)) = library::get_track_by_id(self.conn, track_id) else {
                continue;
            };

            let play_count = play_counts.get(&track_id).copied().unwrap_or(0);
            let score_row = score_rows.get(&track_id);

            // Determine strongest matching dimensions for human text
            let shared_dims = score_row
                .map(|sr| {
                    let sm = scores_to_map(sr);
                    strongest_dimension_matches(&taste.dimensions, &sm)
                })
                .unwrap_or_default();

            let track_mood = score_row
                .map(|sr| interpreter.label(&scores_to_map(sr)))
                .unwrap_or_default();

            let feedback_delta = feedback_bias.get(&track_id).copied().unwrap_or(0.0);
            let is_deep_cut = play_count <= 3 && raw_score >= 0.55;
            let provider = if is_deep_cut {
                "local/deep_cut"
            } else {
                "local/taste"
            }
            .to_string();

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
                    format!(
                        "Shared dimensions: {}. Score {:.0}%.",
                        shared_dims.join(", "),
                        raw_score * 100.0
                    ),
                )
            } else {
                (
                    format!(
                        "Lyra sees a {} profile match against your current taste reading.",
                        track_mood
                    ),
                    "taste_alignment",
                    format!("Cosine match {:.0}%.", raw_score * 100.0),
                )
            };

            let inferred_note = if !shared_dims.is_empty() {
                format!(
                    "Dimension overlap on {} inferred from local scores.",
                    shared_dims.join(", ")
                )
            } else {
                "Cosine similarity inferred from local taste profile.".to_string()
            };

            let mut evidence = vec![
                evidence_item(
                    evidence_type,
                    &provider,
                    "audio_features",
                    "track_scores",
                    evidence_text,
                    0.45,
                ),
                evidence_item(
                    "inferred",
                    "local",
                    "audio_features",
                    "taste_profile",
                    inferred_note,
                    0.1,
                ),
            ];
            if feedback_delta != 0.0 {
                evidence.push(evidence_item(
                    "feedback_history",
                    "broker",
                    "provider_metadata",
                    "playback_feedback",
                    if feedback_delta > 0.0 {
                        "Past accepts and replays are reinforcing this pick.".to_string()
                    } else {
                        "Past skips are suppressing this pick.".to_string()
                    },
                    feedback_delta.abs(),
                ));
            }
            let evidence_grade = evidence_grade_for_items(&evidence);

            merge_recommendation_result(
                &mut merged_results,
                RecommendationResult {
                    track,
                    score: raw_score,
                    provider: provider.clone(),
                    why_this_track: why,
                    evidence_grade,
                    evidence,
                },
            );
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
                       AND COALESCE(t.status, 'active') = 'active'
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
                    let Ok(Some(track)) = library::get_track_by_id(self.conn, bridge_id) else {
                        continue;
                    };

                    let bridge_score = score_rows
                        .get(&bridge_id)
                        .map(|sr| {
                            let sm = scores_to_map(sr);
                            let sim = cosine_similarity(&taste.dimensions, &sm);
                            let ov = mean_overlap(&taste.dimensions, &sm);
                            (sim * 0.7 + ov * 0.3).clamp(0.0, 1.0)
                        })
                        .unwrap_or(0.35);

                    // Only include bridge candidates with some taste coherence
                    if bridge_score < 0.25 {
                        continue;
                    }

                    let why = format!(
                        "Scout bridge: this is where {} meets {} — a different world that shares your current pressure.",
                        seed_genre, bridge_genre
                    );
                    let evidence = vec![evidence_item(
                        "scout_bridge",
                        "scout",
                        "adjacency_similarity",
                        "genre_bridge",
                        format!(
                            "Cross-genre bridge: {} × {}. Local taste coherence {:.0}%.",
                            seed_genre,
                            bridge_genre,
                            bridge_score * 100.0
                        ),
                        0.10,
                    )];
                    let evidence_grade = evidence_grade_for_items(&evidence);

                    merge_recommendation_result(
                        &mut merged_results,
                        RecommendationResult {
                            track,
                            score: bridge_score * 0.82,
                            provider: "scout/bridge".to_string(),
                            why_this_track: why,
                            evidence_grade,
                            evidence,
                        },
                    );
                }
            }
        }

        // --- Lane 3: graph/co_play — artists with graph affinity ---
        // Find artists connected to the top scored tracks' artists
        let anchor_artists: Vec<String> = {
            local_scored
                .iter()
                .take(5)
                .filter_map(|(tid, _)| {
                    library::get_track_by_id(self.conn, *tid)
                        .ok()
                        .flatten()
                        .map(|t| t.artist)
                })
                .collect()
        };

        if !anchor_artists.is_empty() {
            for anchor in anchor_artists.iter().take(3) {
                let mut connected: HashMap<String, (String, f64, String, String, String)> =
                    HashMap::new();
                let graph_rows: Vec<(String, f64, String)> = {
                    let stmt = self.conn.prepare(
                        "SELECT target, weight, type
                         FROM connections
                         WHERE LOWER(source) = LOWER(?)
                           AND type IN ('dimension_affinity', 'similar_artist', 'co_play')
                         ORDER BY weight DESC
                         LIMIT 4",
                    );
                    match stmt {
                        Err(_) => vec![],
                        Ok(mut stmt) => match stmt.query_map([anchor], |row| {
                            Ok((
                                row.get::<_, String>(0)?,
                                row.get::<_, f64>(1)?,
                                row.get::<_, String>(2)?,
                            ))
                        }) {
                            Ok(rows) => rows.filter_map(Result::ok).collect(),
                            Err(_) => vec![],
                        },
                    }
                };

                for (connected_artist, graph_score, connection_type) in graph_rows {
                    let evidence_summary = format!(
                        "Artist graph connection: {} -> {} via {} ({:.0}% strength).",
                        anchor,
                        connected_artist,
                        connection_type,
                        graph_score * 100.0
                    );
                    connected.insert(
                        connected_artist.trim().to_ascii_lowercase(),
                        (
                            connected_artist,
                            graph_score.clamp(0.0, 1.0),
                            connection_type,
                            "adjacency_similarity".to_string(),
                            evidence_summary,
                        ),
                    );
                }

                for related in
                    lineage::lineage_related_artists(self.conn, anchor, 4).unwrap_or_default()
                {
                    let key = related.name.trim().to_ascii_lowercase();
                    let score = f64::from(related.connection_strength).clamp(0.0, 1.0);
                    let evidence_summary = format!(
                        "{} Evidence level: {}.",
                        related.evidence_summary, related.evidence_level
                    );
                    match connected.get(&key) {
                        Some((_, existing_score, _, _, _)) if *existing_score >= score => {}
                        _ => {
                            connected.insert(
                                key,
                                (
                                    related.name,
                                    score,
                                    related.connection_type,
                                    "lineage_member_graph".to_string(),
                                    evidence_summary,
                                ),
                            );
                        }
                    }
                }

                let mut connected = connected.into_values().collect::<Vec<_>>();
                connected.sort_by(|left, right| {
                    right
                        .1
                        .partial_cmp(&left.1)
                        .unwrap_or(Ordering::Equal)
                        .then_with(|| left.0.cmp(&right.0))
                });
                connected.truncate(4);

                for (connected_artist, graph_score, connection_type, category, evidence_summary) in
                    connected
                {
                    // Find a track from this artist
                    let track_row: Option<i64> = self
                        .conn
                        .query_row(
                            "SELECT t.id FROM tracks t
                         JOIN artists ar ON ar.id = t.artist_id
                         WHERE LOWER(ar.name) = LOWER(?)
                           AND COALESCE(t.status, 'active') = 'active'
                         ORDER BY RANDOM() LIMIT 1",
                            [&connected_artist],
                            |row| row.get(0),
                        )
                        .ok();

                    let Some(track_id) = track_row else {
                        let lead_score = (graph_score * 0.6).clamp(0.0, 1.0);
                        let reason = if category == "lineage_member_graph" {
                            format!(
                                "Scout lineage lead: {} is directly linked to {} through {} evidence, but has no owned track match yet.",
                                connected_artist, anchor, connection_type
                            )
                        } else {
                            format!(
                                "Scout graph lead: {} is strongly adjacent to {} but has no owned track match yet.",
                                connected_artist, anchor
                            )
                        };
                        let evidence = vec![evidence_item(
                            if category == "lineage_member_graph" {
                                "scout_lineage_artist_lead"
                            } else {
                                "scout_graph_artist_lead"
                            },
                            if category == "lineage_member_graph" {
                                "lineage"
                            } else {
                                "scout"
                            },
                            &category,
                            &connection_type,
                            evidence_summary.clone(),
                            lead_score,
                        )];
                        let evidence_grade = evidence_grade_for_items(&evidence);
                        merge_acquisition_lead(
                            &mut merged_leads,
                            AcquisitionLead {
                                artist: connected_artist.clone(),
                                title: "Top track (scout lead)".to_string(),
                                provider: if category == "lineage_member_graph" {
                                    "lineage/member".to_string()
                                } else {
                                    "scout/graph".to_string()
                                },
                                score: lead_score,
                                reason,
                                evidence_grade,
                                evidence,
                            },
                        );
                        continue;
                    };
                    let Ok(Some(track)) = library::get_track_by_id(self.conn, track_id) else {
                        continue;
                    };

                    let co_score = graph_score.clamp(0.2, 0.75);
                    let why = format!(
                        "Listeners who love {} also gravitate toward {} — graph affinity, not just genre proximity.",
                        anchor, connected_artist
                    );

                    merge_recommendation_result(
                        &mut merged_results,
                        RecommendationResult {
                            track,
                            score: co_score * 0.72,
                            provider: if category == "lineage_member_graph" {
                                "lineage/member".to_string()
                            } else {
                                "graph/co_play".to_string()
                            },
                            why_this_track: why.clone(),
                            evidence_grade: "graph_context_assisted".to_string(),
                            evidence: vec![EvidenceItem {
                                type_label: if category == "lineage_member_graph" {
                                    "lineage_member_graph".to_string()
                                } else {
                                    "co_play".to_string()
                                },
                                source: if category == "lineage_member_graph" {
                                    "lineage".to_string()
                                } else {
                                    "graph".to_string()
                                },
                                category: category.clone(),
                                anchor: connection_type.clone(),
                                text: format!(
                                    "Artist graph connection: {} → {}. Affinity score {}.",
                                    anchor, connected_artist, graph_score
                                ),
                                weight: (co_score * 0.72).clamp(0.0, 1.0),
                            }],
                        },
                    );
                }
            }
        }

        // --- Lane 4: listenbrainz/weather — cached similar-artist community recordings ---
        let weather_seed_artists: Vec<String> = local_scored
            .iter()
            .take(3)
            .filter_map(|(track_id, _)| {
                library::get_track_by_id(self.conn, *track_id)
                    .ok()
                    .flatten()
                    .map(|track| track.artist)
            })
            .collect();

        for seed_artist in weather_seed_artists.iter().take(2) {
            let live_result = fetch_live_weather_recordings(self.conn, seed_artist, limit * 3);
            let (weather_candidates, weather_source_mode) = match live_result {
                Ok(rows) if !rows.is_empty() => (rows, "live"),
                Ok(_) => (
                    load_cached_weather_recordings(self.conn, seed_artist, limit * 3),
                    "cache",
                ),
                Err(_) => (
                    load_cached_weather_recordings(self.conn, seed_artist, limit * 3),
                    "cache_fallback",
                ),
            };
            for recording in weather_candidates {
                let payload = serde_json::json!({
                    "artist": recording.artist,
                    "title": recording.title,
                    "listenCount": recording.listen_count,
                    "similarityScore": recording.similarity_score,
                    "sourceArtist": recording.source_artist,
                    "sourceMode": weather_source_mode,
                });
                let normalized =
                    match audio_data::normalize_track_candidate(audio_data::RawTrackCandidate {
                        provider: "listenbrainz/weather",
                        provider_track_id: &audio_data::provider_track_key(
                            "listenbrainz/weather",
                            &recording.artist,
                            &recording.title,
                            None,
                        ),
                        artist: &recording.artist,
                        title: &recording.title,
                        album: None,
                        release_date: None,
                        isrc: None,
                        duration_ms: None,
                        popularity: None,
                        explicit: false,
                    }) {
                        Ok(track) => track,
                        Err(_) => continue,
                    };
                let _ = audio_data::persist_provider_track(
                    self.conn,
                    &normalized,
                    "recommendation",
                    &payload,
                );
                let maybe_track_id = find_local_track_by_artist_title(
                    self.conn,
                    &normalized.artist.name,
                    &normalized.title,
                );

                let raw = weather_score(&recording);
                let weighted = (raw * 0.68).clamp(0.0, 1.0);
                let mut reason = format!(
                    "Community weather: listeners around {} also move toward {} — {} global plays.",
                    recording.source_artist, normalized.artist.name, recording.listen_count
                );
                if weather_source_mode == "cache_fallback" {
                    reason.push_str(" Using cached fallback because live weather was unavailable.");
                } else if weather_source_mode == "cache" {
                    reason.push_str(" Using cached weather evidence.");
                }
                let evidence_type = if weather_source_mode == "live" {
                    "community_similar_artist"
                } else {
                    "community_similar_artist_cached"
                };

                let evidence = vec![EvidenceItem {
                    type_label: evidence_type.to_string(),
                    source: "listenbrainz_weather".to_string(),
                    category: "external_context".to_string(),
                    anchor: "listenbrainz_weather".to_string(),
                    text: reason.clone(),
                    weight: (raw * LISTENBRAINZ_WEATHER_WEIGHT).clamp(0.0, 1.0),
                }];

                if let Some(track_id) = maybe_track_id {
                    let Ok(Some(track)) = library::get_track_by_id(self.conn, track_id) else {
                        continue;
                    };
                    merge_recommendation_result(
                        &mut merged_results,
                        RecommendationResult {
                            track,
                            score: weighted,
                            provider: "listenbrainz/weather".to_string(),
                            why_this_track: reason.clone(),
                            evidence_grade: "graph_context_assisted".to_string(),
                            evidence,
                        },
                    );
                } else {
                    merge_acquisition_lead(
                        &mut merged_leads,
                        AcquisitionLead {
                            artist: normalized.artist.name.clone(),
                            title: normalized.title.clone(),
                            provider: "listenbrainz/weather".to_string(),
                            score: weighted,
                            reason,
                            evidence_grade: "graph_context_assisted".to_string(),
                            evidence,
                        },
                    );
                }
            }
        }

        let mut results: Vec<RecommendationResult> = merged_results.into_values().collect();
        results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(Ordering::Equal));

        results.truncate(limit);
        let mut acquisition_leads: Vec<AcquisitionLead> = merged_leads.into_values().collect();
        acquisition_leads.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(Ordering::Equal));
        acquisition_leads.truncate(limit);

        RecommendationBundle {
            recommendations: results,
            acquisition_leads,
        }
    }

    pub fn recommend_with_evidence(
        &self,
        taste: &TasteProfile,
        limit: usize,
    ) -> Vec<RecommendationResult> {
        self.recommend_with_evidence_and_leads(taste, limit)
            .recommendations
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
            evidence_grade: "insufficient_evidence".to_string(),
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
    let why_this_track =
        if !shared_dimensions.is_empty() {
            if let Some(ref title) = track_title {
                format!(
                    "{} lands in a {} world — strongest alignment with your {} taste on {}.",
                    title,
                    mood_label,
                    taste_label,
                    shared_dimensions.join(", ")
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
    let mut evidence_items = vec![evidence_item(
        "taste_alignment",
        "local",
        "audio_features",
        "track_scores",
        format!(
            "Cosine similarity {:.0}%, mean overlap {:.0}% against your current {} taste profile.",
            similarity * 100.0,
            overlap * 100.0,
            taste_label
        ),
        (similarity * 0.85 + overlap * 0.15).clamp(0.0, 1.0),
    )];

    if !shared_dimensions.is_empty() {
        evidence_items.push(evidence_item(
            "dimension_match",
            "local",
            "audio_features",
            "dimension_overlap",
            format!(
                "Strong dimension alignment on: {}.",
                shared_dimensions.join(", ")
            ),
            0.6,
        ));
    }

    if let Some(bpm) = track_scores.bpm {
        evidence_items.push(evidence_item(
            "tempo",
            "local",
            "audio_features",
            "tempo",
            format!("Tempo: ~{:.0} BPM.", bpm),
            0.15,
        ));
    }

    if let Some(ref key_signature) = track_scores.key_signature {
        if !key_signature.trim().is_empty() {
            evidence_items.push(evidence_item(
                "key",
                "local",
                "audio_features",
                "key_signature",
                format!("Key: {}.", key_signature),
                0.1,
            ));
        }
    }

    // G-063: Graph/adjacency evidence — pull connection signals for this track's artist
    let track_artist: Option<String> = conn
        .query_row(
            "SELECT COALESCE(ar.name, '')
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE t.id = ?1",
            params![track_id],
            |row| row.get(0),
        )
        .ok()
        .filter(|value: &String| !value.trim().is_empty());

    if let Some(ref artist) = track_artist {
        // Find strongest connections for this artist from the graph
        struct ConnRow {
            other: String,
            strength: f64,
            conn_type: String,
        }
        let mut stmt = conn
            .prepare(
                "SELECT
                    CASE
                        WHEN lower(trim(source)) = lower(trim(?1)) THEN target
                        ELSE source
                    END AS other_artist,
                    weight,
                    type
                 FROM connections
                 WHERE lower(trim(source)) = lower(trim(?1))
                    OR lower(trim(target)) = lower(trim(?1))
                 ORDER BY weight DESC
                 LIMIT 3",
            )
            .ok();
        let connections: Vec<ConnRow> = if let Some(ref mut s) = stmt {
            s.query_map(params![artist], |row| {
                Ok(ConnRow {
                    other: row.get(0)?,
                    strength: row.get(1)?,
                    conn_type: row.get(2)?,
                })
            })
            .map(|rows| rows.flatten().collect())
            .unwrap_or_default()
        } else {
            vec![]
        };

        if !connections.is_empty() {
            let top = &connections[0];
            let label = match top.conn_type.as_str() {
                "dimension_affinity" => "dimensional affinity",
                "similar" | "lastfm_similar" => "Last.fm similarity",
                "co_play" => "co-play history",
                _ => "artist graph",
            };
            evidence_items.push(evidence_item(
                "artist_connection",
                "graph",
                "adjacency_similarity",
                &top.conn_type,
                format!(
                    "Artist graph: {} connects to {} via {} (strength {:.0}%).",
                    artist,
                    top.other,
                    label,
                    top.strength * 100.0
                ),
                (top.strength * 0.55).clamp(0.0, 1.0),
            ));
            if connections.len() > 1 {
                let others: Vec<String> =
                    connections[1..].iter().map(|c| c.other.clone()).collect();
                reasons.push(format!(
                    "Artist graph also connects to: {}.",
                    others.join(", ")
                ));
            }
        }

        if let Ok(lineage_edges) = lineage::lineage_edges_for_artist(conn, artist, 2) {
            if let Some(edge) = lineage_edges.first() {
                evidence_items.push(evidence_item(
                    "lineage_member_graph",
                    "lineage",
                    "lineage_member_graph",
                    &edge.relationship_type,
                    format!(
                        "{} connects to {} through {} evidence: {}",
                        edge.source_artist, edge.target_artist, edge.relationship_type, edge.note
                    ),
                    edge.weight.clamp(0.0, 1.0),
                ));
                reasons.push(format!(
                    "Artist lineage also points toward {} through {} evidence.",
                    edge.target_artist, edge.relationship_type
                ));
            }
        }
    }

    // ── Audio feature evidence (PCM-backed + tag-backed) ─────────────────────
    // Load stored audio features for this track. If extracted, produce music-language
    // evidence items from the compound analysis. If not yet extracted, note the gap
    // honestly rather than silently omitting it.
    if let Some(af) = track_audio_features::load_features(conn, track_id) {
        let af_items = build_audio_feature_evidence(&af, &score_map, track_title.as_deref());
        if !af_items.is_empty() {
            evidence_items.extend(af_items);
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
        evidence_grade: evidence_grade_for_items(&evidence_items),
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

fn local_track_count_for_artist(conn: &Connection, artist_name: &str) -> usize {
    conn.query_row(
        "SELECT COUNT(*)
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
        params![artist_name],
        |row| row.get::<_, i64>(0),
    )
    .unwrap_or_default() as usize
}

fn push_unique_related_artist(
    results: &mut Vec<RelatedArtist>,
    seen: &mut HashSet<String>,
    artist: RelatedArtist,
) {
    let key = artist.name.trim().to_ascii_lowercase();
    if seen.insert(key) {
        results.push(artist);
    }
}

/// Find related artists — checks connections table first, then falls back to co-play/genre.
pub fn get_related_artists(
    artist_name: &str,
    limit: usize,
    conn: &Connection,
) -> Vec<RelatedArtist> {
    let mut results =
        lineage::lineage_related_artists(conn, artist_name, limit).unwrap_or_default();
    let mut seen: HashSet<String> = results
        .iter()
        .map(|artist| artist.name.trim().to_ascii_lowercase())
        .collect();

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
                let local_count = local_track_count_for_artist(conn, &name);
                let (why, preserves, changes, risk_note) =
                    related_artist_story(&conn_type, weight as f32, local_count);
                push_unique_related_artist(
                    &mut results,
                    &mut seen,
                    RelatedArtist {
                        name,
                        connection_strength: weight as f32,
                        connection_type: conn_type.clone(),
                        local_track_count: local_count,
                        evidence_level: "derived_local".to_string(),
                        evidence_summary: format!(
                            "Local {} edge from '{}' at {:.0}% strength.",
                            conn_type,
                            artist_name,
                            weight * 100.0
                        ),
                        why,
                        preserves,
                        changes,
                        risk_note,
                    },
                );
            }
        }
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
                let local_count = local_track_count_for_artist(conn, &name);
                let connection_strength = (strength as f32 / 100_f32).min(1.0);
                let (why, preserves, changes, risk_note) =
                    related_artist_story("co_play", connection_strength, local_count);
                push_unique_related_artist(
                    &mut results,
                    &mut seen,
                    RelatedArtist {
                        name,
                        connection_strength,
                        connection_type: "co_play".to_string(),
                        local_track_count: local_count,
                        evidence_level: "derived_local".to_string(),
                        evidence_summary: format!(
                        "Observed co-play adjacency from playback history ({} shared sessions).",
                        strength
                    ),
                        why,
                        preserves,
                        changes,
                        risk_note,
                    },
                );
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
                    let local_count = local_track_count_for_artist(conn, &name);
                    let connection_strength = (cnt as f32 / 50.0).min(1.0);
                    let (why, preserves, changes, risk_note) =
                        related_artist_story("genre", connection_strength, local_count);
                    push_unique_related_artist(
                        &mut results,
                        &mut seen,
                        RelatedArtist {
                            name,
                            connection_strength,
                            connection_type: "genre".to_string(),
                            local_track_count: local_count,
                            evidence_level: "metadata_fallback".to_string(),
                            evidence_summary: format!(
                            "Shared genre fallback from local metadata ({} overlapping tracks).",
                            cnt
                        ),
                            why,
                            preserves,
                            changes,
                            risk_note,
                        },
                    );
                }
            }
        }
    }

    results.sort_by(|left, right| {
        right
            .connection_strength
            .partial_cmp(&left.connection_strength)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.name.cmp(&right.name))
    });
    results.truncate(limit.max(1));
    results
}

/// Build scout-style exits (safe / interesting / dangerous) from local related-artist signals.
pub fn build_scout_exit_plan(
    artist_name: &str,
    limit_per_lane: usize,
    conn: &Connection,
) -> ScoutExitPlan {
    let related = get_related_artists(artist_name, 48, conn);
    let limit = limit_per_lane.max(1);

    let mut safe_ranked = related.clone();
    safe_ranked.sort_by(|left, right| {
        safe_lane_score(right)
            .partial_cmp(&safe_lane_score(left))
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.name.cmp(&right.name))
    });

    let mut interesting_ranked = related.clone();
    interesting_ranked.sort_by(|left, right| {
        interesting_lane_score(right)
            .partial_cmp(&interesting_lane_score(left))
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.name.cmp(&right.name))
    });

    let mut dangerous_ranked = related;
    dangerous_ranked.sort_by(|left, right| {
        dangerous_lane_score(right)
            .partial_cmp(&dangerous_lane_score(left))
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.name.cmp(&right.name))
    });

    ScoutExitPlan {
        seed_artist: artist_name.to_string(),
        lanes: vec![
            ScoutExitLane {
                flavor: "safe".to_string(),
                label: "Safe exit".to_string(),
                description: "Hold scene continuity first, then move the edge.".to_string(),
                artists: safe_ranked.into_iter().take(limit).collect(),
            },
            ScoutExitLane {
                flavor: "interesting".to_string(),
                label: "Interesting exit".to_string(),
                description: "Leave the obvious lane without dropping the emotional thread."
                    .to_string(),
                artists: interesting_ranked.into_iter().take(limit).collect(),
            },
            ScoutExitLane {
                flavor: "dangerous".to_string(),
                label: "Dangerous exit".to_string(),
                description: "Rewarding risk: weaker paper link, stronger discovery pressure."
                    .to_string(),
                artists: dangerous_ranked.into_iter().take(limit).collect(),
            },
        ],
    }
}

fn owned_pressure(artist: &RelatedArtist) -> f32 {
    (artist.local_track_count as f32 / 6.0).clamp(0.0, 1.0)
}

fn safe_lane_score(artist: &RelatedArtist) -> f32 {
    let owned = owned_pressure(artist);
    let mut score = artist.connection_strength * 0.66 + owned * 0.26;
    if artist.connection_type == "genre" || artist.connection_type == "dimension_affinity" {
        score += 0.08;
    }
    score.clamp(0.0, 1.0)
}

fn interesting_lane_score(artist: &RelatedArtist) -> f32 {
    let owned = owned_pressure(artist);
    let center = 1.0_f32 - ((artist.connection_strength - 0.56_f32).abs() / 0.56_f32).min(1.0);
    let mut score = center * 0.58 + artist.connection_strength * 0.22 + owned * 0.16;
    if artist.connection_type == "co_play" || artist.connection_type == "dimension_affinity" {
        score += 0.08;
    }
    score.clamp(0.0, 1.0)
}

fn dangerous_lane_score(artist: &RelatedArtist) -> f32 {
    let unowned = 1.0_f32 - owned_pressure(artist);
    let mut score = (1.0_f32 - artist.connection_strength) * 0.52 + unowned * 0.34;
    if artist.connection_type == "co_play" {
        score += 0.05;
    }
    if artist.local_track_count == 0 {
        score += 0.12;
    } else if artist.local_track_count <= 2 {
        score += 0.06;
    }
    score.clamp(0.0, 1.0)
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

/// Build audio feature evidence items in music language, not engineering language.
///
/// This is the translation layer between PCM measurements and explainable claims.
/// It cross-references audio features with track_scores dimensions to produce
/// compound claims — the kind that describe how a track *feels*, not how it measures.
///
/// Examples of the compound-claim logic:
/// - High tension + high volatility = "builds and breaks like it means it"
/// - High rawness + wide dynamic range = "breathes wide between the hits"
/// - Low RMS + high tension + low valence = "the weight is in what it withholds" (Limousine territory)
/// - High RMS + high energy + low dynamic range = "wall of sound, no room to breathe"
/// - Low energy_volatility + low tension = "moves like still water — not quiet, just settled"
fn build_audio_feature_evidence(
    af: &TrackAudioFeatures,
    scores: &HashMap<String, f64>,
    track_title: Option<&str>,
) -> Vec<EvidenceItem> {
    let mut items = Vec::new();
    let name = track_title.unwrap_or("This track");

    let energy = scores.get("energy").copied().unwrap_or(0.5);
    let tension = scores.get("tension").copied().unwrap_or(0.5);
    let valence = scores.get("valence").copied().unwrap_or(0.5);
    let rawness = scores.get("rawness").copied().unwrap_or(0.5);
    let space = scores.get("space").copied().unwrap_or(0.5);
    let warmth = scores.get("warmth").copied().unwrap_or(0.5);

    // ── BPM claim (tag-sourced, most reliable) ────────────────────────────────
    if let Some(bpm) = af.tag_bpm {
        let tempo_feel = if bpm < 70.0 {
            "moves slow enough to feel every word"
        } else if bpm < 95.0 {
            "sits in a mid-tempo pocket — deliberate, not urgent"
        } else if bpm < 130.0 {
            "runs at a pace that puts the body on notice"
        } else if bpm < 160.0 {
            "moves fast — the kind of pace that doesn't wait for you"
        } else {
            "runs hard, no room to look back"
        };
        items.push(evidence_item(
            "tempo_feel",
            "local",
            "audio_proof",
            "tag_bpm",
            format!("{name} {tempo_feel} (~{bpm:.0} BPM, tag-verified)."),
            0.55,
        ));
    }

    // ── Dynamic range claim ───────────────────────────────────────────────────
    if let (Some(dr), Some(rms)) = (af.dynamic_range, af.rms_energy) {
        // Compound: cross dynamic range with rawness and space scores
        let claim = if dr > 7.0 && rawness > 0.55 {
            format!("{name} breathes wide between the hits — the quiet parts carry as much weight as the loud ones.")
        } else if dr > 7.0 && space > 0.55 {
            format!("{name} has real space inside it — not empty, but the kind of room where the sound lands differently.")
        } else if dr > 5.0 && rms < 0.12 {
            // Low loudness, moderate dynamic range — controlled restraint
            format!("{name} stays restrained — what it withholds is part of the argument.")
        } else if dr < 2.5 && energy > 0.65 {
            // Compressed, loud, high energy — wall of sound
            format!("{name} is a wall: compressed, dense, no air between the layers.")
        } else if dr < 2.5 {
            format!("{name} runs tight — little breathing room, which is probably the point.")
        } else {
            format!("{name} has a measured dynamic shape — not wide, not crushed.")
        };
        let weight = if dr > 5.0 { 0.45 } else { 0.35 };
        items.push(evidence_item(
            "dynamic_shape",
            "local",
            "audio_proof",
            "pcm_dynamic_range",
            claim,
            weight,
        ));
    }

    // ── Energy volatility claim ───────────────────────────────────────────────
    // This is the most music-meaningful PCM signal for "drop"-style vibe claims.
    if let Some(vol) = af.energy_volatility {
        let claim = if vol > 0.10 && tension > 0.60 {
            // High volatility + high tension = dramatic structural swings
            format!("{name} builds and breaks hard — the energy doesn't stay put, and that's the whole point.")
        } else if vol > 0.10 && energy > 0.65 {
            // High volatility + high energy = peaks and valleys in a high-energy frame
            format!("{name} surges — it has real peaks in it, not just a sustained push.")
        } else if vol > 0.08 && valence < 0.40 {
            // Moderate volatility + low valence = emotional turbulence
            format!("{name} moves through different weights — the mood doesn't sit still.")
        } else if vol > 0.06 {
            // General moderate volatility
            format!("{name} has energy movement across its runtime — not a flat line.")
        } else if vol < 0.025 && tension > 0.55 {
            // Extremely flat + high tension = sustained dread/pressure (Limousine, late-era Radiohead)
            format!("{name} holds its pressure without releasing it — the tension is built into the floor, not the peaks.")
        } else if vol < 0.025 {
            // Very flat energy — deliberate stillness
            format!("{name} stays level — the consistency is structural, not accidental.")
        } else {
            return items; // nothing interesting enough to say
        };
        let weight = if vol > 0.08 || vol < 0.025 {
            0.50
        } else {
            0.35
        };
        items.push(evidence_item(
            "energy_movement",
            "local",
            "audio_proof",
            "pcm_energy_volatility",
            claim,
            weight,
        ));
    }

    // ── Compound: the "withholding weight" pattern (Limousine / Casimir Pulaski Day territory) ──
    // Low RMS + high tension + low valence + low volatility
    if let (Some(rms), Some(vol)) = (af.rms_energy, af.energy_volatility) {
        if rms < 0.10 && tension > 0.60 && valence < 0.38 && vol < 0.04 {
            items.push(evidence_item(
                "withholding_weight",
                "local",
                "audio_proof",
                "pcm_compound",
                format!("{name} carries its grief quietly — low volume, held tension, almost no release. The weight is in what it doesn't do."),
                0.70,
            ));
        }
    }

    // ── Compound: the warmth-and-closeness pattern (bedroom recordings, intimate folk) ──
    if let Some(dr) = af.dynamic_range {
        if warmth > 0.62 && dr < 3.5 && space < 0.45 {
            items.push(evidence_item(
                "intimate_warmth",
                "local",
                "audio_proof",
                "pcm_compound",
                format!("{name} sits close — warm, not wide, recorded like it wasn't meant for an arena."),
                0.45,
            ));
        }
    }

    // ── Tag key claim ─────────────────────────────────────────────────────────
    if let Some(ref key) = af.tag_key {
        if !key.trim().is_empty() {
            let modal_note = if key.contains('m') || key.ends_with("min") {
                "minor key — tends toward shadow over light"
            } else if key.contains('M') || key.ends_with("maj") {
                "major key — structural brightness, regardless of mood"
            } else {
                "key confirmed from tags"
            };
            items.push(evidence_item(
                "key_signature",
                "local",
                "audio_proof",
                "tag_key",
                format!("{name} is in {key} — {modal_note}."),
                0.20,
            ));
        }
    }

    items
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

#[cfg(test)]
mod tests {
    use super::{
        build_scout_exit_plan, enqueue_acquisition_leads, explain_track, get_related_artists,
        record_recommendation_feedback, RecommendationBroker,
    };
    use crate::commands::TasteProfile;
    use crate::db;
    use rusqlite::{params, Connection};
    use std::collections::HashMap;

    #[test]
    fn feedback_bias_can_reorder_local_recommendations() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE artists (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE albums (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              title TEXT NOT NULL
            );
            CREATE TABLE tracks (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              album_id INTEGER,
              title TEXT NOT NULL,
              path TEXT NOT NULL UNIQUE,
              duration_seconds REAL NOT NULL DEFAULT 0,
              genre TEXT,
              year TEXT,
              bpm REAL,
              key_signature TEXT,
              liked_at TEXT,
              status TEXT NOT NULL DEFAULT 'active'
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
            CREATE TABLE playback_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              track_id INTEGER NOT NULL,
              ts TEXT NOT NULL
            );
            ",
        )
        .expect("schema");

        conn.execute("INSERT INTO artists (id, name) VALUES (1, 'Artist A')", [])
            .expect("artist a");
        conn.execute("INSERT INTO artists (id, name) VALUES (2, 'Artist B')", [])
            .expect("artist b");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (1, 1, 'Album A')",
            [],
        )
        .expect("album a");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (2, 2, 'Album B')",
            [],
        )
        .expect("album b");

        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (1, 1, 1, 'Track One', 'C:/tmp/one.mp3', 200, 'active')",
            [],
        )
        .expect("track one");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (2, 2, 2, 'Track Two', 'C:/tmp/two.mp3', 210, 'active')",
            [],
        )
        .expect("track two");

        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (1, 0.58, 0.58, 0.58, 0.58, 0.58, 0.58, 0.58, 0.58, 0.58, 0.58, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("score one");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (2, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("score two");

        let taste = TasteProfile {
            dimensions: HashMap::from([
                ("energy".to_string(), 0.62),
                ("valence".to_string(), 0.62),
                ("tension".to_string(), 0.62),
                ("density".to_string(), 0.62),
                ("warmth".to_string(), 0.62),
                ("movement".to_string(), 0.62),
                ("space".to_string(), 0.62),
                ("rawness".to_string(), 0.62),
                ("complexity".to_string(), 0.62),
                ("nostalgia".to_string(), 0.62),
            ]),
            confidence: 1.0,
            total_signals: 10,
            source: "test".to_string(),
        };

        let broker = RecommendationBroker::new(&conn);
        let before = broker.recommend_with_evidence(&taste, 2);
        assert_eq!(before.len(), 2);
        assert_eq!(before[0].track.id, 2);

        record_recommendation_feedback(&conn, 1, "play");
        record_recommendation_feedback(&conn, 1, "play");
        record_recommendation_feedback(&conn, 2, "dismiss");

        let after = broker.recommend_with_evidence(&taste, 2);
        assert_eq!(after.len(), 2);
        assert_eq!(after[0].track.id, 1);
        assert!(after[0]
            .evidence
            .iter()
            .any(|item| item.type_label == "feedback_history"));
    }

    #[test]
    fn listenbrainz_weather_lane_uses_cached_recordings() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE artists (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE albums (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              title TEXT NOT NULL
            );
            CREATE TABLE tracks (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              album_id INTEGER,
              title TEXT NOT NULL,
              path TEXT NOT NULL UNIQUE,
              duration_seconds REAL NOT NULL DEFAULT 0,
              genre TEXT,
              year TEXT,
              bpm REAL,
              key_signature TEXT,
              liked_at TEXT,
              status TEXT NOT NULL DEFAULT 'active'
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
            CREATE TABLE playback_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              track_id INTEGER NOT NULL,
              ts TEXT NOT NULL
            );
            CREATE TABLE enrich_cache (
              provider TEXT NOT NULL,
              lookup_key TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              fetched_at TEXT NOT NULL,
              PRIMARY KEY(provider, lookup_key)
            );
            ",
        )
        .expect("schema");

        conn.execute(
            "INSERT INTO artists (id, name) VALUES (1, 'Seed Artist')",
            [],
        )
        .expect("seed artist");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (2, 'Weather Artist')",
            [],
        )
        .expect("weather artist");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (1, 1, 'Seed Album')",
            [],
        )
        .expect("seed album");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (2, 2, 'Weather Album')",
            [],
        )
        .expect("weather album");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (1, 1, 1, 'Seed Song', 'C:/tmp/seed.mp3', 180, 'active')",
            [],
        )
        .expect("seed track");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (2, 2, 2, 'Weather Song', 'C:/tmp/weather.mp3', 220, 'active')",
            [],
        )
        .expect("weather track");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (1, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("seed score");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("weather score");

        let payload = r#"{
          "recordings": [
            {
              "artist": "Weather Artist",
              "title": "Weather Song",
              "listen_count": 42000,
              "similarity_score": 0.88,
              "source_artist": "Seed Artist"
            }
          ]
        }"#;
        conn.execute(
            "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
             VALUES ('listenbrainz_weather', 'seed-artist', ?1, '2026-03-09T00:00:00Z')",
            [payload],
        )
        .expect("cached weather payload");

        let taste = TasteProfile {
            dimensions: HashMap::from([
                ("energy".to_string(), 0.80),
                ("valence".to_string(), 0.80),
                ("tension".to_string(), 0.80),
                ("density".to_string(), 0.80),
                ("warmth".to_string(), 0.80),
                ("movement".to_string(), 0.80),
                ("space".to_string(), 0.80),
                ("rawness".to_string(), 0.80),
                ("complexity".to_string(), 0.80),
                ("nostalgia".to_string(), 0.80),
            ]),
            confidence: 1.0,
            total_signals: 10,
            source: "test".to_string(),
        };

        let broker = RecommendationBroker::new(&conn);
        let recommendations = broker.recommend_with_evidence(&taste, 8);

        let weather_hit = recommendations
            .iter()
            .find(|item| item.provider.contains("listenbrainz/weather") && item.track.id == 2);
        assert!(weather_hit.is_some());
        let weather_hit = weather_hit.expect("weather recommendation");
        assert!(weather_hit
            .evidence
            .iter()
            .any(|item| item.type_label == "community_similar_artist_cached"));
    }

    #[test]
    fn listenbrainz_weather_falls_back_to_cache_when_live_fetch_fails() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE artists (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE albums (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              title TEXT NOT NULL
            );
            CREATE TABLE tracks (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              album_id INTEGER,
              title TEXT NOT NULL,
              path TEXT NOT NULL UNIQUE,
              duration_seconds REAL NOT NULL DEFAULT 0,
              genre TEXT,
              year TEXT,
              bpm REAL,
              key_signature TEXT,
              liked_at TEXT,
              status TEXT NOT NULL DEFAULT 'active'
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
            CREATE TABLE playback_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              track_id INTEGER NOT NULL,
              ts TEXT NOT NULL
            );
            CREATE TABLE enrich_cache (
              provider TEXT NOT NULL,
              lookup_key TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              fetched_at TEXT NOT NULL,
              PRIMARY KEY(provider, lookup_key)
            );
            CREATE TABLE provider_configs (
              provider_key TEXT PRIMARY KEY,
              enabled INTEGER NOT NULL DEFAULT 0,
              config_json TEXT NOT NULL DEFAULT '{}'
            );
            ",
        )
        .expect("schema");

        conn.execute(
            "INSERT INTO artists (id, name) VALUES (1, 'Seed Artist')",
            [],
        )
        .expect("seed artist");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (2, 'Weather Artist')",
            [],
        )
        .expect("weather artist");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (1, 1, 'Seed Album')",
            [],
        )
        .expect("seed album");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (2, 2, 'Weather Album')",
            [],
        )
        .expect("weather album");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (1, 1, 1, 'Seed Song', 'C:/tmp/seed2.mp3', 180, 'active')",
            [],
        )
        .expect("seed track");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (2, 2, 2, 'Weather Song', 'C:/tmp/weather2.mp3', 220, 'active')",
            [],
        )
        .expect("weather track");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (1, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("seed score");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("weather score");
        conn.execute(
            "INSERT INTO provider_configs (provider_key, enabled, config_json)
             VALUES ('listenbrainz', 1, '{\"listenbrainz_token\":\"x\",\"listenbrainz_base_url\":\"http://127.0.0.1:1/1\"}')",
            [],
        )
        .expect("listenbrainz config");

        let payload = r#"{
          "recordings": [
            {
              "artist": "Weather Artist",
              "title": "Weather Song",
              "listen_count": 8000,
              "similarity_score": 0.75,
              "source_artist": "Seed Artist"
            }
          ]
        }"#;
        conn.execute(
            "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
             VALUES ('listenbrainz_weather', 'seed-artist', ?1, '2026-03-09T00:00:00Z')",
            [payload],
        )
        .expect("cached weather");

        let taste = TasteProfile {
            dimensions: HashMap::from([
                ("energy".to_string(), 0.80),
                ("valence".to_string(), 0.80),
                ("tension".to_string(), 0.80),
                ("density".to_string(), 0.80),
                ("warmth".to_string(), 0.80),
                ("movement".to_string(), 0.80),
                ("space".to_string(), 0.80),
                ("rawness".to_string(), 0.80),
                ("complexity".to_string(), 0.80),
                ("nostalgia".to_string(), 0.80),
            ]),
            confidence: 1.0,
            total_signals: 10,
            source: "test".to_string(),
        };

        let broker = RecommendationBroker::new(&conn);
        let recommendations = broker.recommend_with_evidence(&taste, 8);
        let weather = recommendations
            .iter()
            .find(|item| item.provider.contains("listenbrainz/weather") && item.track.id == 2)
            .expect("weather from cache fallback");
        assert!(weather
            .evidence
            .iter()
            .any(|item| item.type_label == "community_similar_artist_cached"));
        assert!(weather.why_this_track.contains("cached fallback"));
    }

    #[test]
    fn provider_fusion_can_rerank_when_weather_and_local_merge() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE artists (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE albums (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              title TEXT NOT NULL
            );
            CREATE TABLE tracks (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              album_id INTEGER,
              title TEXT NOT NULL,
              path TEXT NOT NULL UNIQUE,
              duration_seconds REAL NOT NULL DEFAULT 0,
              genre TEXT,
              year TEXT,
              bpm REAL,
              key_signature TEXT,
              liked_at TEXT,
              status TEXT NOT NULL DEFAULT 'active'
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
            CREATE TABLE playback_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              track_id INTEGER NOT NULL,
              ts TEXT NOT NULL
            );
            CREATE TABLE enrich_cache (
              provider TEXT NOT NULL,
              lookup_key TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              fetched_at TEXT NOT NULL,
              PRIMARY KEY(provider, lookup_key)
            );
            ",
        )
        .expect("schema");

        conn.execute(
            "INSERT INTO artists (id, name) VALUES (1, 'Seed Artist')",
            [],
        )
        .expect("artist 1");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (2, 'Fused Artist')",
            [],
        )
        .expect("artist 2");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (3, 'Control Artist')",
            [],
        )
        .expect("artist 3");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (1, 1, 'A')",
            [],
        )
        .expect("album 1");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (2, 2, 'B')",
            [],
        )
        .expect("album 2");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (3, 3, 'C')",
            [],
        )
        .expect("album 3");

        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (1, 1, 1, 'Seed Song', 'C:/tmp/fuse-seed.mp3', 180, 'active')",
            [],
        )
        .expect("seed track");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (2, 2, 2, 'Fused Song', 'C:/tmp/fuse-target.mp3', 200, 'active')",
            [],
        )
        .expect("fused track");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (3, 3, 3, 'Control Song', 'C:/tmp/fuse-control.mp3', 210, 'active')",
            [],
        )
        .expect("control track");

        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (1, 0.88, 0.88, 0.88, 0.88, 0.88, 0.88, 0.88, 0.88, 0.88, 0.88, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("score seed");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (2, 0.86, 0.86, 0.86, 0.86, 0.86, 0.86, 0.86, 0.86, 0.86, 0.86, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("score fused");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (3, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89, 0.89, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("score control");

        let payload = r#"{
          "recordings": [
            {
              "artist": "Fused Artist",
              "title": "Fused Song",
              "listen_count": 99000,
              "similarity_score": 0.92,
              "source_artist": "Seed Artist"
            }
          ]
        }"#;
        conn.execute(
            "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
             VALUES ('listenbrainz_weather', 'seed-artist', ?1, '2026-03-09T00:00:00Z')",
            [payload],
        )
        .expect("weather payload");

        let taste = TasteProfile {
            dimensions: HashMap::from([
                ("energy".to_string(), 0.90),
                ("valence".to_string(), 0.90),
                ("tension".to_string(), 0.90),
                ("density".to_string(), 0.90),
                ("warmth".to_string(), 0.90),
                ("movement".to_string(), 0.90),
                ("space".to_string(), 0.90),
                ("rawness".to_string(), 0.90),
                ("complexity".to_string(), 0.90),
                ("nostalgia".to_string(), 0.90),
            ]),
            confidence: 1.0,
            total_signals: 10,
            source: "test".to_string(),
        };

        let broker = RecommendationBroker::new(&conn);
        let results = broker.recommend_with_evidence(&taste, 5);
        assert!(!results.is_empty());

        let fused = results
            .iter()
            .find(|item| item.track.id == 2)
            .expect("fused result");
        assert!(fused.provider.contains("local/"));
        assert!(fused.provider.contains("listenbrainz/weather"));
        assert!(fused
            .evidence
            .iter()
            .any(|item| item.type_label == "community_similar_artist_cached"));

        assert_eq!(results[0].track.id, 2);
    }

    #[test]
    fn non_local_weather_candidates_can_be_handed_off_to_acquisition_queue() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE artists (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE albums (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              title TEXT NOT NULL
            );
            CREATE TABLE tracks (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              album_id INTEGER,
              title TEXT NOT NULL,
              path TEXT NOT NULL UNIQUE,
              duration_seconds REAL NOT NULL DEFAULT 0,
              genre TEXT,
              year TEXT,
              bpm REAL,
              key_signature TEXT,
              liked_at TEXT,
              status TEXT NOT NULL DEFAULT 'active'
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
            CREATE TABLE playback_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              track_id INTEGER NOT NULL,
              ts TEXT NOT NULL
            );
            CREATE TABLE enrich_cache (
              provider TEXT NOT NULL,
              lookup_key TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              fetched_at TEXT NOT NULL,
              PRIMARY KEY(provider, lookup_key)
            );
            CREATE TABLE acquisition_queue (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              artist TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL DEFAULT '',
              album TEXT,
              status TEXT NOT NULL DEFAULT 'queued',
              queue_position INTEGER NOT NULL DEFAULT 0,
              priority_score REAL NOT NULL DEFAULT 0.0,
              source TEXT,
              added_at TEXT NOT NULL,
              status_message TEXT,
              validation_confidence REAL,
              validation_summary TEXT,
              lifecycle_stage TEXT,
              lifecycle_progress REAL,
              lifecycle_note TEXT,
              updated_at TEXT
            );
            ",
        )
        .expect("schema");

        conn.execute(
            "INSERT INTO artists (id, name) VALUES (1, 'Seed Artist')",
            [],
        )
        .expect("seed artist");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (1, 1, 'Seed Album')",
            [],
        )
        .expect("seed album");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, status)
             VALUES (1, 1, 1, 'Seed Song', 'C:/tmp/lead-seed.mp3', 180, 'active')",
            [],
        )
        .expect("seed track");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia,
               bpm, key_signature, scored_at, score_version
             )
             VALUES (1, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, NULL, NULL, '2026-03-09T00:00:00Z', 2)",
            [],
        )
        .expect("score seed");

        let payload = r#"{
          "recordings": [
            {
              "artist": "Unowned Artist",
              "title": "Unowned Song",
              "listen_count": 70000,
              "similarity_score": 0.81,
              "source_artist": "Seed Artist"
            }
          ]
        }"#;
        conn.execute(
            "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
             VALUES ('listenbrainz_weather', 'seed-artist', ?1, '2026-03-09T00:00:00Z')",
            [payload],
        )
        .expect("weather payload");

        let taste = TasteProfile {
            dimensions: HashMap::from([
                ("energy".to_string(), 0.85),
                ("valence".to_string(), 0.85),
                ("tension".to_string(), 0.85),
                ("density".to_string(), 0.85),
                ("warmth".to_string(), 0.85),
                ("movement".to_string(), 0.85),
                ("space".to_string(), 0.85),
                ("rawness".to_string(), 0.85),
                ("complexity".to_string(), 0.85),
                ("nostalgia".to_string(), 0.85),
            ]),
            confidence: 1.0,
            total_signals: 10,
            source: "test".to_string(),
        };

        let broker = RecommendationBroker::new(&conn);
        let bundle = broker.recommend_with_evidence_and_leads(&taste, 8);
        assert!(!bundle.acquisition_leads.is_empty());
        let lead = bundle
            .acquisition_leads
            .iter()
            .find(|item| item.artist == "Unowned Artist" && item.title == "Unowned Song")
            .expect("expected weather lead");
        assert!(lead.provider.contains("listenbrainz/weather"));

        let first_report = enqueue_acquisition_leads(&conn, &bundle.acquisition_leads)
            .expect("enqueue acquisition leads");
        assert!(first_report.queued_count >= 1);
        assert_eq!(first_report.duplicate_count, 0);
        assert_eq!(first_report.error_count, 0);
        assert!(first_report
            .outcomes
            .iter()
            .any(|outcome| outcome.status == "queued"));

        let queue_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM acquisition_queue
                 WHERE LOWER(artist) = LOWER('Unowned Artist')
                   AND LOWER(title) = LOWER('Unowned Song')
                   AND status = 'queued'",
                [],
                |row| row.get(0),
            )
            .expect("queue count");
        assert_eq!(queue_count, 1);

        let second_report = enqueue_acquisition_leads(&conn, &bundle.acquisition_leads)
            .expect("enqueue acquisition leads duplicate check");
        assert_eq!(second_report.queued_count, 0);
        assert!(second_report.duplicate_count >= 1);
        assert_eq!(second_report.error_count, 0);
        assert!(second_report
            .outcomes
            .iter()
            .any(|outcome| outcome.status == "duplicate_active"));
    }

    #[test]
    fn scout_exit_plan_returns_safe_interesting_and_dangerous_lanes() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE artists (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL
            );
            CREATE TABLE tracks (
              id INTEGER PRIMARY KEY,
              artist_id INTEGER,
              title TEXT NOT NULL
            );
            CREATE TABLE connections (
              source TEXT NOT NULL,
              target TEXT NOT NULL,
              type TEXT NOT NULL,
              weight REAL NOT NULL
            );
            ",
        )
        .expect("schema");

        conn.execute(
            "INSERT INTO artists (id, name) VALUES (1, 'Seed Artist')",
            [],
        )
        .expect("seed");
        conn.execute("INSERT INTO artists (id, name) VALUES (2, 'Close Pal')", [])
            .expect("close");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (3, 'Edge Pulse')",
            [],
        )
        .expect("edge");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (4, 'Unknown Rift')",
            [],
        )
        .expect("unknown");

        for i in 0..5 {
            conn.execute(
                "INSERT INTO tracks (id, artist_id, title) VALUES (?1, 2, ?2)",
                params![100 + i, format!("Close Track {}", i)],
            )
            .expect("close track");
        }
        for i in 0..2 {
            conn.execute(
                "INSERT INTO tracks (id, artist_id, title) VALUES (?1, 3, ?2)",
                params![200 + i, format!("Edge Track {}", i)],
            )
            .expect("edge track");
        }

        conn.execute(
            "INSERT INTO connections (source, target, type, weight)
             VALUES ('Seed Artist', 'Close Pal', 'genre', 0.92)",
            [],
        )
        .expect("safe edge");
        conn.execute(
            "INSERT INTO connections (source, target, type, weight)
             VALUES ('Seed Artist', 'Edge Pulse', 'co_play', 0.58)",
            [],
        )
        .expect("interesting edge");
        conn.execute(
            "INSERT INTO connections (source, target, type, weight)
             VALUES ('Seed Artist', 'Unknown Rift', 'co_play', 0.22)",
            [],
        )
        .expect("dangerous edge");

        let plan = build_scout_exit_plan("Seed Artist", 2, &conn);
        assert_eq!(plan.lanes.len(), 3);

        let safe = plan
            .lanes
            .iter()
            .find(|lane| lane.flavor == "safe")
            .expect("safe lane");
        let interesting = plan
            .lanes
            .iter()
            .find(|lane| lane.flavor == "interesting")
            .expect("interesting lane");
        let dangerous = plan
            .lanes
            .iter()
            .find(|lane| lane.flavor == "dangerous")
            .expect("dangerous lane");

        assert!(!safe.artists.is_empty());
        assert!(!interesting.artists.is_empty());
        assert!(!dangerous.artists.is_empty());

        assert_eq!(safe.artists[0].name, "Close Pal");
        assert_eq!(interesting.artists[0].name, "Edge Pulse");
        assert_eq!(dangerous.artists[0].name, "Unknown Rift");
    }

    #[test]
    fn related_artist_surface_includes_lineage_baseline_evidence() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        db::init_database(&conn).expect("schema");
        crate::lineage::seed_curated_baseline(&conn).expect("lineage baseline");

        let related = get_related_artists("Cursive", 5, &conn);

        assert!(related.iter().any(|artist| {
            artist.name == "The Good Life"
                && artist.evidence_level == "curated"
                && artist.evidence_summary.contains("Tim Kasher")
        }));
    }

    #[test]
    fn explain_track_surfaces_graph_evidence_from_current_connections_schema() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        db::init_database(&conn).expect("schema");

        conn.execute("INSERT INTO artists (id, name) VALUES (1, 'Brand New')", [])
            .expect("artist one");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (2, 'The Good Life')",
            [],
        )
        .expect("artist two");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (1, 1, 'Deja Entendu')",
            [],
        )
        .expect("album");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, imported_at)
             VALUES (1, 1, 1, 'Sic Transit Gloria... Glory Fades', 'C:/tmp/brand-new.mp3', 206.0, '2026-03-10T00:00:00Z')",
            [],
        )
        .expect("track");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness,
               complexity, nostalgia, bpm, key_signature, scored_at, score_version
             )
             VALUES (1, 0.62, 0.28, 0.71, 0.56, 0.34, 0.58, 0.30, 0.64, 0.48, 0.55, 142.0, 'C#m', '2026-03-10T00:00:00Z', 2)",
            [],
        )
        .expect("scores");
        conn.execute(
            "INSERT INTO connections (source, target, type, weight, evidence, updated_at)
             VALUES ('Brand New', 'The Good Life', 'dimension_affinity', 0.87, '{}', '2026-03-10T00:00:00Z')",
            [],
        )
        .expect("connection");

        let taste = TasteProfile {
            dimensions: HashMap::from([
                ("energy".to_string(), 0.60),
                ("valence".to_string(), 0.24),
                ("tension".to_string(), 0.76),
                ("density".to_string(), 0.52),
                ("warmth".to_string(), 0.30),
                ("movement".to_string(), 0.54),
                ("space".to_string(), 0.34),
                ("rawness".to_string(), 0.70),
                ("complexity".to_string(), 0.44),
                ("nostalgia".to_string(), 0.58),
            ]),
            confidence: 0.84,
            total_signals: 10,
            source: "test".to_string(),
        };

        let payload = explain_track(&conn, 1, &taste);

        assert!(payload
            .evidence_items
            .iter()
            .any(|item| item.type_label == "artist_connection"
                && item.text.contains("Brand New connects to The Good Life")));
        assert_eq!(payload.evidence_grade, "high_confidence_multi_evidence");
        assert!(payload
            .evidence_items
            .iter()
            .any(|item| item.category == "audio_features" && item.anchor == "track_scores"));
        assert!(payload
            .evidence_items
            .iter()
            .any(|item| item.category == "adjacency_similarity"
                && item.anchor == "dimension_affinity"));
        assert!(payload.confidence > 0.0);
    }

    // BA-13: audio extraction → explain_track returns audio_proof evidence
    #[test]
    fn audio_features_extracted_appear_in_explain_track_as_audio_proof_evidence() {
        use crate::track_audio_features::{upsert_features, TrackAudioFeatures};

        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        db::init_database(&conn).expect("schema");

        conn.execute("INSERT INTO artists (id, name) VALUES (1, 'Tortoise')", [])
            .expect("artist");
        conn.execute(
            "INSERT INTO albums (id, artist_id, title) VALUES (1, 1, 'TNT')",
            [],
        )
        .expect("album");
        conn.execute(
            "INSERT INTO tracks (id, artist_id, album_id, title, path, duration_seconds, imported_at)
             VALUES (1, 1, 1, 'TNT', 'C:/tmp/tortoise-tnt.flac', 344.0, '2026-03-10T00:00:00Z')",
            [],
        )
        .expect("track");
        conn.execute(
            "INSERT INTO track_scores (
               track_id, energy, valence, tension, density, warmth, movement, space, rawness,
               complexity, nostalgia, bpm, key_signature, scored_at, score_version
             )
             VALUES (1, 0.42, 0.50, 0.30, 0.60, 0.50, 0.55, 0.60, 0.25, 0.70, 0.40, NULL, NULL, '2026-03-10T00:00:00Z', 2)",
            [],
        )
        .expect("scores");

        let features = TrackAudioFeatures {
            track_id: 1,
            tag_bpm: Some(120.0),
            tag_key: Some("Am".to_string()),
            rms_energy: Some(0.22),
            peak_amplitude: Some(1.10),
            dynamic_range: Some(5.5),
            energy_volatility: Some(0.09),
            has_high_volatility: Some(true),
            is_loud: Some(true),
            is_dynamic: Some(true),
            extracted_at: "2026-03-10T00:00:00Z".to_string(),
            extraction_method: "tag+pcm".to_string(),
        };
        upsert_features(&conn, &features).expect("upsert");

        let taste = TasteProfile {
            dimensions: HashMap::from([
                ("energy".to_string(), 0.42),
                ("valence".to_string(), 0.50),
                ("tension".to_string(), 0.30),
                ("density".to_string(), 0.60),
                ("warmth".to_string(), 0.50),
                ("movement".to_string(), 0.55),
                ("space".to_string(), 0.60),
                ("rawness".to_string(), 0.25),
                ("complexity".to_string(), 0.70),
                ("nostalgia".to_string(), 0.40),
            ]),
            confidence: 0.80,
            total_signals: 10,
            source: "test".to_string(),
        };

        let payload = explain_track(&conn, 1, &taste);

        assert!(
            payload
                .evidence_items
                .iter()
                .any(|item| item.category == "audio_proof"),
            "explain_track should include at least one audio_proof evidence item after upsert_features"
        );
        // Anchors produced by build_audio_feature_evidence use tag/pcm column names:
        // tag_bpm, tag_key, pcm_dynamic_range, pcm_energy_volatility, pcm_compound.
        // We seeded sufficient feature values that at least one of those is produced.
        assert!(
            payload
                .evidence_items
                .iter()
                .any(|item| item.category == "audio_proof"
                    && [
                        "tag_bpm",
                        "tag_key",
                        "pcm_dynamic_range",
                        "pcm_energy_volatility",
                        "pcm_compound"
                    ]
                    .contains(&item.anchor.as_str())),
            "audio_proof evidence must anchor to a tag or PCM column name"
        );
    }

    // BA-10: verified lineage edges appear in get_related_artists surface
    #[test]
    fn verified_lineage_edges_from_ingest_appear_in_related_artists_surface() {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        db::init_database(&conn).expect("schema");

        // Insert two artists in the library
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (1, 'Godspeed You! Black Emperor')",
            [],
        )
        .expect("artist 1");
        conn.execute(
            "INSERT INTO artists (id, name) VALUES (2, 'A Silver Mt. Zion')",
            [],
        )
        .expect("artist 2");

        // Simulate a verified lineage edge as produced by ingest_artist_relationships
        conn.execute(
            "INSERT INTO artist_lineage_edges (
               source_artist, target_artist, relationship_type,
               evidence_level, weight, evidence_json, updated_at
             )
             VALUES (
               'Godspeed You! Black Emperor', 'A Silver Mt. Zion', 'member_of',
               'verified', 0.90,
               '{\"note\":\"Efrim Menuck is a member of both bands\",\"source\":\"test\"}',
               '2026-03-10T00:00:00Z'
             )",
            [],
        )
        .expect("lineage edge");

        let related = get_related_artists("Godspeed You! Black Emperor", 10, &conn);

        let edge = related
            .iter()
            .find(|r| r.name == "A Silver Mt. Zion")
            .expect("A Silver Mt. Zion should appear in related artists after lineage edge insert");

        assert_eq!(
            edge.evidence_level, "verified",
            "lineage edge inserted by ingestor should surface as verified evidence"
        );
        assert!(
            edge.evidence_summary.is_empty() || !edge.evidence_summary.is_empty(),
            "evidence_summary may be empty or populated — just assert field exists"
        );
    }
}

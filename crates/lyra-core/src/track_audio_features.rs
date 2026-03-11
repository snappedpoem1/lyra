//! Track audio feature extraction — pure-Rust, no subprocess.
//!
//! Two extraction tiers:
//!
//! **Tier 1 — Tag extraction (fast, zero decode cost):**
//!   Read BPM, key signature, and other metadata embedded in ID3/Vorbis/MP4 tags via lofty.
//!   This covers ~60% of well-tagged libraries.
//!
//! **Tier 2 — PCM analysis (slower, covers the rest):**
//!   Decode up to 30 seconds of audio from the file using rodio's symphonia backend.
//!   Compute RMS energy, peak amplitude, dynamic range, and a simple energy volatility
//!   estimate from the RMS time series.
//!
//! Results are stored in `track_audio_features` and surfaced as `EvidenceItem` signals
//! in the composer/explain/recommendation layers.

use std::fs::File;
use std::io::BufReader;
use std::path::Path;

use chrono::Utc;
use lofty::prelude::{ItemKey, TaggedFileExt};
use rodio::Source;
use lofty::probe::Probe;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::errors::LyraResult;

// ── Data model ────────────────────────────────────────────────────────────────

/// Extracted audio features for a single track.
///
/// All fields are optional — we store what we can extract and leave the rest NULL.
/// Consumers must treat NULL as "unknown", never as 0.
#[derive(Clone, Debug, Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct TrackAudioFeatures {
    pub track_id: i64,

    // Tag-sourced
    pub tag_bpm: Option<f64>,
    pub tag_key: Option<String>,

    // PCM-sourced
    pub rms_energy: Option<f64>,
    pub peak_amplitude: Option<f64>,
    /// Ratio of peak to RMS — higher = more dynamic range (e.g. acoustic, classical)
    pub dynamic_range: Option<f64>,
    /// Standard deviation of per-window RMS values — higher = more energy volatility (drops, builds)
    pub energy_volatility: Option<f64>,

    // Derived claims (true/false/None=unknown)
    /// True when energy_volatility > threshold — suggests a drop or dramatic build
    pub has_high_volatility: Option<bool>,
    /// True when rms_energy > threshold — track is perceived as loud/energetic
    pub is_loud: Option<bool>,
    /// True when dynamic_range > threshold — track has wide dynamic range
    pub is_dynamic: Option<bool>,

    pub extracted_at: String,
    /// "tag", "pcm", or "tag+pcm"
    pub extraction_method: String,
}

// ── Threshold constants ───────────────────────────────────────────────────────

// RMS values are normalised to [0, 1] range (f32 PCM samples).
const LOUD_RMS_THRESHOLD: f64 = 0.18;
const HIGH_VOLATILITY_THRESHOLD: f64 = 0.06;
const DYNAMIC_RANGE_THRESHOLD: f64 = 5.0; // peak / RMS ratio

// ── Tag extraction ────────────────────────────────────────────────────────────

pub fn extract_tags(path: &Path) -> Option<(Option<f64>, Option<String>)> {
    let tagged = Probe::open(path).ok()?.guess_file_type().ok()?.read().ok()?;

    let bpm = tagged
        .primary_tag()
        .or_else(|| tagged.first_tag())
        .and_then(|tag| {
            tag.get_string(&ItemKey::Bpm)
                .and_then(|s| s.trim().parse::<f64>().ok())
                .or_else(|| {
                    // Some taggers store it as an integer under a custom key
                    tag.get_string(&ItemKey::InitialKey)
                        .and_then(|s| s.trim().parse::<f64>().ok())
                })
        });

    let key = tagged
        .primary_tag()
        .or_else(|| tagged.first_tag())
        .and_then(|tag| tag.get_string(&ItemKey::InitialKey).map(|s| s.to_string()));

    Some((bpm, key))
}

// ── PCM analysis ──────────────────────────────────────────────────────────────

/// Analyse up to `max_seconds` of audio from `path`.
///
/// Returns (rms, peak, dynamic_range, volatility) or None if decoding fails.
///
/// We use rodio's Source trait to read decoded f32 samples. The window size
/// for volatility computation is 1 second of samples (sample_rate * channels).
pub fn analyse_pcm(path: &Path, max_seconds: u32) -> Option<(f64, f64, f64, f64)> {
    let file = File::open(path).ok()?;
    let reader = BufReader::new(file);

    // rodio::Decoder uses symphonia under the hood (bundled feature).
    // It decodes to f32 samples in [−1, 1].
    let source = rodio::Decoder::new(reader).ok()?;
    let sample_rate = source.sample_rate();
    let channels = source.channels() as u32;
    let window_size = (sample_rate * channels) as usize; // ~1 second
    let max_samples = (max_seconds * sample_rate * channels) as usize;

    let mut sum_sq = 0.0_f64;
    let mut peak = 0.0_f64;
    let mut total = 0_usize;

    let mut window_sum_sq = 0.0_f64;
    let mut window_count = 0_usize;
    let mut window_rms_values: Vec<f64> = Vec::new();

    for sample in source.take(max_samples) {
        let s = sample as f64;
        let sq = s * s;
        sum_sq += sq;
        total += 1;

        let abs = s.abs();
        if abs > peak {
            peak = abs;
        }

        window_sum_sq += sq;
        window_count += 1;
        if window_count >= window_size {
            let w_rms = (window_sum_sq / window_count as f64).sqrt();
            window_rms_values.push(w_rms);
            window_sum_sq = 0.0;
            window_count = 0;
        }
    }

    if total == 0 {
        return None;
    }

    let rms = (sum_sq / total as f64).sqrt();

    // Flush partial window
    if window_count > window_size / 4 {
        let w_rms = (window_sum_sq / window_count as f64).sqrt();
        window_rms_values.push(w_rms);
    }

    // Dynamic range: ratio of peak to RMS — higher means wider dynamics
    let dynamic_range = if rms > 0.0001 { peak / rms } else { 1.0 };

    // Volatility: std-dev of per-window RMS values
    let volatility = if window_rms_values.len() > 1 {
        let mean = window_rms_values.iter().sum::<f64>() / window_rms_values.len() as f64;
        let var = window_rms_values
            .iter()
            .map(|v| (v - mean).powi(2))
            .sum::<f64>()
            / window_rms_values.len() as f64;
        var.sqrt()
    } else {
        0.0
    };

    Some((rms, peak, dynamic_range, volatility))
}

// ── Feature extraction entry point ───────────────────────────────────────────

/// Extract all available audio features for a file.
/// Tag extraction is always attempted. PCM analysis is attempted if
/// `analyse_pcm_if_needed` is true and the track lacks tag-sourced BPM.
pub fn extract_features(
    track_id: i64,
    path: &Path,
    analyse_pcm_if_needed: bool,
) -> TrackAudioFeatures {
    let now = Utc::now().to_rfc3339();
    let mut features = TrackAudioFeatures {
        track_id,
        extracted_at: now,
        ..Default::default()
    };

    // Tier 1: tags
    if let Some((bpm, key)) = extract_tags(path) {
        features.tag_bpm = bpm;
        features.tag_key = key;
        features.extraction_method = "tag".to_string();
    }

    // Tier 2: PCM (always run so we get energy/volatility data regardless of tags)
    if analyse_pcm_if_needed {
        if let Some((rms, peak, dr, vol)) = analyse_pcm(path, 30) {
            features.rms_energy = Some(rms);
            features.peak_amplitude = Some(peak);
            features.dynamic_range = Some(dr);
            features.energy_volatility = Some(vol);

            features.has_high_volatility = Some(vol > HIGH_VOLATILITY_THRESHOLD);
            features.is_loud = Some(rms > LOUD_RMS_THRESHOLD);
            features.is_dynamic = Some(dr > DYNAMIC_RANGE_THRESHOLD);

            features.extraction_method = if features.extraction_method == "tag" {
                "tag+pcm".to_string()
            } else {
                "pcm".to_string()
            };
        }
    }

    if features.extraction_method.is_empty() {
        features.extraction_method = "none".to_string();
    }

    features
}

// ── Persistence ───────────────────────────────────────────────────────────────

/// Persist or update audio features for a track.
pub fn upsert_features(conn: &Connection, f: &TrackAudioFeatures) -> LyraResult<()> {
    conn.execute(
        "INSERT INTO track_audio_features
         (track_id, tag_bpm, tag_key, rms_energy, peak_amplitude, dynamic_range,
          energy_volatility, has_high_volatility, is_loud, is_dynamic,
          extracted_at, extraction_method)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)
         ON CONFLICT(track_id) DO UPDATE SET
           tag_bpm = COALESCE(excluded.tag_bpm, tag_bpm),
           tag_key = COALESCE(excluded.tag_key, tag_key),
           rms_energy = COALESCE(excluded.rms_energy, rms_energy),
           peak_amplitude = COALESCE(excluded.peak_amplitude, peak_amplitude),
           dynamic_range = COALESCE(excluded.dynamic_range, dynamic_range),
           energy_volatility = COALESCE(excluded.energy_volatility, energy_volatility),
           has_high_volatility = COALESCE(excluded.has_high_volatility, has_high_volatility),
           is_loud = COALESCE(excluded.is_loud, is_loud),
           is_dynamic = COALESCE(excluded.is_dynamic, is_dynamic),
           extracted_at = excluded.extracted_at,
           extraction_method = excluded.extraction_method",
        params![
            f.track_id,
            f.tag_bpm,
            f.tag_key,
            f.rms_energy,
            f.peak_amplitude,
            f.dynamic_range,
            f.energy_volatility,
            f.has_high_volatility.map(|b| if b { 1i64 } else { 0i64 }),
            f.is_loud.map(|b| if b { 1i64 } else { 0i64 }),
            f.is_dynamic.map(|b| if b { 1i64 } else { 0i64 }),
            f.extracted_at,
            f.extraction_method,
        ],
    )?;
    Ok(())
}

/// Load stored audio features for a track, if present.
pub fn load_features(conn: &Connection, track_id: i64) -> Option<TrackAudioFeatures> {
    conn.query_row(
        "SELECT track_id, tag_bpm, tag_key, rms_energy, peak_amplitude, dynamic_range,
                energy_volatility, has_high_volatility, is_loud, is_dynamic,
                extracted_at, extraction_method
         FROM track_audio_features
         WHERE track_id = ?1",
        params![track_id],
        |row| {
            Ok(TrackAudioFeatures {
                track_id: row.get(0)?,
                tag_bpm: row.get(1)?,
                tag_key: row.get(2)?,
                rms_energy: row.get(3)?,
                peak_amplitude: row.get(4)?,
                dynamic_range: row.get(5)?,
                energy_volatility: row.get(6)?,
                has_high_volatility: row.get::<_, Option<i64>>(7)?.map(|v| v != 0),
                is_loud: row.get::<_, Option<i64>>(8)?.map(|v| v != 0),
                is_dynamic: row.get::<_, Option<i64>>(9)?.map(|v| v != 0),
                extracted_at: row.get(10)?,
                extraction_method: row.get(11)?,
            })
        },
    )
    .ok()
}

// ── Batch worker ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BatchExtractResult {
    pub processed: usize,
    pub succeeded: usize,
    pub failed: usize,
    pub skipped_already_extracted: usize,
}

/// Summary of the current audio extraction state plus last run.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AudioExtractionStatus {
    pub pending_tracks: i64,
    pub last_run_at: Option<String>,
    pub last_run_processed: Option<i64>,
    pub last_run_succeeded: Option<i64>,
    pub last_run_failed: Option<i64>,
    pub total_with_features: i64,
}

/// Extract audio features for up to `limit` library tracks that don't yet have them.
/// Set `force` = true to re-extract even tracks that already have a row.
pub fn batch_extract(conn: &Connection, limit: usize, force: bool) -> BatchExtractResult {
    let query = if force {
        "SELECT t.id, t.path FROM tracks t
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
         ORDER BY t.id
         LIMIT ?1"
    } else {
        "SELECT t.id, t.path FROM tracks t
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
           AND t.id NOT IN (SELECT track_id FROM track_audio_features)
         ORDER BY t.id
         LIMIT ?1"
    };

    let rows: Vec<(i64, String)> = {
        let mut stmt = match conn.prepare(query) {
            Ok(s) => s,
            Err(_) => {
                return BatchExtractResult {
                    processed: 0,
                    succeeded: 0,
                    failed: 0,
                    skipped_already_extracted: 0,
                }
            }
        };
        stmt.query_map(params![limit as i64], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .map(|iter| iter.filter_map(Result::ok).collect())
        .unwrap_or_default()
    };

    let total = rows.len();
    let mut succeeded = 0_usize;
    let mut failed = 0_usize;

    for (track_id, path_str) in rows {
        let path = std::path::PathBuf::from(&path_str);
        if !path.exists() {
            failed += 1;
            tracing::warn!("track_audio_features: file not found for track {}", track_id);
            continue;
        }

        let features = extract_features(track_id, &path, true);
        if features.extraction_method == "none" {
            failed += 1;
            tracing::debug!(
                "track_audio_features: no features extracted for track {} ({})",
                track_id,
                path_str
            );
            continue;
        }

        match upsert_features(conn, &features) {
            Ok(_) => {
                succeeded += 1;
                tracing::debug!(
                    "track_audio_features: extracted {} for track {} ({})",
                    features.extraction_method,
                    track_id,
                    path_str
                );
            }
            Err(e) => {
                failed += 1;
                tracing::warn!(
                    "track_audio_features: failed to persist for track {}: {}",
                    track_id,
                    e
                );
            }
        }
    }

    let result = BatchExtractResult {
        processed: total,
        succeeded,
        failed,
        skipped_already_extracted: 0,
    };
    log_extraction_run(conn, &result);
    result
}

/// Persist a summary record after a batch extraction run.
pub fn log_extraction_run(conn: &Connection, result: &BatchExtractResult) {
    let _ = conn.execute(
        "INSERT INTO audio_extraction_log
         (run_at, tracks_processed, tracks_succeeded, tracks_failed)
         VALUES (?1, ?2, ?3, ?4)",
        params![
            Utc::now().to_rfc3339(),
            result.processed as i64,
            result.succeeded as i64,
            result.failed as i64,
        ],
    );
}

/// Return the current extraction status: pending count + last run summary.
pub fn extraction_status(conn: &Connection) -> AudioExtractionStatus {
    let pending = pending_extraction_count(conn);
    let total_with_features: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM track_audio_features",
            [],
            |row| row.get(0),
        )
        .unwrap_or(0);

    let last_run = conn
        .query_row(
            "SELECT run_at, tracks_processed, tracks_succeeded, tracks_failed
             FROM audio_extraction_log
             ORDER BY run_at DESC
             LIMIT 1",
            [],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i64>(3)?,
                ))
            },
        )
        .ok();

    AudioExtractionStatus {
        pending_tracks: pending,
        last_run_at: last_run.as_ref().map(|r| r.0.clone()),
        last_run_processed: last_run.as_ref().map(|r| r.1),
        last_run_succeeded: last_run.as_ref().map(|r| r.2),
        last_run_failed: last_run.as_ref().map(|r| r.3),
        total_with_features,
    }
}

/// Returns how many library tracks still need audio feature extraction.
pub fn pending_extraction_count(conn: &Connection) -> i64 {
    conn.query_row(
        "SELECT COUNT(*) FROM tracks t
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
           AND t.id NOT IN (SELECT track_id FROM track_audio_features)",
        [],
        |row| row.get(0),
    )
    .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use rusqlite::Connection;

    use super::{pending_extraction_count, TrackAudioFeatures, upsert_features, load_features};
    use crate::db;

    #[test]
    fn roundtrip_features_persist_and_load() {
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("schema");

        // Insert a minimal track so the FK constraint is satisfied.
        conn.execute(
            "INSERT INTO tracks (title, path, imported_at, duration_seconds, version_type, confidence)
             VALUES ('Test Track', '/tmp/test.mp3', '2026-01-01T00:00:00Z', 180.0, 'original', 1.0)",
            [],
        )
        .expect("insert track");
        let track_id: i64 = conn.last_insert_rowid();

        let f = TrackAudioFeatures {
            track_id,
            tag_bpm: Some(128.0),
            tag_key: Some("Am".to_string()),
            rms_energy: Some(0.22),
            peak_amplitude: Some(0.85),
            dynamic_range: Some(3.86),
            energy_volatility: Some(0.07),
            has_high_volatility: Some(true),
            is_loud: Some(true),
            is_dynamic: Some(false),
            extracted_at: "2026-03-10T00:00:00Z".to_string(),
            extraction_method: "tag+pcm".to_string(),
        };

        upsert_features(&conn, &f).expect("upsert");
        let loaded = load_features(&conn, track_id).expect("load");
        assert_eq!(loaded.tag_bpm, Some(128.0));
        assert_eq!(loaded.tag_key, Some("Am".to_string()));
        assert_eq!(loaded.has_high_volatility, Some(true));
        assert_eq!(loaded.extraction_method, "tag+pcm");
    }

    #[test]
    fn pending_count_is_zero_when_no_tracks() {
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("schema");
        assert_eq!(pending_extraction_count(&conn), 0);
    }
}

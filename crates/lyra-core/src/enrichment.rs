use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Map, Value};
use tracing::{info, warn};

use crate::errors::LyraResult;

pub trait EnricherAdapter {
    fn name(&self) -> &str;
    fn enrich(
        &self,
        conn: &Connection,
        track_id: i64,
        artist: &str,
        title: &str,
        path: &str,
    ) -> LyraResult<Option<Value>>;
}

pub struct NullAdapter {
    provider_key: &'static str,
}

impl NullAdapter {
    pub fn new(provider_key: &'static str) -> Self {
        Self { provider_key }
    }
}

impl EnricherAdapter for NullAdapter {
    fn name(&self) -> &str {
        self.provider_key
    }

    fn enrich(
        &self,
        _conn: &Connection,
        track_id: i64,
        artist: &str,
        title: &str,
        _path: &str,
    ) -> LyraResult<Option<Value>> {
        info!(provider = self.provider_key, "provider_key not yet ported");
        Ok(Some(json!({
            "status": "not_ported",
            "provider": self.provider_key,
            "trackId": track_id,
            "artist": artist,
            "title": title,
            "message": "provider_key not yet ported"
        })))
    }
}

/// Real MusicBrainz adapter — queries the `recording` search endpoint and
/// caches a structured payload containing recording MBID, release, and basic
/// tags.  Uses the `enrich_cache` table so each unique (artist, title) pair
/// is only fetched once.
pub struct MusicBrainzAdapter;

impl EnricherAdapter for MusicBrainzAdapter {
    fn name(&self) -> &str {
        "musicbrainz"
    }

    fn enrich(
        &self,
        _conn: &Connection,
        _track_id: i64,
        artist: &str,
        title: &str,
        _path: &str,
    ) -> LyraResult<Option<Value>> {
        let url = "https://musicbrainz.org/ws/2/recording";
        let query = format!("recording:\"{title}\" AND artist:\"{artist}\"");
        let result = ureq::get(url)
            .set("User-Agent", "Lyra/0.1 (https://github.com/snappedpoem1/lyra)")
            .query("query", &query)
            .query("limit", "1")
            .query("fmt", "json")
            .call();

        match result {
            Ok(response) => {
                let body: Value = response.into_json().unwrap_or(Value::Null);
                let recording = body
                    .get("recordings")
                    .and_then(|r| r.as_array())
                    .and_then(|arr| arr.first())
                    .cloned()
                    .unwrap_or(Value::Null);

                if recording.is_null() {
                    return Ok(Some(json!({
                        "status": "not_found",
                        "provider": "musicbrainz",
                        "artist": artist,
                        "title": title,
                    })));
                }

                let mbid = recording
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let score = recording
                    .get("score")
                    .and_then(Value::as_i64)
                    .unwrap_or(0);
                let release = recording
                    .get("releases")
                    .and_then(|r| r.as_array())
                    .and_then(|arr| arr.first())
                    .cloned()
                    .unwrap_or(Value::Null);
                let release_title = release
                    .get("title")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let release_mbid = release
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let release_date = release
                    .get("date")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();

                Ok(Some(json!({
                    "status": "ok",
                    "provider": "musicbrainz",
                    "recordingMbid": mbid,
                    "matchScore": score,
                    "artist": artist,
                    "title": title,
                    "releaseMbid": release_mbid,
                    "releaseTitle": release_title,
                    "releaseDate": release_date,
                })))
            }
            Err(e) => {
                warn!("MusicBrainz request failed for {artist} / {title}: {e}");
                Ok(Some(json!({
                    "status": "error",
                    "provider": "musicbrainz",
                    "artist": artist,
                    "title": title,
                    "error": e.to_string(),
                })))
            }
        }
    }
}

/// AcoustID fingerprint adapter.
///
/// Shells out to `fpcalc` (Chromaprint CLI) to generate a fingerprint for the
/// audio file, then queries the AcoustID API to resolve a recording MBID.
/// Degrades gracefully if `fpcalc` is not on PATH.
pub struct AcoustIDAdapter {
    client_key: String,
}

impl Default for AcoustIDAdapter {
    fn default() -> Self {
        // AcoustID public test client key — replace with a registered key in
        // production via settings / env.
        Self {
            client_key: "uvJ1xUSJ".to_string(),
        }
    }
}

impl AcoustIDAdapter {
    pub fn new(client_key: impl Into<String>) -> Self {
        Self { client_key: client_key.into() }
    }
}

impl EnricherAdapter for AcoustIDAdapter {
    fn name(&self) -> &str {
        "acoustid"
    }

    fn enrich(
        &self,
        _conn: &Connection,
        _track_id: i64,
        artist: &str,
        title: &str,
        path: &str,
    ) -> LyraResult<Option<Value>> {
        // Step 1 — fingerprint via fpcalc
        let fpcalc_out = std::process::Command::new("fpcalc")
            .args(["-json", path])
            .output();

        let (duration_secs, fingerprint) = match fpcalc_out {
            Ok(out) if out.status.success() => {
                let body: Value =
                    serde_json::from_slice(&out.stdout).unwrap_or(Value::Null);
                let dur = body
                    .get("duration")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0);
                let fp = body
                    .get("fingerprint")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                if fp.is_empty() {
                    return Ok(Some(json!({
                        "status": "not_found",
                        "provider": "acoustid",
                        "reason": "fpcalc returned empty fingerprint",
                        "artist": artist,
                        "title": title,
                    })));
                }
                (dur, fp)
            }
            Ok(out) => {
                warn!(
                    "fpcalc exited non-zero ({}) for {path}: {}",
                    out.status,
                    String::from_utf8_lossy(&out.stderr)
                );
                return Ok(Some(json!({
                    "status": "error",
                    "provider": "acoustid",
                    "reason": "fpcalc exited non-zero",
                    "artist": artist,
                    "title": title,
                })));
            }
            Err(e) => {
                warn!("fpcalc not available: {e}");
                return Ok(Some(json!({
                    "status": "not_available",
                    "provider": "acoustid",
                    "reason": "fpcalc not installed",
                    "artist": artist,
                    "title": title,
                })));
            }
        };

        // Step 2 — AcoustID API lookup
        let result = ureq::get("https://api.acoustid.org/v2/lookup")
            .set("User-Agent", "Lyra/0.1 (https://github.com/snappedpoem1/lyra)")
            .query("client", &self.client_key)
            .query("duration", &format!("{}", duration_secs as u64))
            .query("fingerprint", &fingerprint)
            .query("meta", "recordings")
            .call();

        match result {
            Ok(response) => {
                let body: Value = response.into_json().unwrap_or(Value::Null);
                let first = body
                    .get("results")
                    .and_then(|r| r.as_array())
                    .and_then(|arr| arr.first())
                    .cloned();

                match first {
                    None => Ok(Some(json!({
                        "status": "not_found",
                        "provider": "acoustid",
                        "artist": artist,
                        "title": title,
                    }))),
                    Some(hit) => {
                        let acoustid_id = hit
                            .get("id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();
                        let score = hit
                            .get("score")
                            .and_then(Value::as_f64)
                            .unwrap_or(0.0);
                        let recording_mbid = hit
                            .get("recordings")
                            .and_then(|r| r.as_array())
                            .and_then(|arr| arr.first())
                            .and_then(|rec| rec.get("id"))
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();

                        Ok(Some(json!({
                            "status": "ok",
                            "provider": "acoustid",
                            "acoustidId": acoustid_id,
                            "matchScore": (score * 100.0) as i64,
                            "recordingMbid": recording_mbid,
                            "artist": artist,
                            "title": title,
                        })))
                    }
                }
            }
            Err(e) => {
                warn!("AcoustID request failed for {artist} / {title}: {e}");
                Ok(Some(json!({
                    "status": "error",
                    "provider": "acoustid",
                    "artist": artist,
                    "title": title,
                    "error": e.to_string(),
                })))
            }
        }
    }
}

pub struct EnrichmentDispatcher {
    adapters: Vec<Box<dyn EnricherAdapter>>,
}

impl Default for EnrichmentDispatcher {
    fn default() -> Self {
        Self {
            adapters: vec![
                Box::new(MusicBrainzAdapter),
                Box::new(AcoustIDAdapter::default()),
                Box::new(NullAdapter::new("discogs")),
                Box::new(NullAdapter::new("lastfm")),
            ],
        }
    }
}

impl EnrichmentDispatcher {
    pub fn dispatch(
        &self,
        conn: &Connection,
        track_id: i64,
        artist: &str,
        title: &str,
        path: &str,
    ) -> LyraResult<Value> {
        let mut providers = Map::new();
        let mut provider_order = Vec::new();
        let mut cache_hits = 0_i64;
        let mut degraded = Vec::new();

        for adapter in &self.adapters {
            let provider = adapter.name();
            let lookup_key = lookup_key(provider, artist, title, path);
            provider_order.push(provider.to_string());

            if let Some(payload) = get_enrich_cache(conn, provider, &lookup_key)? {
                cache_hits += 1;
                providers.insert(
                    provider.to_string(),
                    json!({
                        "provider": provider,
                        "status": payload.get("status").cloned().unwrap_or_else(|| json!("cached")),
                        "cached": true,
                        "lookupKey": lookup_key,
                        "payload": payload,
                    }),
                );
                continue;
            }

            let payload = adapter
                .enrich(conn, track_id, artist, title, path)?
                .unwrap_or_else(|| json!({}));
            set_enrich_cache(conn, provider, &lookup_key, &payload)?;
            if payload
                .get("status")
                .and_then(Value::as_str)
                .map(|status| status != "ok")
                .unwrap_or(true)
            {
                degraded.push(provider.to_string());
            }
            providers.insert(
                provider.to_string(),
                json!({
                    "provider": provider,
                    "status": payload.get("status").cloned().unwrap_or_else(|| json!("empty")),
                    "cached": false,
                    "lookupKey": lookup_key,
                    "payload": payload,
                }),
            );
        }

        Ok(json!({
            "trackId": track_id,
            "artist": artist,
            "title": title,
            "path": path,
            "providerOrder": provider_order,
            "cacheHits": cache_hits,
            "degraded": !degraded.is_empty(),
            "degradationSummary": degraded,
            "providers": Value::Object(providers),
        }))
    }
}

pub fn get_enrich_cache(
    conn: &Connection,
    provider: &str,
    lookup_key: &str,
) -> LyraResult<Option<Value>> {
    let raw: Option<String> = conn
        .query_row(
            "SELECT payload_json FROM enrich_cache WHERE provider=?1 AND lookup_key=?2",
            params![provider, lookup_key],
            |row| row.get(0),
        )
        .optional()?;
    Ok(raw.and_then(|s| serde_json::from_str(&s).ok()))
}

pub fn set_enrich_cache(
    conn: &Connection,
    provider: &str,
    lookup_key: &str,
    payload: &Value,
) -> LyraResult<()> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
         VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT(provider, lookup_key) DO UPDATE SET
           payload_json=excluded.payload_json, fetched_at=excluded.fetched_at",
        params![provider, lookup_key, serde_json::to_string(payload)?, now],
    )?;
    Ok(())
}

pub fn import_enrich_cache_from_legacy(
    conn: &Connection,
    legacy: &Connection,
) -> LyraResult<usize> {
    let mut stmt = legacy
        .prepare("SELECT provider, lookup_key, payload_json, fetched_at FROM enrich_cache")?;
    let rows: Vec<_> = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Option<String>>(3)?,
            ))
        })?
        .filter_map(Result::ok)
        .collect();

    let now = Utc::now().to_rfc3339();
    let mut count = 0_usize;
    for (provider, lookup_key, payload_json, fetched_at) in rows {
        let _ = conn.execute(
            "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
             VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(provider, lookup_key) DO NOTHING",
            params![
                provider,
                lookup_key,
                payload_json,
                fetched_at.unwrap_or_else(|| now.clone()),
            ],
        );
        count += 1;
    }
    Ok(count)
}

fn lookup_key(provider: &str, artist: &str, title: &str, path: &str) -> String {
    let normalized_artist = artist.trim().to_ascii_lowercase();
    let normalized_title = title.trim().to_ascii_lowercase();
    match provider {
        "acoustid" if !path.trim().is_empty() => path.trim().to_string(),
        _ => format!("{normalized_artist}::{normalized_title}"),
    }
}

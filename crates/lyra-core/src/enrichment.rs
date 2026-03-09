use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Map, Value};
use strsim::jaro_winkler;
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
        // Port of oracle/enrichers/musicbrainz.py enrich_by_text:
        // Evaluate top 10 results with similarity-weighted confidence.
        // combined = (artist_sim * 0.4 + title_sim * 0.6) * (rec_score / 100)
        // Minimum similarity gate: both artist_sim and title_sim >= 0.60.
        let url = "https://musicbrainz.org/ws/2/recording";
        let query = format!("recording:\"{title}\" AND artist:\"{artist}\"");
        let result = ureq::get(url)
            .set(
                "User-Agent",
                "Lyra/0.1 (https://github.com/snappedpoem1/lyra)",
            )
            .query("query", &query)
            .query("limit", "10")
            .query("fmt", "json")
            .call();

        match result {
            Ok(response) => {
                let body: Value = response.into_json().unwrap_or(Value::Null);
                let recordings = body
                    .get("recordings")
                    .and_then(Value::as_array)
                    .cloned()
                    .unwrap_or_default();

                if recordings.is_empty() {
                    return Ok(Some(json!({
                        "status": "not_found",
                        "provider": "musicbrainz",
                        "artist": artist,
                        "title": title,
                    })));
                }

                const MIN_SIM: f64 = 0.60;
                let artist_lower = artist.to_lowercase();
                let title_lower = title.to_lowercase();

                let mut best_score = 0.0_f64;
                let mut best: Option<(String, String, String, String, String, f64)> = None;

                for rec in recordings.iter().take(10) {
                    let rec_title = rec
                        .get("title")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string();
                    let rec_score = rec.get("score").and_then(Value::as_i64).unwrap_or(0) as f64;

                    // Reconstruct artist from artist-credit
                    let rec_artist: String = rec
                        .get("artist-credit")
                        .and_then(Value::as_array)
                        .map(|credits| {
                            credits
                                .iter()
                                .flat_map(|c| {
                                    let name = c
                                        .get("name")
                                        .or_else(|| c.get("artist").and_then(|a| a.get("name")))
                                        .and_then(Value::as_str)
                                        .unwrap_or("");
                                    let join =
                                        c.get("joinphrase").and_then(Value::as_str).unwrap_or("");
                                    [name, join]
                                })
                                .collect::<String>()
                        })
                        .unwrap_or_default()
                        .trim()
                        .to_string();

                    let title_sim = jaro_winkler(&title_lower, &rec_title.to_lowercase());
                    let artist_sim = jaro_winkler(&artist_lower, &rec_artist.to_lowercase());

                    if title_sim < MIN_SIM || artist_sim < MIN_SIM {
                        continue;
                    }

                    let combined = (artist_sim * 0.4 + title_sim * 0.6) * (rec_score / 100.0);

                    if combined > best_score {
                        best_score = combined;

                        let mbid = rec
                            .get("id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();
                        let release = rec
                            .get("releases")
                            .and_then(Value::as_array)
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
                        best = Some((
                            mbid,
                            rec_artist,
                            release_mbid,
                            release_title,
                            release_date,
                            combined,
                        ));
                    }
                }

                match best {
                    Some((
                        mbid,
                        rec_artist,
                        release_mbid,
                        release_title,
                        release_date,
                        combined,
                    )) => {
                        Ok(Some(json!({
                            "status": "ok",
                            "provider": "musicbrainz",
                            "recordingMbid": mbid,
                            // matchScore is 0-1 combined similarity score (ported from Python)
                            "matchScore": combined,
                            "artist": rec_artist,
                            "title": title,
                            "releaseMbid": release_mbid,
                            "releaseTitle": release_title,
                            "releaseDate": release_date,
                        })))
                    }
                    None => {
                        // No result passed the similarity gate
                        Ok(Some(json!({
                            "status": "not_found",
                            "provider": "musicbrainz",
                            "artist": artist,
                            "title": title,
                            "note": "No result passed similarity gate (min 0.60)",
                        })))
                    }
                }
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
        Self {
            client_key: client_key.into(),
        }
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
                let body: Value = serde_json::from_slice(&out.stdout).unwrap_or(Value::Null);
                let dur = body.get("duration").and_then(Value::as_f64).unwrap_or(0.0);
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
            .set(
                "User-Agent",
                "Lyra/0.1 (https://github.com/snappedpoem1/lyra)",
            )
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
                        let score = hit.get("score").and_then(Value::as_f64).unwrap_or(0.0);
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

// ── Last.fm adapter ───────────────────────────────────────────────────────────

const LASTFM_JUNK_TAGS: &[&str] = &[
    "seen live",
    "favorites",
    "favourite",
    "favourites",
    "my favorite",
    "my favourite",
    "awesome",
    "love",
    "cool",
    "amazing",
];

const LASTFM_BASE: &str = "https://ws.audioscrobbler.com/2.0/";
const LASTFM_UA: &str = "Lyra/0.1 (https://github.com/snappedpoem1/lyra)";
const LASTFM_RATE_MS: u64 = 250;

fn lastfm_call(api_key: &str, method: &str, params: &[(&str, &str)]) -> Value {
    std::thread::sleep(std::time::Duration::from_millis(LASTFM_RATE_MS));
    let mut req = ureq::get(LASTFM_BASE)
        .set("User-Agent", LASTFM_UA)
        .query("method", method)
        .query("api_key", api_key)
        .query("format", "json")
        .query("autocorrect", "1");
    for (k, v) in params {
        req = req.query(k, v);
    }
    req.call()
        .ok()
        .and_then(|r| r.into_json::<Value>().ok())
        .unwrap_or(Value::Null)
}

fn lastfm_extract_tags(toptags_node: &Value, limit: usize) -> Vec<String> {
    let tag_arr = match toptags_node.get("tag") {
        Some(Value::Array(arr)) => arr.clone(),
        Some(single @ Value::Object(_)) => vec![single.clone()],
        _ => return vec![],
    };
    let mut out = Vec::new();
    for tag in &tag_arr {
        let name = tag
            .get("name")
            .and_then(Value::as_str)
            .map(|s| s.trim().to_ascii_lowercase())
            .unwrap_or_default();
        if name.is_empty() || LASTFM_JUNK_TAGS.contains(&name.as_str()) {
            continue;
        }
        if !out.contains(&name) {
            out.push(name);
        }
        if out.len() >= limit {
            break;
        }
    }
    out
}

pub struct LastFmAdapter {
    api_key: String,
}

impl LastFmAdapter {
    pub fn from_db(conn: &Connection) -> Self {
        let api_key = conn
            .query_row(
                "SELECT config_json FROM provider_configs WHERE provider_key = 'lastfm'",
                [],
                |row| row.get::<_, String>(0),
            )
            .ok()
            .and_then(|json| serde_json::from_str::<Value>(&json).ok())
            .and_then(|v| {
                v.get("lastfm_api_key")
                    .or_else(|| v.get("LASTFM_API_KEY"))
                    .and_then(Value::as_str)
                    .map(String::from)
            })
            .unwrap_or_default();
        Self { api_key }
    }
}

impl EnricherAdapter for LastFmAdapter {
    fn name(&self) -> &str {
        "lastfm"
    }

    fn enrich(
        &self,
        _conn: &Connection,
        _track_id: i64,
        artist: &str,
        title: &str,
        _path: &str,
    ) -> LyraResult<Option<Value>> {
        if self.api_key.is_empty() {
            return Ok(Some(json!({
                "status": "not_configured",
                "provider": "lastfm",
                "artist": artist,
                "title": title,
            })));
        }

        // 1. track.getInfo — primary data + tag cascade
        let info_body = lastfm_call(
            &self.api_key,
            "track.getInfo",
            &[("artist", artist), ("track", title)],
        );
        if info_body.get("error").is_some() {
            return Ok(Some(json!({
                "status": "not_found",
                "provider": "lastfm",
                "artist": artist,
                "title": title,
            })));
        }

        let track = info_body.get("track").cloned().unwrap_or(Value::Null);
        let listeners = track
            .get("listeners")
            .and_then(Value::as_str)
            .and_then(|s| s.parse::<i64>().ok())
            .unwrap_or(0);
        let playcount = track
            .get("playcount")
            .and_then(Value::as_str)
            .and_then(|s| s.parse::<i64>().ok())
            .unwrap_or(0);
        let mbid = track
            .get("mbid")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let summary = track
            .get("wiki")
            .and_then(|w| w.get("summary"))
            .and_then(Value::as_str)
            .map(|s| {
                s.split("<a href=\"https://www.last.fm")
                    .next()
                    .unwrap_or(s)
                    .trim()
                    .to_string()
            })
            .unwrap_or_default();

        // Tag cascade: track.getInfo → track.getTopTags → artist.getTopTags
        let mut tags =
            lastfm_extract_tags(&track.get("toptags").cloned().unwrap_or(Value::Null), 5);
        if tags.is_empty() {
            let top = lastfm_call(
                &self.api_key,
                "track.getTopTags",
                &[("artist", artist), ("track", title)],
            );
            tags = lastfm_extract_tags(&top.get("toptags").cloned().unwrap_or(Value::Null), 5);
        }
        if tags.is_empty() {
            let atop = lastfm_call(&self.api_key, "artist.getTopTags", &[("artist", artist)]);
            tags = lastfm_extract_tags(&atop.get("toptags").cloned().unwrap_or(Value::Null), 5);
        }

        // 2. track.getSimilar
        let sim_tracks_body = lastfm_call(
            &self.api_key,
            "track.getSimilar",
            &[("artist", artist), ("track", title), ("limit", "10")],
        );
        let similar_tracks: Vec<Value> = sim_tracks_body
            .pointer("/similartracks/track")
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .take(10)
                    .filter_map(|row| {
                        let name = row.get("name").and_then(Value::as_str)?;
                        let sim_artist = row
                            .get("artist")
                            .map(|a| {
                                if a.is_object() {
                                    a.get("name").and_then(Value::as_str).unwrap_or("")
                                } else {
                                    a.as_str().unwrap_or("")
                                }
                            })
                            .unwrap_or("");
                        Some(json!({"artist": sim_artist, "title": name}))
                    })
                    .collect()
            })
            .unwrap_or_default();

        // 3. artist.getSimilar
        let sim_artists_body = lastfm_call(
            &self.api_key,
            "artist.getSimilar",
            &[("artist", artist), ("limit", "10")],
        );
        let similar_artists: Vec<String> = sim_artists_body
            .pointer("/similarartists/artist")
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .take(10)
                    .filter_map(|row| row.get("name").and_then(Value::as_str).map(String::from))
                    .collect()
            })
            .unwrap_or_default();

        Ok(Some(json!({
            "status": "ok",
            "provider": "lastfm",
            "artist": artist,
            "title": title,
            "listeners": listeners,
            "playcount": playcount,
            "tags": tags,
            "mbid": mbid,
            "summary": summary,
            "similarTracks": similar_tracks,
            "similarArtists": similar_artists,
        })))
    }
}

// ── Discogs adapter ───────────────────────────────────────────────────────────

pub struct DiscogsAdapter {
    user_token: String,
}

impl DiscogsAdapter {
    pub fn from_db(conn: &Connection) -> Self {
        let user_token = conn
            .query_row(
                "SELECT config_json FROM provider_configs WHERE provider_key = 'discogs'",
                [],
                |row| row.get::<_, String>(0),
            )
            .ok()
            .and_then(|json| serde_json::from_str::<Value>(&json).ok())
            .and_then(|v| {
                v.get("discogs_token")
                    .or_else(|| v.get("DISCOGS_TOKEN"))
                    .or_else(|| v.get("discogs_user_token"))
                    .and_then(Value::as_str)
                    .map(String::from)
            })
            .unwrap_or_default();
        Self { user_token }
    }
}

impl EnricherAdapter for DiscogsAdapter {
    fn name(&self) -> &str {
        "discogs"
    }

    fn enrich(
        &self,
        conn: &Connection,
        track_id: i64,
        artist: &str,
        title: &str,
        _path: &str,
    ) -> LyraResult<Option<Value>> {
        // Look up the album title from the DB — Discogs is a release database;
        // searching artist + album gives far better results than artist + track title.
        let album: Option<String> = conn
            .query_row(
                "SELECT al.title FROM tracks t
                 LEFT JOIN albums al ON al.id = t.album_id
                 WHERE t.id = ?1",
                params![track_id],
                |row| row.get(0),
            )
            .ok()
            .flatten()
            .filter(|s: &String| !s.trim().is_empty());

        let mut request = ureq::get("https://api.discogs.com/database/search")
            .set(
                "User-Agent",
                "Lyra/0.1 +https://github.com/snappedpoem1/lyra",
            )
            .query("type", "release")
            .query("per_page", "5");

        // Prefer artist + release_title when album is known (matches Python behaviour);
        // fall back to free-text artist + track title otherwise.
        if let Some(ref album_title) = album {
            request = request
                .query("artist", artist)
                .query("release_title", album_title);
        } else {
            request = request.query("q", &format!("{artist} {title}"));
        }

        if !self.user_token.is_empty() {
            request = request.set(
                "Authorization",
                &format!("Discogs token={}", self.user_token),
            );
        }

        // Discogs rate limit: ~60 req/min for authenticated, ~25 for unauthenticated.
        // A 1-second delay keeps us well within limits.
        std::thread::sleep(std::time::Duration::from_millis(1000));

        match request.call() {
            Ok(response) => {
                let body: Value = response.into_json().unwrap_or(Value::Null);
                let first = body
                    .get("results")
                    .and_then(Value::as_array)
                    .and_then(|arr| arr.first())
                    .cloned();

                match first {
                    None => Ok(Some(json!({
                        "status": "not_found",
                        "provider": "discogs",
                        "artist": artist,
                        "title": title,
                    }))),
                    Some(hit) => {
                        let year = hit
                            .get("year")
                            .cloned()
                            .map(|v| match v {
                                Value::String(s) => s,
                                Value::Number(n) => n.to_string(),
                                _ => String::new(),
                            })
                            .unwrap_or_default();

                        let genres: Vec<String> = hit
                            .get("genre")
                            .and_then(Value::as_array)
                            .map(|arr| {
                                arr.iter()
                                    .filter_map(|v| v.as_str().map(String::from))
                                    .collect()
                            })
                            .unwrap_or_default();

                        let styles: Vec<String> = hit
                            .get("style")
                            .and_then(Value::as_array)
                            .map(|arr| {
                                arr.iter()
                                    .take(3)
                                    .filter_map(|v| v.as_str().map(String::from))
                                    .collect()
                            })
                            .unwrap_or_default();

                        let label = hit
                            .get("label")
                            .and_then(Value::as_array)
                            .and_then(|arr| arr.first())
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();

                        let country = hit
                            .get("country")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();

                        let cover_image = hit
                            .get("cover_image")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();

                        Ok(Some(json!({
                            "status": "ok",
                            "provider": "discogs",
                            "artist": artist,
                            "title": title,
                            "year": year,
                            "genres": genres,
                            "styles": styles,
                            "label": label,
                            "country": country,
                            "coverImage": cover_image,
                        })))
                    }
                }
            }
            Err(e) => {
                warn!("Discogs request failed for {artist} / {title}: {e}");
                Ok(Some(json!({
                    "status": "error",
                    "provider": "discogs",
                    "artist": artist,
                    "title": title,
                    "error": e.to_string(),
                })))
            }
        }
    }
}

// ── Genius adapter ────────────────────────────────────────────────────────────
//
// Queries the Genius search API for the track and returns the canonical Genius
// URL, full_title, and album art thumbnail.  Actual lyrics text is not returned
// by the API, but the URL can be opened by the user.

pub struct GeniusAdapter {
    token: String,
}

impl GeniusAdapter {
    pub fn from_db(conn: &Connection) -> Self {
        let token = conn
            .query_row(
                "SELECT config_json FROM provider_configs WHERE provider_key = 'genius'",
                [],
                |row| row.get::<_, String>(0),
            )
            .ok()
            .and_then(|json| serde_json::from_str::<Value>(&json).ok())
            .and_then(|v| {
                v.get("genius_token")
                    .or_else(|| v.get("GENIUS_TOKEN"))
                    .or_else(|| v.get("genius_access_token"))
                    .or_else(|| v.get("GENIUS_ACCESS_TOKEN"))
                    .and_then(Value::as_str)
                    .map(String::from)
            })
            .unwrap_or_default();
        Self { token }
    }
}

impl EnricherAdapter for GeniusAdapter {
    fn name(&self) -> &str {
        "genius"
    }

    fn enrich(
        &self,
        _conn: &Connection,
        _track_id: i64,
        artist: &str,
        title: &str,
        _path: &str,
    ) -> LyraResult<Option<Value>> {
        if self.token.is_empty() {
            return Ok(Some(json!({
                "status": "not_configured",
                "provider": "genius",
                "artist": artist,
                "title": title,
            })));
        }

        let query = format!("{artist} {title}");
        let result = ureq::get("https://api.genius.com/search")
            .set(
                "User-Agent",
                "Lyra/0.1 (https://github.com/snappedpoem1/lyra)",
            )
            .set("Authorization", &format!("Bearer {}", self.token))
            .query("q", &query)
            .call();

        match result {
            Ok(response) => {
                let body: Value = response.into_json().unwrap_or(Value::Null);
                let hit = body.pointer("/response/hits/0/result").cloned();

                match hit {
                    None => Ok(Some(json!({
                        "status": "not_found",
                        "provider": "genius",
                        "artist": artist,
                        "title": title,
                    }))),
                    Some(result) => {
                        let url = result
                            .get("url")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();
                        let full_title = result
                            .get("full_title")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();
                        let art_url = result
                            .get("song_art_image_thumbnail_url")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();
                        let genius_id = result.get("id").and_then(Value::as_i64).unwrap_or(0);
                        let artist_name = result
                            .pointer("/primary_artist/name")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string();

                        Ok(Some(json!({
                            "status": "ok",
                            "provider": "genius",
                            "artist": artist,
                            "title": title,
                            "geniusId": genius_id,
                            "fullTitle": full_title,
                            "artistName": artist_name,
                            "url": url,
                            "artUrl": art_url,
                        })))
                    }
                }
            }
            Err(e) => {
                warn!("Genius request failed for {artist} / {title}: {e}");
                Ok(Some(json!({
                    "status": "error",
                    "provider": "genius",
                    "artist": artist,
                    "title": title,
                    "error": e.to_string(),
                })))
            }
        }
    }
}

// ── LRC sidecar adapter ───────────────────────────────────────────────────────
//
// Checks for a `.lrc` file co-located with the audio file (same path, `.lrc`
// extension).  Returns the raw LRC content so the UI can display synchronized
// lyrics without any network call.

pub struct LrcSidecarAdapter;

impl EnricherAdapter for LrcSidecarAdapter {
    fn name(&self) -> &str {
        "lrc_sidecar"
    }

    fn enrich(
        &self,
        _conn: &Connection,
        _track_id: i64,
        artist: &str,
        title: &str,
        path: &str,
    ) -> LyraResult<Option<Value>> {
        use std::path::Path;
        let audio_path = Path::new(path);
        let lrc_path = audio_path.with_extension("lrc");
        if !lrc_path.exists() {
            return Ok(Some(json!({
                "status": "not_found",
                "provider": "lrc_sidecar",
                "artist": artist,
                "title": title,
            })));
        }
        match std::fs::read_to_string(&lrc_path) {
            Ok(content) => Ok(Some(json!({
                "status": "ok",
                "provider": "lrc_sidecar",
                "artist": artist,
                "title": title,
                "lrcContent": content,
                "lrcPath": lrc_path.to_string_lossy(),
            }))),
            Err(e) => Ok(Some(json!({
                "status": "error",
                "provider": "lrc_sidecar",
                "artist": artist,
                "title": title,
                "error": e.to_string(),
            }))),
        }
    }
}

// ── Dispatcher ────────────────────────────────────────────────────────────────

pub struct EnrichmentDispatcher {
    adapters: Vec<Box<dyn EnricherAdapter>>,
}

impl EnrichmentDispatcher {
    /// Full dispatcher: all providers, credentials read from DB.
    pub fn new(conn: &Connection) -> Self {
        Self {
            adapters: vec![
                Box::new(MusicBrainzAdapter),
                Box::new(AcoustIDAdapter::default()),
                Box::new(LastFmAdapter::from_db(conn)),
                Box::new(DiscogsAdapter::from_db(conn)),
                Box::new(GeniusAdapter::from_db(conn)),
                Box::new(LrcSidecarAdapter),
            ],
        }
    }

    /// Background-safe dispatcher: only MusicBrainz + AcoustID (no credential reads needed).
    pub fn background() -> Self {
        Self {
            adapters: vec![
                Box::new(MusicBrainzAdapter),
                Box::new(AcoustIDAdapter::default()),
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
            let status_ok = payload
                .get("status")
                .and_then(Value::as_str)
                .map(|s| s == "ok")
                .unwrap_or(false);
            if !status_ok {
                degraded.push(provider.to_string());
            }
            // Write the first tag back to tracks.genre when the enricher supplies
            // tags and the track doesn't already have a genre set.
            if status_ok {
                let first_tag = payload
                    .get("tags")
                    .and_then(Value::as_array)
                    .and_then(|arr| arr.first())
                    .and_then(Value::as_str);
                if let Some(genre) = first_tag {
                    let now = Utc::now().to_rfc3339();
                    let _ = conn.execute(
                        "UPDATE tracks SET
                            genre = CASE WHEN genre IS NULL OR trim(genre) = '' THEN ?1 ELSE genre END,
                            last_enriched_at = ?2
                         WHERE id = ?3",
                        params![genre, now, track_id],
                    );
                }
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

/// Last.fm scrobbling and Now Playing notification.
///
/// Requires provider config keys for the 'lastfm' provider:
///   - lastfm_api_key      (public key)
///   - lastfm_api_secret   (shared secret for signing)
///   - lastfm_session_key  (per-user session token — obtained via auth.getMobileSession or web OAuth)
///
/// If any of these are absent the functions return Ok(()) silently (no-op).
use rusqlite::Connection;
use serde_json::Value;
use std::collections::BTreeMap;
use tracing::{info, warn};

const LASTFM_API_URL: &str = "https://ws.audioscrobbler.com/2.0/";

struct LastFmCreds {
    api_key: String,
    api_secret: String,
    session_key: String,
}

impl LastFmCreds {
    fn from_db(conn: &Connection) -> Option<Self> {
        let json: String = conn
            .query_row(
                "SELECT config_json FROM provider_configs WHERE provider_key = 'lastfm'",
                [],
                |row| row.get(0),
            )
            .ok()?;
        let v: Value = serde_json::from_str(&json).ok()?;
        let get = |k1: &str, k2: &str| -> Option<String> {
            v.get(k1)
                .or_else(|| v.get(k2))
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty())
                .map(String::from)
        };
        let api_key = get("lastfm_api_key", "LASTFM_API_KEY")?;
        let api_secret = get("lastfm_api_secret", "LASTFM_API_SECRET")?;
        let session_key = get("lastfm_session_key", "LASTFM_SESSION_KEY")?;
        Some(Self {
            api_key,
            api_secret,
            session_key,
        })
    }
}

/// Compute the Last.fm API signature: md5(sorted_key_value_pairs + api_secret)
fn sign(params: &BTreeMap<&str, String>, api_secret: &str) -> String {
    let mut sig_base = String::new();
    for (k, v) in params {
        sig_base.push_str(k);
        sig_base.push_str(v);
    }
    sig_base.push_str(api_secret);
    let digest = md5::compute(sig_base.as_bytes());
    format!("{:x}", digest)
}

/// Send a "track.updateNowPlaying" notification to Last.fm.
/// Call this when a track begins playing.
pub fn now_playing(conn: &Connection, artist: &str, title: &str, album: &str, duration_secs: u64) {
    let Some(creds) = LastFmCreds::from_db(conn) else {
        return;
    };
    let mut params = BTreeMap::new();
    params.insert("method", "track.updateNowPlaying".to_string());
    params.insert("api_key", creds.api_key.clone());
    params.insert("sk", creds.session_key.clone());
    params.insert("artist", artist.to_string());
    params.insert("track", title.to_string());
    params.insert("album", album.to_string());
    if duration_secs > 0 {
        params.insert("duration", duration_secs.to_string());
    }
    let sig = sign(&params, &creds.api_secret);
    params.insert("api_sig", sig);
    params.insert("format", "json".to_string());

    let form_data: Vec<(String, String)> = params
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();
    match ureq::post(LASTFM_API_URL).send_form(
        &form_data
            .iter()
            .map(|(k, v)| (k.as_str(), v.as_str()))
            .collect::<Vec<_>>(),
    ) {
        Ok(_) => info!("Last.fm now playing: {artist} - {title}"),
        Err(e) => warn!("Last.fm now_playing failed: {e}"),
    }
}

/// Submit a scrobble to Last.fm. Call this when playback completes (completion_rate >= 0.5
/// and track duration > 30s, as per Last.fm guidelines).
pub fn scrobble(
    conn: &Connection,
    artist: &str,
    title: &str,
    album: &str,
    timestamp_unix: i64,
    duration_secs: u64,
) {
    // Last.fm guidelines: scrobble only if track >= 30s and listened >= 50%
    if duration_secs < 30 {
        return;
    }
    let Some(creds) = LastFmCreds::from_db(conn) else {
        return;
    };
    let mut params = BTreeMap::new();
    params.insert("method", "track.scrobble".to_string());
    params.insert("api_key", creds.api_key.clone());
    params.insert("sk", creds.session_key.clone());
    params.insert("artist[0]", artist.to_string());
    params.insert("track[0]", title.to_string());
    params.insert("album[0]", album.to_string());
    params.insert("timestamp[0]", timestamp_unix.to_string());
    if duration_secs > 0 {
        params.insert("duration[0]", duration_secs.to_string());
    }
    let sig = sign(&params, &creds.api_secret);
    params.insert("api_sig", sig);
    params.insert("format", "json".to_string());

    let form_data: Vec<(String, String)> = params
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();
    match ureq::post(LASTFM_API_URL).send_form(
        &form_data
            .iter()
            .map(|(k, v)| (k.as_str(), v.as_str()))
            .collect::<Vec<_>>(),
    ) {
        Ok(resp) => match resp.into_json::<Value>() {
            Ok(body) => {
                if body.get("error").is_some() {
                    warn!(
                        "Last.fm scrobble error for {artist} - {title}: {:?}",
                        body.get("message")
                    );
                } else {
                    info!("Last.fm scrobbled: {artist} - {title}");
                }
            }
            Err(e) => warn!("Last.fm scrobble response parse error: {e}"),
        },
        Err(e) => warn!("Last.fm scrobble failed: {e}"),
    }
}

/// Obtain a Last.fm session key via the "mobile session" method (username + password).
/// On success, returns the session key string. This should be stored in provider config
/// as `lastfm_session_key`.
pub fn get_mobile_session(
    api_key: &str,
    api_secret: &str,
    username: &str,
    password: &str,
) -> Result<String, String> {
    let mut params = BTreeMap::new();
    params.insert("method", "auth.getMobileSession".to_string());
    params.insert("api_key", api_key.to_string());
    params.insert("username", username.to_string());
    params.insert("password", password.to_string());
    let sig = sign(&params, api_secret);
    params.insert("api_sig", sig);
    params.insert("format", "json".to_string());

    let form_data: Vec<(String, String)> = params
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();
    let resp = ureq::post(LASTFM_API_URL)
        .send_form(
            &form_data
                .iter()
                .map(|(k, v)| (k.as_str(), v.as_str()))
                .collect::<Vec<_>>(),
        )
        .map_err(|e| format!("HTTP error: {e}"))?;
    let body: Value = resp.into_json().map_err(|e| format!("Parse error: {e}"))?;
    if let Some(err) = body.get("error") {
        let msg = body
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("unknown");
        return Err(format!("Last.fm error {err}: {msg}"));
    }
    body.pointer("/session/key")
        .and_then(Value::as_str)
        .map(String::from)
        .ok_or_else(|| "session key not found in response".to_string())
}

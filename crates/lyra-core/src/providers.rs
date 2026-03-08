use std::collections::HashMap;
use std::path::Path;
use std::time::Instant;

use chrono::Utc;
use dotenvy::from_path_iter;
use keyring::Entry;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use tracing::warn;

use crate::commands::{ProviderConfigRecord, ProviderHealth, ProviderValidationResult};
use crate::errors::LyraResult;

/// Helper function to base64-encode a string (used for HTTP Basic auth).
fn base64_encode(s: &str) -> String {
    use base64::prelude::*;
    BASE64_STANDARD.encode(s.as_bytes())
}

#[derive(Clone, Debug)]
pub struct ProviderCapabilitySeed {
    pub provider_key: &'static str,
    pub display_name: &'static str,
    pub capabilities: Vec<&'static str>,
}

pub fn default_provider_capabilities() -> Vec<ProviderCapabilitySeed> {
    vec![
        ProviderCapabilitySeed {
            provider_key: "qobuz",
            display_name: "Qobuz",
            capabilities: vec!["search", "acquire"],
        },
        ProviderCapabilitySeed {
            provider_key: "streamrip",
            display_name: "Streamrip",
            capabilities: vec!["acquire"],
        },
        ProviderCapabilitySeed {
            provider_key: "spotdl",
            display_name: "SpotDL",
            capabilities: vec!["fallback-acquire"],
        },
        ProviderCapabilitySeed {
            provider_key: "prowlarr",
            display_name: "Prowlarr",
            capabilities: vec!["search", "torrent-indexer"],
        },
        ProviderCapabilitySeed {
            provider_key: "realdebrid",
            display_name: "Real-Debrid",
            capabilities: vec!["cached-downloads", "torrent-conversion"],
        },
        ProviderCapabilitySeed {
            provider_key: "slskd",
            display_name: "Slskd (Soulseek)",
            capabilities: vec!["p2p-search", "p2p-download"],
        },
        ProviderCapabilitySeed {
            provider_key: "lastfm",
            display_name: "Last.fm",
            capabilities: vec!["artist-context", "similarity"],
        },
        ProviderCapabilitySeed {
            provider_key: "musicbrainz",
            display_name: "MusicBrainz",
            capabilities: vec!["identity", "release-metadata"],
        },
        ProviderCapabilitySeed {
            provider_key: "genius",
            display_name: "Genius",
            capabilities: vec!["lyrics"],
        },
        ProviderCapabilitySeed {
            provider_key: "spotify",
            display_name: "Spotify",
            capabilities: vec!["history-import", "library-import"],
        },
        ProviderCapabilitySeed {
            provider_key: "listenbrainz",
            display_name: "ListenBrainz",
            capabilities: vec!["community-weather"],
        },
        ProviderCapabilitySeed {
            provider_key: "discogs",
            display_name: "Discogs",
            capabilities: vec!["release-metadata", "identity"],
        },
        ProviderCapabilitySeed {
            provider_key: "acoustid",
            display_name: "AcoustID",
            capabilities: vec!["fingerprint", "identity"],
        },
    ]
}

pub fn provider_env_mappings() -> HashMap<&'static str, Vec<&'static str>> {
    HashMap::from([
        (
            "qobuz",
            vec![
                "QOBUZ_EMAIL",
                "QOBUZ_PASSWORD",
                "QOBUZ_USERNAME",
                "QOBUZ_APP_ID",
                "QOBUZ_SECRETS",
                "QOBUZ_QUALITY",
                "QOBUZ_SERVICE_URL",
            ],
        ),
        (
            "streamrip",
            vec![
                "LYRA_STREAMRIP_BINARY",
                "LYRA_STREAMRIP_CMD_TEMPLATE",
                "LYRA_STREAMRIP_SOURCE",
            ],
        ),
        (
            "spotdl",
            vec!["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
        ),
        (
            "prowlarr",
            vec!["PROWLARR_URL", "PROWLARR_API_KEY"],
        ),
        (
            "realdebrid",
            vec!["REAL_DEBRID_KEY", "REAL_DEBRID_API_KEY"],
        ),
        (
            "slskd",
            vec![
                "LYRA_PROTOCOL_NODE_USER",
                "LYRA_PROTOCOL_NODE_PASS",
                "SLSKD_URL",
                "SLSKD_API_KEY",
            ],
        ),
        ("lastfm", vec!["LASTFM_API_KEY", "LASTFM_API_SECRET"]),
        ("genius", vec!["GENIUS_TOKEN", "GENIUS_ACCESS_TOKEN"]),
        (
            "spotify",
            vec!["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
        ),
        ("listenbrainz", vec!["LISTENBRAINZ_TOKEN"]),
        (
            "musicbrainz",
            vec!["MUSICBRAINZ_USERNAME", "MUSICBRAINZ_PASSWORD"],
        ),
        ("acoustid", vec!["ACOUSTID_API_KEY"]),
        ("discogs", vec!["DISCOGS_TOKEN", "DISCOGS_USER_TOKEN"]),
    ])
}

pub fn list_provider_configs(conn: &Connection) -> LyraResult<Vec<ProviderConfigRecord>> {
    let mut stmt = conn.prepare(
        "
        SELECT pcap.provider_key,
               pcap.display_name,
               COALESCE(pc.enabled, 0),
               COALESCE(pc.config_json, '{}'),
               pcap.capabilities_json
        FROM provider_capabilities pcap
        LEFT JOIN provider_configs pc ON pc.provider_key = pcap.provider_key
        ORDER BY pcap.display_name ASC
        ",
    )?;
    let rows = stmt.query_map([], |row| {
        let config_json: String = row.get(3)?;
        let config: Value = serde_json::from_str(&config_json).unwrap_or_else(|_| json!({}));
        let capabilities_json: String = row.get(4)?;
        let capabilities: Vec<String> =
            serde_json::from_str(&capabilities_json).unwrap_or_default();
        Ok(ProviderConfigRecord {
            provider_key: row.get(0)?,
            display_name: row.get(1)?,
            enabled: row.get::<_, bool>(2)?,
            is_configured: config
                .as_object()
                .map(|value| !value.is_empty())
                .unwrap_or(false),
            config,
            capabilities,
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn update_provider_config(
    conn: &Connection,
    provider_key: &str,
    enabled: bool,
    values: &Value,
) -> LyraResult<()> {
    let display_name = conn
        .query_row(
            "SELECT display_name FROM provider_capabilities WHERE provider_key = ?1",
            params![provider_key],
            |row| row.get::<_, String>(0),
        )
        .unwrap_or_else(|_| provider_key.to_string());
    conn.execute(
        "
        INSERT INTO provider_configs (provider_key, display_name, enabled, config_json, updated_at)
        VALUES (?1, ?2, ?3, ?4, ?5)
        ON CONFLICT(provider_key) DO UPDATE SET
          display_name = excluded.display_name,
          enabled = excluded.enabled,
          config_json = excluded.config_json,
          updated_at = excluded.updated_at
        ",
        params![
            provider_key,
            display_name,
            enabled,
            serde_json::to_string(values)?,
            Utc::now().to_rfc3339(),
        ],
    )?;
    Ok(())
}

pub fn import_env_file(
    conn: &Connection,
    env_path: &Path,
    imported: &mut Vec<String>,
    unsupported: &mut Vec<String>,
) -> LyraResult<usize> {
    let mappings = provider_env_mappings();
    let mut env_values: HashMap<String, String> = HashMap::new();
    for item in from_path_iter(env_path)? {
        let (key, value) = item?;
        env_values.insert(key, value);
    }

    let mut imported_count = 0_usize;
    for (provider_key, keys) in &mappings {
        let mut values = serde_json::Map::new();
        for key in keys {
            if let Some(value) = env_values.get(*key) {
                values.insert(key.to_lowercase(), Value::String(value.clone()));
            }
        }
        if !values.is_empty() {
            update_provider_config(conn, provider_key, true, &Value::Object(values))?;
            imported.push((*provider_key).to_string());
            imported_count += 1;
        }
    }

    for key in env_values.keys() {
        if !mappings
            .values()
            .flatten()
            .any(|candidate| candidate == key)
        {
            unsupported.push(key.to_string());
        }
    }
    unsupported.sort();
    unsupported.dedup();
    Ok(imported_count)
}

// ── Provider health ──────────────────────────────────────────────────────────

pub fn get_provider_health(conn: &Connection, provider_key: &str) -> LyraResult<ProviderHealth> {
    let row = conn
        .query_row(
            "SELECT provider_key, status, failure_count, last_failure, last_success, circuit_open, last_check
             FROM provider_health WHERE provider_key = ?1",
            params![provider_key],
            map_provider_health,
        )
        .optional()?;
    Ok(row.unwrap_or_else(|| ProviderHealth {
        provider_key: provider_key.to_string(),
        status: "healthy".to_string(),
        failure_count: 0,
        last_failure: None,
        last_success: None,
        circuit_open: false,
        last_check: chrono::Utc::now().to_rfc3339(),
    }))
}

pub fn list_provider_health(conn: &Connection) -> LyraResult<Vec<ProviderHealth>> {
    let mut stmt = conn.prepare(
        "SELECT provider_key, status, failure_count, last_failure, last_success, circuit_open, last_check
         FROM provider_health ORDER BY provider_key ASC",
    )?;
    let rows = stmt.query_map([], map_provider_health)?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn record_provider_success(conn: &Connection, provider_key: &str) -> LyraResult<()> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO provider_health (provider_key, status, failure_count, last_success, circuit_open, last_check)
         VALUES (?1, 'healthy', 0, ?2, 0, ?2)
         ON CONFLICT(provider_key) DO UPDATE SET
           status = 'healthy',
           failure_count = 0,
           last_success = excluded.last_success,
           circuit_open = 0,
           last_check = excluded.last_check",
        params![provider_key, now],
    )?;
    Ok(())
}

pub fn record_provider_failure(conn: &Connection, provider_key: &str) -> LyraResult<ProviderHealth> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO provider_health (provider_key, status, failure_count, last_failure, circuit_open, last_check)
         VALUES (?1, 'degraded', 1, ?2, 0, ?2)
         ON CONFLICT(provider_key) DO UPDATE SET
           failure_count = failure_count + 1,
           status = CASE WHEN failure_count + 1 >= 5 THEN 'failed' ELSE 'degraded' END,
           last_failure = excluded.last_failure,
           circuit_open = CASE WHEN failure_count + 1 >= 5 THEN 1 ELSE 0 END,
           last_check = excluded.last_check",
        params![provider_key, now],
    )?;
    get_provider_health(conn, provider_key)
}

pub fn reset_provider_health(conn: &Connection, provider_key: &str) -> LyraResult<()> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO provider_health (provider_key, status, failure_count, circuit_open, last_check)
         VALUES (?1, 'healthy', 0, 0, ?2)
         ON CONFLICT(provider_key) DO UPDATE SET
           status = 'healthy',
           failure_count = 0,
           circuit_open = 0,
           last_check = excluded.last_check",
        params![provider_key, now],
    )?;
    Ok(())
}

pub fn is_circuit_open(conn: &Connection, provider_key: &str) -> bool {
    conn.query_row(
        "SELECT circuit_open FROM provider_health WHERE provider_key = ?1",
        params![provider_key],
        |row| row.get::<_, i64>(0),
    )
    .map(|v| v != 0)
    .unwrap_or(false)
}

fn map_provider_health(row: &rusqlite::Row<'_>) -> rusqlite::Result<ProviderHealth> {
    Ok(ProviderHealth {
        provider_key: row.get(0)?,
        status: row.get(1)?,
        failure_count: row.get(2)?,
        last_failure: row.get(3)?,
        last_success: row.get(4)?,
        circuit_open: row.get::<_, i64>(5).map(|v| v != 0)?,
        last_check: row.get(6)?,
    })
}

// ── Provider credential validation ───────────────────────────────────────────

/// Perform a lightweight credential probe for the given provider.
/// Records provider health based on the result.
pub fn validate_provider(
    conn: &Connection,
    provider_key: &str,
) -> LyraResult<ProviderValidationResult> {
    let config_json: Option<String> = conn
        .query_row(
            "SELECT config_json FROM provider_configs WHERE provider_key = ?1",
            params![provider_key],
            |row| row.get(0),
        )
        .optional()?;

    let config: Value = config_json
        .as_deref()
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_else(|| json!({}));

    let t0 = Instant::now();

    let result = match provider_key {
        "lastfm" => {
            let api_key = config
                .get("lastfm_api_key")
                .or_else(|| config.get("LASTFM_API_KEY"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if api_key.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("No API key configured".to_string()),
                    detail: None,
                });
            }
            ureq::get("https://ws.audioscrobbler.com/2.0/")
                .set("User-Agent", "Lyra/0.1")
                .query("method", "tag.getTopTracks")
                .query("tag", "rock")
                .query("limit", "1")
                .query("api_key", api_key)
                .query("format", "json")
                .call()
                .map(|_| None::<String>)
                .map_err(|e| e.to_string())
        }
        "discogs" => {
            let token = config
                .get("discogs_token")
                .or_else(|| config.get("DISCOGS_TOKEN"))
                .or_else(|| config.get("discogs_user_token"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if token.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("No user token configured".to_string()),
                    detail: None,
                });
            }
            ureq::get("https://api.discogs.com/oauth/identity")
                .set("User-Agent", "Lyra/0.1 +https://github.com/snappedpoem1/lyra")
                .set("Authorization", &format!("Discogs token={token}"))
                .call()
                .map(|resp| {
                    resp.into_json::<Value>()
                        .ok()
                        .and_then(|v| v.get("username").and_then(Value::as_str).map(String::from))
                })
                .map_err(|e| e.to_string())
        }
        "genius" => {
            let token = config
                .get("genius_token")
                .or_else(|| config.get("GENIUS_TOKEN"))
                .or_else(|| config.get("genius_access_token"))
                .or_else(|| config.get("GENIUS_ACCESS_TOKEN"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if token.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("No API token configured".to_string()),
                    detail: None,
                });
            }
            ureq::get("https://api.genius.com/account")
                .set("User-Agent", "Lyra/0.1")
                .set("Authorization", &format!("Bearer {token}"))
                .call()
                .map(|resp| {
                    resp.into_json::<Value>()
                        .ok()
                        .and_then(|v| {
                            v.pointer("/response/user/name")
                                .and_then(Value::as_str)
                                .map(String::from)
                        })
                })
                .map_err(|e| e.to_string())
        }
        "qobuz" => {
            let email = config
                .get("qobuz_email")
                .or_else(|| config.get("QOBUZ_EMAIL"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let password = config
                .get("qobuz_password")
                .or_else(|| config.get("QOBUZ_PASSWORD"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if email.is_empty() || password.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("qobuz_email and qobuz_password required".to_string()),
                    detail: None,
                });
            }
            // Probe the Qobuz login endpoint — returns 200 + user object on success.
            ureq::post("https://www.qobuz.com/api.json/0.2/user/login")
                .set("User-Agent", "Lyra/0.1")
                .send_form(&[
                    ("email", email),
                    ("password", password),
                    ("app_id", "950096963"),
                ])
                .map(|resp| {
                    resp.into_json::<Value>()
                        .ok()
                        .and_then(|v| {
                            v.pointer("/user/display_name")
                                .and_then(Value::as_str)
                                .map(String::from)
                        })
                })
                .map_err(|e| e.to_string())
        }
        "musicbrainz" => {
            // MusicBrainz is always available — no auth needed.  Just confirm reachability.
            ureq::get("https://musicbrainz.org/ws/2/artist")
                .set("User-Agent", "Lyra/0.1 (https://github.com/snappedpoem1/lyra)")
                .query("query", "Radiohead")
                .query("limit", "1")
                .query("fmt", "json")
                .call()
                .map(|_| Some("reachable".to_string()))
                .map_err(|e| e.to_string())
        }
        "prowlarr" => {
            let url = config
                .get("prowlarr_url")
                .or_else(|| config.get("PROWLARR_URL"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let api_key = config
                .get("prowlarr_api_key")
                .or_else(|| config.get("PROWLARR_API_KEY"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if url.is_empty() || api_key.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("prowlarr_url and prowlarr_api_key required".to_string()),
                    detail: None,
                });
            }
            let endpoint = format!("{}/api/v1/system/status", url.trim_end_matches('/'));
            ureq::get(&endpoint)
                .set("User-Agent", "Lyra/0.1")
                .set("X-Api-Key", api_key)
                .call()
                .map(|resp| {
                    resp.into_json::<Value>()
                        .ok()
                        .and_then(|v| v.get("version").and_then(Value::as_str).map(|s| format!("Prowlarr {}", s)))
                })
                .map_err(|e| e.to_string())
        }
        "realdebrid" => {
            let api_key = config
                .get("real_debrid_key")
                .or_else(|| config.get("REAL_DEBRID_KEY"))
                .or_else(|| config.get("real_debrid_api_key"))
                .or_else(|| config.get("REAL_DEBRID_API_KEY"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if api_key.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("real_debrid_key required".to_string()),
                    detail: None,
                });
            }
            ureq::get("https://api.real-debrid.com/rest/1.0/user")
                .set("User-Agent", "Lyra/0.1")
                .set("Authorization", &format!("Bearer {}", api_key))
                .call()
                .map(|resp| {
                    resp.into_json::<Value>()
                        .ok()
                        .and_then(|v| v.get("username").and_then(Value::as_str).map(String::from))
                })
                .map_err(|e| e.to_string())
        }
        "slskd" => {
            let user = config
                .get("lyra_protocol_node_user")
                .or_else(|| config.get("LYRA_PROTOCOL_NODE_USER"))
                .or_else(|| config.get("slskd_user"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let pass = config
                .get("lyra_protocol_node_pass")
                .or_else(|| config.get("LYRA_PROTOCOL_NODE_PASS"))
                .or_else(|| config.get("slskd_pass"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let url = config
                .get("slskd_url")
                .or_else(|| config.get("SLSKD_URL"))
                .and_then(Value::as_str)
                .unwrap_or("http://localhost:5030");
            if user.is_empty() || pass.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("slskd credentials required".to_string()),
                    detail: None,
                });
            }
            let endpoint = format!("{}/api/v0/session", url.trim_end_matches('/'));
            ureq::get(&endpoint)
                .set("User-Agent", "Lyra/0.1")
                .set("Authorization", &format!("Basic {}", base64_encode(&format!("{}:{}", user, pass))))
                .call()
                .map(|_| Some("authenticated".to_string()))
                .map_err(|e| e.to_string())
        }
        "streamrip" => {
            // Streamrip validation: check if binary exists
            let binary_path = config
                .get("lyra_streamrip_binary")
                .or_else(|| config.get("LYRA_STREAMRIP_BINARY"))
                .and_then(Value::as_str)
                .unwrap_or("rip");
            
            // Try to find the binary
            let found = if std::path::Path::new(binary_path).exists() {
                Some(binary_path.to_string())
            } else {
                which::which(binary_path).ok().map(|p| p.display().to_string())
            };
            
            match found {
                Some(path) => Ok(Some(format!("binary found: {}", path))),
                None => Err(format!("streamrip binary '{}' not found", binary_path)),
            }
        }
        "spotdl" => {
            // SpotDL uses Spotify credentials for metadata lookup
            let client_id = config
                .get("spotify_client_id")
                .or_else(|| config.get("SPOTIFY_CLIENT_ID"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let client_secret = config
                .get("spotify_client_secret")
                .or_else(|| config.get("SPOTIFY_CLIENT_SECRET"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if client_id.is_empty() || client_secret.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("spotify_client_id and spotify_client_secret required".to_string()),
                    detail: None,
                });
            }
            // Validate Spotify credentials via OAuth token endpoint
            ureq::post("https://accounts.spotify.com/api/token")
                .set("User-Agent", "Lyra/0.1")
                .set("Authorization", &format!("Basic {}", base64_encode(&format!("{}:{}", client_id, client_secret))))
                .send_form(&[("grant_type", "client_credentials")])
                .map(|resp| {
                    resp.into_json::<Value>()
                        .ok()
                        .and_then(|v| v.get("access_token").map(|_| "credentials valid".to_string()))
                })
                .map_err(|e| e.to_string())
        }
        "spotify" => {
            // Spotify library import validation
            let client_id = config
                .get("spotify_client_id")
                .or_else(|| config.get("SPOTIFY_CLIENT_ID"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let client_secret = config
                .get("spotify_client_secret")
                .or_else(|| config.get("SPOTIFY_CLIENT_SECRET"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if client_id.is_empty() || client_secret.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("spotify_client_id and spotify_client_secret required".to_string()),
                    detail: None,
                });
            }
            ureq::post("https://accounts.spotify.com/api/token")
                .set("User-Agent", "Lyra/0.1")
                .set("Authorization", &format!("Basic {}", base64_encode(&format!("{}:{}", client_id, client_secret))))
                .send_form(&[("grant_type", "client_credentials")])
                .map(|resp| {
                    resp.into_json::<Value>()
                        .ok()
                        .and_then(|v| v.get("access_token").map(|_| "credentials valid".to_string()))
                })
                .map_err(|e| e.to_string())
        }
        "listenbrainz" => {
            let token = config
                .get("listenbrainz_token")
                .or_else(|| config.get("LISTENBRAINZ_TOKEN"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if token.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("listenbrainz_token required".to_string()),
                    detail: None,
                });
            }
            ureq::get("https://api.listenbrainz.org/1/validate-token")
                .set("User-Agent", "Lyra/0.1")
                .set("Authorization", &format!("Token {}", token))
                .call()
                .map(|resp| {
                    resp.into_json::<Value>()
                        .ok()
                        .and_then(|v| {
                            if v.get("valid").and_then(Value::as_bool).unwrap_or(false) {
                                v.get("user_name").and_then(Value::as_str).map(String::from)
                            } else {
                                None
                            }
                        })
                })
                .map_err(|e| e.to_string())
        }
        "acoustid" => {
            let api_key = config
                .get("acoustid_api_key")
                .or_else(|| config.get("ACOUSTID_API_KEY"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if api_key.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("acoustid_api_key required".to_string()),
                    detail: None,
                });
            }
            // AcoustID doesn't have a dedicated validation endpoint, but we can check if the key format is valid
            // and try a minimal lookup request
            if api_key.len() < 8 {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("acoustid_api_key appears invalid".to_string()),
                    detail: None,
                });
            }
            Ok(Some(format!("api_key configured ({}...)", &api_key[..8.min(api_key.len())])))
        }
        _ => {
            // Unknown or not-yet-probed provider — check if credentials are at least configured.
            let configured = config.as_object().map(|m| !m.is_empty()).unwrap_or(false);
            return Ok(ProviderValidationResult {
                provider_key: provider_key.to_string(),
                valid: configured,
                latency_ms: 0,
                error: if configured { None } else { Some("No credentials configured".to_string()) },
                detail: if configured { Some("credentials present, probe not implemented".to_string()) } else { None },
            });
        }
    };

    let latency_ms = t0.elapsed().as_millis() as u64;

    match result {
        Ok(detail) => {
            if let Err(e) = record_provider_success(conn, provider_key) {
                warn!("Failed to record provider success for {provider_key}: {e}");
            }
            Ok(ProviderValidationResult {
                provider_key: provider_key.to_string(),
                valid: true,
                latency_ms,
                error: None,
                detail,
            })
        }
        Err(err) => {
            let _ = record_provider_failure(conn, provider_key);
            Ok(ProviderValidationResult {
                provider_key: provider_key.to_string(),
                valid: false,
                latency_ms,
                error: Some(err),
                detail: None,
            })
        }
    }
}

// ── Keyring: OS-level secure credential storage ───────────────────────────────
//
// Service name used for all Lyra secrets in the system keychain.
const KEYRING_SERVICE: &str = "lyra-media-player";

/// Save a secret for a provider to the OS keychain.
/// `key_name` is an identifier within that provider (e.g. "api_key", "token").
pub fn keyring_save(provider_key: &str, key_name: &str, secret: &str) -> Result<(), String> {
    let account = format!("{provider_key}:{key_name}");
    Entry::new(KEYRING_SERVICE, &account)
        .map_err(|e| e.to_string())?
        .set_password(secret)
        .map_err(|e| e.to_string())
}

/// Load a secret for a provider from the OS keychain.
/// Returns `None` if no entry exists yet.
pub fn keyring_load(provider_key: &str, key_name: &str) -> Result<Option<String>, String> {
    let account = format!("{provider_key}:{key_name}");
    match Entry::new(KEYRING_SERVICE, &account)
        .map_err(|e| e.to_string())?
        .get_password()
    {
        Ok(secret) => Ok(Some(secret)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

/// Delete a provider secret from the OS keychain.
/// No-ops silently if the entry does not exist.
pub fn keyring_delete(provider_key: &str, key_name: &str) -> Result<(), String> {
    let account = format!("{provider_key}:{key_name}");
    match Entry::new(KEYRING_SERVICE, &account)
        .map_err(|e| e.to_string())?
        .delete_credential()
    {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

/// Acquire a Last.fm session key by authenticating with username + password.
/// Stores `lastfm_session_key` into the provider config JSON on success.
pub fn lastfm_get_session(
    conn: &Connection,
    api_key: &str,
    api_secret: &str,
    username: &str,
    password: &str,
) -> Result<String, String> {
    let session_key = crate::scrobble::get_mobile_session(api_key, api_secret, username, password)?;
    // Persist into provider config JSON
    let existing_json: String = conn
        .query_row(
            "SELECT config_json FROM provider_configs WHERE provider_key = 'lastfm'",
            [],
            |row| row.get(0),
        )
        .unwrap_or_else(|_| "{}".to_string());
    let mut config: serde_json::Value =
        serde_json::from_str(&existing_json).unwrap_or(serde_json::json!({}));
    config["lastfm_session_key"] = serde_json::Value::String(session_key.clone());
    let updated_json = serde_json::to_string(&config).map_err(|e| e.to_string())?;
    conn.execute(
        "UPDATE provider_configs SET config_json = ?1, updated_at = ?2 WHERE provider_key = 'lastfm'",
        rusqlite::params![updated_json, chrono::Utc::now().to_rfc3339()],
    )
    .map_err(|e| e.to_string())?;
    Ok(session_key)
}

/// Read a `.env` file and save all credential-like entries to the OS keychain.
///
/// A key is treated as a credential if its name (uppercased) contains any of:
/// `KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `PASS`, `AUTH`, `EMAIL`.
///
/// Entries are stored under service `"lyra-media-player"` with account `"env:{KEY_NAME}"`.
///
/// Returns a summary: `(saved, skipped)` counts.
pub fn backup_env_to_keychain(env_path: &str) -> Result<(usize, usize), String> {
    let credential_indicators = ["KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "AUTH", "EMAIL"];
    let mut saved = 0usize;
    let mut skipped = 0usize;

    // Read file bytes, strip UTF-8 BOM (EF BB BF) if present, then parse.
    let raw = std::fs::read(env_path).map_err(|e| format!("Failed to read {env_path}: {e}"))?;
    let content = if raw.starts_with(b"\xef\xbb\xbf") { &raw[3..] } else { &raw[..] };
    let pairs = dotenvy::from_read_iter(std::io::Cursor::new(content));

    for pair in pairs {
        let (k, v) = match pair {
            Ok(kv) => kv,
            Err(e) => { warn!("Skipping .env line: {e}"); skipped += 1; continue; }
        };
        let ku = k.to_ascii_uppercase();
        let is_cred = credential_indicators.iter().any(|ind| ku.contains(ind));
        if !is_cred || v.trim().is_empty() {
            skipped += 1;
            continue;
        }
        let account = format!("env:{k}");
        match Entry::new(KEYRING_SERVICE, &account)
            .map_err(|e| e.to_string())
            .and_then(|e| e.set_password(&v).map_err(|e| e.to_string()))
        {
            Ok(()) => { saved += 1; }
            Err(err) => {
                warn!("keychain save failed for {k}: {err}");
                skipped += 1;
            }
        }
    }
    Ok((saved, skipped))
}

/// Load a single credential that was previously backed up from `.env`.
pub fn load_env_credential(key_name: &str) -> Result<Option<String>, String> {
    let account = format!("env:{key_name}");
    match Entry::new(KEYRING_SERVICE, &account)
        .map_err(|e| e.to_string())?
        .get_password()
    {
        Ok(v) => Ok(Some(v)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

use std::collections::HashMap;
use std::path::Path;
use std::time::Instant;

use chrono::Utc;
use dotenvy::from_path_iter;
use keyring::Entry;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use tracing::warn;

use crate::commands::{
    ProviderConfigRecord, ProviderHealth, ProviderValidationResult, SpotifyOauthBootstrap,
    SpotifyOauthSession,
};
use crate::errors::LyraResult;
use crate::provider_runtime;

/// Helper function to base64-encode a string (used for HTTP Basic auth).
fn base64_encode(s: &str) -> String {
    use base64::prelude::*;
    BASE64_STANDARD.encode(s.as_bytes())
}

const SPOTIFY_ACCESS_TOKEN_KEY: &str = "oauth_access_token";
const SPOTIFY_REFRESH_TOKEN_KEY: &str = "oauth_refresh_token";
const SPOTIFY_AUTH_FLOW_TTL_MINUTES: i64 = 10;
const SPOTIFY_DEFAULT_SCOPES: &[&str] = &[
    "user-library-read",
    "playlist-read-private",
    "user-top-read",
    "user-read-recently-played",
];

// ── LLM config ────────────────────────────────────────────────────────────────

/// Resolved LLM configuration for making chat-completion calls.
#[derive(Clone, Debug)]
pub struct LlmConfig {
    pub base_url: String,
    pub model: String,
    pub api_key: String,
    /// One of "ollama", "openai", "openrouter", "groq", or "openai_compatible".
    pub provider_kind: String,
}

/// Load a single provider's raw config JSON from the `provider_configs` table.
/// Returns `None` if the provider has no row or is disabled.
pub fn load_provider_config(conn: &Connection, provider_key: &str) -> Option<Value> {
    conn.query_row(
        "SELECT config_json FROM provider_configs WHERE provider_key = ?1 AND enabled = 1",
        params![provider_key],
        |row| row.get::<_, String>(0),
    )
    .ok()
    .and_then(|s| serde_json::from_str(&s).ok())
}

/// Upsert a provider's config JSON into the `provider_configs` table.
pub fn save_provider_config(
    conn: &Connection,
    provider_key: &str,
    config_json: &Value,
) -> LyraResult<()> {
    let display_name = conn
        .query_row(
            "SELECT display_name FROM provider_capabilities WHERE provider_key = ?1",
            params![provider_key],
            |row| row.get::<_, String>(0),
        )
        .unwrap_or_else(|_| provider_key.to_string());
    conn.execute(
        "INSERT INTO provider_configs (provider_key, display_name, enabled, config_json, updated_at)
         VALUES (?1, ?2, 1, ?3, ?4)
         ON CONFLICT(provider_key) DO UPDATE SET
           display_name = excluded.display_name,
           config_json  = excluded.config_json,
           updated_at   = excluded.updated_at",
        params![
            provider_key,
            display_name,
            serde_json::to_string(config_json)?,
            Utc::now().to_rfc3339(),
        ],
    )?;
    Ok(())
}

fn provider_config_json(conn: &Connection, provider_key: &str) -> Result<Value, String> {
    let raw: String = conn
        .query_row(
            "SELECT config_json FROM provider_configs WHERE provider_key = ?1",
            params![provider_key],
            |row| row.get(0),
        )
        .unwrap_or_else(|_| "{}".to_string());
    serde_json::from_str(&raw).map_err(|error| error.to_string())
}

fn spotify_client_credentials(config: &Value) -> Result<(String, String), String> {
    let client_id = config
        .get("spotify_client_id")
        .or_else(|| config.get("SPOTIFY_CLIENT_ID"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .ok_or_else(|| "spotify client id missing".to_string())?;
    let client_secret = config
        .get("spotify_client_secret")
        .or_else(|| config.get("SPOTIFY_CLIENT_SECRET"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .ok_or_else(|| "spotify client secret missing".to_string())?;
    Ok((client_id, client_secret))
}

fn spotify_authorize_url(config: &Value) -> String {
    config_str(config, &["spotify_authorize_url", "SPOTIFY_AUTHORIZE_URL"])
        .map(str::to_string)
        .unwrap_or_else(|| "https://accounts.spotify.com/authorize".to_string())
}

fn spotify_token_url(config: &Value) -> String {
    config_str(config, &["spotify_token_url", "SPOTIFY_TOKEN_URL"])
        .map(str::to_string)
        .unwrap_or_else(|| "https://accounts.spotify.com/api/token".to_string())
}

fn spotify_scope_value(config: &Value) -> String {
    config_str(config, &["spotify_scopes", "SPOTIFY_SCOPES"])
        .map(str::to_string)
        .unwrap_or_else(|| SPOTIFY_DEFAULT_SCOPES.join(" "))
}

fn spotify_redirect_uri(
    config: &Value,
    override_redirect_uri: Option<&str>,
) -> Result<String, String> {
    override_redirect_uri
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .or_else(|| {
            config_str(config, &["spotify_redirect_uri", "SPOTIFY_REDIRECT_URI"])
                .map(str::to_string)
        })
        .ok_or_else(|| "spotify redirect uri missing".to_string())
}

fn spotify_auth_state(redirect_uri: &str) -> String {
    let seed = format!(
        "spotify:{}:{}:{}",
        redirect_uri.trim(),
        Utc::now().timestamp_nanos_opt().unwrap_or_default(),
        std::process::id()
    );
    format!("{:x}", md5::compute(seed))
}

fn split_scopes(scope: &str) -> Vec<String> {
    scope
        .split_whitespace()
        .filter(|value| !value.trim().is_empty())
        .map(|value| value.trim().to_string())
        .collect()
}

fn spotify_session_row(
    conn: &Connection,
) -> Result<Option<(String, String, Option<String>)>, String> {
    conn.query_row(
        "SELECT token_type, scope, access_token_expires_at
         FROM provider_oauth_sessions
         WHERE provider_key = 'spotify'",
        [],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
    )
    .optional()
    .map_err(|error| error.to_string())
}

pub fn begin_spotify_oauth_flow(
    conn: &Connection,
    redirect_uri: Option<&str>,
) -> Result<SpotifyOauthBootstrap, String> {
    let config = provider_config_json(conn, "spotify")?;
    let (client_id, _) = spotify_client_credentials(&config)?;
    let redirect_uri = spotify_redirect_uri(&config, redirect_uri)?;
    let scope = spotify_scope_value(&config);
    let scopes = split_scopes(&scope);
    let state = spotify_auth_state(&redirect_uri);
    let expires_at =
        (Utc::now() + chrono::Duration::minutes(SPOTIFY_AUTH_FLOW_TTL_MINUTES)).to_rfc3339();

    conn.execute(
        "INSERT INTO provider_auth_flows
         (provider_key, state, redirect_uri, scope, expires_at, completed_at)
         VALUES ('spotify', ?1, ?2, ?3, ?4, NULL)
         ON CONFLICT(provider_key) DO UPDATE SET
           state = excluded.state,
           redirect_uri = excluded.redirect_uri,
           scope = excluded.scope,
           expires_at = excluded.expires_at,
           completed_at = NULL",
        params![state, redirect_uri, scope, expires_at],
    )
    .map_err(|error| error.to_string())?;

    let authorization_url = format!(
        "{}?client_id={}&response_type=code&redirect_uri={}&scope={}&state={}&show_dialog=true",
        spotify_authorize_url(&config),
        urlencoding::encode(&client_id),
        urlencoding::encode(&redirect_uri),
        urlencoding::encode(&scope),
        urlencoding::encode(&state),
    );

    Ok(SpotifyOauthBootstrap {
        authorization_url,
        state,
        redirect_uri,
        scopes,
        expires_at,
    })
}

pub fn complete_spotify_oauth_flow(
    conn: &Connection,
    code: &str,
    state: &str,
) -> Result<SpotifyOauthSession, String> {
    if code.trim().is_empty() {
        return Err("spotify authorization code required".to_string());
    }
    if state.trim().is_empty() {
        return Err("spotify oauth state required".to_string());
    }

    let (stored_state, redirect_uri, stored_scope, expires_at, completed_at): (
        String,
        String,
        String,
        String,
        Option<String>,
    ) = conn
        .query_row(
            "SELECT state, redirect_uri, scope, expires_at, completed_at
             FROM provider_auth_flows
             WHERE provider_key = 'spotify'",
            [],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                ))
            },
        )
        .map_err(|_| "spotify oauth flow has not been started".to_string())?;

    if completed_at.is_some() {
        return Err("spotify oauth flow has already been completed".to_string());
    }
    if stored_state != state.trim() {
        return Err("spotify oauth state mismatch".to_string());
    }
    let expires_at = chrono::DateTime::parse_from_rfc3339(&expires_at)
        .map_err(|error| error.to_string())?
        .with_timezone(&Utc);
    if expires_at < Utc::now() {
        return Err("spotify oauth flow expired".to_string());
    }

    let config = provider_config_json(conn, "spotify")?;
    let (client_id, client_secret) = spotify_client_credentials(&config)?;
    let payload = provider_runtime::json_request_with_retry(|| {
        ureq::post(&spotify_token_url(&config))
            .set("User-Agent", "Lyra/0.1")
            .set(
                "Authorization",
                &format!(
                    "Basic {}",
                    base64_encode(&format!("{}:{}", client_id, client_secret))
                ),
            )
            .send_form(&[
                ("grant_type", "authorization_code"),
                ("code", code.trim()),
                ("redirect_uri", redirect_uri.as_str()),
            ])
    })?;

    let access_token = payload
        .get("access_token")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "spotify auth exchange did not return access_token".to_string())?;
    let refresh_token = payload
        .get("refresh_token")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "spotify auth exchange did not return refresh_token".to_string())?;
    let expires_in_seconds = payload
        .get("expires_in")
        .and_then(Value::as_i64)
        .unwrap_or(3600);
    let scope = payload
        .get("scope")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .unwrap_or(stored_scope.as_str());
    let token_type = payload
        .get("token_type")
        .and_then(Value::as_str)
        .unwrap_or("Bearer");

    let session = store_spotify_oauth_session(
        conn,
        access_token,
        Some(refresh_token),
        expires_in_seconds,
        scope,
        Some(token_type),
    )?;
    conn.execute(
        "UPDATE provider_auth_flows
         SET completed_at = ?1
         WHERE provider_key = 'spotify'",
        params![Utc::now().to_rfc3339()],
    )
    .map_err(|error| error.to_string())?;
    Ok(session)
}

pub fn get_spotify_oauth_session(conn: &Connection) -> Result<Option<SpotifyOauthSession>, String> {
    let Some((token_type, scope, access_token_expires_at)) = spotify_session_row(conn)? else {
        return Ok(None);
    };
    let has_refresh_token = keyring_load("spotify", SPOTIFY_REFRESH_TOKEN_KEY)?
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false);
    let access_token_ready = keyring_load("spotify", SPOTIFY_ACCESS_TOKEN_KEY)?
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false);
    Ok(Some(SpotifyOauthSession {
        token_type,
        scopes: split_scopes(&scope),
        access_token_expires_at,
        refreshed_at: conn
            .query_row(
                "SELECT refreshed_at FROM provider_oauth_sessions WHERE provider_key = 'spotify'",
                [],
                |row| row.get(0),
            )
            .unwrap_or_else(|_| Utc::now().to_rfc3339()),
        has_refresh_token,
        access_token_ready,
    }))
}

pub fn store_spotify_oauth_session(
    conn: &Connection,
    access_token: &str,
    refresh_token: Option<&str>,
    expires_in_seconds: i64,
    scope: &str,
    token_type: Option<&str>,
) -> Result<SpotifyOauthSession, String> {
    if access_token.trim().is_empty() {
        return Err("spotify access token required".to_string());
    }
    keyring_save("spotify", SPOTIFY_ACCESS_TOKEN_KEY, access_token)?;
    if let Some(refresh_token) = refresh_token.filter(|value| !value.trim().is_empty()) {
        keyring_save("spotify", SPOTIFY_REFRESH_TOKEN_KEY, refresh_token)?;
    }

    let expires_at = Utc::now() + chrono::Duration::seconds(expires_in_seconds.max(0));
    let refreshed_at = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO provider_oauth_sessions
         (provider_key, token_type, scope, access_token_expires_at, refreshed_at)
         VALUES ('spotify', ?1, ?2, ?3, ?4)
         ON CONFLICT(provider_key) DO UPDATE SET
           token_type = excluded.token_type,
           scope = excluded.scope,
           access_token_expires_at = excluded.access_token_expires_at,
           refreshed_at = excluded.refreshed_at",
        params![
            token_type.unwrap_or("Bearer"),
            scope.trim(),
            expires_at.to_rfc3339(),
            refreshed_at,
        ],
    )
    .map_err(|error| error.to_string())?;
    get_spotify_oauth_session(conn)?.ok_or_else(|| "spotify session not persisted".to_string())
}

pub fn spotify_access_token(conn: &Connection) -> Result<String, String> {
    let config = provider_config_json(conn, "spotify")?;
    let (client_id, client_secret) = spotify_client_credentials(&config)?;
    let token_url = spotify_token_url(&config);
    let access_token = keyring_load("spotify", SPOTIFY_ACCESS_TOKEN_KEY)?;
    let refresh_token = keyring_load("spotify", SPOTIFY_REFRESH_TOKEN_KEY)?;
    let session = get_spotify_oauth_session(conn)?;

    let should_refresh = match session
        .as_ref()
        .and_then(|value| value.access_token_expires_at.as_deref())
    {
        Some(value) => chrono::DateTime::parse_from_rfc3339(value)
            .map(|expires_at| {
                expires_at.with_timezone(&Utc) <= Utc::now() + chrono::Duration::seconds(60)
            })
            .unwrap_or(true),
        None => true,
    };

    if !should_refresh {
        if let Some(access_token) = access_token.filter(|value| !value.trim().is_empty()) {
            return Ok(access_token);
        }
    }

    let refresh_token = refresh_token
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| "spotify refresh token missing".to_string())?;
    refresh_spotify_access_token(conn, &client_id, &client_secret, &token_url, &refresh_token)
}

fn refresh_spotify_access_token(
    conn: &Connection,
    client_id: &str,
    client_secret: &str,
    token_url: &str,
    refresh_token: &str,
) -> Result<String, String> {
    let payload = provider_runtime::json_request_with_retry(|| {
        ureq::post(token_url)
            .set("User-Agent", "Lyra/0.1")
            .set(
                "Authorization",
                &format!(
                    "Basic {}",
                    base64_encode(&format!("{}:{}", client_id, client_secret))
                ),
            )
            .send_form(&[
                ("grant_type", "refresh_token"),
                ("refresh_token", refresh_token),
            ])
    })?;

    let access_token = payload
        .get("access_token")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "spotify refresh did not return access_token".to_string())?;
    let expires_in_seconds = payload
        .get("expires_in")
        .and_then(Value::as_i64)
        .unwrap_or(3600);
    let returned_refresh_token = payload
        .get("refresh_token")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty());
    let scope = payload.get("scope").and_then(Value::as_str).unwrap_or("");
    let token_type = payload
        .get("token_type")
        .and_then(Value::as_str)
        .unwrap_or("Bearer");

    let session = store_spotify_oauth_session(
        conn,
        access_token,
        returned_refresh_token.or(Some(refresh_token)),
        expires_in_seconds,
        scope,
        Some(token_type),
    )?;
    keyring_save("spotify", SPOTIFY_ACCESS_TOKEN_KEY, access_token)?;
    if let Some(new_refresh_token) = returned_refresh_token {
        keyring_save("spotify", SPOTIFY_REFRESH_TOKEN_KEY, new_refresh_token)?;
    }
    let _ = session;
    Ok(access_token.to_string())
}

/// Return the provider keys that have a non-empty config_json in the DB.
pub fn list_configured_providers(conn: &Connection) -> Vec<String> {
    let mut stmt = match conn.prepare(
        "SELECT provider_key FROM provider_configs WHERE config_json != '{}' AND config_json != ''",
    ) {
        Ok(s) => s,
        Err(_) => return vec![],
    };
    let result: Result<Vec<String>, _> = stmt
        .query_map([], |row| row.get::<_, String>(0))
        .map(|rows| rows.filter_map(Result::ok).collect());
    result.unwrap_or_default()
}

/// Helper to pull a string field from a JSON object, trying multiple key spellings.
fn config_str<'a>(config: &'a Value, keys: &[&str]) -> Option<&'a str> {
    keys.iter()
        .find_map(|k| config.get(*k).and_then(Value::as_str))
        .filter(|v| !v.trim().is_empty())
}

/// Load LLM configuration, preferring the `provider_configs` DB rows for the
/// first enabled LLM provider found (`groq`, `openrouter`, `openai`, `ollama`),
/// with a fallback to the legacy `LYRA_LLM_*` environment variables.
pub fn load_llm_config(conn: &Connection) -> LlmConfig {
    // Try DB providers in priority order (cloud-first, matching the intelligence.rs heuristic).
    let db_order = ["groq", "openrouter", "openai", "ollama"];
    for key in &db_order {
        if let Some(cfg) = load_provider_config(conn, key) {
            let (base_url, model, api_key) = match *key {
                "ollama" => {
                    let url = config_str(&cfg, &["base_url", "ollama_base_url"])
                        .unwrap_or("http://127.0.0.1:11434")
                        .to_owned();
                    let model = config_str(&cfg, &["model", "ollama_model"])
                        .unwrap_or_default()
                        .to_owned();
                    (url, model, String::new())
                }
                _ => {
                    let url = config_str(
                        &cfg,
                        &[
                            "base_url",
                            "openai_base_url",
                            "openrouter_base_url",
                            "groq_base_url",
                            "lyra_llm_base_url",
                        ],
                    )
                    .unwrap_or(match *key {
                        "openai" => "https://api.openai.com/v1",
                        "openrouter" => "https://openrouter.ai/api/v1",
                        "groq" => "https://api.groq.com/openai/v1",
                        _ => "",
                    })
                    .to_owned();
                    let model = config_str(
                        &cfg,
                        &[
                            "model",
                            "cloud_model",
                            "openai_model",
                            "groq_model",
                            "openrouter_model",
                            "lyra_llm_model",
                        ],
                    )
                    .unwrap_or_default()
                    .to_owned();
                    let api_key = config_str(
                        &cfg,
                        &[
                            "api_key",
                            "token",
                            "openai_api_key",
                            "groq_api_key",
                            "openrouter_api_key",
                            "lyra_llm_api_key",
                        ],
                    )
                    .unwrap_or_default()
                    .to_owned();
                    (url, model, api_key)
                }
            };
            if !model.is_empty() {
                return LlmConfig {
                    base_url,
                    model,
                    api_key,
                    provider_kind: key.to_string(),
                };
            }
        }
    }

    // Fall back to legacy LYRA_LLM_* environment variables.
    let base_url = std::env::var("LYRA_LLM_BASE_URL").unwrap_or_default();
    let model = std::env::var("LYRA_LLM_MODEL").unwrap_or_default();
    let api_key = std::env::var("LYRA_LLM_API_KEY").unwrap_or_default();
    let provider_kind =
        std::env::var("LYRA_LLM_PROVIDER").unwrap_or_else(|_| "openai_compatible".to_string());
    LlmConfig {
        base_url,
        model,
        api_key,
        provider_kind,
    }
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
            capabilities: vec!["horizon", "release-intelligence", "indexer-health"],
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
            capabilities: vec!["history-import", "library-import", "oauth-session"],
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
        ProviderCapabilitySeed {
            provider_key: "clap",
            display_name: "CLAP Semantic",
            capabilities: vec!["semantic-search", "embedding"],
        },
        ProviderCapabilitySeed {
            provider_key: "ollama",
            display_name: "Ollama",
            capabilities: vec!["llm", "local-intent-parse", "local-explanation"],
        },
        ProviderCapabilitySeed {
            provider_key: "openai",
            display_name: "OpenAI",
            capabilities: vec!["llm", "cloud-intent-parse", "cloud-explanation"],
        },
        ProviderCapabilitySeed {
            provider_key: "openrouter",
            display_name: "OpenRouter",
            capabilities: vec!["llm", "cloud-intent-parse", "cloud-explanation"],
        },
        ProviderCapabilitySeed {
            provider_key: "groq",
            display_name: "Groq",
            capabilities: vec!["llm", "cloud-intent-parse", "cloud-explanation"],
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
        ("spotdl", vec!["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]),
        ("prowlarr", vec!["PROWLARR_URL", "PROWLARR_API_KEY"]),
        ("realdebrid", vec!["REAL_DEBRID_KEY", "REAL_DEBRID_API_KEY"]),
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
        ("ollama", vec!["OLLAMA_BASE_URL", "OLLAMA_MODEL"]),
        (
            "openai",
            vec!["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"],
        ),
        (
            "openrouter",
            vec![
                "OPENROUTER_API_KEY",
                "OPENROUTER_BASE_URL",
                "OPENROUTER_MODEL",
            ],
        ),
        (
            "groq",
            vec![
                "GROQ_API_KEY",
                "GROQ_BASE_URL",
                "GROQ_MODEL",
                // Legacy generic LLM interface — maps to groq when present
                "LYRA_LLM_API_KEY",
                "LYRA_LLM_BASE_URL",
                "LYRA_LLM_MODEL",
                "LYRA_LLM_PROVIDER",
            ],
        ),
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
    for (key, value) in (from_path_iter(env_path)?).flatten() {
        // Skip individual lines that fail to parse (e.g. unquoted Windows paths
        // with backslashes). We only care about known provider key names.
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

pub fn record_provider_failure(
    conn: &Connection,
    provider_key: &str,
) -> LyraResult<ProviderHealth> {
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
                .set(
                    "User-Agent",
                    "Lyra/0.1 +https://github.com/snappedpoem1/lyra",
                )
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
                    resp.into_json::<Value>().ok().and_then(|v| {
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
                    resp.into_json::<Value>().ok().and_then(|v| {
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
                .set(
                    "User-Agent",
                    "Lyra/0.1 (https://github.com/snappedpoem1/lyra)",
                )
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
                    resp.into_json::<Value>().ok().and_then(|v| {
                        v.get("version")
                            .and_then(Value::as_str)
                            .map(|s| format!("Prowlarr {}", s))
                    })
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
                .set(
                    "Authorization",
                    &format!("Basic {}", base64_encode(&format!("{}:{}", user, pass))),
                )
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
                which::which(binary_path)
                    .ok()
                    .map(|p| p.display().to_string())
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
            let token_url = spotify_token_url(&config);
            provider_runtime::json_request_with_retry(|| {
                ureq::post(&token_url)
                    .set("User-Agent", "Lyra/0.1")
                    .set(
                        "Authorization",
                        &format!(
                            "Basic {}",
                            base64_encode(&format!("{}:{}", client_id, client_secret))
                        ),
                    )
                    .send_form(&[("grant_type", "client_credentials")])
            })
            .map(|payload| {
                payload
                    .get("access_token")
                    .map(|_| "credentials valid".to_string())
            })
        }
        "spotify" => match spotify_access_token(conn) {
            Ok(_) => {
                let detail = get_spotify_oauth_session(conn)
                    .map_err(|error| crate::errors::LyraError::Message(error.clone()))?
                    .map(|session| {
                        let scope_label = if session.scopes.is_empty() {
                            "no scopes recorded".to_string()
                        } else {
                            session.scopes.join(", ")
                        };
                        format!("oauth session ready ({scope_label})")
                    })
                    .or_else(|| Some("spotify credentials valid".to_string()));
                Ok(detail)
            }
            Err(_) => {
                let (client_id, client_secret) = spotify_client_credentials(&config)
                    .map_err(|error| crate::errors::LyraError::Message(error.clone()))?;
                let token_url = spotify_token_url(&config);
                provider_runtime::json_request_with_retry(|| {
                    ureq::post(&token_url)
                        .set("User-Agent", "Lyra/0.1")
                        .set(
                            "Authorization",
                            &format!(
                                "Basic {}",
                                base64_encode(&format!("{}:{}", client_id, client_secret))
                            ),
                        )
                        .send_form(&[("grant_type", "client_credentials")])
                })
                .map(|payload| {
                    payload
                        .get("access_token")
                        .map(|_| "client credentials valid (no user session yet)".to_string())
                })
            }
        },
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
            provider_runtime::json_request_with_retry(|| {
                ureq::get("https://api.listenbrainz.org/1/validate-token")
                    .set("User-Agent", "Lyra/0.1")
                    .set("Authorization", &format!("Token {}", token))
                    .call()
            })
            .map(|payload| {
                if payload
                    .get("valid")
                    .and_then(Value::as_bool)
                    .unwrap_or(false)
                {
                    payload
                        .get("user_name")
                        .and_then(Value::as_str)
                        .map(String::from)
                } else {
                    None
                }
            })
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
            Ok(Some(format!(
                "api_key configured ({}...)",
                &api_key[..8.min(api_key.len())]
            )))
        }
        "ollama" => {
            let base_url = config
                .get("base_url")
                .or_else(|| config.get("ollama_base_url"))
                .or_else(|| config.get("OLLAMA_BASE_URL"))
                .and_then(Value::as_str)
                .unwrap_or("http://127.0.0.1:11434");
            let model = config
                .get("model")
                .or_else(|| config.get("ollama_model"))
                .or_else(|| config.get("OLLAMA_MODEL"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if model.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("ollama model required".to_string()),
                    detail: None,
                });
            }
            ureq::get(&format!("{}/api/tags", base_url.trim_end_matches('/')))
                .call()
                .map(|_| Some(format!("model configured: {model}")))
                .map_err(|e| e.to_string())
        }
        "openai" | "openrouter" | "groq" => {
            let api_key = config
                .get("api_key")
                .or_else(|| config.get("token"))
                .or_else(|| config.get("OPENAI_API_KEY"))
                .or_else(|| config.get("OPENROUTER_API_KEY"))
                .or_else(|| config.get("GROQ_API_KEY"))
                .or_else(|| config.get("openai_api_key"))
                .or_else(|| config.get("openrouter_api_key"))
                .or_else(|| config.get("groq_api_key"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let base_url = config
                .get("base_url")
                .or_else(|| config.get("openai_base_url"))
                .or_else(|| config.get("openrouter_base_url"))
                .or_else(|| config.get("groq_base_url"))
                .and_then(Value::as_str)
                .unwrap_or(match provider_key {
                    "openai" => "https://api.openai.com/v1",
                    "openrouter" => "https://openrouter.ai/api/v1",
                    "groq" => "https://api.groq.com/openai/v1",
                    _ => unreachable!(),
                });
            let model = config
                .get("model")
                .or_else(|| config.get("cloud_model"))
                .or_else(|| config.get("openai_model"))
                .or_else(|| config.get("openrouter_model"))
                .or_else(|| config.get("groq_model"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if api_key.is_empty() || model.is_empty() {
                return Ok(ProviderValidationResult {
                    provider_key: provider_key.to_string(),
                    valid: false,
                    latency_ms: 0,
                    error: Some("api_key and model required".to_string()),
                    detail: None,
                });
            }
            ureq::get(&format!("{}/models", base_url.trim_end_matches('/')))
                .set("Authorization", &format!("Bearer {api_key}"))
                .call()
                .map(|_| Some(format!("model configured: {model}")))
                .map_err(|e| e.to_string())
        }
        _ => {
            // Unknown or not-yet-probed provider — check if credentials are at least configured.
            let configured = config.as_object().map(|m| !m.is_empty()).unwrap_or(false);
            return Ok(ProviderValidationResult {
                provider_key: provider_key.to_string(),
                valid: configured,
                latency_ms: 0,
                error: if configured {
                    None
                } else {
                    Some("No credentials configured".to_string())
                },
                detail: if configured {
                    Some("credentials present, probe not implemented".to_string())
                } else {
                    None
                },
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
    let credential_indicators = [
        "KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "AUTH", "EMAIL",
    ];
    let mut saved = 0usize;
    let mut skipped = 0usize;

    // Read file bytes, strip UTF-8 BOM (EF BB BF) if present, then parse.
    let raw = std::fs::read(env_path).map_err(|e| format!("Failed to read {env_path}: {e}"))?;
    let content = if raw.starts_with(b"\xef\xbb\xbf") {
        &raw[3..]
    } else {
        &raw[..]
    };
    let pairs = dotenvy::from_read_iter(std::io::Cursor::new(content));

    for pair in pairs {
        let (k, v) = match pair {
            Ok(kv) => kv,
            Err(e) => {
                warn!("Skipping .env line: {e}");
                skipped += 1;
                continue;
            }
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
            Ok(()) => {
                saved += 1;
            }
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

#[cfg(test)]
mod tests {
    use std::any::Any;
    use std::collections::HashMap;
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::{mpsc, Mutex, MutexGuard, Once, OnceLock};
    use std::thread;
    use std::time::Duration;

    use keyring::credential::{
        Credential, CredentialApi, CredentialBuilderApi, CredentialPersistence,
    };
    use keyring::{set_default_credential_builder, Error};
    use rusqlite::Connection;
    use serde_json::json;

    use super::{
        begin_spotify_oauth_flow, complete_spotify_oauth_flow, get_spotify_oauth_session,
        spotify_access_token, store_spotify_oauth_session, update_provider_config,
    };
    use crate::db;

    #[derive(Debug)]
    struct TestCredential {
        key: String,
    }

    impl CredentialApi for TestCredential {
        fn set_secret(&self, secret: &[u8]) -> keyring::Result<()> {
            secret_store()
                .lock()
                .expect("test secret store lock")
                .insert(self.key.clone(), secret.to_vec());
            Ok(())
        }

        fn get_secret(&self) -> keyring::Result<Vec<u8>> {
            secret_store()
                .lock()
                .expect("test secret store lock")
                .get(&self.key)
                .cloned()
                .ok_or(Error::NoEntry)
        }

        fn delete_credential(&self) -> keyring::Result<()> {
            secret_store()
                .lock()
                .expect("test secret store lock")
                .remove(&self.key)
                .map(|_| ())
                .ok_or(Error::NoEntry)
        }

        fn as_any(&self) -> &dyn Any {
            self
        }
    }

    #[derive(Debug, Default)]
    struct TestCredentialBuilder;

    impl CredentialBuilderApi for TestCredentialBuilder {
        fn build(
            &self,
            target: Option<&str>,
            service: &str,
            user: &str,
        ) -> keyring::Result<Box<Credential>> {
            let key = format!("{}::{service}::{user}", target.unwrap_or_default().trim());
            Ok(Box::new(TestCredential { key }))
        }

        fn as_any(&self) -> &dyn Any {
            self
        }

        fn persistence(&self) -> CredentialPersistence {
            CredentialPersistence::ProcessOnly
        }
    }

    fn secret_store() -> &'static Mutex<HashMap<String, Vec<u8>>> {
        static STORE: OnceLock<Mutex<HashMap<String, Vec<u8>>>> = OnceLock::new();
        STORE.get_or_init(|| Mutex::new(HashMap::new()))
    }

    fn install_test_keyring() {
        static INIT: Once = Once::new();
        INIT.call_once(|| {
            set_default_credential_builder(Box::new(TestCredentialBuilder));
        });
        secret_store()
            .lock()
            .expect("test secret store lock")
            .clear();
    }

    fn provider_test_guard() -> MutexGuard<'static, ()> {
        static GUARD: OnceLock<Mutex<()>> = OnceLock::new();
        GUARD
            .get_or_init(|| Mutex::new(()))
            .lock()
            .expect("provider test guard")
    }

    fn setup_conn() -> Connection {
        install_test_keyring();
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("schema");
        update_provider_config(
            &conn,
            "spotify",
            true,
            &json!({
                "spotify_client_id": "client-id",
                "spotify_client_secret": "client-secret",
            }),
        )
        .expect("spotify config");
        conn
    }

    fn spawn_token_server(response_body: serde_json::Value) -> (String, mpsc::Receiver<String>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind token server");
        let addr = listener.local_addr().expect("token server addr");
        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept token request");
            let mut buffer = Vec::new();
            let mut header_end = None;
            let mut content_length = 0_usize;

            loop {
                let mut chunk = [0_u8; 1024];
                let read = stream.read(&mut chunk).expect("read request");
                if read == 0 {
                    break;
                }
                buffer.extend_from_slice(&chunk[..read]);

                if header_end.is_none() {
                    if let Some(index) = buffer.windows(4).position(|window| window == b"\r\n\r\n")
                    {
                        let end = index + 4;
                        header_end = Some(end);
                        let headers = String::from_utf8_lossy(&buffer[..end]);
                        content_length = headers
                            .lines()
                            .find_map(|line| {
                                let mut parts = line.splitn(2, ':');
                                let name = parts.next()?.trim();
                                let value = parts.next()?.trim();
                                if name.eq_ignore_ascii_case("content-length") {
                                    value.parse::<usize>().ok()
                                } else {
                                    None
                                }
                            })
                            .unwrap_or_default();
                    }
                }

                if let Some(end) = header_end {
                    if buffer.len() >= end + content_length {
                        break;
                    }
                }
            }

            let header_end = header_end.expect("request headers");
            let body = String::from_utf8_lossy(&buffer[header_end..header_end + content_length])
                .to_string();
            tx.send(body).expect("send request body");

            let payload = response_body.to_string();
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                payload.len(),
                payload
            );
            stream
                .write_all(response.as_bytes())
                .expect("write token response");
            stream.flush().expect("flush token response");
        });
        (format!("http://{addr}/api/token"), rx)
    }

    #[test]
    fn spotify_oauth_session_round_trip_is_backend_owned() {
        let _guard = provider_test_guard();
        let conn = setup_conn();

        let session = store_spotify_oauth_session(
            &conn,
            "access-token",
            Some("refresh-token"),
            3600,
            "user-library-read playlist-read-private",
            Some("Bearer"),
        )
        .expect("stored session");

        assert!(session.has_refresh_token);
        assert!(session.access_token_ready);
        assert_eq!(
            session.scopes,
            vec![
                "user-library-read".to_string(),
                "playlist-read-private".to_string()
            ]
        );

        let loaded = get_spotify_oauth_session(&conn)
            .expect("load session")
            .expect("session exists");
        assert_eq!(loaded.scopes, session.scopes);
        assert!(loaded.has_refresh_token);
        assert!(loaded.access_token_ready);

        let access_token = spotify_access_token(&conn).expect("access token");
        assert_eq!(access_token, "access-token");
    }

    #[test]
    fn spotify_oauth_flow_bootstrap_persists_state_and_redirect() {
        let _guard = provider_test_guard();
        let conn = setup_conn();
        update_provider_config(
            &conn,
            "spotify",
            true,
            &json!({
                "spotify_client_id": "client-id",
                "spotify_client_secret": "client-secret",
                "spotify_redirect_uri": "http://127.0.0.1:43123/callback",
                "spotify_scopes": "user-library-read playlist-read-private",
                "spotify_authorize_url": "https://accounts.spotify.test/authorize"
            }),
        )
        .expect("spotify config with redirect");

        let bootstrap = begin_spotify_oauth_flow(&conn, None).expect("bootstrap flow");

        assert_eq!(bootstrap.redirect_uri, "http://127.0.0.1:43123/callback");
        assert_eq!(
            bootstrap.scopes,
            vec![
                "user-library-read".to_string(),
                "playlist-read-private".to_string()
            ]
        );
        assert!(bootstrap.authorization_url.contains("response_type=code"));
        assert!(bootstrap.authorization_url.contains(&bootstrap.state));

        let persisted: (String, String, String, Option<String>) = conn
            .query_row(
                "SELECT state, redirect_uri, scope, completed_at
                 FROM provider_auth_flows
                 WHERE provider_key = 'spotify'",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .expect("persisted auth flow");
        assert_eq!(persisted.0, bootstrap.state);
        assert_eq!(persisted.1, bootstrap.redirect_uri);
        assert_eq!(persisted.2, "user-library-read playlist-read-private");
        assert!(persisted.3.is_none());
    }

    #[test]
    fn spotify_oauth_flow_exchange_is_completed_in_backend() {
        let _guard = provider_test_guard();
        let conn = setup_conn();
        let (token_url, request_rx) = spawn_token_server(json!({
            "access_token": "server-access-token",
            "refresh_token": "server-refresh-token",
            "expires_in": 3600,
            "scope": "user-library-read playlist-read-private",
            "token_type": "Bearer"
        }));
        update_provider_config(
            &conn,
            "spotify",
            true,
            &json!({
                "spotify_client_id": "client-id",
                "spotify_client_secret": "client-secret",
                "spotify_redirect_uri": "http://127.0.0.1:43123/callback",
                "spotify_scopes": "user-library-read playlist-read-private",
                "spotify_authorize_url": "https://accounts.spotify.test/authorize",
                "spotify_token_url": token_url
            }),
        )
        .expect("spotify config with token url");

        let bootstrap = begin_spotify_oauth_flow(&conn, None).expect("bootstrap flow");
        let session = complete_spotify_oauth_flow(&conn, "auth-code", &bootstrap.state)
            .expect("complete oauth flow");

        let request_body = request_rx
            .recv_timeout(Duration::from_secs(2))
            .expect("authorization_code request body");
        assert!(request_body.contains("grant_type=authorization_code"));
        assert!(request_body.contains("code=auth-code"));
        assert!(request_body.contains(&format!(
            "redirect_uri={}",
            urlencoding::encode("http://127.0.0.1:43123/callback")
        )));

        assert!(session.has_refresh_token);
        assert!(session.access_token_ready);
        assert_eq!(
            session.scopes,
            vec![
                "user-library-read".to_string(),
                "playlist-read-private".to_string()
            ]
        );

        let completed_at: Option<String> = conn
            .query_row(
                "SELECT completed_at FROM provider_auth_flows WHERE provider_key = 'spotify'",
                [],
                |row| row.get(0),
            )
            .expect("completed flow timestamp");
        assert!(completed_at.is_some());

        let access_token = spotify_access_token(&conn).expect("stored access token");
        assert_eq!(access_token, "server-access-token");
    }

    #[test]
    fn spotify_oauth_flow_rejects_state_mismatch() {
        let _guard = provider_test_guard();
        let conn = setup_conn();
        update_provider_config(
            &conn,
            "spotify",
            true,
            &json!({
                "spotify_client_id": "client-id",
                "spotify_client_secret": "client-secret",
                "spotify_redirect_uri": "http://127.0.0.1:43123/callback"
            }),
        )
        .expect("spotify config with redirect");

        let _bootstrap = begin_spotify_oauth_flow(&conn, None).expect("bootstrap flow");
        let error = complete_spotify_oauth_flow(&conn, "auth-code", "wrong-state")
            .expect_err("state mismatch should fail");

        assert!(error.contains("state mismatch"));
    }

    #[test]
    fn spotify_access_token_reports_missing_refresh_secret_when_session_is_expired() {
        let _guard = provider_test_guard();
        let conn = setup_conn();

        store_spotify_oauth_session(
            &conn,
            "short-lived-access-token",
            None,
            0,
            "user-library-read",
            Some("Bearer"),
        )
        .expect("stored session");

        let error = spotify_access_token(&conn).expect_err("refresh should fail");
        assert!(error.contains("spotify refresh token missing"));
    }
}

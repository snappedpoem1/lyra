use std::collections::HashMap;
use std::path::Path;

use chrono::Utc;
use dotenvy::from_path_iter;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};

use crate::commands::{ProviderConfigRecord, ProviderHealth};
use crate::errors::LyraResult;

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
            provider_key: "realdebrid",
            display_name: "Real-Debrid",
            capabilities: vec!["cached-downloads"],
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
    ]
}

pub fn provider_env_mappings() -> HashMap<&'static str, Vec<&'static str>> {
    HashMap::from([
        (
            "qobuz",
            vec![
                "QOBUZ_EMAIL",
                "QOBUZ_PASSWORD",
                "QOBUZ_APP_ID",
                "QOBUZ_SECRETS",
            ],
        ),
        ("realdebrid", vec!["REAL_DEBRID_KEY"]),
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

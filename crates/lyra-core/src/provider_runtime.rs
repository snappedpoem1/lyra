use std::thread;
use std::time::Duration;

use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::Value;

use crate::errors::LyraResult;

const MAX_ATTEMPTS: usize = 4;
const BASE_BACKOFF_MS: u64 = 250;

#[derive(Clone, Debug)]
pub struct JsonFetchResult {
    pub payload: Value,
    pub source_mode: String,
}

pub fn json_request_with_retry<F>(fetch: F) -> Result<Value, String>
where
    F: Fn() -> Result<ureq::Response, ureq::Error>,
{
    execute_with_retry(fetch)
}

pub fn cached_json_request<F>(
    conn: &Connection,
    provider: &str,
    cache_key: &str,
    ttl: Duration,
    fetch: F,
) -> Result<JsonFetchResult, String>
where
    F: Fn() -> Result<ureq::Response, ureq::Error>,
{
    let cached =
        load_cached_payload(conn, provider, cache_key).map_err(|error| error.to_string())?;
    if let Some((payload, fetched_at)) = cached.as_ref() {
        if cache_is_fresh(fetched_at, ttl) {
            return Ok(JsonFetchResult {
                payload: payload.clone(),
                source_mode: "cache".to_string(),
            });
        }
    }

    match execute_with_retry(fetch) {
        Ok(payload) => {
            save_cached_payload(conn, provider, cache_key, &payload)
                .map_err(|error| error.to_string())?;
            Ok(JsonFetchResult {
                payload,
                source_mode: "live".to_string(),
            })
        }
        Err(error) => {
            if let Some((payload, _)) = cached {
                return Ok(JsonFetchResult {
                    payload,
                    source_mode: "cache_fallback".to_string(),
                });
            }
            Err(error)
        }
    }
}

fn execute_with_retry<F>(fetch: F) -> Result<Value, String>
where
    F: Fn() -> Result<ureq::Response, ureq::Error>,
{
    let mut last_error = "request failed".to_string();
    for attempt in 0..MAX_ATTEMPTS {
        match fetch() {
            Ok(response) => {
                return response
                    .into_json::<Value>()
                    .map_err(|error| format!("json parse failed: {error}"));
            }
            Err(ureq::Error::Status(status, response)) => {
                let retry_after = response
                    .header("Retry-After")
                    .and_then(parse_retry_after_seconds)
                    .unwrap_or_else(|| backoff_seconds(attempt));
                let body = response.into_string().unwrap_or_default();
                last_error = if body.trim().is_empty() {
                    format!("http {status}")
                } else {
                    format!("http {status}: {}", body.trim())
                };
                if !is_retryable_status(status) || attempt + 1 == MAX_ATTEMPTS {
                    break;
                }
                thread::sleep(Duration::from_secs(retry_after.max(1)));
            }
            Err(ureq::Error::Transport(error)) => {
                last_error = error.to_string();
                if attempt + 1 == MAX_ATTEMPTS {
                    break;
                }
                thread::sleep(Duration::from_millis(backoff_millis(attempt)));
            }
        }
    }
    Err(last_error)
}

fn load_cached_payload(
    conn: &Connection,
    provider: &str,
    cache_key: &str,
) -> LyraResult<Option<(Value, String)>> {
    let raw: Option<(String, String)> = conn
        .query_row(
            "SELECT payload_json, fetched_at
             FROM enrich_cache
             WHERE provider = ?1 AND lookup_key = ?2",
            params![provider, cache_key],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    Ok(raw.and_then(|(payload_json, fetched_at)| {
        serde_json::from_str::<Value>(&payload_json)
            .ok()
            .map(|payload| (payload, fetched_at))
    }))
}

fn save_cached_payload(
    conn: &Connection,
    provider: &str,
    cache_key: &str,
    payload: &Value,
) -> LyraResult<()> {
    conn.execute(
        "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
         VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT(provider, lookup_key) DO UPDATE SET
           payload_json = excluded.payload_json,
           fetched_at = excluded.fetched_at",
        params![
            provider,
            cache_key,
            serde_json::to_string(payload)?,
            Utc::now().to_rfc3339(),
        ],
    )?;
    Ok(())
}

fn cache_is_fresh(fetched_at: &str, ttl: Duration) -> bool {
    if ttl.is_zero() {
        return false;
    }
    let Ok(timestamp) = DateTime::parse_from_rfc3339(fetched_at) else {
        return false;
    };
    let Ok(ttl_chrono) = chrono::Duration::from_std(ttl) else {
        return false;
    };
    Utc::now().signed_duration_since(timestamp.with_timezone(&Utc)) <= ttl_chrono
}

fn is_retryable_status(status: u16) -> bool {
    status == 429 || (500..=599).contains(&status)
}

fn parse_retry_after_seconds(raw: &str) -> Option<u64> {
    raw.trim().parse::<u64>().ok()
}

fn backoff_seconds(attempt: usize) -> u64 {
    let millis = backoff_millis(attempt);
    (millis / 1000).max(1)
}

fn backoff_millis(attempt: usize) -> u64 {
    BASE_BACKOFF_MS.saturating_mul(1_u64 << attempt.min(5))
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::time::Duration;

    use chrono::Utc;
    use rusqlite::{params, Connection};
    use serde_json::json;

    use super::cached_json_request;
    use crate::db;

    #[test]
    fn stale_cache_falls_back_when_live_fetch_fails() {
        let conn = Connection::open_in_memory().expect("in-memory db");
        db::init_database(&conn).expect("schema");
        conn.execute(
            "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
             VALUES (?1, ?2, ?3, ?4)",
            params![
                "listenbrainz",
                "artist:brand-new",
                json!({"artist": "Brand New", "source": "cached"}).to_string(),
                (Utc::now() - chrono::Duration::hours(6)).to_rfc3339(),
            ],
        )
        .expect("cache row");

        let attempts = AtomicUsize::new(0);
        let result = cached_json_request(
            &conn,
            "listenbrainz",
            "artist:brand-new",
            Duration::from_secs(1),
            || {
                attempts.fetch_add(1, Ordering::SeqCst);
                let response =
                    ureq::Response::new(400, "Bad Request", "{\"error\":\"bad request\"}")
                        .expect("response");
                Err(ureq::Error::Status(400, response))
            },
        )
        .expect("cache fallback");

        assert_eq!(attempts.load(Ordering::SeqCst), 1);
        assert_eq!(result.source_mode, "cache_fallback");
        assert_eq!(result.payload["artist"], "Brand New");
    }
}

use std::ffi::OsStr;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use rusqlite::{params, OptionalExtension};
use serde::Deserialize;
use serde_json::Value;
use tracing::{info, warn};

use crate::acquisition;
use crate::config::AppPaths;
use crate::errors::{LyraError, LyraResult};
use crate::library;
use crate::providers;

type QueuedItemRow = (
    i64,
    String,
    String,
    Option<String>,
    Option<i64>,
    Option<String>,
);

#[derive(Debug, Default)]
struct AcquireTrackResult {
    path: Option<PathBuf>,
    provider: Option<String>,
    tier: Option<String>,
    failure_stage: Option<String>,
    failure_reason: Option<String>,
    cancelled: bool,
}

#[derive(Debug)]
struct MonitoredCommandResult {
    cancelled: bool,
    timed_out: bool,
    stdout: String,
    stderr: String,
    exit_code: Option<i32>,
}

#[derive(Debug, Clone)]
struct SlskdCandidate {
    username: String,
    filename: String,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "event", rename_all = "snake_case")]
enum WaterfallEvent {
    Phase {
        stage: String,
        progress: f64,
        note: String,
        provider: Option<String>,
        tier: Option<String>,
    },
    Success {
        path: String,
        tier: String,
        provider: Option<String>,
        elapsed: f64,
    },
    Failure {
        error: String,
        stage: Option<String>,
        provider: Option<String>,
        tier: Option<String>,
        elapsed: f64,
    },
}

fn sanitize_segment(value: &str, fallback: &str) -> String {
    let trimmed = value.trim();
    let mut output = String::new();
    for ch in trimmed.chars() {
        if matches!(ch, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*') {
            output.push('_');
        } else {
            output.push(ch);
        }
    }
    let cleaned = output.trim().trim_matches('.').trim();
    if cleaned.is_empty() {
        fallback.to_string()
    } else {
        cleaned.to_string()
    }
}

fn infer_provider_from_tier(tier: &str) -> &'static str {
    match tier {
        "T1" => "qobuz",
        "T2" => "streamrip",
        "T3" => "slskd",
        "T4" => "real_debrid",
        "T5" => "spotdl",
        _ => "unknown",
    }
}

fn acquisition_workspace_root(paths: &AppPaths) -> &Path {
    paths.app_data_dir
        .parent()
        .and_then(|p| p.parent())
        .unwrap_or(paths.app_data_dir.as_path())
}

fn acquisition_data_root(paths: &AppPaths) -> PathBuf {
    std::env::var("LYRA_DATA_ROOT")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var("LOCALAPPDATA")
                .ok()
                .filter(|value| !value.trim().is_empty())
                .map(PathBuf::from)
                .map(|root| root.join("Lyra").join("dev"))
        })
        .unwrap_or_else(|| acquisition_workspace_root(paths).join(".lyra-data"))
}

fn acquisition_staging_dir(paths: &AppPaths) -> PathBuf {
    std::env::var("STAGING_FOLDER")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| acquisition_data_root(paths).join("staging"))
}

fn load_provider_config(conn: &rusqlite::Connection, provider_key: &str) -> Option<Value> {
    let config_json: Option<String> = conn
        .query_row(
            "SELECT config_json FROM provider_configs WHERE provider_key = ?1",
            params![provider_key],
            |row| row.get(0),
        )
        .optional()
        .ok()
        .flatten();
    config_json
        .as_deref()
        .and_then(|value| serde_json::from_str(value).ok())
}

fn find_command(configured: Option<&str>, candidates: &[&str]) -> Option<PathBuf> {
    if let Some(configured) = configured.filter(|value| !value.trim().is_empty()) {
        let configured_path = PathBuf::from(configured);
        if configured_path.exists() {
            return Some(configured_path);
        }
        if let Ok(found) = which::which(configured) {
            return Some(found);
        }
    }
    for candidate in candidates {
        if let Ok(found) = which::which(candidate) {
            return Some(found);
        }
    }
    None
}

fn build_streamrip_query(artist: &str, title: &str, album: Option<&str>) -> String {
    [Some(artist.trim()), Some(title.trim()), album.map(str::trim)]
        .into_iter()
        .flatten()
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

fn percent_encode_segment(value: &str) -> String {
    let mut output = String::new();
    for byte in value.bytes() {
        let ch = byte as char;
        if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.' | '~') {
            output.push(ch);
        } else {
            output.push_str(&format!("%{byte:02X}"));
        }
    }
    output
}

fn remote_filename_leaf(value: &str) -> &str {
    value.rsplit(['\\', '/']).next().unwrap_or(value)
}

fn newest_audio_file(output_dir: &Path, started_at: std::time::SystemTime) -> Option<PathBuf> {
    let mut candidates = Vec::new();
    let mut stack = vec![output_dir.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            let is_audio = path
                .extension()
                .and_then(OsStr::to_str)
                .map(|value| matches!(value.to_ascii_lowercase().as_str(), "flac" | "mp3" | "m4a" | "aac" | "ogg" | "opus" | "wav" | "aiff"))
                .unwrap_or(false);
            if !is_audio {
                continue;
            }
            let modified = path.metadata().ok()?.modified().ok()?;
            if modified >= started_at {
                candidates.push((modified, path));
            }
        }
    }
    candidates.sort_by(|left, right| right.0.cmp(&left.0));
    candidates.into_iter().map(|(_, path)| path).next()
}

fn run_monitored_command(
    mut cmd: Command,
    queue_id: i64,
    conn: &rusqlite::Connection,
) -> LyraResult<MonitoredCommandResult> {
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());
    let mut child = cmd.spawn()?;
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let (stdout_tx, stdout_rx) = mpsc::channel::<String>();
    let (stderr_tx, stderr_rx) = mpsc::channel::<String>();
    if let Some(stdout) = stdout {
        thread::spawn(move || {
            let mut buffer = String::new();
            let reader = BufReader::new(stdout);
            for line in reader.lines().map_while(Result::ok) {
                buffer.push_str(&line);
                buffer.push('\n');
            }
            let _ = stdout_tx.send(buffer);
        });
    }
    if let Some(stderr) = stderr {
        thread::spawn(move || {
            let mut buffer = String::new();
            let reader = BufReader::new(stderr);
            for line in reader.lines().map_while(Result::ok) {
                buffer.push_str(&line);
                buffer.push('\n');
            }
            let _ = stderr_tx.send(buffer);
        });
    }

    let started = std::time::Instant::now();
    loop {
        if acquisition::cancel_requested(conn, queue_id)? {
            let _ = child.kill();
            let _ = child.wait();
            return Ok(MonitoredCommandResult {
                cancelled: true,
                timed_out: false,
                stdout: stdout_rx.try_recv().unwrap_or_default(),
                stderr: stderr_rx.try_recv().unwrap_or_default(),
                exit_code: None,
            });
        }
        if started.elapsed() > Duration::from_secs(300) {
            let _ = child.kill();
            let _ = child.wait();
            return Ok(MonitoredCommandResult {
                cancelled: false,
                timed_out: true,
                stdout: stdout_rx.try_recv().unwrap_or_default(),
                stderr: stderr_rx.try_recv().unwrap_or_default(),
                exit_code: None,
            });
        }
        if let Some(status) = child.try_wait()? {
            return Ok(MonitoredCommandResult {
                cancelled: false,
                timed_out: false,
                stdout: stdout_rx.recv_timeout(Duration::from_secs(2)).unwrap_or_default(),
                stderr: stderr_rx.recv_timeout(Duration::from_secs(2)).unwrap_or_default(),
                exit_code: status.code(),
            });
        }
        thread::sleep(Duration::from_millis(250));
    }
}

fn try_native_streamrip(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    album: Option<&str>,
    queue_id: i64,
    conn: &rusqlite::Connection,
    notify: &Arc<dyn Fn(i64) + Send + Sync>,
) -> LyraResult<AcquireTrackResult> {
    let config = load_provider_config(conn, "streamrip");
    let configured_binary = config
        .as_ref()
        .and_then(|value| value.get("lyra_streamrip_binary").or_else(|| value.get("LYRA_STREAMRIP_BINARY")))
        .and_then(Value::as_str)
        .map(str::to_string)
        .or_else(|| std::env::var("LYRA_STREAMRIP_BINARY").ok());
    let Some(binary) = find_command(configured_binary.as_deref(), &["rip"]) else {
        return Ok(AcquireTrackResult {
            provider: Some("streamrip".to_string()),
            tier: Some("T2".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some("streamrip binary not found".to_string()),
            ..AcquireTrackResult::default()
        });
    };

    let output_dir = acquisition_staging_dir(paths).join(format!("streamrip-queue-{queue_id}"));
    fs::create_dir_all(&output_dir)?;
    let query = build_streamrip_query(artist, title, album);
    let source = config
        .as_ref()
        .and_then(|value| value.get("lyra_streamrip_source").or_else(|| value.get("LYRA_STREAMRIP_SOURCE")))
        .and_then(Value::as_str)
        .unwrap_or("qobuz");
    let started_at = std::time::SystemTime::now();

    let _ = acquisition::update_lifecycle(
        conn,
        queue_id,
        "acquiring",
        0.2,
        Some("Trying native Streamrip provider"),
        Some("streamrip"),
        Some("T2"),
        Some("rust-native"),
    );
    (notify)(queue_id);

    let mut cmd = Command::new(binary);
    cmd.arg("-f")
        .arg(&output_dir)
        .arg("search")
        .arg(source)
        .arg("track")
        .arg(&query)
        .arg("--first");
    let result = run_monitored_command(cmd, queue_id, conn)?;
    if result.cancelled {
        return Ok(AcquireTrackResult {
            provider: Some("streamrip".to_string()),
            tier: Some("T2".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some("Cancellation requested".to_string()),
            cancelled: true,
            ..AcquireTrackResult::default()
        });
    }
    if result.timed_out {
        return Ok(AcquireTrackResult {
            provider: Some("streamrip".to_string()),
            tier: Some("T2".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some("streamrip command timed out".to_string()),
            ..AcquireTrackResult::default()
        });
    }
    if result.exit_code.unwrap_or(1) != 0 {
        let detail = result.stderr.trim();
        let reason = if detail.is_empty() {
            result.stdout.trim()
        } else {
            detail
        };
        return Ok(AcquireTrackResult {
            provider: Some("streamrip".to_string()),
            tier: Some("T2".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some(format!("streamrip failed: {}", if reason.is_empty() { "unknown error" } else { reason })),
            ..AcquireTrackResult::default()
        });
    }
    let Some(path) = newest_audio_file(&output_dir, started_at) else {
        return Ok(AcquireTrackResult {
            provider: Some("streamrip".to_string()),
            tier: Some("T2".to_string()),
            failure_stage: Some("staging".to_string()),
            failure_reason: Some("streamrip finished without producing an audio file".to_string()),
            ..AcquireTrackResult::default()
        });
    };
    Ok(AcquireTrackResult {
        path: Some(path),
        provider: Some("streamrip".to_string()),
        tier: Some("T2".to_string()),
        ..AcquireTrackResult::default()
    })
}

fn try_native_qobuz_service(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    queue_id: i64,
    conn: &rusqlite::Connection,
    notify: &Arc<dyn Fn(i64) + Send + Sync>,
) -> LyraResult<AcquireTrackResult> {
    let config = load_provider_config(conn, "qobuz");
    let service_url = config
        .as_ref()
        .and_then(|value| value.get("qobuz_service_url").or_else(|| value.get("QOBUZ_SERVICE_URL")))
        .and_then(Value::as_str)
        .unwrap_or("http://localhost:7700")
        .trim_end_matches('/')
        .to_string();

    let _ = acquisition::update_lifecycle(
        conn,
        queue_id,
        "acquiring",
        0.1,
        Some("Trying native Qobuz service"),
        Some("qobuz"),
        Some("T1"),
        Some("rust-native"),
    );
    (notify)(queue_id);

    let response = match ureq::post(&format!("{service_url}/acquire"))
        .set("Content-Type", "application/json")
        .send_json(serde_json::json!({ "artist": artist, "title": title }))
    {
        Ok(response) => response,
        Err(error) => {
            return Ok(AcquireTrackResult {
                provider: Some("qobuz".to_string()),
                tier: Some("T1".to_string()),
                failure_stage: Some("acquiring".to_string()),
                failure_reason: Some(format!("Qobuz service unavailable: {error}")),
                ..AcquireTrackResult::default()
            });
        }
    };

    let payload: Value = match response.into_json() {
        Ok(payload) => payload,
        Err(error) => {
            return Ok(AcquireTrackResult {
                provider: Some("qobuz".to_string()),
                tier: Some("T1".to_string()),
                failure_stage: Some("acquiring".to_string()),
                failure_reason: Some(format!("Invalid Qobuz service response: {error}")),
                ..AcquireTrackResult::default()
            });
        }
    };

    if !payload.get("success").and_then(Value::as_bool).unwrap_or(false) {
        return Ok(AcquireTrackResult {
            provider: Some("qobuz".to_string()),
            tier: Some("T1".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: payload
                .get("error")
                .and_then(Value::as_str)
                .map(str::to_string)
                .or_else(|| Some("Qobuz service acquisition failed".to_string())),
            ..AcquireTrackResult::default()
        });
    }

    let response_path = payload
        .get("path")
        .and_then(Value::as_str)
        .map(PathBuf::from);
    let existing_path = response_path
        .as_ref()
        .filter(|path| path.exists())
        .cloned()
        .or_else(|| {
            response_path.as_ref().map(|path| {
                acquisition_staging_dir(paths).join(
                    path.file_name()
                        .and_then(OsStr::to_str)
                        .unwrap_or_default(),
                )
            })
        })
        .filter(|path| path.exists());

    match existing_path {
        Some(path) => Ok(AcquireTrackResult {
            path: Some(path),
            provider: Some("qobuz".to_string()),
            tier: Some("T1".to_string()),
            ..AcquireTrackResult::default()
        }),
        None => Ok(AcquireTrackResult {
            provider: Some("qobuz".to_string()),
            tier: Some("T1".to_string()),
            failure_stage: Some("staging".to_string()),
            failure_reason: Some("Qobuz service reported success but no staged file was visible to Lyra".to_string()),
            ..AcquireTrackResult::default()
        }),
    }
}

fn slskd_node_config(conn: &rusqlite::Connection) -> (String, String, Option<String>, String, String) {
    let config = load_provider_config(conn, "slskd");
    let base_url = config
        .as_ref()
        .and_then(|value| {
            value.get("slskd_url")
                .or_else(|| value.get("SLSKD_URL"))
                .or_else(|| value.get("lyra_protocol_node_url"))
                .or_else(|| value.get("LYRA_PROTOCOL_NODE_URL"))
        })
        .and_then(Value::as_str)
        .unwrap_or("http://localhost:5030")
        .trim_end_matches('/')
        .to_string();
    let api_base = std::env::var("LYRA_PROTOCOL_NODE_API_BASE")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "/api/v0".to_string());
    let api_key = config
        .as_ref()
        .and_then(|value| value.get("slskd_api_key").or_else(|| value.get("SLSKD_API_KEY")).or_else(|| value.get("lyra_protocol_node_key")).or_else(|| value.get("LYRA_PROTOCOL_NODE_KEY")))
        .and_then(Value::as_str)
        .map(str::to_string);
    let username = config
        .as_ref()
        .and_then(|value| value.get("lyra_protocol_node_user").or_else(|| value.get("LYRA_PROTOCOL_NODE_USER")).or_else(|| value.get("slskd_user")))
        .and_then(Value::as_str)
        .unwrap_or("slskd")
        .to_string();
    let password = config
        .as_ref()
        .and_then(|value| value.get("lyra_protocol_node_pass").or_else(|| value.get("LYRA_PROTOCOL_NODE_PASS")).or_else(|| value.get("slskd_pass")))
        .and_then(Value::as_str)
        .unwrap_or("slskd")
        .to_string();
    (base_url, api_base, api_key, username, password)
}

fn slskd_api_url(base_url: &str, api_base: &str, path: &str) -> String {
    let trimmed_base = base_url.trim_end_matches('/');
    let trimmed_api = api_base.trim_matches('/');
    if trimmed_api.is_empty() {
        format!("{trimmed_base}/{}", path.trim_start_matches('/'))
    } else {
        format!("{trimmed_base}/{trimmed_api}/{}", path.trim_start_matches('/'))
    }
}

fn slskd_headers(
    conn: &rusqlite::Connection,
) -> LyraResult<Vec<(String, String)>> {
    let (base_url, api_base, api_key, username, password) = slskd_node_config(conn);
    if let Some(api_key) = api_key.filter(|value| !value.trim().is_empty()) {
        return Ok(vec![("X-API-Key".to_string(), api_key)]);
    }
    let login_url = slskd_api_url(&base_url, &api_base, "/session");
    let response = ureq::post(&login_url)
        .set("Content-Type", "application/json")
        .send_json(serde_json::json!({ "username": username, "password": password }))
        .map_err(|_| LyraError::InvalidInput("slskd authentication failed"))?;
    let payload: Value = response.into_json()?;
    let token = payload
        .get("token")
        .and_then(Value::as_str)
        .ok_or(LyraError::InvalidInput("slskd authentication failed"))?;
    Ok(vec![("Authorization".to_string(), format!("Bearer {token}"))])
}

fn slskd_best_candidate(
    detail: &Value,
) -> Option<SlskdCandidate> {
    let mut best: Option<(i64, SlskdCandidate)> = None;
    for response in detail.get("responses")?.as_array()? {
        let username = response.get("username")?.as_str()?.to_string();
        if response.get("locked").and_then(Value::as_bool).unwrap_or(false) {
            continue;
        }
        for file in response.get("files")?.as_array()? {
            if file.get("isLocked").and_then(Value::as_bool).unwrap_or(false) {
                continue;
            }
            let filename = file.get("filename")?.as_str()?.to_string();
            let extension = file
                .get("extension")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_ascii_lowercase();
            let bitrate = file.get("bitRate").and_then(Value::as_i64).unwrap_or(0);
            let score = match extension.as_str() {
                "flac" => 90,
                "mp3" if bitrate >= 320 => 60,
                "mp3" | "m4a" | "aac" | "ogg" | "opus" if bitrate >= 192 => 40,
                "mp3" | "m4a" | "aac" | "ogg" | "opus" => 20,
                _ => 0,
            };
            if score <= 0 {
                continue;
            }
            let candidate = SlskdCandidate {
                username: username.clone(),
                filename,
            };
            match best.as_ref() {
                Some((best_score, _)) if *best_score >= score => {}
                _ => best = Some((score, candidate)),
            }
        }
    }
    best.map(|(_, candidate)| candidate)
}

fn find_downloaded_leaf(root: &Path, expected_leaf: &str) -> Option<PathBuf> {
    let expected = expected_leaf.to_ascii_lowercase();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            let Some(name) = path.file_name().and_then(OsStr::to_str) else {
                continue;
            };
            if name.to_ascii_lowercase() == expected {
                return Some(path);
            }
        }
    }
    None
}

fn try_native_slskd(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    queue_id: i64,
    conn: &rusqlite::Connection,
    notify: &Arc<dyn Fn(i64) + Send + Sync>,
) -> LyraResult<AcquireTrackResult> {
    let (base_url, api_base, _, _, _) = slskd_node_config(conn);
    let headers = match slskd_headers(conn) {
        Ok(headers) => headers,
        Err(_) => {
            return Ok(AcquireTrackResult {
                provider: Some("slskd".to_string()),
                tier: Some("T3".to_string()),
                failure_stage: Some("acquiring".to_string()),
                failure_reason: Some("slskd authentication failed".to_string()),
                ..AcquireTrackResult::default()
            });
        }
    };

    let _ = acquisition::update_lifecycle(
        conn,
        queue_id,
        "acquiring",
        0.4,
        Some("Trying native slskd provider"),
        Some("slskd"),
        Some("T3"),
        Some("rust-native"),
    );
    (notify)(queue_id);

    let query = format!("{artist} {title}");
    let mut request = ureq::post(&slskd_api_url(&base_url, &api_base, "/searches"))
        .set("Content-Type", "application/json");
    for (key, value) in &headers {
        request = request.set(key, value);
    }
    let search_response = match request.send_json(serde_json::json!({ "searchText": query })) {
        Ok(response) => response,
        Err(error) => {
            return Ok(AcquireTrackResult {
                provider: Some("slskd".to_string()),
                tier: Some("T3".to_string()),
                failure_stage: Some("acquiring".to_string()),
                failure_reason: Some(format!("slskd search failed: {error}")),
                ..AcquireTrackResult::default()
            });
        }
    };
    let search_payload: Value = search_response.into_json()?;
    let Some(search_id) = search_payload.get("id").and_then(Value::as_str).or_else(|| search_payload.get("id").and_then(Value::as_i64).map(|value| Box::leak(value.to_string().into_boxed_str()) as &str)) else {
        return Ok(AcquireTrackResult {
            provider: Some("slskd".to_string()),
            tier: Some("T3".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some("slskd search did not return an id".to_string()),
            ..AcquireTrackResult::default()
        });
    };

    let mut candidate: Option<SlskdCandidate> = None;
    for _ in 0..6 {
        if acquisition::cancel_requested(conn, queue_id)? {
            return Ok(AcquireTrackResult {
                provider: Some("slskd".to_string()),
                tier: Some("T3".to_string()),
                failure_stage: Some("acquiring".to_string()),
                failure_reason: Some("Cancellation requested".to_string()),
                cancelled: true,
                ..AcquireTrackResult::default()
            });
        }
        thread::sleep(Duration::from_secs(3));
        let detail_url = slskd_api_url(&base_url, &api_base, &format!("/searches/{search_id}?includeResponses=true"));
        let mut detail_request = ureq::get(&detail_url);
        for (key, value) in &headers {
            detail_request = detail_request.set(key, value);
        }
        let Ok(detail_response) = detail_request.call() else {
            continue;
        };
        let detail_payload: Value = match detail_response.into_json() {
            Ok(payload) => payload,
            Err(_) => continue,
        };
        candidate = slskd_best_candidate(&detail_payload);
        if candidate.is_some() {
            break;
        }
    }

    let Some(candidate) = candidate else {
        return Ok(AcquireTrackResult {
            provider: Some("slskd".to_string()),
            tier: Some("T3".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some("slskd returned no viable candidate".to_string()),
            ..AcquireTrackResult::default()
        });
    };

    let mut enqueue_request = ureq::post(&slskd_api_url(
        &base_url,
        &api_base,
        &format!(
            "/transfers/downloads/{}",
            percent_encode_segment(&candidate.username)
        ),
    ))
    .set("Content-Type", "application/json");
    for (key, value) in &headers {
        enqueue_request = enqueue_request.set(key, value);
    }
    if let Err(error) = enqueue_request.send_json(serde_json::json!([{ "filename": candidate.filename }])) {
        return Ok(AcquireTrackResult {
            provider: Some("slskd".to_string()),
            tier: Some("T3".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some(format!("slskd enqueue failed: {error}")),
            ..AcquireTrackResult::default()
        });
    }

    let expected_leaf = remote_filename_leaf(&candidate.filename).to_string();
    let downloads_dir = std::env::var("DOWNLOADS_FOLDER")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| acquisition_data_root(paths).join("downloads"));
    let _ = acquisition::update_lifecycle(
        conn,
        queue_id,
        "staging",
        0.72,
        Some("Waiting for slskd download to materialize"),
        Some("slskd"),
        Some("T3"),
        Some("rust-native"),
    );
    (notify)(queue_id);

    for _ in 0..60 {
        if acquisition::cancel_requested(conn, queue_id)? {
            return Ok(AcquireTrackResult {
                provider: Some("slskd".to_string()),
                tier: Some("T3".to_string()),
                failure_stage: Some("acquiring".to_string()),
                failure_reason: Some("Cancellation requested".to_string()),
                cancelled: true,
                ..AcquireTrackResult::default()
            });
        }
        if let Some(path) = find_downloaded_leaf(&downloads_dir, &expected_leaf) {
            return Ok(AcquireTrackResult {
                path: Some(path),
                provider: Some("slskd".to_string()),
                tier: Some("T3".to_string()),
                ..AcquireTrackResult::default()
            });
        }
        thread::sleep(Duration::from_secs(3));
    }

    Ok(AcquireTrackResult {
        provider: Some("slskd".to_string()),
        tier: Some("T3".to_string()),
        failure_stage: Some("staging".to_string()),
        failure_reason: Some("slskd queued a download but no completed file appeared in DOWNLOADS_FOLDER".to_string()),
        ..AcquireTrackResult::default()
    })
}

fn try_native_spotdl(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    queue_id: i64,
    conn: &rusqlite::Connection,
    notify: &Arc<dyn Fn(i64) + Send + Sync>,
) -> LyraResult<AcquireTrackResult> {
    let Some(binary) = find_command(None, &["spotdl"]) else {
        return Ok(AcquireTrackResult {
            provider: Some("spotdl".to_string()),
            tier: Some("T5".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some("spotdl binary not found".to_string()),
            ..AcquireTrackResult::default()
        });
    };

    let output_dir = acquisition_staging_dir(paths).join(format!("spotdl-queue-{queue_id}"));
    fs::create_dir_all(&output_dir)?;
    let started_at = std::time::SystemTime::now();
    let query = format!("{artist} - {title}");

    let _ = acquisition::update_lifecycle(
        conn,
        queue_id,
        "acquiring",
        0.65,
        Some("Trying native SpotDL fallback"),
        Some("spotdl"),
        Some("T5"),
        Some("rust-native"),
    );
    (notify)(queue_id);

    let mut cmd = Command::new(binary);
    cmd.arg("download")
        .arg(&query)
        .arg("--output")
        .arg(&output_dir)
        .arg("--format")
        .arg("mp3")
        .arg("--bitrate")
        .arg("320k")
        .arg("--threads")
        .arg("1");
    let result = run_monitored_command(cmd, queue_id, conn)?;
    if result.cancelled {
        return Ok(AcquireTrackResult {
            provider: Some("spotdl".to_string()),
            tier: Some("T5".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some("Cancellation requested".to_string()),
            cancelled: true,
            ..AcquireTrackResult::default()
        });
    }
    if result.timed_out {
        return Ok(AcquireTrackResult {
            provider: Some("spotdl".to_string()),
            tier: Some("T5".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some("spotdl command timed out".to_string()),
            ..AcquireTrackResult::default()
        });
    }
    if result.exit_code.unwrap_or(1) != 0 {
        let detail = result.stderr.trim();
        let reason = if detail.is_empty() {
            result.stdout.trim()
        } else {
            detail
        };
        return Ok(AcquireTrackResult {
            provider: Some("spotdl".to_string()),
            tier: Some("T5".to_string()),
            failure_stage: Some("acquiring".to_string()),
            failure_reason: Some(format!("spotdl failed: {}", if reason.is_empty() { "unknown error" } else { reason })),
            ..AcquireTrackResult::default()
        });
    }
    let Some(path) = newest_audio_file(&output_dir, started_at) else {
        return Ok(AcquireTrackResult {
            provider: Some("spotdl".to_string()),
            tier: Some("T5".to_string()),
            failure_stage: Some("staging".to_string()),
            failure_reason: Some("spotdl finished without producing an audio file".to_string()),
            ..AcquireTrackResult::default()
        });
    };
    Ok(AcquireTrackResult {
        path: Some(path),
        provider: Some("spotdl".to_string()),
        tier: Some("T5".to_string()),
        ..AcquireTrackResult::default()
    })
}

fn try_native_acquire_track(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    album: Option<&str>,
    queue_id: i64,
    conn: &rusqlite::Connection,
    notify: &Arc<dyn Fn(i64) + Send + Sync>,
) -> LyraResult<AcquireTrackResult> {
    let qobuz = try_native_qobuz_service(paths, artist, title, queue_id, conn, notify)?;
    if qobuz.cancelled || qobuz.path.is_some() {
        return Ok(qobuz);
    }
    let streamrip = try_native_streamrip(paths, artist, title, album, queue_id, conn, notify)?;
    if streamrip.cancelled || streamrip.path.is_some() {
        return Ok(streamrip);
    }
    let slskd = try_native_slskd(paths, artist, title, queue_id, conn, notify)?;
    if slskd.cancelled || slskd.path.is_some() {
        return Ok(slskd);
    }
    let spotdl = try_native_spotdl(paths, artist, title, queue_id, conn, notify)?;
    if spotdl.cancelled || spotdl.path.is_some() {
        return Ok(spotdl);
    }
    Ok(spotdl)
}

fn organize_download(
    conn: &rusqlite::Connection,
    source_path: &Path,
    target_root: Option<&Path>,
    artist: &str,
    title: &str,
    album: Option<&str>,
) -> LyraResult<PathBuf> {
    let root = match target_root {
        Some(path) if path.exists() => path.to_path_buf(),
        Some(_) => {
            return Err(LyraError::InvalidInput(
                "Selected library root is no longer accessible",
            ))
        }
        None => library::list_library_roots(conn)?
            .into_iter()
            .find_map(|root| {
                let path = PathBuf::from(root.path);
                path.exists().then_some(path)
            })
            .ok_or(LyraError::InvalidInput("No accessible library root configured"))?,
    };
    let artist_dir = sanitize_segment(artist, "Unknown Artist");
    let album_dir = sanitize_segment(album.unwrap_or("Singles"), "Singles");
    let ext = source_path
        .extension()
        .and_then(OsStr::to_str)
        .map(|value| format!(".{}", value))
        .unwrap_or_default();
    let file_name = format!(
        "{} - {}{}",
        sanitize_segment(artist, "Unknown Artist"),
        sanitize_segment(title, "Unknown Track"),
        ext
    );
    let target_dir = root.join(artist_dir).join(album_dir);
    fs::create_dir_all(&target_dir)?;
    let mut target = target_dir.join(file_name);
    if source_path == target {
        return Ok(target);
    }
    if target.exists() {
        let stem = target
            .file_stem()
            .and_then(OsStr::to_str)
            .unwrap_or("track")
            .to_string();
        let ext = target
            .extension()
            .and_then(OsStr::to_str)
            .map(|value| format!(".{}", value))
            .unwrap_or_default();
        let mut counter: usize = 1;
        loop {
            let candidate = target_dir.join(format!("{stem}_{counter}{ext}"));
            if !candidate.exists() {
                target = candidate;
                break;
            }
            counter += 1;
        }
    }
    match fs::rename(source_path, &target) {
        Ok(()) => Ok(target),
        Err(_) => {
            fs::copy(source_path, &target)?;
            let _ = fs::remove_file(source_path);
            Ok(target)
        }
    }
}

fn track_id_for_path(conn: &rusqlite::Connection, path: &Path) -> LyraResult<Option<i64>> {
    conn.query_row(
        "SELECT id FROM tracks WHERE path = ?1",
        params![path.to_string_lossy().to_string()],
        |row| row.get(0),
    )
    .optional()
    .map_err(Into::into)
}

fn acquire_track(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    album: Option<&str>,
    queue_id: i64,
    conn: &rusqlite::Connection,
    notify: &Arc<dyn Fn(i64) + Send + Sync>,
) -> LyraResult<AcquireTrackResult> {
    let workspace_root = acquisition_workspace_root(paths);
    let python_exe = workspace_root.join(".venv").join("Scripts").join("python.exe");
    if !python_exe.exists() {
        return try_native_acquire_track(paths, artist, title, album, queue_id, conn, notify);
    }

    let mut cmd = Command::new(&python_exe);
    cmd.arg("-m")
        .arg("oracle.acquirers.waterfall")
        .arg("acquire")
        .arg(artist)
        .arg(title);
    if let Some(value) = album {
        cmd.arg("--album").arg(value);
    }
    cmd.current_dir(workspace_root);
    cmd.env("PYTHONPATH", workspace_root);
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::inherit());

    let mut child = match cmd.spawn() {
        Ok(child) => child,
        Err(error) => {
            warn!("Falling back to native acquisition after waterfall spawn error: {}", error);
            return try_native_acquire_track(paths, artist, title, album, queue_id, conn, notify);
        }
    };

    let stdout = child.stdout.take().expect("stdout was piped");
    let mut result = AcquireTrackResult::default();
    let (line_tx, line_rx) = mpsc::channel::<Result<String, std::io::Error>>();
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line_result in reader.lines() {
            if line_tx.send(line_result).is_err() {
                return;
            }
        }
    });

    let mut stdout_closed = false;
    loop {
        if acquisition::cancel_requested(conn, queue_id)? {
            let _ = child.kill();
            let _ = child.wait();
            result.cancelled = true;
            result.failure_stage = Some("acquiring".to_string());
            result.failure_reason = Some("Cancellation requested".to_string());
            break;
        }

        match line_rx.recv_timeout(Duration::from_millis(250)) {
            Ok(Ok(line)) => {
                let trimmed = line.trim();
                if trimmed.is_empty() {
                    continue;
                }
                match serde_json::from_str::<WaterfallEvent>(trimmed) {
                    Ok(WaterfallEvent::Phase {
                        stage,
                        progress,
                        note,
                        provider,
                        tier,
                    }) => {
                        let provider_ref = provider.as_deref();
                        let tier_ref = tier.as_deref();
                        let _ = acquisition::update_lifecycle(
                            conn,
                            queue_id,
                            &stage,
                            progress,
                            Some(&note),
                            provider_ref,
                            tier_ref,
                            Some("python-waterfall"),
                        );
                        (notify)(queue_id);
                    }
                    Ok(WaterfallEvent::Success {
                        path,
                        tier,
                        provider,
                        elapsed,
                    }) => {
                        info!("[waterfall] success tier={} path={} elapsed={:.1}s", tier, path, elapsed);
                        let provider =
                            provider.unwrap_or_else(|| infer_provider_from_tier(&tier).to_string());
                        let path_buf = PathBuf::from(&path);
                        if path_buf.exists() {
                            result.path = Some(path_buf.clone());
                            result.provider = Some(provider.clone());
                            result.tier = Some(tier.clone());
                            let _ = acquisition::mark_output_path(
                                conn,
                                queue_id,
                                &path,
                                Some(&provider),
                                Some(&tier),
                                Some("Acquired bytes, staging for library ingest"),
                            );
                            (notify)(queue_id);
                        }
                    }
                    Ok(WaterfallEvent::Failure {
                        error,
                        stage,
                        provider,
                        tier,
                        elapsed,
                    }) => {
                        warn!("[waterfall] failure error={} elapsed={:.1}s", error, elapsed);
                        result.failure_stage = Some(stage.unwrap_or_else(|| "acquiring".to_string()));
                        result.failure_reason = Some(error);
                        result.provider = provider.or(result.provider);
                        result.tier = tier.or(result.tier);
                    }
                    Err(_) => {
                        if trimmed.starts_with("Downloaded:") || trimmed.starts_with("SUCCESS:") {
                            let path = trimmed
                                .split_once(':')
                                .map(|(_, value)| value.trim())
                                .unwrap_or("");
                            let path_buf = PathBuf::from(path);
                            if path_buf.exists() {
                                result.path = Some(path_buf);
                            }
                        }
                    }
                }
            }
            Ok(Err(error)) => {
                warn!("Error reading waterfall stdout: {}", error);
                stdout_closed = true;
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                stdout_closed = true;
            }
        }

        if stdout_closed {
            if child.try_wait()?.is_some() {
                break;
            }
            stdout_closed = false;
        }
    }

    let _ = child.wait();
    Ok(result)
}

fn duplicate_path_for_track(
    conn: &rusqlite::Connection,
    artist: &str,
    title: &str,
) -> LyraResult<Option<String>> {
    conn.query_row(
        "SELECT t.path
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
           AND lower(trim(COALESCE(t.title, ''))) = lower(trim(?2))
         LIMIT 1",
        params![artist, title],
        |row| row.get(0),
    )
    .optional()
    .map_err(Into::into)
}

pub fn process_next_queue_item(paths: &AppPaths) -> LyraResult<bool> {
    process_next_queue_item_with_callback(paths, |_| {})
}

pub fn process_next_queue_item_with_callback<F>(paths: &AppPaths, notify: F) -> LyraResult<bool>
where
    F: Fn(i64) + Send + Sync + 'static,
{
    let conn = crate::db::connect(paths)?;
    let notify: Arc<dyn Fn(i64) + Send + Sync> = Arc::new(notify);
    let item: Option<QueuedItemRow> = conn
        .query_row(
            "SELECT id, artist, title, album, target_root_id, target_root_path
             FROM acquisition_queue
             WHERE status = 'queued'
             ORDER BY priority_score DESC, queue_position ASC, id ASC
             LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?, row.get(5)?)),
        )
        .optional()?;

    let Some((id, artist, title, album, target_root_id, target_root_path)) = item else {
        return Ok(false);
    };

    let _ = acquisition::update_lifecycle(
        &conn,
        id,
        "validating",
        0.05,
        Some("Checking acquisition preflight"),
        None,
        None,
        Some("manual-or-worker"),
    );
    notify(id);

    let target_root = if let Some(path) = target_root_path.as_ref() {
        let root_path = PathBuf::from(path);
        if !root_path.exists() {
            let _ = acquisition::mark_failed(
                &conn,
                id,
                "validating",
                "Selected library root is not accessible",
                Some(path),
            );
            notify(id);
            return Ok(true);
        }
        Some(root_path)
    } else {
        None
    };

    let library_root_available = if let Some(root) = target_root.as_ref() {
        root.exists()
    } else {
        library::list_library_roots(&conn)?
            .into_iter()
            .any(|root| PathBuf::from(root.path).exists())
    };
    if !library_root_available {
        let _ = acquisition::mark_failed(
            &conn,
            id,
            "validating",
            "No accessible library root configured",
            Some("Configure a library root before processing acquisitions"),
        );
        notify(id);
        return Ok(true);
    }

    if let Some(path) = duplicate_path_for_track(&conn, &artist, &title)? {
        let _ = acquisition::mark_failed(
            &conn,
            id,
            "validating",
            "Track already exists in the library",
            Some(&path),
        );
        notify(id);
        return Ok(true);
    }

    let _ = acquisition::update_lifecycle(
        &conn,
        id,
        "acquiring",
        0.12,
        Some("Running provider waterfall"),
        None,
        None,
        Some("manual-or-worker"),
    );
    notify(id);

    let acquire_result = acquire_track(paths, &artist, &title, album.as_deref(), id, &conn, &notify)?;
    if let Some(provider) = acquire_result.provider.as_deref() {
        if acquire_result.path.is_some() {
            let _ = providers::record_provider_success(&conn, provider);
        } else if acquire_result.failure_reason.is_some() {
            let _ = providers::record_provider_failure(&conn, provider);
        }
    }
    if acquire_result.cancelled {
        let _ = acquisition::mark_cancelled(
            &conn,
            id,
            "acquiring",
            Some("Cancelled while provider waterfall was running"),
        );
        notify(id);
        return Ok(true);
    }
    let Some(acquired_path) = acquire_result.path else {
        let _ = acquisition::mark_failed(
            &conn,
            id,
            acquire_result
                .failure_stage
                .as_deref()
                .unwrap_or("acquiring"),
            acquire_result
                .failure_reason
                .as_deref()
                .unwrap_or("Acquisition finished without a file"),
            acquire_result.failure_reason.as_deref(),
        );
        notify(id);
        return Ok(true);
    };

    let _ = acquisition::update_lifecycle(
        &conn,
        id,
        "staging",
        0.7,
        Some("Validating staged audio"),
        acquire_result.provider.as_deref(),
        acquire_result.tier.as_deref(),
        Some("manual-or-worker"),
    );
    notify(id);

    if acquisition::cancel_requested(&conn, id)? {
        let _ = acquisition::mark_cancelled(&conn, id, "staging", Some("Cancelled after acquisition"));
        notify(id);
        return Ok(true);
    }

    let _ = acquisition::update_lifecycle(
        &conn,
        id,
        "organizing",
        0.82,
        Some("Moving track into the active library root"),
        acquire_result.provider.as_deref(),
        acquire_result.tier.as_deref(),
        Some("manual-or-worker"),
    );
    notify(id);

    let organized_path = match organize_download(
        &conn,
        &acquired_path,
        target_root.as_deref(),
        &artist,
        &title,
        album.as_deref(),
    ) {
        Ok(path) => path,
        Err(error) => {
            let _ = acquisition::mark_failed(
                &conn,
                id,
                "organizing",
                "Failed to organize acquired file into the library root",
                Some(&error.to_string()),
            );
            notify(id);
            return Ok(true);
        }
    };
    let _ = acquisition::mark_organize_complete(
        &conn,
        id,
        &organized_path.to_string_lossy(),
        Some(if target_root_id.is_some() {
            "Track organized into the selected library root"
        } else {
            "Track organized into the active library root"
        }),
    );
    notify(id);

    if acquisition::cancel_requested(&conn, id)? {
        let _ = acquisition::mark_cancelled(&conn, id, "organizing", Some("Cancelled after organize stage"));
        notify(id);
        return Ok(true);
    }

    let _ = acquisition::update_lifecycle(
        &conn,
        id,
        "scanning",
        0.9,
        Some("Importing organized track into the library database"),
        acquire_result.provider.as_deref(),
        acquire_result.tier.as_deref(),
        Some("manual-or-worker"),
    );
    notify(id);

    let imported = match library::import_track_from_path(&conn, &organized_path) {
        Ok(imported) => imported,
        Err(error) => {
            let _ = acquisition::mark_failed(
                &conn,
                id,
                "scanning",
                "Failed to scan organized track into the library",
                Some(&error.to_string()),
            );
            notify(id);
            return Ok(true);
        }
    };
    let track_id = track_id_for_path(&conn, &organized_path)?;
    let scan_note = if imported {
        "Track imported into the library"
    } else {
        "Track already existed in the library catalog"
    };
    let _ = acquisition::mark_scan_complete(&conn, id, track_id, Some(scan_note));
    notify(id);

    if acquisition::cancel_requested(&conn, id)? {
        let _ = acquisition::mark_cancelled(&conn, id, "scanning", Some("Cancelled after scan stage"));
        notify(id);
        return Ok(true);
    }

    let _ = acquisition::update_lifecycle(
        &conn,
        id,
        "indexing",
        0.97,
        Some("Finalizing index visibility for the acquired track"),
        acquire_result.provider.as_deref(),
        acquire_result.tier.as_deref(),
        Some("manual-or-worker"),
    );
    notify(id);

    let _ = acquisition::mark_completed(
        &conn,
        id,
        track_id,
        Some("Track is now available in the library"),
    );
    notify(id);
    Ok(true)
}

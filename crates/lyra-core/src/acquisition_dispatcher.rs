/// Acquisition dispatcher - coordinates download attempts across providers.
///
/// For initial restoration, this dispatcher shells out to the Python acquirer scripts.
/// Future work may port acquisition logic directly to Rust, but the Python waterfall
/// is battle-tested and supports:
/// - Qobuz (tier 1, lossless)
/// - Streamrip (tier 2, multi-source)
/// - Prowlarr + Real-Debrid (tier 3, torrent→instant)
/// - SpotDL (tier 4, YouTube fallback)
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use rusqlite::{params, OptionalExtension};
use serde::Deserialize;
use tracing::{info, warn};

use crate::config::AppPaths;
use crate::errors::LyraResult;
use crate::acquisition;

/// A structured phase event emitted by the Python waterfall to stdout.
#[derive(Debug, Deserialize)]
#[serde(tag = "event", rename_all = "snake_case")]
enum WaterfallEvent {
    Phase {
        stage: String,
        progress: f64,
        note: String,
    },
    Success {
        path: String,
        tier: String,
        elapsed: f64,
    },
    Failure {
        error: String,
        elapsed: f64,
    },
}

/// Attempt to acquire a track using the Python waterfall dispatcher.
///
/// Invokes `python -m oracle.acquirers.waterfall acquire <artist> <title>`,
/// streams stdout line-by-line, parses JSON phase events, and updates the
/// acquisition lifecycle in the DB in real-time.
///
/// Returns the path to the downloaded file on success.
pub fn acquire_track(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    album: Option<&str>,
    queue_id: Option<i64>,
    conn: Option<&rusqlite::Connection>,
) -> LyraResult<Option<PathBuf>> {
    let workspace_root = paths
        .app_data_dir
        .parent()
        .and_then(|p| p.parent())
        .unwrap_or(paths.app_data_dir.as_path());

    // Look for Python venv
    let python_exe = workspace_root.join(".venv").join("Scripts").join("python.exe");
    if !python_exe.exists() {
        warn!("Python venv not found at {:?}, skipping acquisition", python_exe);
        return Ok(None);
    }

    info!("Attempting acquisition: {} - {}", artist, title);

    let mut cmd = Command::new(&python_exe);
    cmd.arg("-m")
        .arg("oracle.acquirers.waterfall")
        .arg("acquire")
        .arg(artist)
        .arg(title);

    if let Some(a) = album {
        cmd.arg("--album").arg(a);
    }

    cmd.current_dir(workspace_root);
    cmd.env("PYTHONPATH", workspace_root);
    // Capture stdout for JSON events; stderr flows through to our logs.
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::inherit());

    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            warn!("Failed to spawn acquisition process: {}", e);
            return Ok(None);
        }
    };

    let stdout = child.stdout.take().expect("stdout was piped");
    let reader = BufReader::new(stdout);

    let mut result_path: Option<PathBuf> = None;
    let mut acquisition_failed = false;

    for line_result in reader.lines() {
        let line = match line_result {
            Ok(l) => l,
            Err(e) => {
                warn!("Error reading waterfall stdout: {}", e);
                break;
            }
        };

        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        match serde_json::from_str::<WaterfallEvent>(trimmed) {
            Ok(WaterfallEvent::Phase { stage, progress, note }) => {
                info!("[waterfall] phase stage={} progress={:.2} note={}", stage, progress, note);
                if let (Some(id), Some(db)) = (queue_id, conn) {
                    let _ = acquisition::update_lifecycle(db, id, &stage, progress, Some(&note));
                }
            }
            Ok(WaterfallEvent::Success { path, tier, elapsed }) => {
                info!("[waterfall] success tier={} path={} elapsed={:.1}s", tier, path, elapsed);
                let p = PathBuf::from(&path);
                if p.exists() {
                    result_path = Some(p);
                } else {
                    warn!("[waterfall] success event path does not exist on disk: {}", path);
                }
            }
            Ok(WaterfallEvent::Failure { error, elapsed }) => {
                warn!("[waterfall] failure error={} elapsed={:.1}s", error, elapsed);
                acquisition_failed = true;
            }
            Err(_) => {
                // Non-JSON line — could be a legacy "Downloaded:" or "SUCCESS:" prefix
                // from older waterfall versions, or other informational output.
                if trimmed.starts_with("Downloaded:") || trimmed.starts_with("SUCCESS:") {
                    let path_str = trimmed
                        .split_once(':')
                        .map(|(_, p)| p.trim())
                        .unwrap_or("");
                    if !path_str.is_empty() {
                        let p = PathBuf::from(path_str);
                        if p.exists() {
                            result_path = Some(p);
                        }
                    }
                }
                // Other non-JSON lines are silently ignored (e.g. progress bars).
            }
        }
    }

    // Wait for the subprocess to finish before returning.
    match child.wait() {
        Ok(status) if !status.success() && result_path.is_none() => {
            warn!("Acquisition process exited with status: {}", status);
        }
        Err(e) => {
            warn!("Failed to wait for acquisition process: {}", e);
        }
        _ => {}
    }

    if let Some(ref path) = result_path {
        info!("Acquisition successful: {:?}", path);
    } else if !acquisition_failed {
        warn!("Acquisition command completed but no file path found in output");
    }

    Ok(result_path)
}

/// Process the next pending acquisition queue item.
///
/// For now, this is a synchronous blocking operation.
/// Returns true if an item was processed, false if queue was empty.
pub fn process_next_queue_item(paths: &AppPaths) -> LyraResult<bool> {
    use rusqlite::params;

    let conn = crate::db::connect(paths)?;

    // Grab the highest-priority pending item.
    let item: Option<(i64, String, String, Option<String>)> = conn
        .query_row(
            "SELECT id, artist, title, album FROM acquisition_queue
             WHERE status = 'pending'
             ORDER BY priority_score DESC, id ASC LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()?;

    let Some((id, artist, title, album)) = item else {
        return Ok(false);
    };

    info!("Processing acquisition queue item {}: {} - {}", id, artist, title);

    // Mark as in-progress
    conn.execute(
        "UPDATE acquisition_queue SET status = 'in_progress' WHERE id = ?1",
        params![id],
    )?;
    let _ = acquisition::update_lifecycle(&conn, id, "acquire", 0.0, Some("Starting provider waterfall"));

    // Attempt acquisition — pass conn and queue_id so phase events update the DB in real-time.
    match acquire_track(paths, &artist, &title, album.as_deref(), Some(id), Some(&conn)) {
        Ok(Some(path)) => {
            let _ = acquisition::update_lifecycle(&conn, id, "scan", 0.55, Some("Triggering scan"));
            let _ = acquisition::update_lifecycle(&conn, id, "organize", 0.75, Some("Organizing into library"));
            let _ = acquisition::update_lifecycle(&conn, id, "index", 0.92, Some("Indexing metadata"));
            // Success: mark completed and optionally trigger a library scan
            conn.execute(
                "UPDATE acquisition_queue SET status = 'completed', completed_at = datetime('now'), error = NULL
                 WHERE id = ?1",
                params![id],
            )?;
            let _ = acquisition::update_lifecycle(&conn, id, "index", 1.0, Some("Complete"));
            info!("Acquisition completed: {:?}", path);
            // TODO: Trigger incremental library scan of the download folder
            Ok(true)
        }
        Ok(None) => {
            // Failed (no file path returned)
            let retry_count: i64 = conn
                .query_row(
                    "SELECT retry_count FROM acquisition_queue WHERE id = ?1",
                    params![id],
                    |row| row.get(0),
                )
                .unwrap_or(0);

            if retry_count >= 2 {
                let _ = acquisition::update_lifecycle(&conn, id, "acquire", 1.0, Some("Failed"));
                conn.execute(
                    "UPDATE acquisition_queue SET status = 'failed', completed_at = datetime('now'),
                     error = 'Max retries exceeded', retry_count = retry_count + 1
                     WHERE id = ?1",
                    params![id],
                )?;
                warn!("Acquisition failed after retries: {} - {}", artist, title);
            } else {
                let _ = acquisition::update_lifecycle(&conn, id, "acquire", 0.0, Some("Retrying"));
                conn.execute(
                    "UPDATE acquisition_queue SET status = 'pending', retry_count = retry_count + 1
                     WHERE id = ?1",
                    params![id],
                )?;
                warn!("Acquisition attempt failed, will retry: {} - {}", artist, title);
            }
            Ok(true)
        }
        Err(e) => {
            let _ = acquisition::update_lifecycle(&conn, id, "acquire", 1.0, Some("Error"));
            conn.execute(
                "UPDATE acquisition_queue SET status = 'failed', completed_at = datetime('now'),
                 error = ?2, retry_count = retry_count + 1
                 WHERE id = ?1",
                params![id, e.to_string()],
            )?;
            warn!("Acquisition error: {}", e);
            Ok(true)
        }
    }
}

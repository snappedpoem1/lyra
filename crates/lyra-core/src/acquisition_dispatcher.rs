/// Acquisition dispatcher - coordinates download attempts across providers.
///
/// For initial restoration, this dispatcher shells out to the Python acquirer scripts.
/// Future work may port acquisition logic directly to Rust, but the Python waterfall
/// is battle-tested and supports:
/// - Qobuz (tier 1, lossless)
/// - Streamrip (tier 2, multi-source)
/// - Prowlarr + Real-Debrid (tier 3, torrent→instant)
/// - SpotDL (tier 4, YouTube fallback)
use std::path::PathBuf;
use std::process::Command;
use rusqlite::{params, OptionalExtension};
use tracing::{info, warn};

use crate::config::AppPaths;
use crate::errors::LyraResult;

/// Attempt to acquire a track using the Python waterfall dispatcher.
///
/// This invokes `python -m oracle.acquirers.waterfall acquire <artist> <title>`.
/// Returns the path to the downloaded file on success.
pub fn acquire_track(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    album: Option<&str>,
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

    let output = cmd.output();

    match output {
        Ok(result) if result.status.success() => {
            let stdout = String::from_utf8_lossy(&result.stdout);
            // The waterfall script should print the downloaded file path on success.
            // Parse it from stdout (look for "Downloaded: <path>").
            for line in stdout.lines() {
                if line.starts_with("Downloaded:") || line.starts_with("SUCCESS:") {
                    let path_str = line
                        .split_once(':')
                        .map(|(_, p)| p.trim())
                        .unwrap_or("");
                    if !path_str.is_empty() {
                        let path = PathBuf::from(path_str);
                        if path.exists() {
                            info!("Acquisition successful: {:?}", path);
                            return Ok(Some(path));
                        }
                    }
                }
            }
            warn!("Acquisition command succeeded but no file path found in output");
            Ok(None)
        }
        Ok(result) => {
            let stderr = String::from_utf8_lossy(&result.stderr);
            warn!("Acquisition failed: {}", stderr);
            Ok(None)
        }
        Err(e) => {
            warn!("Failed to spawn acquisition process: {}", e);
            Ok(None)
        }
    }
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

    // Attempt acquisition
    match acquire_track(paths, &artist, &title, album.as_deref()) {
        Ok(Some(path)) => {
            // Success: mark completed and optionally trigger a library scan
            conn.execute(
                "UPDATE acquisition_queue SET status = 'completed', completed_at = datetime('now'), error = NULL
                 WHERE id = ?1",
                params![id],
            )?;
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
                conn.execute(
                    "UPDATE acquisition_queue SET status = 'failed', completed_at = datetime('now'),
                     error = 'Max retries exceeded', retry_count = retry_count + 1
                     WHERE id = ?1",
                    params![id],
                )?;
                warn!("Acquisition failed after retries: {} - {}", artist, title);
            } else {
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

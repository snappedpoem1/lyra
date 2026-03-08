/// System diagnostics for health checking and status reporting.
///
/// This module provides status checks for the Lyra runtime, including:
/// - Database connectivity
/// - Python runtime availability
/// - Provider credential validation
/// - Acquisition queue status
/// - Library scan status
/// - Worker thread status

use crate::config::AppPaths;
use crate::errors::LyraResult;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use tracing::info;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiagnosticsReport {
    /// Overall system status ("healthy", "degraded", "error")
    pub status: String,
    /// Individual component health checks
    pub checks: HashMap<String, ComponentHealth>,
    /// Summary statistics
    pub stats: SystemStats,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ComponentHealth {
    /// Component status ("ok", "warning", "error", "not_configured")
    pub status: String,
    /// Human-readable message
    pub message: String,
    /// Optional error detail
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SystemStats {
    pub total_tracks: i64,
    pub total_playlists: i64,
    pub pending_acquisitions: i64,
    pub library_roots: i64,
    pub enriched_tracks: i64,
    pub liked_tracks: i64,
}

impl ComponentHealth {
    fn ok(message: impl Into<String>) -> Self {
        Self {
            status: "ok".to_string(),
            message: message.into(),
            error: None,
        }
    }

    fn warning(message: impl Into<String>, detail: impl Into<String>) -> Self {
        Self {
            status: "warning".to_string(),
            message: message.into(),
            error: Some(detail.into()),
        }
    }

    fn error(message: impl Into<String>, err: impl std::fmt::Display) -> Self {
        Self {
            status: "error".to_string(),
            message: message.into(),
            error: Some(err.to_string()),
        }
    }

    fn not_configured(message: impl Into<String>) -> Self {
        Self {
            status: "not_configured".to_string(),
            message: message.into(),
            error: None,
        }
    }
}

/// Run full system diagnostics.
pub fn run_diagnostics(paths: &AppPaths) -> LyraResult<DiagnosticsReport> {
    info!("Running system diagnostics");
    
    let mut checks = HashMap::new();
    
    // Database connectivity
    checks.insert("database".to_string(), check_database(paths));
    
    // Python runtime
    checks.insert("python".to_string(), check_python());
    
    // Library roots
    checks.insert("library_roots".to_string(), check_library_roots(paths));
    
    // Acquisition worker
    checks.insert("acquisition_worker".to_string(), check_acquisition_worker());
    
    // Gather statistics
    let stats = gather_stats(paths)?;
    
    // Determine overall status
    let status = determine_overall_status(&checks);
    
    Ok(DiagnosticsReport {
        status,
        checks,
        stats,
    })
}

fn check_database(paths: &AppPaths) -> ComponentHealth {
    match Connection::open(&paths.db_path) {
        Ok(conn) => {
            // Try a simple query
            match conn.query_row("SELECT COUNT(*) FROM tracks", [], |row| {
                row.get::<_, i64>(0)
            }) {
                Ok(count) => ComponentHealth::ok(format!("Database connected ({} tracks)", count)),
                Err(e) => ComponentHealth::error("Database query failed", e),
            }
        }
        Err(e) => ComponentHealth::error("Failed to open database", e),
    }
}

fn check_python() -> ComponentHealth {
    match std::process::Command::new("python")
        .arg("--version")
        .output()
    {
        Ok(output) if output.status.success() => {
            let version = String::from_utf8_lossy(&output.stdout);
            ComponentHealth::ok(format!("Python available: {}", version.trim()))
        }
        Ok(_) => ComponentHealth::warning("Python found but version check failed", "Non-zero exit"),
        Err(e) => ComponentHealth::error("Python not found in PATH", e),
    }
}

fn check_library_roots(paths: &AppPaths) -> ComponentHealth {
    match Connection::open(&paths.db_path) {
        Ok(conn) => {
            match conn.query_row(
                "SELECT COUNT(*) FROM library_roots",
                [],
                |row| row.get::<_, i64>(0),
            ) {
                Ok(0) => ComponentHealth::not_configured("No library roots configured"),
                Ok(count) => {
                    // Check if roots are accessible
                    let mut stmt = match conn.prepare(
                        "SELECT path FROM library_roots"
                    ) {
                        Ok(s) => s,
                        Err(e) => return ComponentHealth::error("Failed to prepare query", e),
                    };
                    let paths_result: Result<Vec<String>, _> = stmt
                        .query_map([], |row| row.get(0))
                        .and_then(|rows| rows.collect());
                    
                    match paths_result {
                        Ok(root_paths) => {
                            let missing: Vec<_> = root_paths
                                .iter()
                                .filter(|p| !Path::new(p).exists())
                                .collect();
                            
                            if missing.is_empty() {
                                ComponentHealth::ok(format!("{} library root(s) accessible", count))
                            } else {
                                ComponentHealth::warning(
                                    format!("{} library roots, {} missing", count, missing.len()),
                                    format!("Missing: {:?}", missing),
                                )
                            }
                        }
                        Err(e) => ComponentHealth::error("Failed to check library root paths", e),
                    }
                }
                Err(e) => ComponentHealth::error("Failed to query library roots", e),
            }
        }
        Err(e) => ComponentHealth::error("Failed to open database", e),
    }
}

fn check_acquisition_worker() -> ComponentHealth {
    // Check if worker is running
    if crate::acquisition_worker::is_running() {
        ComponentHealth::ok("Acquisition worker is running")
    } else {
        ComponentHealth::not_configured("Acquisition worker is stopped")
    }
}

fn gather_stats(paths: &AppPaths) -> LyraResult<SystemStats> {
    let conn = Connection::open(&paths.db_path)?;
    
    let total_tracks = conn.query_row("SELECT COUNT(*) FROM tracks", [], |row| row.get(0))?;
    let total_playlists = conn.query_row("SELECT COUNT(*) FROM playlists", [], |row| row.get(0))?;
    let pending_acquisitions = conn.query_row(
        "SELECT COUNT(*) FROM acquisition_queue WHERE status = 'pending'",
        [],
        |row| row.get(0),
    )?;
    let library_roots = conn.query_row(
        "SELECT COUNT(*) FROM library_roots",
        [],
        |row| row.get(0),
    )?;
    let enriched_tracks = conn.query_row(
        "SELECT COUNT(*) FROM enrich_cache",
        [],
        |row| row.get(0),
    )?;
    let liked_tracks = conn.query_row(
        "SELECT COUNT(*) FROM tracks WHERE liked_at IS NOT NULL",
        [],
        |row| row.get(0),
    )?;
    
    Ok(SystemStats {
        total_tracks,
        total_playlists,
        pending_acquisitions,
        library_roots,
        enriched_tracks,
        liked_tracks,
    })
}

fn determine_overall_status(checks: &HashMap<String, ComponentHealth>) -> String {
    let has_error = checks.values().any(|c| c.status == "error");
    let has_warning = checks.values().any(|c| c.status == "warning");
    
    if has_error {
        "error".to_string()
    } else if has_warning {
        "degraded".to_string()
    } else {
        "healthy".to_string()
    }
}

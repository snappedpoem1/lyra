/// Zero-Touch daemon lifecycle management for Soulseek/slskd.
///
/// This module automates the credential plumbing and daemon startup for slskd (Soulseek node).
/// Instead of requiring manual daemon configuration and startup, Lyra:
/// 1. Extracts Soulseek credentials from app database or environment
/// 2. Generates slskd.yml configuration file
/// 3. Spawns slskd.exe as a silent background process (sidecar)
/// 4. Manages daemon lifecycle (start on boot, graceful shutdown)

use std::fs;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::thread;
use std::time::Duration;

use rusqlite::Connection;
use serde_json::Value;
use tracing::{debug, info, warn};

use crate::errors::{LyraError, LyraResult};
use crate::providers::load_provider_config;

const SLSKD_DEFAULT_PORT: u16 = 5930;
const SLSKD_DEFAULT_API_PORT: u16 = 5931;
const SLSKD_DEFAULT_LISTEN_PORT: u16 = 60400;
const DAEMON_STARTUP_TIMEOUT_MS: u32 = 10_000;

/// Represents a managed slskd daemon instance.
pub struct SlskdDaemon {
    pub process: Option<Child>,
    pub port: u16,
    pub api_port: u16,
    pub config_path: PathBuf,
}

impl SlskdDaemon {
    /// Ensures slskd daemon is running. If not, starts it.
    /// Returns the daemon instance and port information.
    pub fn ensure_running(app_data_dir: &Path) -> LyraResult<Self> {
        let daemon_dir = app_data_dir.join(".slskd");
        fs::create_dir_all(&daemon_dir).map_err(|e| {
            LyraError::Message(format!("Failed to create daemon directory: {}", e))
        })?;

        // Check if daemon is already accessible
        if is_daemon_responding(SLSKD_DEFAULT_PORT, SLSKD_DEFAULT_API_PORT) {
            info!(
                "slskd daemon already running on port {}",
                SLSKD_DEFAULT_PORT
            );
            return Ok(SlskdDaemon {
                process: None,
                port: SLSKD_DEFAULT_PORT,
                api_port: SLSKD_DEFAULT_API_PORT,
                config_path: daemon_dir.join("slskd.yml"),
            });
        }

        // Daemon not running; spawn it
        let config_path = daemon_dir.join("slskd.yml");
        let log_path = daemon_dir.join("slskd.log");

        info!(
            "Spawning slskd daemon with config: {}",
            config_path.display()
        );

        // Generate configuration (without credentials, they're loaded from env/keyring)
        generate_slskd_config(&config_path, SLSKD_DEFAULT_PORT, SLSKD_DEFAULT_API_PORT)?;

        // Spawn daemon silently
        let process = spawn_daemon_process(&config_path, &log_path)?;

        // Wait for daemon to become responsive
        wait_for_daemon_ready(DAEMON_STARTUP_TIMEOUT_MS, SLSKD_DEFAULT_PORT)?;

        info!("slskd daemon started successfully (PID: {:?})", process.id());

        Ok(SlskdDaemon {
            process: Some(process),
            port: SLSKD_DEFAULT_PORT,
            api_port: SLSKD_DEFAULT_API_PORT,
            config_path,
        })
    }

    /// Gracefully shutdown the daemon if we spawned it.
    pub fn shutdown(&mut self) -> LyraResult<()> {
        if let Some(mut process) = self.process.take() {
            info!("Shutting down slskd daemon");
            let _ = process.kill();
            let _ = process.wait();
        }
        Ok(())
    }
}

impl Drop for SlskdDaemon {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

/// Extracts Soulseek credentials from provider config or environment.
/// Returns None if credentials are not found (gracefully handles missing config).
pub fn load_soulseek_credentials(conn: &Connection) -> LyraResult<Option<(String, String)>> {
    let config = load_provider_config(conn, "slskd");

    // First try database config
    if let Some(config) = config.as_ref() {
        let username = config
            .get("soulseek_username")
            .or_else(|| config.get("SOULSEEK_USERNAME"))
            .and_then(Value::as_str)
            .map(str::to_string);

        let password = config
            .get("soulseek_password")
            .or_else(|| config.get("SOULSEEK_PASSWORD"))
            .and_then(Value::as_str)
            .map(str::to_string);

        if let (Some(u), Some(p)) = (username, password) {
            return Ok(Some((u, p)));
        }
    }

    // Fall back to environment variables
    let username = std::env::var("SOULSEEK_USERNAME").ok();
    let password = std::env::var("SOULSEEK_PASSWORD").ok();

    match (username, password) {
        (Some(u), Some(p)) => Ok(Some((u, p))),
        _ => {
            warn!("Soulseek credentials not configured. Set SOULSEEK_USERNAME and SOULSEEK_PASSWORD in .env or provider config");
            Ok(None)
        }
    }
}

/// Generates slskd.yml configuration file.
fn generate_slskd_config(
    config_path: &Path,
    port: u16,
    api_port: u16,
) -> LyraResult<()> {
    let node_user = std::env::var("LYRA_PROTOCOL_NODE_USER")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "slskd".to_string());
    let node_pass = std::env::var("LYRA_PROTOCOL_NODE_PASS")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "slskd".to_string());
    let soulseek_user = std::env::var("SOULSEEK_USERNAME")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "~".to_string());
    let soulseek_pass = std::env::var("SOULSEEK_PASSWORD")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "~".to_string());

    let downloads_root = std::env::var("DOWNLOADS_FOLDER")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "A:\\Music".to_string());
    let incomplete_root = format!("{}\\_incomplete", downloads_root.trim_end_matches('\\'));

    // slskd validates these directories at startup; create them proactively.
    fs::create_dir_all(PathBuf::from(&downloads_root)).map_err(|e| {
        LyraError::Message(format!("Failed to create slskd downloads directory: {}", e))
    })?;
    fs::create_dir_all(PathBuf::from(&incomplete_root)).map_err(|e| {
        LyraError::Message(format!("Failed to create slskd incomplete directory: {}", e))
    })?;

    let config_content = format!(
        r#"# Zero-Touch slskd configuration (auto-generated by Lyra)
# This file is regenerated on each app boot.

directories:
    downloads: "{}"
    incomplete: "{}"

web:
    port: {}
    ip_address: 127.0.0.1
    https:
        disabled: false
        port: {}
        ip_address: 127.0.0.1
    authentication:
        disabled: false
        username: "{}"
        password: "{}"

soulseek:
    address: vps.slsknet.org
    port: 2271
    username: {}
    password: {}
    description: "Lyra Music Intelligence"
    listen_ip_address: 0.0.0.0
    listen_port: {}

global:
    upload:
        slots: 5
    download:
        slots: 50

retention:
    search: 1440

logger:
    disk: false
"#,
        downloads_root.replace('\\', "\\\\"),
        incomplete_root.replace('\\', "\\\\"),
        port,
        api_port,
        node_user,
        node_pass,
        soulseek_user,
        soulseek_pass,
        SLSKD_DEFAULT_LISTEN_PORT
    );

    fs::write(config_path, config_content).map_err(|e| {
        LyraError::Message(format!("Failed to write slskd config: {}", e))
    })?;

    debug!("Generated slskd.yml at {}", config_path.display());
    Ok(())
}

/// Spawns slskd.exe as a background process.
/// On Windows, the process is created with CREATE_NO_WINDOW to keep it hidden.
fn spawn_daemon_process(config_path: &Path, _log_path: &Path) -> LyraResult<Child> {
    // Determine slskd binary location
    // Priority: 1. Relative to app root 2. In PATH 3. Error
    let slskd_exe = find_slskd_executable()?;

    let mut cmd = Command::new(&slskd_exe);
    cmd.arg("--config")
        .arg(config_path)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    // On Windows, hide the console window
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.spawn().map_err(|e| {
        LyraError::Message(format!(
            "Failed to spawn slskd daemon ({}): {}\n\
             Please ensure slskd.exe is available on PATH or in the app bundle",
            slskd_exe.display(),
            e
        ))
    })
}

/// Finds the slskd executable in standard locations.
fn find_slskd_executable() -> LyraResult<PathBuf> {
    // Try relative paths first (bundled sidecar)
    let candidates = vec![
        PathBuf::from(".").join("slskd.exe"), // App root
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("binaries")
            .join("slskd.exe"), // Monorepo structure
    ];

    for candidate in candidates {
        if candidate.exists() {
            info!(
                "Found slskd.exe at bundled location: {}",
                candidate.display()
            );
            return Ok(candidate);
        }
    }

    // Fall back to PATH
    "slskd"
        .lines()
        .next()
        .ok_or(LyraError::InvalidInput(
            "slskd not found. Please place slskd.exe in app bundle or PATH",
        ))?;

    Ok(PathBuf::from("slskd.exe"))
}

/// Checks if daemon is already responding.
fn is_daemon_responding(port: u16, api_port: u16) -> bool {
    // Check main listener port
    if let Ok(listener) = TcpListener::bind(format!("127.0.0.1:{}", port)) {
        drop(listener);
        return false; // Port is free, daemon not running
    }

    // Check API port
    if let Ok(listener) = TcpListener::bind(format!("127.0.0.1:{}", api_port)) {
        drop(listener);
        return false; // Port is free, daemon not running
    }

    true // Both ports in use, daemon likely running
}

/// Waits for daemon to become responsive (API endpoint reachable).
fn wait_for_daemon_ready(timeout_ms: u32, _api_port: u16) -> LyraResult<()> {
    let start = std::time::Instant::now();
    let timeout = Duration::from_millis(timeout_ms as u64);

    loop {
        if start.elapsed() > timeout {
            return Err(LyraError::InvalidInput(
                "slskd daemon failed to start within timeout period",
            ));
        }

        // Try to connect to API port
        if let Ok(stream) = std::net::TcpStream::connect("127.0.0.1:5031") {
            drop(stream);
            thread::sleep(Duration::from_millis(100)); // Extra stabilization delay
            return Ok(());
        }

        thread::sleep(Duration::from_millis(100));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_generation() {
        let temp_dir = tempfile::tempdir().unwrap();
        let config_path = temp_dir.path().join("test.yml");
        generate_slskd_config(&config_path, 5030, 5031).unwrap();
        assert!(config_path.exists());
        let content = fs::read_to_string(&config_path).unwrap();
        assert!(content.contains("127.0.0.1"));
        assert!(content.contains("5030"));
        assert!(content.contains("5031"));
    }
}

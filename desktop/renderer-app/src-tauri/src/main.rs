use serde::Serialize;
use serde_json::{json, Value};
use std::env;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::GlobalShortcutManager;
use tauri::Manager;

#[derive(Clone, Serialize)]
struct BootStatus {
    phase: String,
    message: String,
    ready: bool,
}

struct AppState {
    backend_process: Mutex<Option<Child>>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum BackendLaunchMode {
    Auto,
    Dev,
    Packaged,
}

fn boot_log_path() -> PathBuf {
    if let Ok(path) = env::var("LYRA_HOST_BOOT_LOG") {
        let trimmed = path.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    env::temp_dir().join("lyra-host-boot.log")
}

fn write_boot_log(message: &str) {
    let path = boot_log_path();
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{message}");
    }
}

fn emit_boot_status(app: &tauri::AppHandle, phase: &str, message: &str, ready: bool) {
    write_boot_log(&format!("[boot-status] phase={phase} ready={ready} message={message}"));
    let payload = BootStatus {
        phase: phase.to_string(),
        message: message.to_string(),
        ready,
    };
    let _ = app.emit_all("lyra://boot-status", payload);
}

fn backend_base_url() -> String {
    env::var("LYRA_BACKEND_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:5000".to_string())
        .trim_end_matches('/')
        .to_string()
}

fn parse_backend_launch_mode() -> BackendLaunchMode {
    let raw = env::var("LYRA_BACKEND_MODE")
        .unwrap_or_else(|_| "auto".to_string())
        .trim()
        .to_lowercase();
    match raw.as_str() {
        "dev" => BackendLaunchMode::Dev,
        "packaged" | "sidecar" => BackendLaunchMode::Packaged,
        _ => BackendLaunchMode::Auto,
    }
}

fn env_truthy(value: &str) -> bool {
    matches!(value.trim().to_lowercase().as_str(), "1" | "true" | "yes" | "on")
}

fn is_tauri_dev_runtime() -> bool {
    if let Ok(value) = env::var("TAURI_DEV") {
        if env_truthy(&value) {
            return true;
        }
    }
    if let Ok(value) = env::var("LYRA_TAURI_DEV") {
        if env_truthy(&value) {
            return true;
        }
    }
    false
}

fn health_ready(base_url: &str) -> bool {
    let url = format!("{base_url}/api/health");
    let request = ureq::get(&url).timeout(Duration::from_millis(900));

    match request.call() {
        Ok(response) => {
            if response.status() != 200 {
                return false;
            }
            let body = response.into_string().unwrap_or_default();
            if body.trim().is_empty() {
                return false;
            }
            match serde_json::from_str::<Value>(&body) {
                Ok(payload) => payload
                    .get("status")
                    .and_then(Value::as_str)
                    .map(|status| status.eq_ignore_ascii_case("ok"))
                    .unwrap_or(false),
                Err(_) => false,
            }
        }
        Err(_) => false,
    }
}

fn resolve_project_root() -> Option<PathBuf> {
    if let Ok(root) = env::var("LYRA_PROJECT_ROOT") {
        let candidate = PathBuf::from(root);
        if candidate.join("lyra_api.py").exists() {
            write_boot_log(&format!(
                "[resolve-project-root] using LYRA_PROJECT_ROOT={}",
                candidate.display()
            ));
            return Some(candidate);
        }
    }

    if let Ok(cwd) = env::current_dir() {
        for dir in cwd.ancestors() {
            if dir.join("lyra_api.py").exists() {
                write_boot_log(&format!(
                    "[resolve-project-root] discovered from cwd={}",
                    dir.display()
                ));
                return Some(dir.to_path_buf());
            }
        }
    }

    None
}

fn resolve_packaged_backend_exe() -> Option<PathBuf> {
    if let Ok(path) = env::var("LYRA_BACKEND_EXE") {
        if !path.trim().is_empty() {
            let candidate = PathBuf::from(path);
            if candidate.exists() {
                write_boot_log(&format!(
                    "[resolve-packaged-backend] using LYRA_BACKEND_EXE={}",
                    candidate.display()
                ));
                return Some(candidate);
            }
        }
    }

    if let Ok(current_exe) = env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            let candidates = [
                parent.join("lyra_backend.exe"),
                parent.join("bin").join("lyra_backend.exe"),
                parent.join("resources").join("lyra_backend.exe"),
                parent.join("resources").join("bin").join("lyra_backend.exe"),
            ];
            for candidate in candidates {
                if candidate.exists() {
                    write_boot_log(&format!(
                        "[resolve-packaged-backend] using bundled candidate={}",
                        candidate.display()
                    ));
                    return Some(candidate);
                }
            }
        }
    }

    None
}

fn resolve_python_exe(project_root: &Path) -> String {
    if let Ok(python) = env::var("LYRA_PYTHON_EXE") {
        if !python.trim().is_empty() {
            return python;
        }
    }

    let venv_python = project_root.join(".venv").join("Scripts").join("python.exe");
    if venv_python.exists() {
        return venv_python.to_string_lossy().to_string();
    }

    "python".to_string()
}

fn resolve_runtime_root(project_root: &Path) -> PathBuf {
    if project_root
        .file_name()
        .and_then(|name| name.to_str())
        .map(|name| name.eq_ignore_ascii_case("runtime"))
        .unwrap_or(false)
    {
        project_root.to_path_buf()
    } else {
        project_root.join("runtime")
    }
}

fn runtime_bin_dirs(project_root: &Path) -> Vec<PathBuf> {
    let runtime_root = resolve_runtime_root(project_root);
    vec![
        runtime_root.join("bin"),
        runtime_root.join("tools"),
        runtime_root.join("acquisition-tools"),
    ]
}

fn apply_runtime_environment(command: &mut Command, project_root: &Path) {
    let runtime_root = resolve_runtime_root(project_root);
    command.env(
        "LYRA_RUNTIME_ROOT",
        runtime_root.to_string_lossy().to_string(),
    );
    write_boot_log(&format!(
        "[runtime-env] project_root={} runtime_root={}",
        project_root.display(),
        runtime_root.display()
    ));

    let mut paths: Vec<PathBuf> = runtime_bin_dirs(project_root)
        .into_iter()
        .filter(|path| path.exists())
        .collect();
    if let Some(existing_path) = env::var_os("PATH") {
        paths.extend(env::split_paths(&existing_path));
    }
    if let Ok(joined_path) = env::join_paths(paths) {
        command.env("PATH", joined_path);
    }
}

fn launch_dev_backend_process() -> Result<Child, String> {
    let project_root = resolve_project_root()
        .ok_or_else(|| "LYRA dev backend launch failed: project root was not found".to_string())?;
    let python_exe = resolve_python_exe(&project_root);
    write_boot_log(&format!(
        "[launch-dev-backend] python={} cwd={}",
        python_exe,
        project_root.display()
    ));
    let mut command = Command::new(&python_exe);
    command
        .arg("lyra_api.py")
        .current_dir(&project_root)
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    apply_runtime_environment(&mut command, &project_root);
    command
        .spawn()
        .map_err(|error| format!("LYRA dev backend launch failed: {error}"))
}

fn launch_packaged_backend_process() -> Result<Child, String> {
    let sidecar_exe = resolve_packaged_backend_exe().ok_or_else(|| {
        "LYRA packaged backend launch failed: lyra_backend.exe was not found".to_string()
    })?;
    let fallback_runtime_root = sidecar_exe
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    let runtime_root = resolve_project_root().unwrap_or(fallback_runtime_root);
    write_boot_log(&format!(
        "[launch-packaged-backend] exe={} cwd={}",
        sidecar_exe.display(),
        runtime_root.display()
    ));

    let mut command = Command::new(sidecar_exe);
    command
        .current_dir(&runtime_root)
        .env("LYRA_SKIP_VENV_REEXEC", "1")
        .env("LYRA_PROJECT_ROOT", runtime_root.to_string_lossy().to_string());
    apply_runtime_environment(&mut command, &runtime_root);

    if env::var("LYRA_DB_PATH").ok().map(|value| value.trim().is_empty()).unwrap_or(true) {
        command.env(
            "LYRA_DB_PATH",
            runtime_root.join("lyra_registry.db").to_string_lossy().to_string(),
        );
    }
    if env::var("CHROMA_PATH").ok().map(|value| value.trim().is_empty()).unwrap_or(true) {
        command.env(
            "CHROMA_PATH",
            runtime_root.join("chroma_storage").to_string_lossy().to_string(),
        );
    }
    if env::var("LIBRARY_BASE").ok().map(|value| value.trim().is_empty()).unwrap_or(true) {
        command.env(
            "LIBRARY_BASE",
            runtime_root.join("library").to_string_lossy().to_string(),
        );
    }

    command
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("LYRA packaged backend launch failed: {error}"))
}

fn launch_backend_process() -> Result<Child, String> {
    let mode = parse_backend_launch_mode();
    write_boot_log(&format!("[launch-backend] mode={mode:?}"));
    match mode {
        BackendLaunchMode::Dev => launch_dev_backend_process(),
        BackendLaunchMode::Packaged => launch_packaged_backend_process(),
        BackendLaunchMode::Auto => {
            if is_tauri_dev_runtime() {
                launch_dev_backend_process().or_else(|dev_error| {
                    launch_packaged_backend_process().map_err(|packaged_error| {
                        format!("{dev_error}; {packaged_error}")
                    })
                })
            } else {
                launch_packaged_backend_process().or_else(|packaged_error| {
                    launch_dev_backend_process().map_err(|dev_error| {
                        format!("{packaged_error}; {dev_error}")
                    })
                })
            }
        }
    }
}

fn start_backend_sidecar(app: tauri::AppHandle) {
    let base_url = backend_base_url();
    write_boot_log(&format!("[start-backend-sidecar] base_url={base_url}"));
    if health_ready(&base_url) {
        emit_boot_status(&app, "backend", "Backend already running", true);
        return;
    }

    emit_boot_status(&app, "backend", "Starting Lyra backend (attempt 1/3)...", false);

    let mut last_error = String::new();
    let mut launched = None;
    for attempt in 1..=3 {
        match launch_backend_process() {
            Ok(process) => {
                launched = Some(process);
                break;
            }
            Err(error) => {
                last_error = error;
                emit_boot_status(
                    &app,
                    "backend",
                    &format!("Backend launch attempt {attempt}/3 failed: {last_error}"),
                    false,
                );
                thread::sleep(Duration::from_millis(350 * attempt as u64));
            }
        }
    }

    let Some(process) = launched else {
        emit_boot_status(
            &app,
            "backend",
            &format!("Failed to start backend after retries: {last_error}"),
            false,
        );
        return;
    };

    if let Ok(mut guard) = app.state::<AppState>().backend_process.lock() {
        *guard = Some(process);
    }

    let app_handle = app.clone();
    thread::spawn(move || {
        let mut sleep_ms = 250_u64;
        for _ in 0..32 {
            if health_ready(&base_url) {
                emit_boot_status(&app_handle, "backend", "Backend ready", true);
                return;
            }
            thread::sleep(Duration::from_millis(sleep_ms));
            sleep_ms = (sleep_ms * 2).min(2_000);
        }
        emit_boot_status(
            &app_handle,
            "backend",
            "Backend health timeout; open retry in UI or restart app",
            false,
        );
    });
}

fn post_player_command(base_url: &str, path: &str, body: Value) -> Result<(), String> {
    let url = format!("{base_url}{path}");
    let response = ureq::post(&url)
        .set("Content-Type", "application/json")
        .send_string(&body.to_string());

    match response {
        Ok(_) => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}

fn get_player_status(base_url: &str) -> Result<String, String> {
    let url = format!("{base_url}/api/player/state");
    let response = ureq::get(&url)
        .timeout(Duration::from_millis(1200))
        .call()
        .map_err(|error| error.to_string())?;

    let text = response.into_string().map_err(|error| error.to_string())?;
    let payload: Value = serde_json::from_str(&text).map_err(|error| error.to_string())?;
    Ok(payload
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or("idle")
        .to_string())
}

fn dispatch_transport_to_backend(app: &tauri::AppHandle, action: &str) {
    let base_url = backend_base_url();
    if !health_ready(&base_url) {
        emit_boot_status(app, "backend", "Backend unavailable for transport command", false);
        return;
    }

    let result = match action {
        "play-pause" => {
            let status = get_player_status(&base_url).unwrap_or_else(|_| "idle".to_string());
            if status == "playing" {
                post_player_command(&base_url, "/api/player/pause", json!({}))
            } else {
                post_player_command(&base_url, "/api/player/play", json!({}))
            }
        }
        "next" => post_player_command(&base_url, "/api/player/next", json!({})),
        "previous" => post_player_command(&base_url, "/api/player/previous", json!({})),
        _ => Ok(()),
    };

    if let Err(error) = result {
        emit_boot_status(
            app,
            "backend",
            &format!("Player command failed: {error}"),
            false,
        );
    }
}

fn register_media_shortcuts(app: &tauri::AppHandle) {
    let mut manager = app.global_shortcut_manager();

    let shortcuts = [
        ("MediaPlayPause", "play-pause"),
        ("MediaNextTrack", "next"),
        ("MediaPrevTrack", "previous"),
    ];

    for (accelerator, action) in shortcuts {
        let app_handle = app.clone();
        let _ = manager.register(accelerator, move || {
            dispatch_transport_to_backend(&app_handle, action);
        });
    }
}

fn stop_backend_process(app: &tauri::AppHandle) {
    if let Ok(mut guard) = app.state::<AppState>().backend_process.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
        }
    }
}

fn main() {
    write_boot_log("[main] starting tauri host");
    let tray_menu = tauri::SystemTrayMenu::new()
        .add_item(tauri::CustomMenuItem::new("show", "Show / Hide"))
        .add_item(tauri::CustomMenuItem::new("play_pause", "Play / Pause"))
        .add_item(tauri::CustomMenuItem::new("previous", "Previous"))
        .add_item(tauri::CustomMenuItem::new("next", "Next"))
        .add_native_item(tauri::SystemTrayMenuItem::Separator)
        .add_item(tauri::CustomMenuItem::new("quit", "Quit"));

    let state = AppState {
        backend_process: Mutex::new(None),
    };

    tauri::Builder::default()
        .manage(state)
        .system_tray(tauri::SystemTray::new().with_menu(tray_menu))
        .setup(|app| {
            write_boot_log("[main] setup entered");
            let app_handle = app.handle();
            start_backend_sidecar(app_handle.clone());
            register_media_shortcuts(&app_handle);
            Ok(())
        })
        .on_system_tray_event(|app, event| {
            if let tauri::SystemTrayEvent::MenuItemClick { id, .. } = event {
                match id.as_str() {
                    "show" => {
                        if let Some(window) = app.get_window("main") {
                            if window.is_visible().unwrap_or(true) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                    "play_pause" => dispatch_transport_to_backend(app, "play-pause"),
                    "previous" => dispatch_transport_to_backend(app, "previous"),
                    "next" => dispatch_transport_to_backend(app, "next"),
                    "quit" => {
                        stop_backend_process(app);
                        std::process::exit(0);
                    }
                    _ => {}
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while running tauri application")
        .run(|app_handle, run_event| {
            if matches!(run_event, tauri::RunEvent::Exit) {
                write_boot_log("[main] exit event received");
                stop_backend_process(app_handle);
            }
        });
}

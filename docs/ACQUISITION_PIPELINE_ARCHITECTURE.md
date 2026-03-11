# Lyra Acquisition Pipeline Architecture

**Document Date:** March 10, 2026  
**Scope:** Comprehensive mapping of acquisition waterfall, credential handling, provider configuration, and subprocess execution in the canonical Rust runtime.

---

## Executive Summary

The current acquisition pipeline is fully implemented in **Rust** within the canonical Tauri/SvelteKit/Rust architecture. No Python sidecar is active in the main runtime. Credentials are stored in SQLite `provider_configs` table with fallback to OS keyring for sensitive tokens. The waterfall chain (Qobuz → Streamrip → Slskd → SpotDL → yt-dlp) executes as a series of native Rust tier functions with subprocess bridging for external tools.

---

## 1. CREDENTIAL STORAGE & LOADING

### 1.1 Primary Credential Store: SQLite `provider_configs` Table

**Location:** `crates/lyra-core/src/db.rs` (lines 105-113)

```sql
CREATE TABLE IF NOT EXISTS provider_configs (
  provider_key TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  config_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);
```

**Why JSON field?** Flexible schema per provider. Each provider stores its config as a single JSON object:
```json
{
  "qobuz_service_url": "http://localhost:7700",
  "qobuz_app_id": "...",
  "QOBUZ_QUALITY": "flac"
}
```

**Save/Load Pattern:**

```rust
// Load (providers.rs, line 50)
pub fn load_provider_config(conn: &Connection, provider_key: &str) -> Option<Value> {
    conn.query_row(
        "SELECT config_json FROM provider_configs WHERE provider_key = ?1 AND enabled = 1",
        params![provider_key],
        |row| row.get::<_, String>(0),
    )
    .ok()
    .and_then(|s| serde_json::from_str(&s).ok())
}

// Save (providers.rs, line 62)
pub fn save_provider_config(
    conn: &Connection,
    provider_key: &str,
    config_json: &Value,
) -> LyraResult<()> {
    conn.execute(
        "INSERT INTO provider_configs (...) VALUES (...)
         ON CONFLICT(provider_key) DO UPDATE SET ...",
        params![provider_key, display_name, serde_json::to_string(config_json)?, ...]
    )?;
    Ok(())
}
```

### 1.2 OS Keyring (Windows Credential Manager)

**Location:** `crates/lyra-core/src/providers.rs` (lines 1559–1586)

**Purpose:** Store sensitive secrets (OAuth tokens, passwords) outside the SQLite database.

```rust
pub fn keyring_save(provider_key: &str, key_name: &str, secret: &str) -> Result<(), String> {
    let account = format!("{provider_key}:{key_name}");
    Entry::new(KEYRING_SERVICE, &account)  // KEYRING_SERVICE = "lyra-media-player"
        .map_err(|e| e.to_string())?
        .set_password(secret)
        .map_err(|e| e.to_string())
}

pub fn keyring_load(provider_key: &str, key_name: &str) -> Result<Option<String>, String> {
    let account = format!("{provider_key}:{key_name}");
    match Entry::new(KEYRING_SERVICE, &account).map_err(|e| e.to_string())?
        .get_password() {
        Ok(secret) => Ok(Some(secret)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}
```

**Example Spotify Token Storage:**
```
Service: "lyra-media-player"
Account: "spotify:oauth_access_token"     → stored in Windows Credential Manager
Account: "spotify:oauth_refresh_token"    → stored in Windows Credential Manager
```

**Additional DB Row for Session State:**
```sql
CREATE TABLE provider_oauth_sessions (
  provider_key TEXT PRIMARY KEY,
  token_type TEXT,
  scope TEXT,
  access_token_expires_at TEXT,
  refreshed_at TEXT
);
```

### 1.3 Environment Variable Fallback

**Legacy Pattern:** `LYRA_LLM_*`, `QOBUZ_*`, `STREAMRIP_*`, etc.

**Loading Order (providers.rs, line 844 `load_llm_config`):**
```
1. Try DB provider_configs for: groq → openrouter → openai → ollama
2. Fallback to LYRA_LLM_* environment variables
```

**Environment Credential Backup (providers.rs, line 1614):**
```rust
pub fn backup_env_to_keychain(env_path: &str) -> Result<(usize, usize), String> {
    // Scan .env file for lines with KEY|SECRET|TOKEN|PASSWORD|AUTH|EMAIL
    // Save each to keyring as "env:{KEY_NAME}"
}
```

**Loading Backed-Up Secrets (providers.rs, line 1682):**
```rust
pub fn load_env_credential(key_name: &str) -> Result<Option<String>, String> {
    let account = format!("env:{key_name}");
    match Entry::new(KEYRING_SERVICE, &account)?.get_password() {
        Ok(v) => Ok(Some(v)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}
```

---

## 2. QOBUZ & SOULSEEK CREDENTIAL HANDLING

### 2.1 Qobuz Tier (T1)

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 449–557)

**Architecture:** Lyra calls a local **Qobuz service bridge** (not direct API calls).

**Config Loading:**
```rust
fn try_native_qobuz_service(...) -> LyraResult<AcquireTrackResult> {
    let config = load_provider_config(conn, "qobuz");
    let service_url = config
        .and_then(|v| v.get("qobuz_service_url")
                      .or_else(|| v.get("QOBUZ_SERVICE_URL")))
        .and_then(Value::as_str)
        .unwrap_or("http://localhost:7700")   // Default bridge endpoint
        .trim_end_matches('/')
        .to_string();
    // ...
}
```

**Config Fields:**
| Field | Fallback | Purpose |
|-------|----------|---------|
| `qobuz_service_url` | `http://localhost:7700` | Local service bridge |
| `qobuz_app_id` | (none) | Optional: stored in config_json |
| `QOBUZ_QUALITY` | (none) | Optional: stored in config_json |

**Credential Flow:**
```
Lyra (Rust) → HTTP POST /acquire → Qobuz Service Bridge (local) 
              ↓
           Bridge handles Qobuz OAuth/credentials internally
           (Lyra never sees raw Qobuz username/password)
```

**Request:**
```rust
ureq::post(&format!("{service_url}/acquire"))
    .set("Content-Type", "application/json")
    .send_json(serde_json::json!({ "artist": artist, "title": title }))
```

**Response Handling:** Expects `{ "success": true, "path": "..." }`

**Key Point:** Qobuz credentials are **NOT managed by Lyra**; they're managed by the bridge service.

---

### 2.2 Soulseek/Slskd Tier (T3)

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 567–730)

**Config Loading (lines 567–601):**
```rust
fn slskd_node_config(conn: &Connection) -> (String, String, Option<String>, String, String) {
    let config = load_provider_config(conn, "slskd");
    
    // URL
    let base_url = config
        .and_then(|v| v.get("slskd_url")
                      .or_else(|| v.get("SLSKD_URL"))
                      .or_else(|| v.get("lyra_protocol_node_url"))
                      .or_else(|| v.get("LYRA_PROTOCOL_NODE_URL")))
        .and_then(Value::as_str)
        .unwrap_or("http://localhost:5030")
        .to_string();
    
    // API Base Path
    let api_base = std::env::var("LYRA_PROTOCOL_NODE_API_BASE")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .unwrap_or_else(|| "/api/v0".to_string());
    
    // API Key (optional)
    let api_key = config
        .and_then(|v| v.get("slskd_api_key")
                      .or_else(|| v.get("SLSKD_API_KEY"))
                      .or_else(|| v.get("lyra_protocol_node_key"))
                      .or_else(|| v.get("LYRA_PROTOCOL_NODE_KEY")))
        .and_then(Value::as_str)
        .map(str::to_string);
    
    // Username (fallback)
    let username = config
        .and_then(|v| v.get("lyra_protocol_node_user")
                      .or_else(|| v.get("LYRA_PROTOCOL_NODE_USER"))
                      .or_else(|| v.get("slskd_user")))
        .and_then(Value::as_str)
        .unwrap_or("slskd")
        .to_string();
    
    // Password (fallback)
    let password = config
        .and_then(|v| v.get("lyra_protocol_node_pass")
                      .or_else(|| v.get("LYRA_PROTOCOL_NODE_PASS"))
                      .or_else(|| v.get("slskd_pass")))
        .and_then(Value::as_str)
        .unwrap_or("slskd")
        .to_string();
    
    (base_url, api_base, api_key, username, password)
}
```

**Config Fields:**
| Field | Env Priority | Default |
|-------|---------------|---------|
| `slskd_url` | `LYRA_PROTOCOL_NODE_URL` | `http://localhost:5030` |
| `slskd_api_key` | `LYRA_PROTOCOL_NODE_KEY` | None (optional) |
| `lyra_protocol_node_user` | `LYRA_PROTOCOL_NODE_USER` | `"slskd"` |
| `lyra_protocol_node_pass` | `LYRA_PROTOCOL_NODE_PASS` | `"slskd"` |

**Authentication (lines 634–658):**
```rust
fn slskd_headers(conn: &Connection) -> LyraResult<Vec<(String, String)>> {
    let (base_url, api_base, api_key, username, password) = slskd_node_config(conn);
    
    // If API key exists, use it
    if let Some(api_key) = api_key.filter(|v| !v.trim().is_empty()) {
        return Ok(vec![("X-API-Key".to_string(), api_key)]);
    }
    
    // Otherwise, authenticate with username+password
    let login_url = slskd_api_url(&base_url, &api_base, "/session");
    let response = ureq::post(&login_url)
        .set("Content-Type", "application/json")
        .send_json(serde_json::json!({ "username": username, "password": password }))?;
    
    let payload: Value = response.into_json()?;
    let token = payload.get("token").and_then(Value::as_str)
        .ok_or(LyraError::InvalidInput("slskd authentication failed"))?;
    
    Ok(vec![("Authorization".to_string(), format!("Bearer {token}"))])
}
```

**Credential Flow:**
```
Option 1: API Key
  → Send header: "X-API-Key: {key}"

Option 2: Username+Password
  → POST /session { "username": "...", "password": "..." }
  → Get { "token": "..." }
  → Send header: "Authorization: Bearer {token}"
```

**Search + Download (lines 756–920):**
```
POST /searches { "searchText": "{artist} {title}" }
  ↓
Poll GET /searches/{id}?includeResponses=true (6 attempts, 3s interval)
  ↓
SELECT best candidate by format+bitrate
  ↓
POST /transfers/downloads/{username} { "filename": "..." }
  ↓
Wait for file in DOWNLOADS_FOLDER (60 attempts, 3s interval)
```

---

## 3. STREAMRIP TIER (T2)

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 326–443)

**Architecture:** Spawns `streamrip` as subprocess; **does not pass credentials directly to Lyra**.

**Config Loading (lines 335–367):**
```rust
fn try_native_streamrip(...) -> LyraResult<AcquireTrackResult> {
    let config = load_provider_config(conn, "streamrip");
    
    // Binary path
    let binary_path = config
        .and_then(|v| v.get("lyra_streamrip_binary")
                      .or_else(|| v.get("LYRA_STREAMRIP_BINARY")))
        .and_then(Value::as_str)
        .or_else(|| std::env::var("LYRA_STREAMRIP_BINARY").ok());
    
    // Source (default: Qobuz)
    let source = config
        .and_then(|v| v.get("lyra_streamrip_source")
                      .or_else(|| v.get("LYRA_STREAMRIP_SOURCE")))
        .and_then(Value::as_str)
        .unwrap_or("qobuz");
    
    // Find binary in PATH
    let Some(binary) = find_command(binary_path, &["streamrip"]) else { ... }
}
```

**Config Fields:**
| Field | Env Fallback | Purpose |
|-------|--------------|---------|
| `lyra_streamrip_binary` | `LYRA_STREAMRIP_BINARY` | Path to streamrip executable |
| `lyra_streamrip_source` | `LYRA_STREAMRIP_SOURCE` | Source (qobuz/tidal/etc., default: qobuz) |
| `lyra_streamrip_cmd_template` | `LYRA_STREAMRIP_CMD_TEMPLATE` | Optional: custom command template |

**Subprocess Execution:**
```rust
let output_dir = acquisition_staging_dir(paths).join(format!("streamrip-queue-{queue_id}"));
fs::create_dir_all(&output_dir)?;

let query = build_streamrip_query(artist, title, album);

let mut cmd = Command::new(binary);
// Streamrip is invoked with standard CLI args; it reads its own config (~/.streamrip/)
// Lyra does NOT pass credentials on command line

let result = run_monitored_command(cmd, queue_id, conn)?;
```

**Key Point:** Streamrip credentials are **NOT managed by Lyra**. Lyra only:
1. Points to the streamrip binary
2. Specifies the source (Qobuz/Tidal/etc.)
3. Passes search terms (artist, title, album)

Streamrip reads its own config from `~/.streamrip/` (Linux) or `AppData\streamrip\` (Windows).

---

## 4. SPOTDL TIER (T5)

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 921–975)

**Config Loading:**
```rust
fn try_native_spotdl(...) {
    let Some(binary) = find_command(None, &["spotdl"]) else { ... }
}
```

**Subprocess Execution:**
```rust
let output_dir = acquisition_staging_dir(paths).join(format!("spotdl-queue-{queue_id}"));
fs::create_dir_all(&output_dir)?;

let query = format!("{artist} - {title}");

let mut cmd = Command::new(binary);
cmd.arg("download")
   .arg(&query)
   .arg("--output").arg(&output_dir)
   .arg("--format").arg("mp3")
   .arg("--bitrate").arg("320k")
   .arg("--threads").arg("1");

let result = run_monitored_command(cmd, queue_id, conn)?;
```

**Credential Handling:**
- SpotDL reads Spotify credentials from its own config (~/.spotdl/)
- Lyra does NOT pass credentials

---

## 5. YT-DLP TIER (T4)

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 1026–1049)
**Trait Implementation:** `crates/lyra-core/src/waterfall.rs` (lines 1–200)

**Execution:**
```rust
fn try_native_ytdlp(...) {
    use crate::waterfall::{YtdlpTier, AcquisitionTier, TierResult};
    
    let tier = YtdlpTier::default();
    if tier.find_binary().is_none() { ... }
    
    let staging_dir = acquisition_staging_dir(paths);
    let item = AcquisitionQueueItem { id: queue_id, artist: ..., title: ..., ... };
    
    match tier.try_acquire(&item, &staging_dir) {
        TierResult::Success(path) => Ok(AcquireTrackResult { path: Some(path), ... }),
        TierResult::Fail(reason) => Ok(AcquireTrackResult { failure_reason: Some(reason), ... }),
    }
}
```

**`YtdlpTier` Trait (waterfall.rs):**
```rust
pub trait AcquisitionTier: Send + Sync {
    fn name(&self) -> &str;
    fn try_acquire(&self, item: &AcquisitionQueueItem, staging_dir: &Path) -> TierResult;
}

pub struct YtdlpTier { /* ... */ }

impl AcquisitionTier for YtdlpTier {
    fn try_acquire(&self, item: &AcquisitionQueueItem, staging_dir: &Path) -> TierResult {
        // Spawn yt-dlp with search query
        // Download to staging_dir
        // Return TierResult::Success(path) or TierResult::Fail(reason)
    }
}
```

---

## 6. WATERFALL ORCHESTRATION

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 1091–1140)

### 6.1 Main Waterfall Function

```rust
fn try_native_acquire_track(
    paths: &AppPaths,
    artist: &str,
    title: &str,
    album: Option<&str>,
    queue_id: i64,
    conn: &rusqlite::Connection,
    notify: &Arc<dyn Fn(i64) + Send + Sync>,
) -> LyraResult<AcquireTrackResult> {
    // Waterfall: T1 Qobuz (lossless) → T2 Streamrip (lossless) → T3 Slskd (lossless/lossy) 
    //            → T5 SpotDL (lossy) → T4 yt-dlp (lossy fallback)
    
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
    
    let ytdlp = try_native_ytdlp(paths, artist, title, queue_id, conn, notify)?;
    if ytdlp.cancelled || ytdlp.path.is_some() {
        return Ok(ytdlp);
    }
    
    Ok(ytdlp)  // Return last tier result (success or final failure)
}
```

### 6.2 Queue Item Processing

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 1416–1600+)

```rust
pub fn process_next_queue_item_with_callback<F>(paths: &AppPaths, notify: F) -> LyraResult<bool>
where
    F: Fn(i64) + Send + Sync + 'static,
{
    let conn = crate::db::connect(paths)?;
    let notify: Arc<dyn Fn(i64) + Send + Sync> = Arc::new(notify);
    
    // 1. Fetch next queued item (by priority + queue position)
    let item: Option<QueuedItemRow> = conn.query_row(
        "SELECT id, artist, title, album, target_root_id, target_root_path
         FROM acquisition_queue
         WHERE status = 'queued'
         ORDER BY priority_score DESC, queue_position ASC, id ASC
         LIMIT 1",
        [],
        |row| { Ok((row.get(0)?, ...)) },
    ).optional()?;
    
    let Some((id, artist, title, album, target_root_id, target_root_path)) = item else {
        return Ok(false);  // Queue empty
    };
    
    // 2. Preflight checks
    let _ = acquisition::update_lifecycle(&conn, id, "validating", 0.05, ...);
    notify(id);
    
    // Check target root accessibility
    let target_root = if let Some(path) = target_root_path.as_ref() {
        let root_path = PathBuf::from(path);
        if !root_path.exists() {
            acquisition::mark_failed(&conn, id, "validating", "Target root not accessible", ...)?;
            return Ok(true);
        }
        Some(root_path)
    } else {
        None
    };
    
    // Check library root available
    let library_root_available = if let Some(root) = target_root.as_ref() {
        root.exists()
    } else {
        library::list_library_roots(&conn)?
            .into_iter()
            .any(|root| PathBuf::from(root.path).exists())
    };
    
    if !library_root_available {
        acquisition::mark_failed(&conn, id, "validating", "No accessible library root", ...)?;
        return Ok(true);
    }
    
    // 3. Check for duplicate (already in library)
    if let Some(path) = duplicate_path_for_track(&conn, &artist, &title)? {
        acquisition::mark_skipped(&conn, id, "found existing track", Some(&path))?;
        return Ok(true);
    }
    
    // 4. Run waterfall acquisition
    match acquire_track(paths, &artist, &title, album.as_deref(), id, &conn, &notify) {
        Ok(result) => {
            if result.cancelled {
                acquisition::mark_cancelled(&conn, id)?;
            } else if let Some(path) = result.path {
                // Organize into library structure
                match organize_download(&conn, &path, target_root.as_deref(), &artist, &title, album.as_deref()) {
                    Ok(organized_path) => {
                        if let Ok(Some(track_id)) = track_id_for_path(&conn, &organized_path) {
                            acquisition::mark_completed(&conn, id, organized_path, result.provider, result.tier)?;
                        }
                    }
                    Err(e) => acquisition::mark_failed(&conn, id, "organizing", &e.to_string(), ...)?
                }
            } else {
                acquisition::mark_failed(&conn, id, &result.failure_stage.unwrap_or("unknown"), 
                                        &result.failure_reason.unwrap_or("no output"), ...)?;
            }
        }
        Err(e) => {
            acquisition::mark_failed(&conn, id, "acquiring", &e.to_string(), ...)?;
        }
    }
    
    Ok(true)  // Item was processed
}
```

---

## 7. ACQUISITION QUEUE STATE MANAGEMENT

**Location:** `crates/lyra-core/src/acquisition.rs` (lines 1–100)

### 7.1 Database Schema

```sql
CREATE TABLE acquisition_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  artist TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  album TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  queue_position INTEGER NOT NULL DEFAULT 0,
  priority_score REAL NOT NULL DEFAULT 0.0,
  source TEXT,
  added_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  failed_at TEXT,
  cancelled_at TEXT,
  error TEXT,
  status_message TEXT,
  failure_stage TEXT,
  failure_reason TEXT,
  failure_detail TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  selected_provider TEXT,
  selected_tier TEXT,
  worker_label TEXT,
  output_path TEXT,
  target_root_id INTEGER,
  target_root_path TEXT
);
```

### 7.2 Status Lifecycle

```
queued → validating → acquiring → staging → scanning → organizing → indexing → completed
  ↓                                                                              ↓
  └─────────────────── cancelled (at any stage) ─────────────────────────────→ (cancelled)
  ↓
  └─────────────────── failed → (retry_count < max) → queued
                               → (retry_count ≥ max) → (failed) [terminal]
```

### 7.3 Lifecycle Update Function

```rust
pub fn update_lifecycle(
    conn: &Connection,
    queue_id: i64,
    status: &str,
    progress: f64,           // 0.0 to 1.0
    note: Option<&str>,
    provider: Option<&str>,
    tier: Option<&str>,
    stage: Option<&str>,
) -> LyraResult<()> {
    conn.execute(
        "UPDATE acquisition_queue
         SET status = ?1, failure_reason = ?2, status_message = ?3, 
             selected_provider = ?4, selected_tier = ?5
         WHERE id = ?6",
        params![status, note, format!("{:.1}%", progress * 100.0), provider, tier, queue_id],
    )?;
    Ok(())
}
```

### 7.4 Cancellation Checking

```rust
pub fn cancel_requested(conn: &Connection, queue_id: i64) -> LyraResult<bool> {
    conn.query_row(
        "SELECT 1 FROM acquisition_queue WHERE id = ?1 AND status = 'cancelled'",
        params![queue_id],
        |_| Ok(()),
    )
    .optional()
    .map(|opt| opt.is_some())
    .map_err(Into::into)
}
```

Between every significant operation (search, download, file check), the tier calls `cancel_requested()` and can bail early.

---

## 8. BACKGROUND WORKER

**Location:** `crates/lyra-core/src/acquisition_worker.rs`

### 8.1 Worker Thread

```rust
pub fn start_worker_with_callback<F>(paths: AppPaths, notify: F) -> bool
where
    F: Fn(i64) + Send + Sync + 'static,
{
    if WORKER_RUNNING.swap(true, Ordering::SeqCst) {
        return false;  // Already running
    }
    
    let notify = Arc::new(notify);
    thread::spawn(move || {
        while WORKER_RUNNING.load(Ordering::SeqCst) {
            match acquisition_dispatcher::process_next_queue_item_with_callback(&paths, {
                let notify = notify.clone();
                move |id| notify(id)
            }) {
                Ok(true) => {
                    info!("Processed acquisition queue item");
                    thread::sleep(Duration::from_secs(5));  // Short delay before next
                }
                Ok(false) => {
                    info!("Queue empty, waiting");
                    thread::sleep(Duration::from_secs(30));  // Longer delay if queue empty
                }
                Err(e) => {
                    warn!("Acquisition worker error: {}", e);
                    thread::sleep(Duration::from_secs(60));  // Long delay on error
                }
            }
        }
    });
    true
}

pub fn stop_worker() {
    WORKER_RUNNING.swap(false, Ordering::SeqCst);
}
```

**Callback Pattern:**
```rust
acquisition_dispatcher::process_next_queue_item_with_callback(&paths, |queue_id| {
    // Callback fired after each lifecycle update
    // Typically: notify Tauri frontend via IPC
    tauri_invoke_callback(queue_id);
})
```

---

## 9. CLI RUNNER

**Location:** `crates/lyra-core/src/bin/acquisition_runner.rs`

### 9.1 Standalone Tool

```bash
cargo run -p lyra-core --bin acquisition_runner -- [--limit N] [--dry-run]
```

### 9.2 Implementation

```rust
let app_data_dir = env::var("APPDATA")
    .map(|value| PathBuf::from(value).join("com.lyra.player"))
    .map_err(|_| "APPDATA not set")?;

let core = LyraCore::new(app_data_dir)?;

// Preflight checks
let preflight = core.acquisition_preflight()?;
if !preflight.ready {
    eprintln!("preflight not ready");
    return Ok(());
}

// Get queue
let queue = core.get_acquisition_queue(None)?;
println!("queue total={} queued={}", queue.len(), queued_count);

// Process items
for i in 0..limit {
    match core.process_acquisition_queue_with_callback(|queue_id| {
        eprintln!("[lifecycle] queue_id={queue_id} updated");
    }) {
        Ok(true) => {
            processed += 1;
            // Check result and report
        }
        Ok(false) => break,  // Queue empty
        Err(e) => println!("ERROR: {e}"),
    }
}

println!("done: processed={} success={} failed={}", processed, success, failed);
```

**Preflight Checks:**
- Downloader available (can find at least one tier binary)
- Disk space adequate
- Library root accessible

---

## 10. SUBPROCESS MANAGEMENT

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 1243–1350+)

### 10.1 Monitored Command Execution

```rust
#[derive(Debug, Default)]
struct MonitoredCommandResult {
    cancelled: bool,
    timed_out: bool,
    stdout: String,
    stderr: String,
    exit_code: Option<i32>,
}

fn run_monitored_command(
    mut cmd: Command,
    queue_id: i64,
    conn: &rusqlite::Connection,
) -> LyraResult<MonitoredCommandResult> {
    let mut child = cmd.spawn()?;
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    
    let (tx, rx) = mpsc::channel();
    
    // Spawn reader threads
    if let Some(out) = stdout {
        let tx_clone = tx.clone();
        thread::spawn(move || {
            let reader = BufReader::new(out);
            for line in reader.lines().flatten() {
                let _ = tx_clone.send(line);
            }
        });
    }
    
    // Periodically check cancellation + timeout
    let start = Instant::now();
    let timeout = Duration::from_secs(600);  // 10 minutes
    
    loop {
        if acquisition::cancel_requested(conn, queue_id)? {
            let _ = child.kill();
            return Ok(MonitoredCommandResult {
                cancelled: true,
                ..Default::default()
            });
        }
        
        if start.elapsed() > timeout {
            let _ = child.kill();
            return Ok(MonitoredCommandResult {
                timed_out: true,
                ..Default::default()
            });
        }
        
        match child.try_wait()? {
            Some(status) => {
                return Ok(MonitoredCommandResult {
                    exit_code: status.code(),
                    ..Default::default()
                });
            }
            None => thread::sleep(Duration::from_millis(500)),
        }
    }
}
```

---

## 11. PROVIDER REGISTRY

**Location:** `crates/lyra-core/src/providers.rs` (lines 862–950)

### 11.1 Default Capabilities

```rust
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
            provider_key: "slskd",
            display_name: "Slskd (Soulseek)",
            capabilities: vec!["p2p-search", "p2p-download"],
        },
        ProviderCapabilitySeed {
            provider_key: "spotdl",
            display_name: "SpotDL",
            capabilities: vec!["fallback-acquire"],
        },
        // ... more providers
    ]
}
```

### 11.2 Environment Variable Mappings

```rust
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
            "slskd",
            vec![
                "LYRA_PROTOCOL_NODE_USER",
                "LYRA_PROTOCOL_NODE_PASS",
                "SLSKD_URL",
                "SLSKD_API_KEY",
            ],
        ),
        ("spotdl", vec!["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]),
        // ... more
    ])
}
```

This mapping is used to:
1. Auto-scan `.env` files for known provider keys
2. Validate config completeness
3. Document which env vars map to which provider

---

## 12. PATH RESOLUTION

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 112–144)

### 12.1 Environment Variable Precedence

```rust
fn acquisition_staging_dir(paths: &AppPaths) -> PathBuf {
    std::env::var("STAGING_FOLDER")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| acquisition_data_root(paths).join("staging"))
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
```

**Precedence:**
```
STAGING_FOLDER (env)
  ↓ (empty or unset)
{LYRA_DATA_ROOT}/staging (env)
  ↓ (empty or unset)
{LOCALAPPDATA}/Lyra/dev/staging (Windows standard)
  ↓ (not accessible)
{workspace_root}/.lyra-data/staging (fallback)
```

### 12.2 File Organization

```rust
fn organize_download(
    conn: &Connection,
    source_path: &Path,
    target_root: Option<&Path>,
    artist: &str,
    title: &str,
    album: Option<&str>,
) -> LyraResult<PathBuf> {
    let root = target_root.ok_or(...)?;
    let artist_dir = sanitize_segment(artist, "Unknown Artist");
    let album_dir = sanitize_segment(album.unwrap_or("Singles"), "Singles");
    let ext = source_path.extension().and_then(OsStr::to_str).map(|v| format!(".{v}")).unwrap_or_default();
    let file_name = format!("{} - {}{}", artist_dir, sanitize_segment(title, "Unknown Track"), ext);
    
    let target_dir = root.join(artist_dir).join(album_dir);
    fs::create_dir_all(&target_dir)?;
    // Move source_path → target_dir/file_name
}

fn sanitize_segment(value: &str, fallback: &str) -> String {
    // Replace <>":/\|?* with _
    // Trim dots and whitespace
    // Return fallback if empty
}
```

---

## 13. INTEGRATION POINTS

### 13.1 Tauri Invocations (Desktop App)

Likely called from `desktop/renderer-app/src-tauri/`:
```rust
// Hypothetical Tauri command
#[tauri::command]
pub fn start_acquisition_worker(app_handle: AppHandle) {
    let core = app_handle.state::<Arc<LyraCore>>();
    acquisition_worker::start_worker_with_callback(core.paths.clone(), move |queue_id| {
        app_handle.emit_all("acquisition-update", QueueUpdatePayload { id: queue_id }).ok();
    });
}
```

### 13.2 LyraCore Public API

**Location:** `crates/lyra-core/src/lib.rs`

```rust
impl LyraCore {
    pub fn get_acquisition_queue(&self, ...) -> LyraResult<Vec<AcquisitionQueueItem>> { ... }
    pub fn queue_track_for_acquisition(&self, ...) -> LyraResult<AcquisitionQueueItem> { ... }
    pub fn process_acquisition_queue_with_callback<F>(&self, notify: F) -> LyraResult<bool> { ... }
    pub fn update_provider_config(&self, provider_key: &str, ...) -> LyraResult<Vec<ProviderConfigRecord>> { ... }
    pub fn list_provider_configs(&self) -> LyraResult<Vec<ProviderConfigRecord>> { ... }
    pub fn acquisition_preflight(&self) -> LyraResult<AcquisitionPreflight> { ... }
}
```

---

## 14. LEGACY PYTHON BRIDGE (DEPRECATED)

**Location:** `crates/lyra-core/src/acquisition_dispatcher.rs` (lines 1214–1270)

**Status:** Optional, disabled by default.

**Activation:**
```rust
fn legacy_python_bridge_enabled() -> bool {
    std::env::var("LYRA_ENABLE_LEGACY_ACQUISITION_BRIDGE")
        .ok()
        .map(|v| v.trim().to_ascii_lowercase() == "1" || v == "true" || v == "yes")
        .unwrap_or(false)
}
```

**Fallback:** If native tiers all fail and bridge is enabled:
```rust
let python_exe = workspace_root.join(".venv").join("Scripts").join("python.exe");
let waterfall_script = workspace_root.join("oracle").join("acquirers").join("waterfall.py");

if python_exe.exists() && waterfall_script.exists() {
    // Spawn python acquisition bridge
    let mut cmd = Command::new(&python_exe);
    cmd.arg("-m").arg("oracle.acquirers.waterfall")
       .arg("acquire")
       .arg(artist)
       .arg(title)
       .arg("--album").arg(album);
    // ... run and parse output
}
```

**Reference:** See `archive/legacy-runtime/oracle/acquirers/waterfall.py` for legacy implementation.

---

## 15. SUMMARY TABLE: Credential Storage by Provider

| Provider | Storage | Scope | Polling | Details |
|----------|---------|-------|---------|---------|
| **Qobuz** | Local service bridge | Bridge manages | N/A | Lyra sends HTTP POST, bridge handles OAuth |
| **Streamrip** | Streamrip's ~/.streamrip/ | Subprocess | Lyra only passes source + search terms | Lyra does not access credentials |
| **Slskd** | `provider_configs` (JSON) | DB | Basic or API key auth | Credentials included in HTTP headers/session |
| **SpotDL** | SpotDL's own config + env | Subprocess | Subprocess inherits environment | Lyra does not access credentials |
| **yt-dlp** | yt-dlp's own config | Subprocess | No active auth | YouTube direct scraping |
| **Spotify OAuth** | Keyring (tokens) + DB (session) | OS Keyring | `providers::spotify_access_token()` auto-refresh | Refresh token stored in Credential Manager |
| **LLM (Groq/OpenAI/etc.)** | `provider_configs` (JSON) + Keyring (optional) | DB | At runtime when composing | Priority: DB → legacy env vars |

---

## 16. QUICK REFERENCE: Adding a New Tier

To add a new acquisition tier (e.g., Deezer):

1. **Register Provider** → `crates/lyra-core/src/providers.rs`:
   ```rust
   ProviderCapabilitySeed {
       provider_key: "deezer",
       display_name: "Deezer",
       capabilities: vec!["acquire"],
   },
   ```

2. **Add Env Mappings** → `provider_env_mappings()`:
   ```rust
   ("deezer", vec!["DEEZER_EMAIL", "DEEZER_PASSWORD", ...]),
   ```

3. **Implement Tier** → `crates/lyra-core/src/acquisition_dispatcher.rs`:
   ```rust
   fn try_native_deezer(...) -> LyraResult<AcquireTrackResult> {
       let config = load_provider_config(conn, "deezer");
       // Load config, validate, execute, return result
   }
   ```

4. **Add to Waterfall** → `try_native_acquire_track()`:
   ```rust
   let deezer = try_native_deezer(paths, artist, title, queue_id, conn, notify)?;
   if deezer.cancelled || deezer.path.is_some() {
       return Ok(deezer);
   }
   ```

5. **Configure via UI** or directly in SQLite:
   ```sql
   INSERT INTO provider_configs (provider_key, display_name, enabled, config_json)
   VALUES ('deezer', 'Deezer', 1, '{"deezer_email":"...","deezer_password":"..."}');
   ```

---

## References

- **Canonical Runtime:** `crates/lyra-core/src/`
- **Desktop App:** `desktop/renderer-app/`
- **Legacy Reference (do not reuse):** `archive/legacy-runtime/oracle/acquirers/`
- **Database Schema:** `crates/lyra-core/src/db.rs`
- **CLI Tools:** `crates/lyra-core/src/bin/`


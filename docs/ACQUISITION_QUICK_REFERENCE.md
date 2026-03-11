# Lyra Acquisition Pipeline — Technical Quick Reference

## At a Glance

| Aspect | Location | Status |
|--------|----------|--------|
| **Waterfall Chain** | `crates/lyra-core/src/acquisition_dispatcher.rs:1091–1140` | ✅ Fully implemented in Rust |
| **Credential Store** | SQLite `provider_configs` table + OS Keyring | ✅ Production ready |
| **Qobuz Integration** | `acquisition_dispatcher.rs:449–557` | ✅ HTTP bridge to local service |
| **Soulseek/Slskd** | `acquisition_dispatcher.rs:567–920` | ✅ REST API with dual auth |
| **Streamrip** | `acquisition_dispatcher.rs:326–443` | ✅ Subprocess with config passthrough |
| **SpotDL** | `acquisition_dispatcher.rs:921–975` | ✅ Subprocess binary |
| **yt-dlp** | `acquisition_dispatcher.rs:1026–1049` + `waterfall.rs` | ✅ Trait-based tier system |
| **Background Worker** | `crates/lyra-core/src/acquisition_worker.rs` | ✅ Thread with 5–30s poll intervals |
| **CLI Runner** | `crates/lyra-core/src/bin/acquisition_runner.rs` | ✅ Standalone processor |
| **Queue State** | SQLite `acquisition_queue` table | ✅ Full lifecycle tracking |
| **Python Bridge** | `acquisition_dispatcher.rs:1214–1270` | ⚠️ Optional fallback (disabled by default) |

---

## Waterfall Execution Order

```
try_native_acquire_track()
  ├─ T1: try_native_qobuz_service()         [lossless] → HTTP POST to bridge
  ├─ T2: try_native_streamrip()             [lossless] → Subprocess binary
  ├─ T3: try_native_slskd()                 [lossy OK] → REST API to daemon
  ├─ T5: try_native_spotdl()                [lossy]    → Subprocess binary
  └─ T4: try_native_ytdlp()                 [fallback] → Trait impl, subprocess
  
Each tier: success or cancelled → return result
           else → continue to next tier
```

---

## Credential Loading Patterns

### Pattern 1: Database JSON Config
```rust
let config = load_provider_config(conn, "provider_key");
// Queries: SELECT config_json FROM provider_configs WHERE provider_key=?
// Returns: Option<serde_json::Value>
// Empty if provider disabled or missing

let url = config
    .and_then(|c| c.get("field_name"))
    .or_else(|| c.get("FIELD_NAME"))  // Uppercase fallback
    .and_then(Value::as_str)
    .unwrap_or("default");
```

### Pattern 2: OS Keyring (Windows Credential Manager)
```rust
providers::keyring_save("provider_key", "login_token", secret_value)?;
// Stores in: Credential Manager
//   Service:  "lyra-media-player"
//   Account:  "provider_key:login_token"

let token = providers::keyring_load("provider_key", "login_token")?;
// Returns: Option<String>
```

### Pattern 3: Environment Variables
```
.env file parsing via dotenvy → credential indicators (KEY|SECRET|TOKEN|PASSWORD)
↓
backup_env_to_keychain() → stores in OS keyring
↓
load_env_credential(KEY_NAME) → retrieves from keyring as "env:{KEY_NAME}"
```

---

## Key Configuration Files

### `provider_configs` Table Entries

**Qobuz:**
```json
{
  "qobuz_service_url": "http://localhost:7700",
  "qobuz_app_id": "...",
  "QOBUZ_QUALITY": "flac"
}
```

**Slskd:**
```json
{
  "slskd_url": "http://localhost:5030",
  "slskd_api_key": "optional-key",
  "LYRA_PROTOCOL_NODE_USER": "username",
  "LYRA_PROTOCOL_NODE_PASS": "password"
}
```

**Streamrip:**
```json
{
  "lyra_streamrip_binary": "/path/to/streamrip",
  "lyra_streamrip_source": "qobuz"
}
```

**Spotify:**
```json
{
  "spotify_client_id": "...",
  "spotify_client_secret": "..."
}
```

---

## Environment Variables (Preferred Fallback)

### Staging & Downloads
```
LYRA_DATA_ROOT            → {data_root}
LOCALAPPDATA              → C:\Users\{user}\AppData\Local (Windows)
STAGING_FOLDER            → {staging_root}/staging
DOWNLOADS_FOLDER          → {downloads_root}
```

### Provider-Specific
```
QOBUZ_SERVICE_URL         → Qobuz bridge endpoint
QOBUZ_EMAIL, PASSWORD, etc.

LYRA_STREAMRIP_BINARY     → path to streamrip
LYRA_STREAMRIP_SOURCE     → qobuz|tidal|etc.
LYRA_STREAMRIP_CMD_TEMPLATE → custom command

LYRA_PROTOCOL_NODE_URL    → Slskd base URL
LYRA_PROTOCOL_NODE_KEY    → Slskd API key
LYRA_PROTOCOL_NODE_USER   → Slskd username
LYRA_PROTOCOL_NODE_PASS   → Slskd password

LYRA_LLM_BASE_URL         → LLM provider base URL
LYRA_LLM_API_KEY          → LLM API key
LYRA_LLM_MODEL            → Model name
LYRA_LLM_PROVIDER         → ollama|openai|groq|openrouter

LYRA_ENABLE_LEGACY_ACQUISITION_BRIDGE → "1"|"true"|"yes" (default: disabled)
```

---

## Queue Item Lifecycle

```
Status Transitions:
  queued
    ↓
  validating (0.05) → preflight checks
    ↓
  acquiring (0.1)   → tier attempts
    ↓
  staging (0.72)    → waiting for file materialization
    ↓
  scanning (0.85)   → audio metadata extraction
    ↓
  organizing (0.9)  → file movement into library
    ↓
  indexing (0.95)   → database catalog update
    ↓
  completed (1.0)

OR at any stage:
  → failed := (retryable | terminal)
  → cancelled
  → skipped := (duplicate detected)
```

**Progress Reporting:**
- Each tier calls `acquisition::update_lifecycle(conn, queue_id, status, progress, ...)`
- Callback invoked: `notify(queue_id)` → typically Tauri IPC to UI

---

## Credential Plumbing Summary

### Where Credentials Are NOT Passed
- ❌ Not on command-line arguments (prevents process listing exposure)
- ❌ Not logged or printed
- ❌ Not stored in acquisition_queue table (only provider name + tier)

### Where Credentials ARE Handled
- ✅ `provider_configs` JSON (config values like URLs, API keys)
- ✅ OS Keyring (sensitive tokens: OAuth, passwords)
- ✅ Environment variables (legacy, masked in subprocess)
- ✅ Subprocess inherits parent environment (external tools read own config)

### Per-Provider Credential Strategy

| Provider | Method | Storage | Lyra Visibility |
|----------|--------|---------|-----------------|
| **Qobuz** | Bridge endpoint configured | DB (service_url only) | ✅ None (bridge manages auth) |
| **Streamrip** | Binary subprocess | ~/.streamrip/ (external) | ✅ None (subprocess reads own config) |
| **Slskd** | REST API (username/password or API key) | DB (JSON config) | ✅ Full (in config_json) |
| **SpotDL** | subprocess inherits env | Binary's own config + env | ✅ None (subprocess handles) |
| **yt-dlp** | Direct subprocess | Binary's own config | ✅ None (no auth needed) |
| **Spotify OAuth** | Token refresh cycle | Keyring (tokens) + DB (session meta) | ✅ Partial (tokens hidden, session meta visible) |

---

## Quick Debugger Checklist

### "Acquisition is failing at Qobuz stage"
1. Check `provider_configs` table: `SELECT * FROM provider_configs WHERE provider_key='qobuz';`
2. Verify Qobuz service is running: `curl http://localhost:7700/acquire` (should error gracefully)
3. Check network connectivity: `curl -v http://localhost:7700/`

### "Slskd is not finding files"
1. Test slskd endpoint: `curl -H "X-API-Key: {key}" http://localhost:5030/api/v0/searches`
2. Verify auth: Check if using API key vs. username/password flow
3. Check `DOWNLOADS_FOLDER` permissions

### "Streamrip tier is skipped"
1. Verify binary location: `which streamrip` or `Get-Command streamrip` (PowerShell)
2. Check `lyra_streamrip_binary` in provider_configs
3. Test manually: `streamrip download "artist - title" --source qobuz`

### "Worker thread not processing items"
1. Check if worker started: `acquisition_worker::is_running()`
2. Check queue status: `SELECT COUNT(*) FROM acquisition_queue WHERE status='queued';`
3. Check preflight: `core.acquisition_preflight()?`
4. Look for errors in logs: `~{app_data_dir}/logs/`

### "Duplicate detection preventing acquisition"
1. Query: `SELECT id, path FROM tracks WHERE artist LIKE ? AND title LIKE ?`
2. Check `completion_rate > 0.5` in playback_history to determine if tracked as "owned"

---

## File Organization on Disk

After acquisition:
```
{library_root}/
  {Sanitized Artist}/
    {Sanitized Album}/
      {Sanitized Artist} - {Sanitized Title}.{ext}
```

Sanitization rules:
- Strip: `< > : " / \ | ? *`
- Trim dots and whitespace
- Fallback: "Unknown Artist" or "Unknown Track"

---

## Integration Example: Tauri Command

```rust
// In src-tauri/src/main.rs or commands.rs
#[tauri::command]
async fn process_next_acquisition(app_handle: AppHandle) -> Result<bool, String> {
    let core = app_handle.state::<Arc<LyraCore>>();
    
    match core.process_acquisition_queue_with_callback(|queue_id| {
        let _ = app_handle.emit_all(
            "acquisition-update",
            json!({ "queue_id": queue_id })
        );
    }) {
        Ok(processed) => Ok(processed),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
async fn start_background_worker(app_handle: AppHandle) -> Result<(), String> {
    let paths = /* load from config */;
    acquisition_worker::start_worker_with_callback(paths, move |queue_id| {
        let _ = app_handle.emit_all(
            "acquisition-progress",
            json!({ "queue_id": queue_id })
        );
    });
    Ok(())
}
```

---

## References

- **Full Architecture:** `docs/ACQUISITION_PIPELINE_ARCHITECTURE.md`
- **Core Implementation:** `crates/lyra-core/src/acquisition*.rs`
- **Providers Module:** `crates/lyra-core/src/providers.rs`
- **Database Schema:** `crates/lyra-core/src/db.rs`
- **CLI Tools:** `crates/lyra-core/src/bin/`
- **Legacy Reference:** `archive/legacy-runtime/oracle/acquirers/waterfall.py` (Python version, for reference only)


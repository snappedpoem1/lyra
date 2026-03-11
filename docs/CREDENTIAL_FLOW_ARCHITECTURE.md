# Lyra Acquisition Pipeline — Credential Flow Architecture

## Credential Storage Tiers

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CREDENTIAL STORAGE ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────────────────┘

                        ┌──────────────────────┐
                        │  .env File (plain)   │
                        │  (on disk, not used  │
                        │   in production)     │
                        └──────────┬───────────┘
                                   │
                                   │ backup_env_to_keychain()
                                   ↓
                        ┌──────────────────────────────────────┐
                        │   OS Keyring / Credential Manager    │
                        │   (Windows, macOS, Linux)            │
                        │   Service: "lyra-media-player"       │
                        │   Account: "{provider}:{key_name}"   │
                        │                                      │
                        │   - Spotify OAuth tokens             │
                        │   - Sensitive passwords              │
                        │   - Session credentials              │
                        └──────────┬───────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ↓                             ↓
    ┌──────────────────────────┐    ┌──────────────────────────┐
    │  SQLite Database         │    │  Subprocess Environment  │
    │  `provider_configs`      │    │  (for external tools)    │
    │  (config_json field)     │    │                          │
    │                          │    │  - STREAMRIP_*           │
    │  Config URLs, keys       │    │  - SPOTIFY_*             │
    │  - qobuz_service_url     │    │  - GENIUS_*              │
    │  - slskd_url             │    │  - etc.                  │
    │  - spotdl_binary         │    │                          │
    │  - etc.                  │    │  Passthrough from:       │
    └──────────┬───────────────┘    │  - DB config             │
               │                     │  - Environment variables │
               │                     │  - Legacy .env (not rec) │
               │                     └──────────┬───────────────┘
               │                                │
               └────────────┬───────────────────┘
                            │
                            ↓
                    ┌──────────────────┐
                    │  Subprocess Exec │
                    │  (streamrip,     │
                    │   spotdl,        │
                    │   yt-dlp)        │
                    │                  │
                    │  (tools read     │
                    │   their own      │
                    │   configs)       │
                    └──────────────────┘
```

---

## Per-Provider Credential Flows

### Flow 1: Qobuz (Local Bridge)

```
┌─────────────────────────────────────────────────────────────┐
│ QOBUZ TIER (T1)                                              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  [Lyra Rust Code]                                            │
│    load_provider_config(conn, "qobuz")                       │
│      ↓                                                        │
│    SELECT config_json FROM provider_configs WHERE ...        │
│      ↓                                                        │
│    Extract "qobuz_service_url" (or use default)              │
│      ↓                                                        │
│    HTTP POST http://localhost:7700/acquire                   │
│      ├─ Request: { "artist": "...", "title": "..." }         │
│      │                                                        │
│      ├─→ [Local Qobuz Service Bridge]                        │
│      │   ├─ Handles Qobuz OAuth internally                   │
│      │   ├─ Manages credentials (NOT passed by Lyra)         │
│      │   └─ Returns audio file path or error                 │
│      │                                                        │
│      └─ Response: { "success": true, "path": "..." }         │
│                                                               │
│  Lyra stores result in acquisition_queue:                    │
│    - selected_provider = "qobuz"                             │
│    - selected_tier = "T1"                                    │
│    - output_path = "..."                                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘

KEY POINT:
  ❌ Lyra NEVER sees raw Qobuz credentials
  ❌ Qobuz username/password NOT stored in provider_configs
  ✅ Service bridge URL only (localhost:7700)
```

---

### Flow 2: Slskd/Soulseek (REST API)

```
┌──────────────────────────────────────────────────────────────┐
│ SLSKD TIER (T3)                                               │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  [Lyra Rust Code]                                             │
│    slskd_node_config(conn):                                   │
│      ├─ load_provider_config(conn, "slskd")                   │
│      ├─ Extract: slskd_url, api_key, username, password       │
│      └─ Return tuple: (url, api_base, api_key, user, pass)    │
│                                                                │
│    slskd_headers(conn):                                       │
│      ├─ If api_key exists:                                    │
│      │   └─ Header: "X-API-Key: {key}"                        │
│      │                                                        │
│      └─ Else:                                                 │
│          ├─ POST /session { "username": "...", "password": "..." }
│          ├─→ [Slskd Daemon]                                   │
│          └─ Extract token from response                       │
│              └─ Header: "Authorization: Bearer {token}"       │
│                                                                │
│  REST API Calls (with headers):                               │
│    1. POST /searches { "searchText": "artist title" }         │
│       ↓ get search_id                                         │
│    2. GET /searches/{id}?includeResponses=true                │
│       ↓ poll until candidates appear (6 attempts)             │
│    3. SELECT best candidate (FLAC > MP3 320k > MP3 192k)      │
│       ↓                                                        │
│    4. POST /transfers/downloads/{username}                    │
│       { "filename": "..." }                                   │
│       ↓ Slskd enqueues download                               │
│    5. Wait for file in DOWNLOADS_FOLDER (60 attempts, 3s)     │
│                                                                │
│  Storage:                                                      │
│    provider_configs.config_json (Slskd):                      │
│    {                                                           │
│      "slskd_url": "http://localhost:5030",                    │
│      "slskd_api_key": "optional",                             │
│      "LYRA_PROTOCOL_NODE_USER": "slskd",                      │
│      "LYRA_PROTOCOL_NODE_PASS": "slskd"                       │
│    }                                                           │
│                                                                │
└──────────────────────────────────────────────────────────────┘

KEY POINTS:
  ✅ Credentials stored in SQLite config_json (not sensitive)
  ✅ Sent in HTTP headers (standard REST auth)
  ⚠️  Username/password visible in DB (consider API key instead)
  ✅ No subprocess involved (pure HTTP)
```

---

### Flow 3: Streamrip (Binary Subprocess)

```
┌──────────────────────────────────────────────────────────────┐
│ STREAMRIP TIER (T2)                                            │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  [Lyra Rust Code]                                             │
│    load_provider_config(conn, "streamrip")                    │
│      ├─ Extract: lyra_streamrip_binary, lyra_streamrip_source │
│      └─ (These are PATH and SOURCE PREFERENCE only)           │
│                                                                │
│    find_command(binary_path, &["streamrip"])                  │
│      └─ Search in PATH, resolve to executable                 │
│                                                                │
│    Command construction:                                      │
│      streamrip download "artist - title" --source qobuz ...   │
│                                                                │
│    Subprocess spawn:                                          │
│      let mut cmd = Command::new(binary);                      │
│      cmd.arg("download")                                      │
│         .arg(query)                                           │
│         .arg("--output").arg(staging_dir)                     │
│         // ... other args                                      │
│                                                                │
│    Environment passthrough:                                   │
│      ├─ Subprocess INHERITS parent environment                │
│      ├─ (Any STREAMRIP_* env vars passed automatically)       │
│      └─ Streamrip reads ~/.streamrip/config on its own        │
│                                                                │
│  Storage:                                                      │
│    provider_configs.config_json (Streamrip):                  │
│    {                                                           │
│      "lyra_streamrip_binary": "/usr/bin/streamrip",           │
│      "lyra_streamrip_source": "qobuz"                         │
│    }                                                           │
│                                                                │
│  Streamrip's own storage (NOT Lyra):                          │
│    ~/.streamrip/config (Linux)                                │
│    %APPDATA%\streamrip\config (Windows)                       │
│      ├─ Qobuz credentials                                     │
│      ├─ Tidal credentials                                     │
│      └─ Other source configs                                  │
│                                                                │
└──────────────────────────────────────────────────────────────┘

KEY POINTS:
  ❌ Lyra NEVER accesses Streamrip credentials
  ❌ Streamrip creds NOT in provider_configs
  ✅ Streamrip reads ~/.streamrip/ config directly
  ✅ Lyra only specifies SOURCE and OUTPUT_DIR
  ✅ Subprocess inherits environment (no explicit secrets passed)
```

---

### Flow 4: SpotDL (Binary Subprocess)

```
┌──────────────────────────────────────────────────────────────┐
│ SPOTDL TIER (T5)                                               │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  [Lyra Rust Code]                                             │
│    find_command(None, &["spotdl"])                            │
│      └─ Search in PATH                                        │
│                                                                │
│    Command construction:                                      │
│      spotdl download "artist - title"                         │
│        --output {staging_dir}                                 │
│        --format mp3                                           │
│        --bitrate 320k                                         │
│        --threads 1                                            │
│                                                                │
│    Subprocess span:                                           │
│      let mut cmd = Command::new(binary);                      │
│      cmd.arg("download")                                      │
│         .arg(query)                                           │
│         .arg("--output").arg(output_dir)                      │
│         // ... more args                                      │
│                                                                │
│  Spotify Integration (SpotDL → Spotify API):                  │
│    SpotDL internally:                                         │
│      ├─ Calls Spotify search API                              │
│      ├─ Calls Spotify Web Player (implicit)                   │
│      └─ SpotDL reads Spotify creds from:                      │
│         ├─ ~/.spotdl/config (local)                           │
│         ├─ Environment variables (SPOTIFY_CLIENT_ID, etc.)    │
│         └─ ~/.cache/spotdl/... (downloads)                    │
│                                                                │
│  Storage:                                                      │
│    provider_configs.config_json (SpotDL):                     │
│    {                                                           │
│      "spotdl_binary": "/usr/local/bin/spotdl"                 │
│    }                                                           │
│                                                                │
│    (Spotify credentials elsewhere, NOT passed by Lyra)        │
│                                                                │
└──────────────────────────────────────────────────────────────┘

KEY POINTS:
  ❌ Lyra does NOT manage Spotify credentials
  ✅ Spotify config managed by SpotDL or user
  ✅ Lyra only invokes SpotDL with search query
```

---

### Flow 5: yt-dlp (Binary Subprocess)

```
┌──────────────────────────────────────────────────────────────┐
│ YT-DLP TIER (T4) — FALLBACK                                    │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  [Lyra Rust Code] → waterfall.rs trait                        │
│    YtdlpTier::find_binary()                                   │
│      └─ Search PATH for "yt-dlp"                              │
│                                                                │
│    YtdlpTier::try_acquire(&item, staging_dir)                 │
│      ├─ Build search query from metadata                      │
│      ├─ Spawn:                                                │
│      │   yt-dlp "ytsearch1: artist - title"                   │
│      │    --extract-audio                                     │
│      │    --audio-format mp3                                  │
│      │    --audio-quality 128K                                │
│      │    --output {staging_dir}/%(title)s.%(ext)s            │
│      │                                                        │
│      └─ Monitor subprocess output                             │
│                                                                │
│  Storage:                                                      │
│    provider_configs: (none needed)                            │
│    yt-dlp: reads ~/.config/yt-dlp/ if present                 │
│                                                                │
│  Authentication:                                              │
│    ❌ None needed (YouTube scraping)                           │
│                                                                │
└──────────────────────────────────────────────────────────────┘

KEY POINTS:
  ✅ No credentials needed (YouTube direct scraping)
  ✅ Lowest quality tier (lossy fallback)
  ✅ Most reliable as final fallback
```

---

### Flow 6: Spotify OAuth Session

```
┌──────────────────────────────────────────────────────────────┐
│ SPOTIFY OAUTH (Special: used by composer, not acquisition)    │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  [Lyra Rust - providers.rs]                                   │
│                                                                │
│  Step 1: Bootstrap OAuth Flow                                 │
│    begin_spotify_oauth_flow(conn, redirect_uri)               │
│      ├─ load_provider_config(conn, "spotify")                 │
│      ├─ Extract: spotify_client_id, spotify_client_secret     │
│      ├─ Generate authorization URL with state                 │
│      └─ Store flow state in DB table:                         │
│         provider_auth_flows (state, redirect_uri, scope, ...)  │
│                                                                │
│  Step 2: User Completes OAuth (browser)                       │
│    User → Spotify login page → authorize Lyra                 │
│      ↓                                                         │
│    Browser → Lyra callback with code + state                  │
│                                                                │
│  Step 3: Exchange Authorization Code                          │
│    complete_spotify_oauth_flow(conn, code, state)             │
│      ├─ Verify state (CSRF protection)                        │
│      ├─ POST /token exchange code for tokens                  │
│      │   (using Basic Auth: client_id:client_secret)          │
│      ├─ Extract access_token, refresh_token                   │
│      │                                                        │
│      ├─ Save tokens:                                          │
│      │   keyring_save("spotify", "oauth_access_token", ...)   │
│      │   keyring_save("spotify", "oauth_refresh_token", ...)  │
│      │      ↓                                                  │
│      │   [OS Keyring / Credential Manager]                    │
│      │                                                        │
│      └─ Save session metadata in DB:                          │
│         provider_oauth_sessions (token_type, scope, expires, ...)
│                                                                │
│  Step 4: Subsequent API Calls                                 │
│    spotify_access_token(conn)                                 │
│      ├─ Check if cached token exists & not expired            │
│      ├─ If expired, refresh:                                  │
│      │   refresh_spotify_access_token(client_id, client_secret, refresh_token)
│      │     └─ POST /token with refresh_token                  │
│      │     └─ Get new access_token                            │
│      │     └─ Update keyring + DB                             │
│      │                                                        │
│      └─ Return access_token for API calls                     │
│                                                                │
│  Storage Summary:                                             │
│    ┌─────────────────────────────────────────────────────┐    │
│    │ DB: provider_configs                                │    │
│    │  ├─ spotify_client_id                               │    │
│    │  ├─ spotify_client_secret                           │    │
│    │  ├─ spotify_authorize_url                           │    │
│    │  ├─ spotify_token_url                               │    │
│    │  └─ ... (non-sensitive config)                      │    │
│    │                                                     │    │
│    │ DB: provider_oauth_sessions                         │    │
│    │  ├─ token_type (Bearer)                             │    │
│    │  ├─ scope                                           │    │
│    │  ├─ access_token_expires_at                         │    │
│    │  └─ refreshed_at                                    │    │
│    │                                                     │    │
│    │ Keyring: "lyra-media-player"                        │    │
│    │  ├─ Account: "spotify:oauth_access_token"           │    │
│    │  ├─ Account: "spotify:oauth_refresh_token"          │    │
│    │  └─ (tokens hidden from DB)                         │    │
│    └─────────────────────────────────────────────────────┘    │
│                                                                │
└──────────────────────────────────────────────────────────────┘

KEY POINTS:
  ✅ Client credentials in DB (public, regenerate if exposed)
  ✅ OAuth tokens in OS Keyring (sensitive)
  ✅ Session metadata in DB (non-sensitive)
  ✅ Auto-refresh token logic built in
  ✅ CSRF protection via state parameter
```

---

## Credential Visibility Matrix

| Component | Qobuz | Streamrip | Slskd | SpotDL | yt-dlp | Spotify OAuth |
|-----------|-------|-----------|-------|--------|--------|---------------|
| **DB `provider_configs`** | Service URL only | Binary path | ✅ All | Binary path | ❌ None | Client ID/Secret |
| **OS Keyring** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ Tokens |
| **Lyra Code** | ❌ Sees bridge response | ❌ Query only | ✅ REST calls | ❌ Query only | ❌ Query only | ✅ Token mgmt |
| **Subprocess** | N/A | ❌ (reads own config) | N/A | ❌ (reads own config) | N/A | N/A |
| **Env Vars** | URL override | Binary override | URL, user, pass fallback | Binary override | ❌ | Client ID/Secret |
| **Sensitive?** | No* | No* | Maybe (user/pass) | No* | No | Yes (tokens) |

*If credentials are in bridge/binary configs, those are managed externally.

---

## Subprocess Command-Line Argument Strategy

```
❌ NEVER pass secrets as command-line arguments:
   ❌ spotdl ... --spotify_password "xyz"
   ❌ streamrip acquire --qobuz_password "xyz"

✅ Instead, use environment inheritance:
   export SPOTIFY_CLIENT_SECRET="xyz"
   cmd.env("SPOTIFY_CLIENT_SECRET", secret);  // NOT cmd.arg(secret)

✅ Or use configuration files:
   ~/.spotdl/config
   ~/.streamrip/config
   (External tools read these directly)

✅ Or use HTTP headers (REST APIs):
   X-API-Key: {key}
   Authorization: Bearer {token}
```

Why?
- Process arguments visible in `ps` output
- Logs might capture arguments
- More discrete and secure

---

## Environment Variable Precedence for Config

```
For any config field (e.g., SLSKD_URL):

┌─────────────────────────────────────────────────────────────┐
│ 1. Check environment variable (SLSKD_URL)                   │
│      ↓ (if set and not empty)                               │
│    Use it                                                    │
│      ↓ (if not set or empty)                                │
│                                                              │
│ 2. Check provider_configs.config_json["slskd_url"]           │
│      ↓ (if set and not empty)                               │
│    Use it                                                    │
│      ↓ (if not set or empty)                                │
│                                                              │
│ 3. Use hardcoded default                                    │
│    (e.g., "http://localhost:5030")                          │
│      ↓                                                       │
│    Use it                                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘

This allows:
  - Production defaults in code
  - Per-machine overrides via .env or environment
  - Per-deployment tweaks via SQLite config_json
  - Runtime overrides via environment variables
```

---

## Secret Rotation & Backup Workflow

```
Initial Setup:
  1. User provides credentials via UI
  2. Lyra saves to provider_configs JSON
  3. Sensitive fields backed up to OS Keyring
  4. .env file deleted or archived (not used in production)

Periodic Rotation (Spotify tokens, etc.):
  1. Token expiration detected (check access_token_expires_at)
  2. Refresh token fetched from Keyring
  3. New token obtained from provider
  4. Updated token + new expiration stored
  5. Keyring updated, DB updated
  6. Loop continues transparently

Emergency Credential Reset:
  1. User re-authenticates (e.g., Spotify OAuth flow)
  2. New tokens generated
  3. Old tokens overwritten in Keyring + DB
  4. (No data loss; next refresh gets new token)
```

---

## Troubleshooting Credential Issues

### "Slskd auth failed"
```
1. Check DB: SELECT * FROM provider_configs WHERE provider_key='slskd';
2. Verify slskd runtime: nc -zv localhost 5030
3. Check if using API key or username/password:
   - If api_key set: curl -H "X-API-Key: {key}" http://localhost:5030/api/v0/...
   - If username/password: manually POST /session to test
4. Check for typos in LYRA_PROTOCOL_NODE_* env vars
```

### "Spotify OAuth token expired"
```
1. Check DB: SELECT * FROM provider_oauth_sessions WHERE provider_key='spotify';
2. Compare access_token_expires_at vs current time
3. If expired, next call to spotify_access_token() auto-refreshes
4. If refresh fails: re-run OAuth bootstrap flow
5. Check Keyring has both access_token AND refresh_token:
   Windows: Credential Manager → Lyra section
   macOS: Keychain → login → search "lyra-media-player"
   Linux: Secret Service / pass / kdeKwallet
```

### "Credentials not persisting after restart"
```
1. Verify provider_configs table persists:
   SELECT * FROM lyra.db;  (should be in app_data_dir/db/)
2. Verify Keyring service available:
   - Windows: Credential Manager accessible
   - macOS: Keychain accessible
   - Linux: Secret Service running (secretsd or kdeKwallet)
3. If using .env: was backup_env_to_keyring() called?
   Check that dotenvy parsed correctly.
4. Check enable flag:
   SELECT enabled FROM provider_configs WHERE provider_key='...';
   If 0, provider is disabled.
```

---

## References

- **Full Document:** `docs/ACQUISITION_PIPELINE_ARCHITECTURE.md`
- **Quick Ref:** `docs/ACQUISITION_QUICK_REFERENCE.md`
- **Implementation:** `crates/lyra-core/src/providers.rs` (credential logic)
- **Dispatcher:** `crates/lyra-core/src/acquisition_dispatcher.rs` (per-tier plumbing)
- **Schema:** `crates/lyra-core/src/db.rs` (provider_configs table)


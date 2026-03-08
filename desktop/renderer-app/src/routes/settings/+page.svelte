<script lang="ts">
  import { get } from "svelte/store";
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import { legacyImportReport, shell } from "$lib/stores/lyra";
  import { setWorkspacePage } from "$lib/stores/workspace";
  import type { AudioOutputDevice, DiagnosticsReport, ProviderHealth, ProviderValidationResult, SettingsPayload } from "$lib/types";

  let form: SettingsPayload = get(shell).settings;
  let providerJson: Record<string, string> = {};
  let healthMap: Record<string, ProviderHealth> = {};
  let healthLoaded = false;
  let audioDevices: AudioOutputDevice[] = [];
  let deviceLoadError = "";
  let validationResults: Record<string, ProviderValidationResult | "pending"> = {};
  let keyringStatus: Record<string, string> = {};
  let lastfmAuthForm = { apiKey: "", apiSecret: "", username: "", password: "" };
  let lastfmAuthStatus = "";
  let sleepMinutes = 30;
  let sleepStatus = "";
  let envBackupPath = "C:\\MusicOracle\\.env";
  let envBackupStatus = "";
  let diagnosticsReport: DiagnosticsReport | null = null;
  let workerRunning = false;

  onMount(async () => {
    setWorkspacePage(
      "Settings",
      "Runtime and provider controls",
      "Manage provider trust, diagnostics, acquisition worker behavior, and native playback settings inside the canonical shell.",
      "context"
    );
    try {
      audioDevices = await api.listAudioDevices();
    } catch (e) {
      deviceLoadError = String(e);
    }
  });

  async function selectDevice(deviceId: string) {
    const name = deviceId === "" ? null : deviceId;
    await api.setOutputDevice(name);
    form = { ...form, preferredOutputDevice: name };
    shell.update((state) => ({ ...state, settings: form }));
  }

  $: form = $shell.settings;
  $: for (const provider of $shell.providers) {
    providerJson[provider.providerKey] = JSON.stringify(provider.config, null, 2);
  }

  async function saveSettings() {
    const settings = await api.updateSettings(form);
    shell.update((state) => ({ ...state, settings }));
  }

  async function importLegacy() {
    legacyImportReport.set(await api.legacyImport());
    await shell.update((state) => state);
  }

  async function saveProvider(providerKey: string, enabled: boolean) {
    const providers = await api.updateProviderConfig(providerKey, enabled, JSON.parse(providerJson[providerKey] || "{}"));
    shell.update((state) => ({ ...state, providers }));
  }

  async function loadHealth() {
    const list = await api.listProviderHealth();
    healthMap = Object.fromEntries(list.map((h) => [h.providerKey, h]));
    healthLoaded = true;
  }

  async function resetHealth(providerKey: string) {
    await api.resetProviderHealth(providerKey);
    await loadHealth();
  }

  async function saveToKeychain(providerKey: string) {
    keyringStatus = { ...keyringStatus, [providerKey]: "saving" };
    try {
      const config = JSON.parse(providerJson[providerKey] || "{}");
      for (const [k, v] of Object.entries(config)) {
        if (typeof v === "string" && v.length > 0) {
          await api.keyringSave(providerKey, k, v);
        }
      }
      keyringStatus = { ...keyringStatus, [providerKey]: "saved" };
    } catch (e) {
      keyringStatus = { ...keyringStatus, [providerKey]: `error: ${String(e)}` };
    }
  }

  async function loadFromKeychain(providerKey: string) {
    keyringStatus = { ...keyringStatus, [providerKey]: "loading" };
    try {
      const config = JSON.parse(providerJson[providerKey] || "{}");
      let loaded = 0;
      for (const k of Object.keys(config)) {
        const val = await api.keyringLoad(providerKey, k);
        if (val !== null && val !== undefined) {
          config[k] = val;
          loaded++;
        }
      }
      providerJson = { ...providerJson, [providerKey]: JSON.stringify(config, null, 2) };
      keyringStatus = { ...keyringStatus, [providerKey]: loaded > 0 ? `loaded ${loaded} key(s)` : "nothing found" };
    } catch (e) {
      keyringStatus = { ...keyringStatus, [providerKey]: `error: ${String(e)}` };
    }
  }

  async function validateProvider(providerKey: string) {
    validationResults = { ...validationResults, [providerKey]: "pending" };
    try {
      const result = await api.validateProvider(providerKey);
      validationResults = { ...validationResults, [providerKey]: result };
      // Refresh health after validation
      if (healthLoaded) await loadHealth();
    } catch (e) {
      validationResults = { ...validationResults, [providerKey]: {
        providerKey,
        valid: false,
        latencyMs: 0,
        error: String(e),
        detail: null,
      }};
    }
  }

  async function lastfmAuthenticate() {
    lastfmAuthStatus = "Authenticating...";
    try {
      const sk = await api.lastfmGetSession(
        lastfmAuthForm.apiKey,
        lastfmAuthForm.apiSecret,
        lastfmAuthForm.username,
        lastfmAuthForm.password,
      );
      lastfmAuthStatus = `Session key obtained (${sk.slice(0, 8)}...) - saved to Last.fm config`;
      lastfmAuthForm.password = "";
    } catch (e) {
      lastfmAuthStatus = `Error: ${String(e)}`;
    }
  }

  async function backupEnvToKeychain() {
    envBackupStatus = "Scanning...";
    try {
      const result = await api.backupEnvToKeychain(envBackupPath);
      envBackupStatus = `Saved ${result.saved} credentials to OS keychain (${result.skipped} non-credential entries skipped)`;
    } catch (e) {
      envBackupStatus = `Error: ${String(e)}`;
    }
  }

  async function setSleepTimer() {
    await api.setSleepTimer(sleepMinutes);
    sleepStatus = sleepMinutes > 0 ? `Timer set: stops in ${sleepMinutes} min` : "Timer cancelled";
  }

  async function cancelSleepTimer() {
    await api.setSleepTimer(0);
    sleepStatus = "Timer cancelled";
  }

  async function runDiagnostics() {
    try {
      diagnosticsReport = await api.runDiagnostics();
      workerRunning = await api.acquisitionWorkerStatus();
    } catch (e) {
      console.error("Diagnostics failed:", e);
    }
  }

  async function startWorker() {
    try {
      await api.startAcquisitionWorker();
      workerRunning = true;
    } catch (e) {
      console.error("Failed to start worker:", e);
    }
  }

  async function stopWorker() {
    try {
      await api.stopAcquisitionWorker();
      workerRunning = false;
    } catch (e) {
      console.error("Failed to stop worker:", e);
    }
  }

  function statusColor(status: string): string {
    if (status === "healthy") return "#34cfab";
    if (status === "degraded") return "#f0b429";
    return "#e55";
  }
</script>

<section class="settings-grid">
  <article>
    <p class="eyebrow">App Settings</p>
    <label><input type="checkbox" bind:checked={form.startMinimized} /> Start minimized</label>
    <label><input type="checkbox" bind:checked={form.restoreSession} /> Restore session</label>
    <label><input type="checkbox" bind:checked={form.queuePanelOpen} /> Queue panel open by default</label>
    <label><input type="checkbox" bind:checked={form.libraryAutoScan} /> Auto scan on startup</label>
    <label>Volume step <input type="number" bind:value={form.playbackVolumeStep} min="1" max="20" /></label>
    <button on:click={saveSettings}>Save settings</button>
  </article>

  <article>
    <p class="eyebrow">Sleep Timer</p>
    <p class="settings-hint">Automatically stop playback after a set time.</p>
    <label>Minutes <input type="number" bind:value={sleepMinutes} min="1" max="180" /></label>
    <div style="display:flex;gap:8px;">
      <button on:click={setSleepTimer}>Set Timer</button>
      <button on:click={cancelSleepTimer}>Cancel</button>
    </div>
    {#if sleepStatus}<div class="auth-status">{sleepStatus}</div>{/if}
  </article>

  <article>
    <p class="eyebrow">Audio Output Device</p>
    {#if deviceLoadError}
      <p class="error">{deviceLoadError}</p>
    {:else}
      <select
        value={form.preferredOutputDevice ?? ""}
        on:change={(e) => selectDevice((e.currentTarget as HTMLSelectElement).value)}
      >
        <option value="">System default</option>
        {#each audioDevices as device}
          <option value={device.name}>{device.name}{device.isDefault ? " (default)" : ""}</option>
        {/each}
      </select>
    {/if}
  </article>

  <article>
    <p class="eyebrow">Last.fm Scrobbling</p>
    <p class="settings-hint">Enter your Last.fm credentials to obtain a session key. Scrobbling fires automatically on >=50% completion once the session key is saved in the Last.fm provider config.</p>
    <label>API Key <input type="text" bind:value={lastfmAuthForm.apiKey} placeholder="xxxxxxxxxxxxxxxx" /></label>
    <label>API Secret <input type="password" bind:value={lastfmAuthForm.apiSecret} placeholder="xxxxxxxxxxxxxxxx" /></label>
    <label>Username <input type="text" bind:value={lastfmAuthForm.username} placeholder="your-lastfm-username" /></label>
    <label>Password <input type="password" bind:value={lastfmAuthForm.password} placeholder="password" /></label>
    <button on:click={lastfmAuthenticate}>Authenticate</button>
    {#if lastfmAuthStatus}<div class="auth-status">{lastfmAuthStatus}</div>{/if}
  </article>

  <article>
    <p class="eyebrow">Keychain - .env Backup</p>
    <p class="settings-hint">Save all credential-like values from a .env file to the OS keychain (Windows Credential Manager). Keys containing API_KEY, SECRET, TOKEN, PASSWORD, EMAIL are saved.</p>
    <label>.env path <input type="text" bind:value={envBackupPath} /></label>
    <button on:click={backupEnvToKeychain}>Save credentials to keychain</button>
    {#if envBackupStatus}<div class="auth-status">{envBackupStatus}</div>{/if}
  </article>

  <article>
    <p class="eyebrow">Legacy Import</p>
    <button on:click={importLegacy}>Import .env and legacy DB</button>
    {#if $legacyImportReport}
      <p>Imported: {$legacyImportReport.imported.join(", ") || "none"}</p>
      <p>Unsupported keys: {$legacyImportReport.unsupported.join(", ") || "none"}</p>
      <p>Notes: {$legacyImportReport.notes.join(" | ")}</p>
    {/if}
  </article>

  <article class="providers">
    <p class="eyebrow">Provider Configs</p>
    {#each $shell.providers as provider}
      <div class="provider-card">
        <div>
          <strong>{provider.displayName}</strong>
          <small>{provider.capabilities.join(" | ")}</small>
          {#if healthLoaded && healthMap[provider.providerKey]}
            {@const h = healthMap[provider.providerKey]}
            <span class="health-badge" style="color:{statusColor(h.status)}">Status: {h.status}{h.circuitOpen ? " [tripped]" : ""}</span>
            {#if h.failureCount > 0}
              <span class="health-meta">failures: {h.failureCount}</span>
              <button class="reset-btn" on:click={() => resetHealth(provider.providerKey)}>Reset</button>
            {/if}
          {/if}
        </div>
        <label><input type="checkbox" checked={provider.enabled} on:change={(event) => saveProvider(provider.providerKey, (event.currentTarget as HTMLInputElement).checked)} /> Enabled</label>
        <textarea bind:value={providerJson[provider.providerKey]} rows="5"></textarea>
        <div class="provider-actions">
          <button on:click={() => saveProvider(provider.providerKey, provider.enabled)}>Save</button>
          <button class="validate-btn" on:click={() => validateProvider(provider.providerKey)}
            disabled={validationResults[provider.providerKey] === 'pending'}>
            {validationResults[provider.providerKey] === 'pending' ? 'Checking...' : 'Validate'}
          </button>
          <button class="keychain-btn" on:click={() => saveToKeychain(provider.providerKey)}
            title="Save credentials to OS keychain">Keychain</button>
          <button class="keychain-btn" on:click={() => loadFromKeychain(provider.providerKey)}
            title="Load credentials from OS keychain">Load</button>
        </div>
        {#if keyringStatus[provider.providerKey]}
          <div class="keyring-status">{keyringStatus[provider.providerKey]}</div>
        {/if}
        {#if validationResults[provider.providerKey] && validationResults[provider.providerKey] !== 'pending'}
          {@const vr = validationResults[provider.providerKey] as import('$lib/types').ProviderValidationResult}
          <div class="validation-result" style="color:{vr.valid ? '#34cfab' : '#e55'}">
            {vr.valid ? 'Valid' : 'Invalid'}
            {vr.latencyMs ? ` - ${vr.latencyMs}ms` : ''}
            {vr.detail ? ` - ${vr.detail}` : ''}
            {vr.error ? ` - ${vr.error}` : ''}
          </div>
        {/if}
      </div>
    {/each}
    {#if !healthLoaded}
      <button on:click={loadHealth}>Show provider health</button>
    {/if}
  </article>

  <article>
    <p class="eyebrow">System Diagnostics</p>
    <button on:click={runDiagnostics}>Run Diagnostics</button>
    
    {#if diagnosticsReport}
      <div class="diagnostics-summary">
        <div class="status-badge" style="background-color:{statusColor(diagnosticsReport.status)}15;color:{statusColor(diagnosticsReport.status)}">
          {diagnosticsReport.status.toUpperCase()}
        </div>
        
        <div class="stats-grid">
          <div class="stat">
            <span class="stat-value">{diagnosticsReport.stats.totalTracks}</span>
            <span class="stat-label">Tracks</span>
          </div>
          <div class="stat">
            <span class="stat-value">{diagnosticsReport.stats.totalPlaylists}</span>
            <span class="stat-label">Playlists</span>
          </div>
          <div class="stat">
            <span class="stat-value">{diagnosticsReport.stats.libraryRoots}</span>
            <span class="stat-label">Roots</span>
          </div>
          <div class="stat">
            <span class="stat-value">{diagnosticsReport.stats.pendingAcquisitions}</span>
            <span class="stat-label">Pending</span>
          </div>
          <div class="stat">
            <span class="stat-value">{diagnosticsReport.stats.enrichedTracks}</span>
            <span class="stat-label">Enriched</span>
          </div>
          <div class="stat">
            <span class="stat-value">{diagnosticsReport.stats.likedTracks}</span>
            <span class="stat-label">Liked</span>
          </div>
        </div>

        <div class="checks-grid">
          {#each Object.entries(diagnosticsReport.checks) as [key, check]}
            <div class="check-item">
              <div class="check-header">
                <span class="check-icon" style="color:{check.status === 'ok' ? '#34cfab' : check.status === 'warning' ? '#f0b429' : check.status === 'error' ? '#e55' : '#888'}">
                  {check.status === 'ok' ? 'OK' : check.status === 'warning' ? 'WARN' : check.status === 'error' ? 'ERR' : 'N/A'}
                </span>
                <strong>{key}</strong>
              </div>
              <p class="check-message">{check.message}</p>
              {#if check.error}
                <p class="check-error">{check.error}</p>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </article>

  <article>
    <p class="eyebrow">Acquisition Worker</p>
    <div class="worker-controls">
      <div class="worker-status">
        <span class="status-dot" style="background-color:{workerRunning ? '#34cfab' : '#888'}"></span>
        <span>{workerRunning ? "Running" : "Stopped"}</span>
      </div>
      {#if workerRunning}
        <button on:click={stopWorker}>Stop Worker</button>
      {:else}
        <button on:click={startWorker}>Start Worker</button>
      {/if}
    </div>
    <p class="settings-hint">Background worker automatically processes the acquisition queue every 30 seconds.</p>
  </article>
</section>

<style>
  .eyebrow, small { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .settings-grid { display: grid; gap: 18px; }
  article, .provider-card {
    padding: 18px;
    border-radius: 18px;
    background: rgba(255,255,255,0.05);
    display: grid;
    gap: 12px;
  }
  input, button, textarea {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
  }
  textarea { width: 100%; box-sizing: border-box; }
  .health-badge { font-size: 0.78rem; margin-left: 8px; }
  .health-meta { font-size: 0.72rem; color: #9cb2c7; margin-left: 6px; }
  .reset-btn { padding: 3px 8px; font-size: 0.72rem; }
  .error { color: #e55; font-size: 0.85rem; }
  select { width: 100%; }
  .provider-actions { display: flex; gap: 8px; }
  .validate-btn { color: #a8c4e0; }
  .keychain-btn { color: #b8d4a0; font-size: 0.82rem; }
  .validation-result { font-size: 0.78rem; padding: 4px 0; }
  .keyring-status { font-size: 0.75rem; color: #9cb2c7; padding: 2px 0; }
  .auth-status { font-size: 0.78rem; padding: 4px 0; color: #9cb2c7; }
  .settings-hint { font-size: 0.75rem; color: #9cb2c7; }
  label { display: grid; gap: 4px; font-size: 0.82rem; }
  
  .diagnostics-summary { display: grid; gap: 16px; }
  .status-badge {
    padding: 8px 16px;
    border-radius: 12px;
    font-weight: 600;
    text-align: center;
    font-size: 0.85rem;
    letter-spacing: 0.1em;
  }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
    gap: 12px;
  }
  .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .stat-value {
    font-size: 1.5rem;
    font-weight: 600;
    color: #34cfab;
  }
  .stat-label {
    font-size: 0.7rem;
    color: #9cb2c7;
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }
  .checks-grid {
    display: grid;
    gap: 12px;
  }
  .check-item {
    padding: 12px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 8px;
  }
  .check-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }
  .check-icon {
    font-size: 1.2rem;
    font-weight: 600;
  }
  .check-message {
    font-size: 0.85rem;
    color: #d0e0f0;
    margin: 0;
  }
  .check-error {
    font-size: 0.75rem;
    color: #e55;
    margin: 6px 0 0 0;
    font-family: monospace;
  }
  .worker-controls {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .worker-status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.9rem;
  }
  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
</style>

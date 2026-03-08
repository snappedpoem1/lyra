<script lang="ts">
  import { get } from "svelte/store";
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import { legacyImportReport, shell } from "$lib/stores/lyra";
  import type { AudioOutputDevice, ProviderHealth, SettingsPayload } from "$lib/types";

  let form: SettingsPayload = get(shell).settings;
  let providerJson: Record<string, string> = {};
  let healthMap: Record<string, ProviderHealth> = {};
  let healthLoaded = false;
  let audioDevices: AudioOutputDevice[] = [];
  let deviceLoadError = "";

  onMount(async () => {
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
          <small>{provider.capabilities.join(" • ")}</small>
          {#if healthLoaded && healthMap[provider.providerKey]}
            {@const h = healthMap[provider.providerKey]}
            <span class="health-badge" style="color:{statusColor(h.status)}">● {h.status}{h.circuitOpen ? " [tripped]" : ""}</span>
            {#if h.failureCount > 0}
              <span class="health-meta">failures: {h.failureCount}</span>
              <button class="reset-btn" on:click={() => resetHealth(provider.providerKey)}>Reset</button>
            {/if}
          {/if}
        </div>
        <label><input type="checkbox" checked={provider.enabled} on:change={(event) => saveProvider(provider.providerKey, (event.currentTarget as HTMLInputElement).checked)} /> Enabled</label>
        <textarea bind:value={providerJson[provider.providerKey]} rows="5"></textarea>
        <button on:click={() => saveProvider(provider.providerKey, provider.enabled)}>Save provider</button>
      </div>
    {/each}
    {#if !healthLoaded}
      <button on:click={loadHealth}>Show provider health</button>
    {/if}
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
</style>

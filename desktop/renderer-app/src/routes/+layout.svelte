<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { api } from "$lib/tauri";
  import { errorMessage, legacyImportReport, loadShell, registerLyraEvents, shell } from "$lib/stores/lyra";

  const nav = [
    { href: "/", label: "Home" },
    { href: "/library", label: "Library" },
    { href: "/playlists", label: "Playlists" },
    { href: "/discover", label: "Discover" },
    { href: "/queue", label: "Queue / Now Playing" },
    { href: "/acquisition", label: "Acquisition" },
    { href: "/settings", label: "Settings" }
  ];

  let newPlaylistName = "";
  let rootPath = "";
  let dispose: () => void = () => {};

  onMount(() => {
    void loadShell();
    dispose = registerLyraEvents();
    const interval = window.setInterval(async () => {
      const playback = await api.playback();
      shell.update((state) => ({ ...state, playback }));
    }, 1000);
    return () => {
      window.clearInterval(interval);
    };
  });

  onDestroy(() => {
    dispose();
  });

  async function quickCreatePlaylist() {
    if (!newPlaylistName.trim()) return;
    const playlist = await api.createPlaylist(newPlaylistName.trim());
    newPlaylistName = "";
    await loadShell();
    goto(`/playlists/${playlist.id}`);
  }

  async function quickAddRoot() {
    if (!rootPath.trim()) return;
    await api.addLibraryRoot(rootPath.trim());
    rootPath = "";
    await loadShell();
  }

  async function transport(action: "toggle" | "next" | "previous") {
    const playback =
      action === "toggle"
        ? await api.togglePlayback()
        : action === "next"
          ? await api.playNext()
          : await api.playPrevious();
    shell.update((state) => ({ ...state, playback }));
  }

  async function setVolume(event: Event) {
    const target = event.target as HTMLInputElement;
    const volume = parseFloat(target.value);
    const playback = await api.setVolume(volume);
    shell.update((state) => ({ ...state, playback }));
  }

  async function seek(event: Event) {
    const target = event.target as HTMLInputElement;
    const position = parseFloat(target.value);
    const playback = await api.seekTo(position);
    shell.update((state) => ({ ...state, playback }));
  }

  function active(href: string): boolean {
    return page.url.pathname === href;
  }

  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }
</script>

<svelte:head>
  <title>Lyra</title>
</svelte:head>

<div class="app-shell">
  <aside class="nav-rail">
    <div>
      <p class="eyebrow">Lyra</p>
      <h1>Rust-native desktop player</h1>
    </div>
    <nav class="nav-list">
      {#each nav as item}
        <a class:active={active(item.href)} href={item.href}>{item.label}</a>
      {/each}
    </nav>
    <div class="quick-actions">
      <label>
        <span>New playlist</span>
        <input bind:value={newPlaylistName} placeholder="Late-night drift" />
      </label>
      <button on:click={quickCreatePlaylist}>Create</button>
      <label>
        <span>Library root</span>
        <input bind:value={rootPath} placeholder="C:\Music" />
      </label>
      <button on:click={quickAddRoot}>Add Root</button>
    </div>
  </aside>

  <main class="center-panel">
    {#if $errorMessage}
      <section class="error-banner">{$errorMessage}</section>
    {/if}
    <slot />
  </main>

  <aside class="queue-panel">
    <div class="panel-header">
      <p class="eyebrow">Queue</p>
      <strong>{$shell.queue.length} items</strong>
    </div>
    <div class="queue-list">
      {#if !$shell.queue.length}
        <p class="muted">Queue is empty.</p>
      {/if}
      {#each $shell.queue as item, index}
        <button class:current={index === $shell.playback.queueIndex} on:click={() => api.playQueueIndex(index)}>
          <span>{item.title}</span>
          <small>{item.artist}</small>
        </button>
      {/each}
    </div>
    {#if $legacyImportReport}
      <div class="import-report">
        <p class="eyebrow">Legacy Import</p>
        <p>{$legacyImportReport.notes.join(" | ")}</p>
      </div>
    {/if}
  </aside>
</div>

<footer class="transport">
  <div class="now-playing">
    <p class="eyebrow">Now Playing</p>
    <strong>{$shell.playback.currentTrack?.title ?? "Nothing loaded"}</strong>
    <small>{$shell.playback.currentTrack?.artist ?? "Pick something from Library or Playlists."}</small>
  </div>
  <div class="playback-controls">
    <div class="transport-actions">
      <button on:click={() => transport("previous")}>⏮</button>
      <button class="accent play-pause" on:click={() => transport("toggle")}>
        {$shell.playback.status === "playing" ? "⏸" : "▶"}
      </button>
      <button on:click={() => transport("next")}>⏭</button>
    </div>
    <div class="progress-bar">
      <span class="time">{formatTime($shell.playback.positionSeconds)}</span>
      <input
        type="range"
        min="0"
        max={$shell.playback.durationSeconds || 100}
        value={$shell.playback.positionSeconds}
        on:input={seek}
        class="seek-slider"
      />
      <span class="time">{formatTime($shell.playback.durationSeconds)}</span>
    </div>
  </div>
  <div class="volume-control">
    <span>🔊</span>
    <input
      type="range"
      min="0"
      max="1"
      step="0.01"
      value={$shell.playback.volume}
      on:input={setVolume}
      class="volume-slider"
    />
    <span class="volume-label">{Math.round($shell.playback.volume * 100)}%</span>
  </div>
</footer>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", sans-serif;
    background: linear-gradient(160deg, #0d1117 0%, #101720 40%, #19222e 100%);
    color: #eff5fb;
  }
  :global(a) { color: inherit; text-decoration: none; }
  :global(button), :global(input) { font: inherit; }
  .app-shell {
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr) 320px;
    min-height: calc(100vh - 88px);
  }
  .nav-rail, .queue-panel, .center-panel { padding: 24px; box-sizing: border-box; }
  .nav-rail, .queue-panel { background: rgba(10, 14, 19, 0.72); backdrop-filter: blur(20px); }
  .center-panel { overflow: auto; }
  .nav-list, .quick-actions, .queue-list { display: grid; gap: 12px; }
  .nav-list a, .queue-list button, button {
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    background: rgba(255,255,255,0.04);
    color: inherit;
    padding: 12px 14px;
    text-align: left;
    cursor: pointer;
  }
  .nav-list a.active, .queue-list button.current, button.accent {
    background: linear-gradient(120deg, #cbff6b 0%, #7affc6 100%);
    color: #0f1720;
    border-color: transparent;
  }
  .eyebrow { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.16em; color: #9cb2c7; }
  .muted, small { color: #9cb2c7; }
  
  .transport {
    display: grid;
    grid-template-columns: 1.4fr auto 280px;
    align-items: center;
    gap: 24px;
    padding: 16px 24px;
    background: rgba(6, 10, 14, 0.94);
    border-top: 1px solid rgba(255,255,255,0.08);
  }
  
  .now-playing {
    min-width: 0;
  }
  
  .now-playing strong,
  .now-playing small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .playback-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    min-width: 400px;
  }
  
  .transport-actions {
    display: flex;
    gap: 12px;
    align-items: center;
  }
  
  .transport-actions button {
    font-size: 1.2rem;
    min-width: 48px;
    height: 48px;
    padding: 0;
  }
  
  .transport-actions button.play-pause {
    min-width: 64px;
    height: 64px;
    font-size: 1.8rem;
  }
  
  .progress-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
  }
  
  .time {
    font-size: 0.85rem;
    color: #9cb2c7;
    min-width: 40px;
    text-align: center;
  }
  
  .seek-slider,
  .volume-slider {
    flex: 1;
    height: 6px;
    border-radius: 3px;
    background: rgba(255,255,255,0.15);
    outline: none;
    -webkit-appearance: none;
    appearance: none;
  }
  
  .seek-slider::-webkit-slider-thumb,
  .volume-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: linear-gradient(120deg, #cbff6b 0%, #7affc6 100%);
    cursor: pointer;
  }
  
  .seek-slider::-moz-range-thumb,
  .volume-slider::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: linear-gradient(120deg, #cbff6b 0%, #7affc6 100%);
    cursor: pointer;
    border: none;
  }
  
  .volume-control {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  
  .volume-control .volume-slider {
    width: 120px;
  }
  
  .volume-label {
    min-width: 42px;
    font-size: 0.9rem;
    color: #9cb2c7;
  }
  
  label { display: grid; gap: 6px; }
  input {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
  }
  .error-banner {
    margin-bottom: 16px;
    padding: 12px 14px;
    background: rgba(255, 92, 92, 0.12);
    border: 1px solid rgba(255, 92, 92, 0.32);
    border-radius: 16px;
  }
  @media (max-width: 1400px) {
    .app-shell { grid-template-columns: 240px minmax(0, 1fr) 280px; }
    .nav-rail, .queue-panel { padding: 16px; }
  }
  
  @media (max-width: 1100px) {
    .app-shell { grid-template-columns: 200px minmax(0, 1fr); }
    .queue-panel { display: none; }
    .transport { grid-template-columns: 1fr auto; }
    .volume-control { display: none; }
    .playback-controls { min-width: 300px; }
  }
  
  @media (max-width: 768px) {
    .app-shell { grid-template-columns: 1fr; }
    .nav-rail { display: none; }
    .transport {
      grid-template-columns: 1fr;
      padding: 12px 16px;
    }
    .playback-controls { min-width: 100%; }
    .now-playing { text-align: center; }
  }
</style>

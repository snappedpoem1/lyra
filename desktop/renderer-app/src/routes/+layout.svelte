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

  function active(href: string): boolean {
    return page.url.pathname === href;
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
  <div>
    <p class="eyebrow">Now Playing</p>
    <strong>{$shell.playback.currentTrack?.title ?? "Nothing loaded"}</strong>
    <small>{$shell.playback.currentTrack?.artist ?? "Pick something from Library or Playlists."}</small>
  </div>
  <div class="transport-actions">
    <button on:click={() => transport("previous")}>Previous</button>
    <button class="accent" on:click={() => transport("toggle")}>
      {$shell.playback.status === "playing" ? "Pause" : "Play"}
    </button>
    <button on:click={() => transport("next")}>Next</button>
  </div>
  <div class="transport-status">
    <span>{Math.round($shell.playback.positionSeconds)}s</span>
    <span>{Math.round($shell.playback.durationSeconds)}s</span>
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
    grid-template-columns: 1.4fr auto auto;
    align-items: center;
    gap: 16px;
    padding: 16px 24px;
    background: rgba(6, 10, 14, 0.94);
    border-top: 1px solid rgba(255,255,255,0.08);
  }
  .transport-actions { display: flex; gap: 12px; }
  .transport-status { display: flex; gap: 12px; color: #9cb2c7; }
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
  @media (max-width: 1100px) {
    .app-shell { grid-template-columns: 1fr; }
    .transport { grid-template-columns: 1fr; }
  }
</style>

<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import type { AcquisitionQueueItem, PlaylistSummary } from "$lib/types";

  let vibePlaylists: PlaylistSummary[] = [];
  let acquisitionQueue: AcquisitionQueueItem[] = [];
  let statusFilter = "all";
  let addArtist = "";
  let addTitle = "";
  let addAlbum = "";
  let addSource = "manual";
  let adding = false;

  const STATUS_COLORS: Record<string, string> = {
    pending:   "rgba(203,255,107,0.18)",
    completed: "rgba(122,255,198,0.18)",
    failed:    "rgba(255,107,107,0.18)",
    skipped:   "rgba(155,155,155,0.12)",
  };

  async function load() {
    const all = await api.playlists();
    vibePlaylists = all.filter((p) => p.name.startsWith("[Vibe]"));
    await loadQueue();
  }

  async function loadQueue() {
    const filter = statusFilter === "all" ? undefined : statusFilter;
    acquisitionQueue = await api.acquisitionQueue(filter);
  }

  async function enqueueVibe(playlistId: number) {
    const updated = await api.enqueuePlaylist(playlistId);
    shell.update((s) => ({ ...s, queue: updated }));
  }

  async function submitAdd() {
    if (!addArtist.trim() || !addTitle.trim()) return;
    adding = true;
    try {
      await api.addToAcquisitionQueue(addArtist.trim(), addTitle.trim(), addAlbum.trim() || undefined, addSource || undefined);
      addArtist = ""; addTitle = ""; addAlbum = "";
      await loadQueue();
      shell.update((s) => ({ ...s, acquisitionQueuePending: s.acquisitionQueuePending + 1 }));
    } finally { adding = false; }
  }

  async function markStatus(id: number, status: string) {
    await api.updateAcquisitionItem(id, status);
    await loadQueue();
  }

  onMount(load);
</script>

<section>
  <p class="eyebrow">Discover</p>
  <h2>Vibe playlists &amp; acquisition</h2>
</section>

<div class="two-col">
  <!-- Vibe playlists panel -->
  <div class="panel">
    <p class="panel-head eyebrow">Vibe playlists</p>
    {#if !vibePlaylists.length}
      <p class="muted">No vibe playlists yet. Run a legacy import to populate them from the old oracle database.</p>
    {/if}
    {#each vibePlaylists as pl}
      <div class="vibe-row">
        <div>
          <strong>{pl.name.replace("[Vibe] ", "")}</strong>
          <small>{pl.itemCount} tracks</small>
        </div>
        <div class="row-actions">
          <button on:click={() => enqueueVibe(pl.id)}>Queue</button>
          <a class="btn" href="/playlists/{pl.id}">Detail</a>
        </div>
      </div>
    {/each}
  </div>

  <!-- Acquisition queue panel -->
  <div class="panel">
    <div class="panel-head-row">
      <p class="panel-head eyebrow">Acquisition queue</p>
      <select bind:value={statusFilter} on:change={loadQueue}>
        <option value="all">All</option>
        <option value="pending">Pending</option>
        <option value="completed">Completed</option>
        <option value="failed">Failed</option>
      </select>
    </div>

    <form class="add-form" on:submit|preventDefault={submitAdd}>
      <input bind:value={addArtist} placeholder="Artist" required />
      <input bind:value={addTitle} placeholder="Title" required />
      <input bind:value={addAlbum} placeholder="Album (optional)" />
      <select bind:value={addSource}>
        <option value="manual">Manual</option>
        <option value="wishlist">Wishlist</option>
        <option value="recommendation">Recommendation</option>
      </select>
      <button type="submit" disabled={adding}>Add</button>
    </form>

    <div class="queue-rows">
      {#if !acquisitionQueue.length}
        <p class="muted">No items.</p>
      {/if}
      {#each acquisitionQueue as item}
        <div class="acq-row" style="border-left: 3px solid {STATUS_COLORS[item.status] ?? 'transparent'}">
          <div class="acq-info">
            <strong>{item.title}</strong>
            <small>{item.artist}{item.album ? ` · ${item.album}` : ''}</small>
            <span class="badge" style="background:{STATUS_COLORS[item.status] ?? 'rgba(255,255,255,0.08)'}">
              {item.status}
            </span>
            {#if item.source}<span class="badge source">{item.source}</span>{/if}
            {#if item.error}<small class="err">{item.error}</small>{/if}
          </div>
          <div class="row-actions">
            {#if item.status === "pending"}
              <button on:click={() => markStatus(item.id, "skipped")}>Skip</button>
            {/if}
            {#if item.status === "failed"}
              <button on:click={() => markStatus(item.id, "pending")}>Retry</button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; color: #9cb2c7; font-size: 0.72rem; }
  .muted { color: #9cb2c7; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 20px; }
  .panel { display: flex; flex-direction: column; gap: 10px; }
  .panel-head { margin: 0; }
  .panel-head-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .vibe-row, .acq-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border-radius: 14px;
    background: rgba(255,255,255,0.05);
  }
  .acq-row { border-radius: 0 14px 14px 0; }
  .acq-info { display: grid; gap: 4px; flex: 1; min-width: 0; }
  .row-actions { display: flex; gap: 8px; flex-shrink: 0; }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .source { background: rgba(255,255,255,0.08); }
  .err { color: #ff8080; }
  .add-form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .add-form input, .add-form select {
    padding: 8px 10px;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
    font: inherit;
  }
  .add-form button { grid-column: 1 / -1; }
  button, .btn {
    padding: 8px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
    cursor: pointer;
    font: inherit;
    text-decoration: none;
    display: inline-block;
  }
  .queue-rows { display: flex; flex-direction: column; gap: 4px; }
  select { font: inherit; color: inherit; }
  @media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
</style>

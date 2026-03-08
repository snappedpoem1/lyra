<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { api } from "$lib/tauri";
  import type { PlaylistSummary } from "$lib/types";

  let playlists: PlaylistSummary[] = [];
  let name = "";

  async function refresh() {
    playlists = await api.playlists();
  }

  async function create() {
    if (!name.trim()) return;
    const playlist = await api.createPlaylist(name.trim());
    name = "";
    await goto(`/playlists/${playlist.id}`);
  }

  onMount(refresh);
</script>

<section class="header">
  <div>
    <p class="eyebrow">Playlists</p>
    <h2>Playlist-first by default</h2>
  </div>
  <div class="create-row">
    <input bind:value={name} placeholder="New playlist name" />
    <button on:click={create}>Create</button>
  </div>
</section>

<div class="grid">
  {#if !playlists.length}
    <p class="muted">No playlists yet.</p>
  {/if}
  {#each playlists as playlist}
    <a class="card" href={`/playlists/${playlist.id}`}>
      <strong>{playlist.name}</strong>
      <small>{playlist.itemCount} items</small>
      <span>{playlist.description || "Ready for sequencing, queueing, and future oracle workflows."}</span>
    </a>
  {/each}
</div>

<style>
  .eyebrow, .muted, small { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .header { display: flex; justify-content: space-between; align-items: end; margin-bottom: 20px; }
  .create-row, .grid { display: flex; gap: 12px; }
  .grid { flex-wrap: wrap; }
  .card {
    width: min(320px, 100%);
    padding: 18px;
    border-radius: 18px;
    background: rgba(255,255,255,0.05);
    display: grid;
    gap: 10px;
  }
  input, button {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
  }
</style>

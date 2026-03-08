<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import type { PlaylistDetail } from "$lib/types";

  let playlist: PlaylistDetail | null = null;
  let nextName = "";
  let dragIndex: number | null = null;

  async function loadDetail() {
    playlist = await api.playlistDetail(Number(page.params.id));
    nextName = playlist.name;
  }

  async function rename() {
    playlist = await api.renamePlaylist(Number(page.params.id), nextName);
  }

  async function deletePlaylist() {
    if (!playlist) return;
    await api.deletePlaylist(playlist.id);
    await goto("/playlists");
  }

  async function play(trackId: number) {
    const playback = await api.playTrack(trackId);
    shell.update((s) => ({ ...s, playback }));
  }

  async function enqueueAll() {
    if (!playlist) return;
    const queue = await api.enqueuePlaylist(playlist.id);
    shell.update((s) => ({ ...s, queue }));
  }

  async function removeTrack(trackId: number) {
    if (!playlist) return;
    playlist = await api.removeTrackFromPlaylist(playlist.id, trackId);
  }

  function onDragStart(index: number) {
    dragIndex = index;
  }

  async function onDrop(targetIndex: number) {
    if (!playlist || dragIndex === null || dragIndex === targetIndex) {
      dragIndex = null;
      return;
    }
    const trackId = playlist.items[dragIndex].id;
    playlist = await api.reorderPlaylistItem(playlist.id, trackId, targetIndex);
    dragIndex = null;
  }

  onMount(loadDetail);
</script>

{#if playlist}
  <section class="page-head">
    <div>
      <p class="eyebrow">Playlist Detail</p>
      <h2>{playlist.name}</h2>
      <small>{playlist.items.length} items</small>
    </div>
    <div class="row">
      <input bind:value={nextName} />
      <button on:click={rename}>Rename</button>
      <button on:click={enqueueAll}>Queue All</button>
      <button class="danger" on:click={deletePlaylist}>Delete</button>
    </div>
  </section>

  <div class="list">
    {#each playlist.items as track, idx}
      <article
        draggable="true"
        on:dragstart={() => onDragStart(idx)}
        on:dragover|preventDefault
        on:drop={() => onDrop(idx)}
      >
        <div class="drag-handle">⠿</div>
        <div class="track-info">
          <strong>{track.title}</strong>
          <small>{track.artist} • {track.album}</small>
        </div>
        <div class="actions">
          <button on:click={() => play(track.id)}>▶</button>
          <button class="danger" on:click={() => removeTrack(track.id)}>✕</button>
        </div>
      </article>
    {/each}
    {#if !playlist.items.length}
      <p class="muted">No tracks. Add tracks from the Library view.</p>
    {/if}
  </div>
{/if}

<style>
  .eyebrow, small, .muted { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .page-head, .row, .list, article, .actions { display: flex; gap: 12px; }
  .page-head { justify-content: space-between; align-items: end; margin-bottom: 20px; }
  .list { flex-direction: column; }
  article {
    align-items: center;
    padding: 12px 16px;
    border-radius: 16px;
    background: rgba(255,255,255,0.05);
    cursor: grab;
  }
  .drag-handle { color: #555; user-select: none; }
  .track-info { flex: 1; display: flex; flex-direction: column; gap: 2px; }
  .actions { align-items: center; }
  input, button {
    padding: 8px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
    cursor: pointer;
  }
  button.danger { border-color: rgba(220,50,50,0.4); color: #e07070; }
</style>


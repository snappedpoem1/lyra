<script lang="ts">
  import { goto } from "$app/navigation";
  import { shell } from "$lib/stores/lyra";
  import { api } from "$lib/tauri";

  let saveAsName = "";

  async function move(queueItemId: number, newPosition: number) {
    const queue = await api.moveQueueItem(queueItemId, newPosition);
    shell.update((state) => ({ ...state, queue }));
  }

  async function remove(queueItemId: number) {
    const queue = await api.removeQueueItem(queueItemId);
    shell.update((state) => ({ ...state, queue }));
  }

  async function clear() {
    const queue = await api.clearQueue();
    shell.update((state) => ({ ...state, queue }));
  }

  async function saveAsPlaylist() {
    if (!saveAsName.trim()) return;
    const playlist = await api.createPlaylistFromQueue(saveAsName.trim());
    saveAsName = "";
    await goto(`/playlists/${playlist.id}`);
  }
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Queue / Now Playing</p>
    <h2>Current session</h2>
  </div>
  <div class="row">
    <input bind:value={saveAsName} placeholder="Save queue as playlist…" />
    <button on:click={saveAsPlaylist}>Save</button>
    <button on:click={clear}>Clear Queue</button>
  </div>
</section>

<section class="current">
  <strong>{$shell.playback.currentTrack?.title ?? "Nothing playing"}</strong>
  <small>{$shell.playback.currentTrack?.artist ?? "Queue a track to begin."}</small>
  <span>Status: {$shell.playback.status}</span>
</section>

<div class="queue-list">
  {#each $shell.queue as item, index}
    <article>
      <div>
        <strong>{item.title}</strong>
        <small>{item.artist}</small>
      </div>
      <div class="row">
        <button disabled={index === 0} on:click={() => move(item.id, index - 1)}>Up</button>
        <button on:click={() => api.playQueueIndex(index)}>Play</button>
        <button on:click={() => remove(item.id)}>Remove</button>
      </div>
    </article>
  {/each}
</div>

<style>
  .eyebrow, small, span { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .page-head, .row, .queue-list, article { display: flex; gap: 12px; }
  .page-head { justify-content: space-between; align-items: end; margin-bottom: 20px; }
  .current, article {
    padding: 18px;
    border-radius: 18px;
    background: rgba(255,255,255,0.05);
    margin-bottom: 14px;
  }
  .queue-list { flex-direction: column; }
  article { justify-content: space-between; align-items: center; }
  button {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
  }
</style>

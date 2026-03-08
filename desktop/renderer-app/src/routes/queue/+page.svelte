<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { shell } from "$lib/stores/lyra";
  import { api } from "$lib/tauri";
  import { setInspectorTab, setWorkspacePage, setWorkspaceTrack } from "$lib/stores/workspace";

  let saveAsName = "";
  let likedOverride: boolean | null = null;

  $: currentTrack = $shell.playback.currentTrack;
  $: isLiked = likedOverride !== null ? likedOverride : (currentTrack?.liked ?? false);
  $: if (currentTrack?.id) {
    likedOverride = null;
    setWorkspaceTrack(currentTrack);
  }

  onMount(() => {
    setWorkspacePage(
      "Queue",
      "Current session",
      "Keep now playing, queue order, and playlist capture inside the same canonical shell.",
      "queue"
    );
    setInspectorTab("queue");
  });

  async function toggleLikeCurrentTrack() {
    if (!currentTrack) return;
    const nowLiked = await api.toggleLike(currentTrack.id);
    likedOverride = nowLiked;
    setWorkspaceTrack(currentTrack);
  }

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

  async function playQueueIndex(index: number): Promise<void> {
    const playback = await api.playQueueIndex(index);
    shell.update((state) => ({ ...state, playback }));
    setWorkspaceTrack(playback.currentTrack ?? null);
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
    <input bind:value={saveAsName} placeholder="Save queue as playlist..." />
    <button on:click={saveAsPlaylist}>Save</button>
    <button on:click={clear}>Clear Queue</button>
  </div>
</section>

<section class="current">
  <div class="current-info">
    <strong>{currentTrack?.title ?? "Nothing playing"}</strong>
    {#if currentTrack?.artist}
      <small><a class="artist-link" href={`/artists/${encodeURIComponent(currentTrack.artist)}`}>{currentTrack.artist}</a>{currentTrack?.album ? ` - ${currentTrack.album}` : ""}</small>
    {:else}
      <small>Queue a track to begin.</small>
    {/if}
    <span>Status: {$shell.playback.status}</span>
  </div>
  {#if currentTrack}
    <button class="like-btn" class:liked={isLiked} on:click={toggleLikeCurrentTrack}
      title={isLiked ? "Unlike" : "Like this track"}>{isLiked ? "Liked" : "Like"}</button>
  {/if}
</section>

<div class="queue-list">
  {#each $shell.queue as item, index}
    <article>
      <div>
        <strong>{item.title}</strong>
        <small><a class="artist-link" href={`/artists/${encodeURIComponent(item.artist)}`}>{item.artist}</a></small>
      </div>
      <div class="row">
        <button disabled={index === 0} on:click={() => move(item.id, index - 1)}>Up</button>
        <button on:click={() => playQueueIndex(index)}>Play</button>
        <button on:click={() => remove(item.id)}>Remove</button>
      </div>
    </article>
  {/each}
</div>

<style>
  .eyebrow, small, span { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .page-head, .row, .queue-list, article { display: flex; gap: 12px; }
  .artist-link { color: #a8c4e0; text-decoration: underline; }
  .page-head { justify-content: space-between; align-items: end; margin-bottom: 20px; }
  .current, article {
    padding: 18px;
    border-radius: 18px;
    background: rgba(255,255,255,0.05);
    margin-bottom: 14px;
  }
  .current { display: flex; justify-content: space-between; align-items: center; }
  .current-info { display: flex; flex-direction: column; gap: 4px; }
  .like-btn { font-size: 1.4rem; padding: 6px 12px; color: #9cb2c7; background: transparent; border: none; cursor: pointer; }
  .like-btn.liked { color: #ff6b8a; }
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

<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import type { ArtistProfile } from "$lib/types";

  let profile: ArtistProfile | null = null;
  let loading = true;
  let error = "";

  async function loadProfile() {
    loading = true;
    error = "";
    try {
      const rawName = page.params.name;
      if (!rawName) {
        error = "Artist route is missing a name.";
        return;
      }
      const artistName = decodeURIComponent(rawName);
      profile = await api.getArtistProfile(artistName);
      if (!profile) {
        error = "Artist not found in local library.";
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load artist profile.";
    } finally {
      loading = false;
    }
  }

  async function playTrack(trackId: number) {
    const playback = await api.playTrack(trackId);
    shell.update((s) => ({ ...s, playback }));
  }

  async function queueTrack(trackId: number) {
    const queue = await api.enqueueTracks([trackId]);
    shell.update((s) => ({ ...s, queue }));
  }

  async function playArtist(): Promise<void> {
    if (!profile) return;
    const playback = await api.playArtist(profile.artist);
    shell.update((s) => ({ ...s, playback }));
    const queue = await api.queue();
    shell.update((s) => ({ ...s, queue }));
  }

  async function queueArtist(): Promise<void> {
    if (!profile) return;
    const trackIds = profile.topTracks.map((t) => t.id);
    if (!trackIds.length) return;
    const queue = await api.enqueueTracks(trackIds);
    shell.update((s) => ({ ...s, queue }));
  }

  async function playAlbum(albumTitle: string): Promise<void> {
    if (!profile) return;
    const playback = await api.playAlbum(profile.artist, albumTitle);
    shell.update((s) => ({ ...s, playback }));
    const queue = await api.queue();
    shell.update((s) => ({ ...s, queue }));
  }

  onMount(loadProfile);
</script>

<section class="artist-page">
  {#if loading}
    <p class="muted">Loading artist profile...</p>
  {:else if error}
    <p class="muted">{error}</p>
  {:else if profile}
    <header class="hero">
      {#if profile.imageUrl}
        <img src={profile.imageUrl} alt={profile.artist} class="hero-art" />
      {:else}
        <div class="hero-art fallback">{profile.artist.slice(0, 1).toUpperCase()}</div>
      {/if}
      <div class="hero-copy">
        <p class="eyebrow">Artist</p>
        <h1>{profile.artist}</h1>
        <p class="muted">{profile.trackCount} tracks · {profile.albumCount} albums</p>
        {#if profile.genres.length}
          <p class="genres">{profile.genres.join(" · ")}</p>
        {/if}
        {#if profile.lastfmUrl}
          <a href={profile.lastfmUrl} target="_blank" rel="noopener">Last.fm profile</a>
        {/if}
        <div class="actions hero-actions">
          <button on:click={playArtist}>Play Artist</button>
          <button on:click={queueArtist}>Queue Artist</button>
        </div>
      </div>
    </header>

    <section class="panel">
      <p class="eyebrow">Bio</p>
      <p>{profile.bio ?? "No cached artist biography yet. Enrich tracks in Library to fetch context."}</p>
      {#if profile.albums.length}
        <div class="albums-list">
          <p class="eyebrow">Albums</p>
          {#each profile.albums as album}
            <div class="album-row">
              <span>{album}</span>
              <button on:click={() => playAlbum(album)}>Play Album</button>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <section class="grid">
      <article class="panel">
        <p class="eyebrow">Connections</p>
        {#if profile.connections.length}
          {#each profile.connections as connection}
            <a class="conn-row" href={`/artists/${encodeURIComponent(connection.artist)}`}>
              <span>{connection.artist}</span>
              <small>{connection.score} co-plays</small>
            </a>
          {/each}
        {:else}
          <p class="muted">No local connection graph yet. Play more sessions to build it.</p>
        {/if}
      </article>

      <article class="panel">
        <p class="eyebrow">Top Library Tracks</p>
        {#each profile.topTracks as track}
          <div class="track-row">
            <div>
              <strong>{track.title}</strong>
              <small>{track.album}</small>
            </div>
            <div class="actions">
              <button on:click={() => playTrack(track.id)}>Play</button>
              <button on:click={() => queueTrack(track.id)}>Queue</button>
            </div>
          </div>
        {/each}
      </article>
    </section>
  {/if}
</section>

<style>
  .artist-page { display: grid; gap: 16px; }
  .hero, .panel { border-radius: 14px; background: rgba(255,255,255,0.05); padding: 16px; }
  .hero { display: grid; grid-template-columns: 120px 1fr; gap: 14px; }
  .hero-art { width: 120px; height: 120px; object-fit: cover; border-radius: 12px; }
  .hero-art.fallback { display: grid; place-items: center; background: rgba(255,255,255,0.12); font-size: 2rem; }
  .eyebrow, .muted, small { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .genres { color: #d0e8f8; margin-top: 4px; }
  .grid { display: grid; grid-template-columns: 1fr 1.3fr; gap: 16px; }
  .conn-row, .track-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }
  .track-row:last-child, .conn-row:last-child { border-bottom: none; }
  .actions { display: flex; gap: 8px; }
  .hero-actions { margin-top: 10px; }
  .albums-list { margin-top: 12px; display: grid; gap: 6px; }
  .album-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }
  button { padding: 6px 10px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); color: inherit; }
  @media (max-width: 900px) {
    .hero { grid-template-columns: 1fr; }
    .hero-art { width: 100%; max-width: 240px; }
    .grid { grid-template-columns: 1fr; }
  }
</style>

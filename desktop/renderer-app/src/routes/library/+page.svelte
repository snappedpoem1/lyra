<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import type { DuplicateCluster, PlaylistSummary, TrackRecord, TrackScores } from "$lib/types";

  const SCORE_DIMS = ["energy","valence","tension","density","warmth","movement","space","rawness","complexity","nostalgia"] as const;

  let query = "";
  let tracks: TrackRecord[] = [];
  let playlists: PlaylistSummary[] = [];
  let addToPlaylistTrackId: number | null = null;
  let expandedScores: Record<number, TrackScores | null | "loading"> = {};
  let expandedEnrich: Record<number, Record<string, unknown> | null | "loading"> = {};
  let duplicates: DuplicateCluster[] = [];
  let dupsLoaded = false;
  let dupsOpen = false;
  let enrichLibraryPending = false;

  async function loadTracks() {
    tracks = await api.tracks(query);
  }

  async function play(trackId: number) {
    const playback = await api.playTrack(trackId);
    shell.update((state) => ({ ...state, playback }));
  }

  async function queue(trackId: number) {
    const updated = await api.enqueueTracks([trackId]);
    shell.update((state) => ({ ...state, queue: updated }));
  }

  async function openAddToPlaylist(trackId: number) {
    playlists = await api.playlists();
    addToPlaylistTrackId = trackId;
  }

  async function addToPlaylist(playlistId: number) {
    if (addToPlaylistTrackId === null) return;
    await api.addTrackToPlaylist(playlistId, addToPlaylistTrackId);
    addToPlaylistTrackId = null;
  }

  async function toggleScores(trackId: number) {
    if (expandedScores[trackId] !== undefined) {
      const { [trackId]: _, ...rest } = expandedScores;
      expandedScores = rest;
      return;
    }
    expandedScores = { ...expandedScores, [trackId]: "loading" };
    const scores = await api.trackScores(trackId);
    expandedScores = { ...expandedScores, [trackId]: scores ?? null };
  }

  async function toggleEnrich(trackId: number) {
    if (expandedEnrich[trackId] !== undefined) {
      const { [trackId]: _, ...rest } = expandedEnrich;
      expandedEnrich = rest;
      return;
    }
    expandedEnrich = { ...expandedEnrich, [trackId]: "loading" };
    try {
      const result = await api.enrichTrack(trackId);
      expandedEnrich = { ...expandedEnrich, [trackId]: result };
    } catch {
      expandedEnrich = { ...expandedEnrich, [trackId]: null };
    }
  }

  async function runEnrichLibrary() {
    enrichLibraryPending = true;
    try {
      await api.enrichLibrary();
    } finally {
      enrichLibraryPending = false;
    }
  }

  onMount(loadTracks);

  async function loadDuplicates() {
    duplicates = await api.findDuplicates();
    dupsLoaded = true;
    dupsOpen = true;
  }
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Library</p>
    <h2>Local catalog</h2>
  </div>
  <div class="search-row">
    <input bind:value={query} placeholder="Search title, artist, or album" on:keydown={(e) => e.key === 'Enter' && loadTracks()} />
    <button on:click={loadTracks}>Search</button>
    <button class="dups-btn" on:click={() => dupsLoaded ? (dupsOpen = !dupsOpen) : loadDuplicates()}
      title="Find duplicate tracks">Duplicates{duplicates.length ? ` (${duplicates.length})` : ''}</button>
    <button class="enrich-btn" on:click={runEnrichLibrary} disabled={enrichLibraryPending}
      title="Enrich up to 50 unenriched tracks via MusicBrainz">
      {enrichLibraryPending ? 'Enriching…' : 'Enrich Library'}
    </button>
  </div>
</section>

{#if dupsOpen && duplicates.length > 0}
  <section class="dup-section">
    <p class="eyebrow">Potential Duplicates — {duplicates.length} cluster{duplicates.length !== 1 ? 's' : ''}</p>
    {#each duplicates as cluster}
      <div class="dup-cluster">
        {#each cluster.tracks as track}
          <div class="dup-row">
            <span class="dup-title">{track.title}</span>
            <span class="dup-artist">{track.artist}</span>
            <span class="dup-path">{track.path}</span>
            <button on:click={() => play(track.id)}>Play</button>
          </div>
        {/each}
      </div>
    {/each}
  </section>
{:else if dupsLoaded && duplicates.length === 0 && dupsOpen}
  <section class="dup-section"><p class="muted">No duplicate tracks found.</p></section>
{/if}

<section class="track-list">
  {#if !tracks.length}
    <p class="muted">No imported tracks yet. Add a library root and start a scan.</p>
  {/if}
  {#each tracks as track}
    <article>
      <div class="track-info">
        <strong>{track.title}</strong>
        <small>
          {track.artist} • {track.album}{track.year ? ` · ${track.year}` : ''}{track.genre ? ` · ${track.genre}` : ''}
          {#if track.bpm}<span class="pill">{Math.round(track.bpm)} BPM</span>{/if}
        </small>
      </div>
      <div class="actions">
        <button on:click={() => play(track.id)}>Play</button>
        <button on:click={() => queue(track.id)}>Queue</button>
        <button on:click={() => openAddToPlaylist(track.id)}>+ Playlist</button>
        <button class="scores-toggle" on:click={() => toggleScores(track.id)}
          title="Show scores">{expandedScores[track.id] !== undefined ? '▾' : '▸'}</button>
        <button class="enrich-toggle" on:click={() => toggleEnrich(track.id)}
          title="Show enrichment data">{expandedEnrich[track.id] !== undefined ? '✦' : '✧'}</button>
      </div>
    </article>
    {#if expandedScores[track.id] !== undefined && expandedScores[track.id] !== "loading"}
      {@const rawScore = expandedScores[track.id]}
      {@const sc = (rawScore !== "loading" ? rawScore : null) as import("$lib/types").TrackScores | null}
      {#if sc}
        <div class="score-panel">
          {#each SCORE_DIMS as dim}
            {@const val = sc[dim] ?? 0.5}
            <div class="sdim">
              <span>{dim}</span>
              <div class="sbar-bg"><div class="sbar" style="width:{Math.round((val as number)*100)}%"></div></div>
              <span class="sval">{Math.round((val as number)*100)}</span>
            </div>
          {/each}
        </div>
      {:else}
        <div class="score-panel muted-panel"><small>No scores — run legacy import to populate.</small></div>
      {/if}
    {/if}
    {#if expandedEnrich[track.id] !== undefined}
      {#if expandedEnrich[track.id] === "loading"}
        <div class="enrich-panel muted-panel"><small>Fetching enrichment data…</small></div>
      {:else if expandedEnrich[track.id] === null}
        <div class="enrich-panel muted-panel"><small>Enrichment failed.</small></div>
      {:else}
        {@const er = expandedEnrich[track.id] as Record<string, unknown>}
        {@const mb = typeof er.providers === 'object' && er.providers !== null
          ? (er.providers as Record<string, unknown>)['musicbrainz'] as Record<string, unknown> | undefined
          : undefined}
        {@const pl = mb ? mb.payload as Record<string, unknown> | undefined : undefined}
        <div class="enrich-panel">
          {#if pl && pl.status === 'ok'}
            <div class="enrich-row">
              <span class="elabel">MBID</span>
              <code class="evalue">{pl.recordingMbid ?? '—'}</code>
            </div>
            <div class="enrich-row">
              <span class="elabel">Release</span>
              <span class="evalue">{pl.releaseTitle ?? '—'}{pl.releaseDate ? ` · ${pl.releaseDate}` : ''}</span>
            </div>
            <div class="enrich-row">
              <span class="elabel">Match</span>
              <span class="evalue">{pl.matchScore ?? '—'}%</span>
            </div>
            {#if pl.releaseMbid}
              <div class="enrich-row">
                <span class="elabel">Release MBID</span>
                <code class="evalue">{pl.releaseMbid}</code>
              </div>
            {/if}
          {:else}
            <span class="muted"><small>Status: {pl?.status ?? 'unknown'}</small></span>
          {/if}
        </div>
      {/if}
    {/if}
  {/each}
</section>

{#if addToPlaylistTrackId !== null}
  <div class="overlay" role="dialog" aria-modal="true">
    <div class="dialog">
      <p>Add to playlist</p>
      {#each playlists as pl}
        <button on:click={() => addToPlaylist(pl.id)}>{pl.name}</button>
      {/each}
      <button on:click={() => (addToPlaylistTrackId = null)}>Cancel</button>
    </div>
  </div>
{/if}

<style>
  .eyebrow, .muted, small { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .page-head, .search-row { display: flex; gap: 12px; }
  .page-head { justify-content: space-between; align-items: end; margin-bottom: 20px; }
  .track-list { display: flex; flex-direction: column; gap: 4px; }
  .search-row input {
    min-width: 280px;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
  }
  article {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-radius: 14px;
    background: rgba(255,255,255,0.05);
    gap: 12px;
  }
  .track-info { display: grid; gap: 4px; flex: 1; min-width: 0; }
  .actions { display: flex; gap: 8px; flex-shrink: 0; }
  .pill {
    display: inline-block;
    background: rgba(203,255,107,0.12);
    border-radius: 6px;
    padding: 1px 6px;
    font-size: 0.72rem;
    color: #cbff6b;
  }
  button {
    padding: 8px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
    cursor: pointer;
  }
  .scores-toggle { padding: 8px 10px; min-width: 32px; text-align: center; }
  .enrich-toggle { padding: 8px 10px; min-width: 32px; text-align: center; color: #a8c4e0; }
  .enrich-btn { color: #a8c4e0; }
  .score-panel {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
    padding: 12px 16px;
    border-radius: 12px;
    background: rgba(255,255,255,0.03);
    margin-bottom: 4px;
  }
  .muted-panel { padding: 8px 16px; }
  .enrich-panel {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 12px 16px;
    border-radius: 12px;
    background: rgba(168,196,224,0.05);
    margin-bottom: 4px;
  }
  .enrich-row { display: flex; gap: 10px; align-items: baseline; }
  .elabel { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.12em; color: #9cb2c7; min-width: 90px; }
  .evalue { font-size: 0.8rem; color: #d0e8f8; word-break: break-all; }
  code.evalue { font-family: monospace; font-size: 0.72rem; color: #a8c4e0; }
  .sdim { display: grid; gap: 4px; }
  .sdim span { font-size: 0.68rem; text-transform: capitalize; color: #9cb2c7; }
  .sbar-bg { height: 5px; border-radius: 3px; background: rgba(255,255,255,0.1); }
  .sbar { height: 100%; border-radius: 3px; background: linear-gradient(90deg,#cbff6b,#7affc6); }
  .sval { color: #9cb2c7; font-size: 0.68rem; }
  .overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center;
    z-index: 100;
  }
  .dialog {
    background: #1a2030;
    border-radius: 18px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-width: 240px;
  }
  .dups-btn { margin-left: auto; }
  .dup-section {
    margin-bottom: 18px;
    padding: 14px 16px;
    border-radius: 14px;
    background: rgba(255,255,255,0.04);
  }
  .dup-cluster {
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    margin-bottom: 10px;
    overflow: hidden;
  }
  .dup-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    font-size: 0.85rem;
  }
  .dup-row:last-child { border-bottom: none; }
  .dup-title { font-weight: 600; min-width: 140px; }
  .dup-artist { color: #9cb2c7; min-width: 120px; }
  .dup-path { flex: 1; font-size: 0.72rem; color: #6a8aaa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>


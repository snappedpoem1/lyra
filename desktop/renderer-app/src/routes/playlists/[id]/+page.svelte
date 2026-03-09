<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import { setWorkspaceExplanation, setWorkspacePage, setWorkspaceProvenance, setWorkspaceTrack } from "$lib/stores/workspace";
  import type {
    ExplainPayload,
    PlaylistDetail,
    PlaylistTrackReasonRecord,
    TrackEnrichmentResult,
    TrackRecord
  } from "$lib/types";

  let playlist: PlaylistDetail | null = null;
  let nextName = "";
  let dragIndex: number | null = null;

  // G-061: per-track reasons (from playlist_track_reasons for generated playlists)
  let trackReasons: Record<number, PlaylistTrackReasonRecord> = {};
  // G-061: expand states for explain and provenance
  let expandedExplain: Record<number, ExplainPayload | "loading"> = {};
  let expandedProvenance: Record<number, TrackEnrichmentResult | "loading"> = {};

  async function loadDetail() {
    const id = Number(page.params.id);
    // Load detail and reasons in parallel
    const [detail, reasons] = await Promise.all([
      api.playlistDetail(id),
      api.getPlaylistTrackReasons(id).catch(() => [] as PlaylistTrackReasonRecord[]),
    ]);
    playlist = detail;
    nextName = detail.name;
    trackReasons = Object.fromEntries(reasons.map((reason) => [reason.trackId, reason]));
  }

  async function rename() {
    playlist = await api.renamePlaylist(Number(page.params.id), nextName);
  }

  async function deletePlaylist() {
    if (!playlist) return;
    await api.deletePlaylist(playlist.id);
    await goto("/playlists");
  }

  async function play(track: TrackRecord) {
    const playback = await api.playTrack(track.id);
    shell.update((s) => ({ ...s, playback }));
    setWorkspaceTrack(track);
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

  // G-061: toggle "Why?" explanation for a track
  async function toggleExplain(track: TrackRecord) {
    if (expandedExplain[track.id]) {
      const next = { ...expandedExplain };
      delete next[track.id];
      expandedExplain = next;
      return;
    }
    expandedExplain = { ...expandedExplain, [track.id]: "loading" };
    try {
      const payload = await api.explainRecommendation(track.id);
      expandedExplain = { ...expandedExplain, [track.id]: payload };
      setWorkspaceExplanation(payload, track);
    } catch {
      const next = { ...expandedExplain };
      delete next[track.id];
      expandedExplain = next;
    }
  }

  // G-061: toggle provenance proof for a track
  async function toggleProvenance(track: TrackRecord) {
    if (expandedProvenance[track.id]) {
      const next = { ...expandedProvenance };
      delete next[track.id];
      expandedProvenance = next;
      return;
    }
    expandedProvenance = { ...expandedProvenance, [track.id]: "loading" };
    try {
      const result = await api.getTrackEnrichment(track.id);
      expandedProvenance = { ...expandedProvenance, [track.id]: result };
      setWorkspaceProvenance(result.entries, track);
    } catch {
      const next = { ...expandedProvenance };
      delete next[track.id];
      expandedProvenance = next;
    }
  }

  onMount(() => {
    setWorkspacePage("Cassette", "Saved route", "View a saved Cassette result with Lyra reasoning, phase roles, and proof still attached.", "context");
    loadDetail();
  });
</script>

{#if playlist}
  <section class="page-head">
    <div>
      <p class="eyebrow">Playlist</p>
      <h2>{playlist.name}</h2>
      <small>{playlist.items.length} tracks</small>
    </div>
    <div class="row">
      <input bind:value={nextName} aria-label="Rename playlist" />
      <button on:click={rename}>Rename</button>
      <button on:click={enqueueAll}>Queue All</button>
      <button class="danger" on:click={deletePlaylist}>Delete</button>
    </div>
  </section>

  <div class="list">
    {#each playlist.items as track, idx (track.id)}
      <article
        class="track-row"
        draggable="true"
        on:dragstart={() => onDragStart(idx)}
        on:dragover|preventDefault
        on:drop={() => onDrop(idx)}
      >
        <div class="drag-handle" aria-hidden="true">⠿</div>
        <div class="track-body">
          <div class="track-top">
            <div class="track-info">
              <strong>{track.title}</strong>
              <small>{track.artist}{track.album ? ` · ${track.album}` : ""}</small>
            </div>
            <div class="actions">
              <button class="icon-btn" on:click={() => play(track)} title="Play">▶</button>
              <button
                class="dim-btn"
                class:active={!!expandedProvenance[track.id]}
                on:click={() => toggleProvenance(track)}
                title="Show enrichment provenance"
              >Proof</button>
              <button
                class="dim-btn"
                class:active={!!expandedExplain[track.id]}
                on:click={() => toggleExplain(track)}
                title="Why is this track here?"
              >Why?</button>
              <button class="icon-btn danger" on:click={() => removeTrack(track.id)} title="Remove">✕</button>
            </div>
          </div>

          <!-- Playlist reason badge (populated for generated playlists) -->
          {#if trackReasons[track.id]}
            <div class="saved-reason">
              <p class="reason-badge">{trackReasons[track.id].reason}</p>
              {#if trackReasons[track.id].phaseLabel}
                <small class="phase-chip">{trackReasons[track.id].phaseLabel}</small>
              {/if}
              {#if trackReasons[track.id].reasonPayload}
                <div class="reason-grid">
                  <small><strong>Why</strong> {trackReasons[track.id].reasonPayload?.whyThisTrack}</small>
                  <small><strong>Transition</strong> {trackReasons[track.id].reasonPayload?.transitionNote}</small>
                  {#if trackReasons[track.id].reasonPayload?.explicitFromPrompt.length}
                    <small><strong>Explicit</strong> {trackReasons[track.id].reasonPayload?.explicitFromPrompt.join(", ")}</small>
                  {/if}
                  {#if trackReasons[track.id].reasonPayload?.inferredByLyra.length}
                    <small><strong>Inferred by Lyra</strong> {trackReasons[track.id].reasonPayload?.inferredByLyra.join(", ")}</small>
                  {/if}
                  {#if trackReasons[track.id].reasonPayload?.evidence.length}
                    <small><strong>Evidence</strong> {trackReasons[track.id].reasonPayload?.evidence.join(" | ")}</small>
                  {/if}
                </div>
              {/if}
            </div>
          {/if}

          <!-- G-061: explain panel -->
          {#if expandedExplain[track.id]}
            <div class="expand-panel">
              {#if expandedExplain[track.id] === "loading"}
                <p class="muted">Loading explanation...</p>
              {:else}
                {@const ep = expandedExplain[track.id] as ExplainPayload}
                {#each ep.reasons as reason}
                  <p class="explain-reason">{reason}</p>
                {/each}
                <span class="confidence-chip">Confidence: {Math.round(ep.confidence * 100)}%</span>
              {/if}
            </div>
          {/if}

          <!-- G-061: provenance panel -->
          {#if expandedProvenance[track.id]}
            <div class="expand-panel provenance">
              {#if expandedProvenance[track.id] === "loading"}
                <p class="muted">Loading provenance...</p>
              {:else}
                {@const proof = expandedProvenance[track.id] as TrackEnrichmentResult}
                <div class="proof-head">
                  <span class="state-chip" class:degraded={proof.enrichmentState === "degraded" || proof.degradedProviders.length > 0}>
                    {proof.enrichmentState}
                  </span>
                  {#if proof.primaryMbid}
                    <code class="mbid">{proof.primaryMbid}</code>
                  {/if}
                  {#if proof.degradedProviders.length > 0}
                    <span class="degraded-note">Degraded: {proof.degradedProviders.join(", ")}</span>
                  {/if}
                </div>
                <div class="proof-entries">
                  {#each proof.entries.slice(0, 4) as entry}
                    <div class="proof-row" class:dim={entry.status === "not_configured" || entry.status === "not_found"}>
                      <strong class="proof-provider">{entry.provider}</strong>
                      <span class="proof-status">{entry.status}</span>
                      <span class="proof-conf">{Math.round(entry.confidence * 100)}%</span>
                      {#if entry.note}<span class="proof-note">{entry.note}</span>{/if}
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
        </div>
      </article>
    {/each}
    {#if !playlist.items.length}
      <p class="muted">No tracks yet. Add tracks from the Library view.</p>
    {/if}
  </div>
{/if}

<style>
  .eyebrow { color: #9cb2c7; text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  small, .muted { color: #9cb2c7; }

  .page-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 20px;
    gap: 12px;
  }
  .row { display: flex; gap: 8px; align-items: center; }

  .list { display: flex; flex-direction: column; gap: 6px; }

  .track-row {
    display: flex;
    gap: 10px;
    padding: 12px 16px;
    border-radius: 16px;
    background: rgba(255,255,255,0.05);
    cursor: grab;
    align-items: flex-start;
  }
  .drag-handle { color: #555; user-select: none; padding-top: 2px; }

  .track-body { flex: 1; display: flex; flex-direction: column; gap: 6px; }

  .track-top { display: flex; align-items: center; gap: 10px; }
  .track-info { flex: 1; display: flex; flex-direction: column; gap: 2px; }

  .actions { display: flex; gap: 6px; align-items: center; }

  .reason-badge {
    font-size: 0.8rem;
    color: #a8c4e0;
    border-left: 2px solid rgba(168,196,224,0.4);
    padding-left: 8px;
    margin: 0;
    font-style: italic;
  }

  .saved-reason {
    display: grid;
    gap: 6px;
    padding: 8px 10px;
    border-radius: 12px;
    background: rgba(255,255,255,0.035);
  }

  .phase-chip {
    display: inline-flex;
    align-self: flex-start;
    padding: 3px 8px;
    border-radius: 999px;
    background: rgba(246,196,114,0.1);
    color: #f0c983;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.68rem;
  }

  .reason-grid {
    display: grid;
    gap: 4px;
  }

  .reason-grid strong {
    color: #f4e6c0;
    margin-right: 6px;
  }

  .expand-panel {
    background: rgba(255,255,255,0.04);
    border-radius: 10px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .expand-panel.provenance { border-left: 2px solid rgba(168,196,224,0.25); }

  .explain-reason { font-size: 0.85rem; color: #c8daea; margin: 0; }
  .confidence-chip {
    font-size: 0.75rem;
    color: #9cb2c7;
    background: rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 2px 8px;
    align-self: flex-start;
  }

  .proof-head { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 6px; }
  .state-chip {
    font-size: 0.72rem;
    padding: 2px 8px;
    border-radius: 8px;
    background: rgba(122,255,198,0.12);
    color: #7affc6;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .state-chip.degraded { background: rgba(255,200,80,0.14); color: #ffc850; }
  .mbid { font-size: 0.72rem; color: #9cb2c7; background: rgba(255,255,255,0.05); padding: 1px 6px; border-radius: 6px; }
  .degraded-note { font-size: 0.75rem; color: #ffc850; }

  .proof-entries { display: flex; flex-direction: column; gap: 3px; }
  .proof-row { display: flex; gap: 10px; align-items: center; font-size: 0.8rem; }
  .proof-row.dim { opacity: 0.45; }
  .proof-provider { min-width: 90px; color: #c8daea; }
  .proof-status { color: #9cb2c7; font-size: 0.75rem; text-transform: uppercase; }
  .proof-conf { color: #7affc6; font-size: 0.75rem; min-width: 36px; }
  .proof-note { color: #9cb2c7; font-size: 0.72rem; font-style: italic; }

  input, button {
    padding: 8px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
    cursor: pointer;
  }
  .icon-btn { padding: 6px 10px; border-radius: 10px; }
  .dim-btn {
    padding: 4px 10px;
    border-radius: 10px;
    font-size: 0.78rem;
    border-color: rgba(255,255,255,0.08);
    color: #9cb2c7;
  }
  .dim-btn.active { border-color: rgba(168,196,224,0.35); color: #a8c4e0; }
  button.danger { border-color: rgba(220,50,50,0.4); color: #e07070; }
</style>

<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import { setWorkspaceBridgeActions, setWorkspaceExplanation, setWorkspacePage, setWorkspaceProvenance, setWorkspaceTrack } from "$lib/stores/workspace";
  import type { ExplainPayload, GeneratedPlaylist, PlaylistSummary, TrackEnrichmentResult } from "$lib/types";

  let playlists: PlaylistSummary[] = [];
  let name = "";

  // G-063: Generate panel state
  let generateOpen = false;
  let intent: "energy" | "chill" | "discovery" | "journey" | "smart" = "smart";
  let trackCount = 20;
  let generating = false;
  let generatedPlaylist: GeneratedPlaylist | null = null;
  let saveMessage = "";
  let generatedProof: Record<number, TrackEnrichmentResult | "loading"> = {};

  const INTENT_LABELS: Record<string, string> = {
    energy: "Energy",
    chill: "Chill",
    discovery: "Discovery",
    journey: "Journey",
    smart: "Smart Mix",
  };

  async function refresh() {
    playlists = await api.playlists();
  }

  async function create() {
    if (!name.trim()) return;
    const playlist = await api.createPlaylist(name.trim());
    name = "";
    await goto(`/playlists/${playlist.id}`);
  }

  async function generate() {
    generating = true;
    generatedPlaylist = null;
    saveMessage = "";
    try {
      generatedPlaylist = await api.generateActPlaylist(intent, trackCount);
      setWorkspaceBridgeActions(
        generatedPlaylist.tracks.slice(0, 4).map((item) => ({
          label: item.track.artist,
          href: `/artists/${encodeURIComponent(item.track.artist)}`,
          detail: item.reason,
        })),
      );
    } finally {
      generating = false;
    }
  }

  async function saveGenerated() {
    if (!generatedPlaylist) return;
    saveMessage = "Saving...";
    try {
      const detail = await api.saveGeneratedPlaylist(generatedPlaylist.name, generatedPlaylist);
      saveMessage = `Saved "${detail.name}" with ${detail.items.length} tracks.`;
      await refresh();
      generatedPlaylist = null;
    } catch (e) {
      saveMessage = e instanceof Error ? e.message : "Failed to save.";
    }
  }

  async function enqueueGenerated() {
    if (!generatedPlaylist) return;
    const trackIds = generatedPlaylist.tracks.map(t => t.track.id);
    const queue = await api.enqueueTracks(trackIds);
    shell.update(s => ({ ...s, queue }));
  }

  async function inspectGeneratedTrack(trackId: number) {
    const track = generatedPlaylist?.tracks.find((item) => item.track.id === trackId);
    if (!track) return;
    setWorkspaceTrack(track.track);
    setWorkspaceExplanation({
      trackId,
      reasons: [track.reason],
      confidence: 0.68,
      source: "generated_playlist_reason",
    } satisfies ExplainPayload, track.track);
  }

  async function toggleGeneratedProof(trackId: number) {
    if (generatedProof[trackId]) {
      const next = { ...generatedProof };
      delete next[trackId];
      generatedProof = next;
      return;
    }
    generatedProof = { ...generatedProof, [trackId]: "loading" };
    try {
      const result = await api.getTrackEnrichment(trackId);
      generatedProof = { ...generatedProof, [trackId]: result };
      const track = generatedPlaylist?.tracks.find((item) => item.track.id === trackId)?.track ?? null;
      setWorkspaceProvenance(result.entries, track);
    } catch (e) {
      const next = { ...generatedProof };
      delete next[trackId];
      generatedProof = next;
    }
  }

  onMount(() => {
    setWorkspacePage(
      "Playlists",
      "Playlist-first by default",
      "Generate acts, keep reasons durable, and move from discovery into authored journeys.",
      "bridge"
    );
    refresh();
  });
</script>

<section class="header">
  <div>
    <p class="eyebrow">Playlists</p>
    <h2>Playlist-first by default</h2>
  </div>
  <div class="create-row">
    <input bind:value={name} placeholder="New playlist name" />
    <button on:click={create}>Create</button>
    <button class="generate-btn" on:click={() => (generateOpen = !generateOpen)}>
      {generateOpen ? 'Hide Generator' : 'Generate'}
    </button>
  </div>
</section>

<!-- G-063: Generate Panel -->
{#if generateOpen}
  <div class="generate-panel">
    <p class="eyebrow">Generate Playlist</p>
    <div class="intent-row">
      {#each Object.entries(INTENT_LABELS) as [key, label]}
        <button class="intent-btn" class:active={intent === key}
          on:click={() => intent = key as typeof intent}>
          {label}
        </button>
      {/each}
    </div>
    <div class="slider-row">
      <label for="track-count">Tracks: <strong>{trackCount}</strong></label>
      <input id="track-count" type="range" min="10" max="50" step="5" bind:value={trackCount} />
    </div>
    <button class="gen-action-btn" on:click={generate} disabled={generating}>
      {generating ? 'Generating...' : 'Generate'}
    </button>

    {#if generatedPlaylist}
      <div class="preview-head">
        <strong>{generatedPlaylist.name}</strong>
        <span class="muted">{generatedPlaylist.tracks.length} tracks - {INTENT_LABELS[generatedPlaylist.intent] ?? generatedPlaylist.intent}</span>
        <button on:click={saveGenerated}>Save Playlist</button>
        <button on:click={enqueueGenerated}>Queue All</button>
      </div>
      <div class="preview-list">
        {#each generatedPlaylist.tracks as item}
          <div class="preview-row">
            <span class="preview-pos">{item.position + 1}</span>
            <div class="preview-info">
              <strong>{item.track.title}</strong>
              <small>{item.track.artist}</small>
            </div>
            <span class="reason-badge" title={item.reason}>{item.reason}</span>
            <div class="preview-actions">
              <button on:click={() => inspectGeneratedTrack(item.track.id)}>Why</button>
              <button on:click={() => toggleGeneratedProof(item.track.id)}>
                {generatedProof[item.track.id] ? "Hide Proof" : "Proof"}
              </button>
            </div>
            {#if generatedProof[item.track.id]}
              <div class="proof-inline">
                {#if generatedProof[item.track.id] === "loading"}
                  <small class="muted">Loading provenance...</small>
                {:else}
                  {@const proof = generatedProof[item.track.id] as TrackEnrichmentResult}
                  <div class="proof-inline-row">
                    <span>{proof.enrichmentState}</span>
                    {#if proof.primaryMbid}
                      <code>{proof.primaryMbid}</code>
                    {/if}
                  </div>
                  {#each proof.entries.slice(0, 2) as entry}
                    <div class="proof-inline-row">
                      <strong>{entry.provider}</strong>
                      <span>{entry.status} - {Math.round(entry.confidence * 100)}%</span>
                    </div>
                  {/each}
                {/if}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
    {#if saveMessage}
      <p class="muted">{saveMessage}</p>
    {/if}
  </div>
{/if}

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
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.03));
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 16px 32px rgba(0,0,0,0.14), inset 0 1px 0 rgba(255,255,255,0.05);
    display: grid;
    gap: 10px;
  }
  input, button {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.055);
    color: inherit;
  }
  .generate-btn { color: #a8c4e0; cursor: pointer; }

  /* G-063 Generate Panel */
  .generate-panel {
    margin-bottom: 24px;
    padding: 16px 20px;
    border-radius: 16px;
    background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.035));
    border: 1px solid rgba(255,255,255,0.1);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .intent-row { display: flex; gap: 8px; flex-wrap: wrap; }
  .intent-btn {
    padding: 6px 14px;
    border-radius: 20px;
    border: 1px solid rgba(255,255,255,0.12);
    background: transparent;
    color: #9cb2c7;
    cursor: pointer;
    font-size: 0.82rem;
  }
  .intent-btn.active { background: rgba(255,255,255,0.1); color: #d0e8f8; border-color: rgba(168,196,224,0.4); }
  .slider-row { display: flex; align-items: center; gap: 12px; }
  .slider-row input { flex: 1; padding: 0; background: transparent; border: none; }
  .gen-action-btn { align-self: flex-start; color: #7affc6; border-color: rgba(122,255,198,0.3); cursor: pointer; }
  .preview-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .preview-list { display: flex; flex-direction: column; gap: 4px; max-height: 360px; overflow-y: auto; }
  .preview-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 12px;
    background: rgba(255,255,255,0.035);
    border: 1px solid rgba(255,255,255,0.06);
    flex-wrap: wrap;
  }
  .preview-pos { font-size: 0.72rem; color: #6a8aab; min-width: 24px; text-align: right; flex-shrink: 0; }
  .preview-info { display: grid; gap: 2px; flex: 1; min-width: 0; }
  .preview-info strong { font-size: 0.88rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .preview-actions { display: flex; gap: 8px; flex-shrink: 0; }
  .preview-actions button { padding: 6px 10px; font-size: 0.75rem; }
  .reason-badge {
    font-size: 0.68rem;
    color: #9cb2c7;
    background: rgba(255,255,255,0.06);
    border-radius: 6px;
    padding: 2px 8px;
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .proof-inline {
    width: 100%;
    padding: 10px 12px 2px;
    border-top: 1px solid rgba(255,255,255,0.06);
    display: grid;
    gap: 6px;
  }
  .proof-inline code { font-size: 0.72rem; color: #a8c4e0; }
  .proof-inline-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 0.75rem; color: #9cb2c7; }
</style>

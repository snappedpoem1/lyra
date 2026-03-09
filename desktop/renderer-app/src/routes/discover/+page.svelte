<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import {
    setWorkspaceBridgeActions,
    setWorkspaceExplanation,
    setWorkspacePage,
    setWorkspaceProvenance,
    setWorkspaceTrack
  } from "$lib/stores/workspace";
  import type { AcquisitionQueueItem, DiscoverySession, ExplainPayload, PlaylistSummary, RecentPlayRecord, RecommendationResult, TrackEnrichmentResult } from "$lib/types";

  let vibePlaylists: PlaylistSummary[] = [];
  let acquisitionQueue: AcquisitionQueueItem[] = [];
  // G-064: Discovery session
  let discoverySession: DiscoverySession | null = null;
  let discoveryLoaded = false;
  let statusFilter = "all";
  let addArtist = "";
  let addTitle = "";
  let addAlbum = "";
  let addSource = "manual";
  let adding = false;

  // Taste profile (reactive from store)
  const TASTE_DIMS = ["energy","valence","tension","density","warmth","movement","space","rawness","complexity","nostalgia"];
  const DIM_COLORS: Record<string, string> = {
    energy: "#ff7a5c", valence: "#ffd166", tension: "#ef476f", density: "#8ecae6",
    warmth: "#f4a261", movement: "#06d6a0", space: "#118ab2", rawness: "#e76f51",
    complexity: "#a8c4e0", nostalgia: "#b5ead7",
  };

  $: tasteProfile = $shell.tasteProfile;
  $: tasteDimsList = TASTE_DIMS.map(d => ({
    dim: d,
    val: tasteProfile?.dimensions?.[d] ?? 0,
    color: DIM_COLORS[d] ?? "#9cb2c7",
  }));

  // Playback history
  let recentPlays: RecentPlayRecord[] = [];
  let recentLoaded = false;

  async function loadRecentPlays() {
    recentPlays = await api.listRecentPlays(20);
    recentLoaded = true;
  }

  function formatTs(ts: string): string {
    try {
      const d = new Date(ts);
      return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch { return ts; }
  }

  // Recommendations
  let recommendations: RecommendationResult[] = [];
  let recsLoading = false;
  let recsError = "";
  let recsLoaded = false;
  let expandedExplain: Record<number, ExplainPayload | "loading"> = {};
  let expandedProvenance: Record<number, TrackEnrichmentResult | "loading"> = {};
  let aiPlaylistBusy = false;
  let aiPlaylistMessage = "";

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
    // G-064: load discovery session in background
    loadDiscoverySession();
  }

  async function loadDiscoverySession() {
    try {
      discoverySession = await api.getDiscoverySession();
      discoveryLoaded = true;
      if (discoverySession.recent.length > 0) {
        setWorkspaceBridgeActions(
          discoverySession.recent.slice(0, 3).map((interaction) => ({
            label: interaction.artistName,
            href: `/artists/${encodeURIComponent(interaction.artistName)}`,
            detail: interaction.action.replace(/_/g, " "),
          })),
        );
      }
    } catch {
      discoveryLoaded = true;
    }
  }

  async function loadQueue() {
    const filter = statusFilter === "all" ? undefined : statusFilter;
    acquisitionQueue = await api.acquisitionQueue(filter);
  }

  async function loadRecommendations() {
    recsLoading = true;
    recsError = "";
    try {
      recommendations = await api.getRecommendations(25);
      recsLoaded = true;
    } catch (e) {
      recsError = String(e);
    } finally {
      recsLoading = false;
    }
  }

  async function toggleExplain(trackId: number) {
    if (expandedExplain[trackId]) {
      const next = { ...expandedExplain };
      delete next[trackId];
      expandedExplain = next;
      return;
    }
    expandedExplain = { ...expandedExplain, [trackId]: "loading" };
    try {
      const payload = await api.explainRecommendation(trackId);
      expandedExplain = { ...expandedExplain, [trackId]: payload };
      setWorkspaceExplanation(payload, recommendations.find((rec) => rec.track.id === trackId)?.track ?? null);
    } catch (e) {
      const next = { ...expandedExplain };
      delete next[trackId];
      expandedExplain = next;
    }
  }

  async function enqueueVibe(playlistId: number) {
    const updated = await api.enqueuePlaylist(playlistId);
    shell.update((s) => ({ ...s, queue: updated }));
  }

  async function enqueueRec(trackId: number) {
    const updated = await api.enqueueTracks([trackId]);
    shell.update((s) => ({ ...s, queue: updated }));
    setWorkspaceTrack(recommendations.find((rec) => rec.track.id === trackId)?.track ?? null);
  }

  async function toggleProvenance(trackId: number) {
    if (expandedProvenance[trackId]) {
      const next = { ...expandedProvenance };
      delete next[trackId];
      expandedProvenance = next;
      return;
    }
    expandedProvenance = { ...expandedProvenance, [trackId]: "loading" };
    try {
      const result = await api.getTrackEnrichment(trackId);
      expandedProvenance = { ...expandedProvenance, [trackId]: result };
      setWorkspaceProvenance(result.entries, recommendations.find((rec) => rec.track.id === trackId)?.track ?? null);
    } catch {
      const next = { ...expandedProvenance };
      delete next[trackId];
      expandedProvenance = next;
    }
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

  async function buildAiPlaylist(): Promise<void> {
    if (aiPlaylistBusy) return;
    aiPlaylistBusy = true;
    aiPlaylistMessage = "";
    try {
      if (!recsLoaded) {
        await loadRecommendations();
      }
      if (!recommendations.length) {
        aiPlaylistMessage = "No recommendations available yet.";
        return;
      }
      const now = new Date();
      const name = `AI Mix ${now.toLocaleDateString()} ${now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
      const playlist = await api.createPlaylist(name);
      const topTracks = recommendations.slice(0, 25).map((r) => r.track.id);
      for (const trackId of topTracks) {
        await api.addTrackToPlaylist(playlist.id, trackId);
      }
      aiPlaylistMessage = `Created \"${name}\" with ${topTracks.length} tracks.`;
      await load();
    } catch (e) {
      aiPlaylistMessage = e instanceof Error ? e.message : "Failed to build AI playlist.";
    } finally {
      aiPlaylistBusy = false;
    }
  }

  function scoreBar(score: number): string {
    const pct = Math.round(score * 100);
    return `${pct}%`;
  }

  onMount(() => {
    setWorkspacePage(
      "Discover",
      "Oracle discovery workspace",
      "Follow recommendations, bridge leads, taste signals, and acquisition candidates without leaving the shell.",
      "bridge"
    );
    load();
  });
</script>

<section>
  <p class="eyebrow">Discover</p>
  <h2>For You - Vibes - Acquisition</h2>
</section>

<!-- Taste profile panel -->
{#if tasteProfile && tasteProfile.totalSignals > 0}
<div class="taste-panel">
  <div class="taste-head">
    <p class="panel-head eyebrow">Your taste profile</p>
    <span class="taste-meta">{tasteProfile.totalSignals} signals - confidence {Math.round(tasteProfile.confidence * 100)}%</span>
  </div>
  <div class="taste-bars">
    {#each tasteDimsList as { dim, val, color }}
      <div class="taste-row">
        <span class="dim-label">{dim}</span>
        <div class="dim-bar-bg">
          <div class="dim-bar-fill" style="width:{Math.round(val * 100)}%; background:{color}"></div>
        </div>
        <span class="dim-val">{Math.round(val * 100)}</span>
      </div>
    {/each}
  </div>
</div>
{/if}

<!-- Recent plays panel -->
<div class="recent-panel">
  <div class="panel-head-row">
    <p class="panel-head eyebrow">Recent plays</p>
    <button class="load-btn" on:click={loadRecentPlays}>{recentLoaded ? "Refresh" : "Show history"}</button>
  </div>
  {#if recentLoaded}
    {#if !recentPlays.length}
      <p class="muted">No plays recorded yet.</p>
    {:else}
      <div class="history-rows">
        {#each recentPlays as ev}
          <div class="history-row">
            <span class="hist-ts">{formatTs(ev.ts)}</span>
            <span class="hist-completion" class:skipped={ev.skipped}
              title={ev.skipped ? "Skipped" : `${Math.round((ev.completionRate ?? 0) * 100)}% played`}>
              {ev.skipped ? 'Skip' : 'Play'}
            </span>
            <span class="hist-title">{ev.title}</span>
            <a class="hist-artist" href={`/artists/${encodeURIComponent(ev.artist)}`}>{ev.artist}</a>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<!-- Recommendations panel -->
<div class="recs-panel">
  <div class="panel-head-row">
    <p class="panel-head eyebrow">For You</p>
    <div class="rec-head-actions">
      <button class="load-btn" on:click={loadRecommendations} disabled={recsLoading}>
        {recsLoading ? "Loading..." : recsLoaded ? "Refresh" : "Load recommendations"}
      </button>
      <button class="load-btn" on:click={buildAiPlaylist} disabled={aiPlaylistBusy || recsLoading}>
        {aiPlaylistBusy ? "Building..." : "Build AI Playlist"}
      </button>
    </div>
  </div>
  {#if aiPlaylistMessage}
    <p class="muted">{aiPlaylistMessage}</p>
  {/if}

  {#if recsError}
    <p class="error">{recsError}</p>
  {:else if !recsLoaded}
    <p class="muted">Recommendations are driven by your taste profile. Click "Load recommendations" to generate them.</p>
  {:else if !recommendations.length}
    <p class="muted">No scored tracks yet. Run a library scan and enrich your library to generate recommendations.</p>
  {:else}
    <div class="recs-grid">
      {#each recommendations as rec}
        <div class="rec-card">
          <div class="rec-meta">
            <strong class="rec-title">{rec.track.title}</strong>
            <a class="rec-artist" href={`/artists/${encodeURIComponent(rec.track.artist)}`}>{rec.track.artist}</a>
            {#if rec.track.album}<span class="rec-album">{rec.track.album}</span>{/if}
            <div class="score-row">
              <div class="score-bar-bg">
                <div class="score-bar-fill" style="width:{scoreBar(rec.score)}"></div>
              </div>
              <span class="score-label">{Math.round(rec.score * 100)}%</span>
            </div>
          </div>
          <div class="rec-actions">
            <button on:click={() => enqueueRec(rec.track.id)}>+ Queue</button>
            <button class="provenance-btn" on:click={() => toggleProvenance(rec.track.id)}>
              {expandedProvenance[rec.track.id] ? "Hide Proof" : "Proof"}
            </button>
            <button class="explain-btn" on:click={() => toggleExplain(rec.track.id)}>
              {expandedExplain[rec.track.id] ? "Hide" : "Why?"}
            </button>
          </div>
          {#if expandedExplain[rec.track.id]}
            <div class="explain-panel">
              {#if expandedExplain[rec.track.id] === "loading"}
                <p class="muted">Loading...</p>
              {:else}
                {@const ep = expandedExplain[rec.track.id] as import('$lib/types').ExplainPayload}
                {#each ep.reasons as reason}
                  <p class="reason">{reason}</p>
                {/each}
                <p class="confidence-line">Confidence: {Math.round(ep.confidence * 100)}%</p>
              {/if}
            </div>
          {/if}
          {#if expandedProvenance[rec.track.id]}
            <div class="provenance-panel">
              {#if expandedProvenance[rec.track.id] === "loading"}
                <p class="muted">Loading provenance...</p>
              {:else}
                {@const proof = expandedProvenance[rec.track.id] as TrackEnrichmentResult}
                <div class="proof-head">
                  <span class="proof-state" class:proof-degraded={proof.enrichmentState === "degraded" || proof.degradedProviders.length > 0}>{proof.enrichmentState}</span>
                  {#if proof.primaryMbid}
                    <code class="proof-mbid">{proof.primaryMbid}</code>
                  {/if}
                  {#if proof.degradedProviders.length > 0}
                    <span class="proof-degraded-note">Degraded: {proof.degradedProviders.join(", ")}</span>
                  {/if}
                </div>
                {#each proof.entries.slice(0, 4) as entry}
                  <div class="proof-row" class:proof-row-dim={entry.status === "not_configured" || entry.status === "not_found"}>
                    <strong>{entry.provider}</strong>
                    <span>{entry.status} — {Math.round(entry.confidence * 100)}%</span>
                    {#if entry.note}<span class="proof-note">{entry.note}</span>{/if}
                  </div>
                {/each}
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- G-064: Recent Discovery panel -->
{#if discoveryLoaded && discoverySession && discoverySession.recent.length > 0}
<div class="discovery-panel">
  <p class="panel-head eyebrow">Recent Discovery</p>
  <div class="discovery-rows">
    {#each discoverySession.recent as interaction}
      <div class="discovery-row">
        <span class="disc-action">{interaction.action.replace(/_/g, ' ')}</span>
        <a class="disc-artist" href={`/artists/${encodeURIComponent(interaction.artistName)}`}>
          {interaction.artistName}
        </a>
        <span class="disc-ts muted">{interaction.createdAt.slice(0, 16).replace('T', ' ')}</span>
        <a class="go-btn" href={`/artists/${encodeURIComponent(interaction.artistName)}`}>Go</a>
      </div>
    {/each}
  </div>
</div>
{/if}

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
            <small><a class="hist-artist" href={`/artists/${encodeURIComponent(item.artist)}`}>{item.artist}</a>{item.album ? ` - ${item.album}` : ''}</small>
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
  .error { color: #e55; font-size: 0.85rem; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 20px; }
  .panel { display: flex; flex-direction: column; gap: 10px; }
  .panel-head { margin: 0; }
  .panel-head-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }

  /* Recent plays */
  .recent-panel { margin-bottom: 20px; padding: 14px 18px; border-radius: 18px; background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03)); border: 1px solid rgba(255,255,255,0.1); box-shadow: inset 0 1px 0 rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 8px; }
  .history-rows { display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow-y: auto; }
  .history-row { display: flex; align-items: center; gap: 12px; font-size: 0.78rem; }
  .hist-ts { color: #9cb2c7; min-width: 140px; flex-shrink: 0; }
  .hist-completion { font-size: 0.9rem; flex-shrink: 0; }
  .hist-completion.skipped { color: #9cb2c7; opacity: 0.5; }
  .hist-title { color: #d0e8f8; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hist-artist { color: #9cb2c7; font-size: 0.72rem; flex-shrink: 0; }

  /* Recommendations */
  .recs-panel { margin-bottom: 24px; display: flex; flex-direction: column; gap: 12px; }
  .load-btn { padding: 6px 14px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.07); color: inherit; cursor: pointer; font: inherit; }
  .rec-head-actions { display: flex; gap: 8px; }
  .recs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
  .rec-card {
    padding: 14px 16px;
    border-radius: 16px;
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.035));
    border: 1px solid rgba(255,255,255,0.1);
    box-shadow: 0 18px 40px rgba(0,0,0,0.16), inset 0 1px 0 rgba(255,255,255,0.06);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .rec-meta { display: grid; gap: 3px; }
  .rec-title { font-size: 0.95rem; }
  .rec-artist { color: #9cb2c7; font-size: 0.82rem; }
  .rec-album { color: #7a95a8; font-size: 0.75rem; }
  .score-row { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
  .score-bar-bg { flex: 1; height: 4px; border-radius: 2px; background: rgba(255,255,255,0.1); }
  .score-bar-fill { height: 100%; border-radius: 2px; background: linear-gradient(90deg, #34cfab, #5ad1ff); }
  .score-label { font-size: 0.68rem; color: #9cb2c7; width: 32px; text-align: right; }
  .rec-actions { display: flex; gap: 6px; }
  .explain-btn { color: #a8c4e0; }
  .provenance-btn { color: #d6f07b; }
  .explain-panel {
    padding: 10px 12px;
    border-radius: 10px;
    background: rgba(7, 15, 23, 0.5);
    border: 1px solid rgba(255,255,255,0.08);
    font-size: 0.78rem;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .provenance-panel {
    padding: 10px 12px;
    border-radius: 10px;
    background: rgba(6, 18, 16, 0.45);
    border: 1px solid rgba(122,255,198,0.12);
    font-size: 0.78rem;
    display: grid;
    gap: 6px;
  }
  .proof-head, .proof-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .proof-state { text-transform: uppercase; letter-spacing: 0.12em; color: #7affc6; font-size: 0.68rem; background: rgba(122,255,198,0.1); padding: 2px 7px; border-radius: 6px; }
  .proof-state.proof-degraded { color: #ffc850; background: rgba(255,200,80,0.12); }
  .proof-mbid { font-size: 0.72rem; color: #9cb2c7; background: rgba(255,255,255,0.05); padding: 1px 5px; border-radius: 5px; }
  .proof-degraded-note { font-size: 0.72rem; color: #ffc850; }
  .proof-note { font-size: 0.7rem; color: #7a95a8; font-style: italic; }
  .proof-row-dim { opacity: 0.4; }
  .proof-head code { font-size: 0.72rem; color: #a8c4e0; }
  .proof-row span { color: #9cb2c7; }
  .reason { color: #c0d8ea; line-height: 1.4; }
  .confidence-line { color: #9cb2c7; margin-top: 4px; }

  /* Taste profile */
  .taste-panel { margin-bottom: 20px; padding: 16px 18px; border-radius: 18px; background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.035)); border: 1px solid rgba(255,255,255,0.1); box-shadow: inset 0 1px 0 rgba(255,255,255,0.06); }
  .taste-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
  .taste-meta { font-size: 0.72rem; color: #9cb2c7; }
  .taste-bars { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; }
  .taste-row { display: flex; align-items: center; gap: 8px; }
  .dim-label { font-size: 0.72rem; color: #9cb2c7; width: 72px; text-align: right; text-transform: capitalize; flex-shrink: 0; }
  .dim-bar-bg { flex: 1; height: 6px; border-radius: 3px; background: rgba(255,255,255,0.08); overflow: hidden; }
  .dim-bar-fill { height: 100%; border-radius: 3px; transition: width 0.4s ease; }
  .dim-val { font-size: 0.68rem; color: #9cb2c7; width: 28px; text-align: right; flex-shrink: 0; }

  /* Existing styles */
  .vibe-row, .acq-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border-radius: 14px;
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.035));
    border: 1px solid rgba(255,255,255,0.08);
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

  /* G-064: Recent Discovery panel */
  .discovery-panel {
    margin-bottom: 20px;
    padding: 14px 18px;
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.03));
    border: 1px solid rgba(255,255,255,0.08);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .discovery-rows { display: flex; flex-direction: column; gap: 4px; }
  .discovery-row { display: flex; align-items: center; gap: 12px; font-size: 0.82rem; }
  .disc-action { color: #6a8aab; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em; min-width: 90px; flex-shrink: 0; }
  .disc-artist { color: #a8c4e0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .disc-ts { font-size: 0.68rem; min-width: 130px; text-align: right; flex-shrink: 0; }
  .go-btn {
    padding: 3px 10px;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: #a8c4e0;
    font-size: 0.72rem;
    text-decoration: none;
    flex-shrink: 0;
  }
</style>


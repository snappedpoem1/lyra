<script lang="ts">
  import { goto } from "$app/navigation";
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import {
    setComposerText,
    setWorkspaceBridgeActions,
    setWorkspaceExplanation,
    setWorkspacePage,
    setWorkspaceProvenance,
    setWorkspaceTrack
  } from "$lib/stores/workspace";
  import type {
    AcquisitionLead,
    AcquisitionEventPayload,
    AcquisitionLeadOutcome,
    AcquisitionQueueItem,
    BridgeArtist,
    DeepCutTrack,
    DiscoverySession,
    ExplainPayload,
    GraphStats,
    PlaylistSummary,
    RecentPlayRecord,
    RecommendationResult,
    ScoutTarget,
    SpotifyGapSummary,
    TrackEnrichmentResult
  } from "$lib/types";

  let vibePlaylists: PlaylistSummary[] = [];
  let acquisitionQueue: AcquisitionQueueItem[] = [];
  let acquisitionQueueAll: AcquisitionQueueItem[] = [];
  // G-064: Discovery session + graph
  let discoverySession: DiscoverySession | null = null;
  let discoveryLoaded = false;
  let graphStats: GraphStats | null = null;
  let graphBuilding = false;
  let graphMessage = "";

  // G-064: Genre hunt
  const GENRE_PAIRS: [string, string][] = [
    ["rock", "electronic"], ["rock", "jazz"], ["rock", "folk"],
    ["electronic", "jazz"], ["electronic", "classical"], ["electronic", "hip hop"],
    ["hip hop", "jazz"], ["hip hop", "r&b"], ["hip hop", "electronic"],
    ["metal", "jazz"], ["metal", "classical"], ["folk", "electronic"],
    ["ambient", "classical"], ["punk", "jazz"], ["indie", "folk"],
  ];
  let huntGenreA = "rock";
  let huntGenreB = "electronic";
  let huntResults: ScoutTarget[] = [];
  let huntBridgeArtists: BridgeArtist[] = [];
  let huntLoading = false;
  let huntMessage = "";
  let huntOpen = false;
  let deepcutResults: DeepCutTrack[] = [];
  let deepcutLoading = false;
  let deepcutOpen = false;

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

  // Taste seeding from Spotify history
  let seedPending = false;
  let seedResult: string | null = null;

  async function reseedFromSpotify(force = false) {
    seedPending = true;
    seedResult = null;
    try {
      const matched = await api.seedTasteFromSpotifyHistory(force);
      if (matched === 0) {
        seedResult = force
          ? "No scored local tracks matched Spotify history."
          : "Profile already confident — use Force to override.";
      } else {
        seedResult = `Seeded from ${matched} matched tracks.`;
        // Reload shell state so the taste bars update.
        const updated = await api.tasteProfile();
        shell.update(s => ({ ...s, tasteProfile: updated }));
      }
    } catch (e) {
      seedResult = "Seed failed.";
    } finally {
      seedPending = false;
    }
  }

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
  let recommendationLeads: AcquisitionLead[] = [];
  let recsLoading = false;
  let recsError = "";
  let recsLoaded = false;
  let leadsQueueBusy = false;
  let leadsQueueMessage = "";
  let leadOutcomeByKey: Record<string, AcquisitionLeadOutcome> = {};
  let leadQueueItemByKey: Record<string, AcquisitionQueueItem> = {};
  let expandedExplain: Record<number, ExplainPayload | "loading"> = {};
  let expandedProvenance: Record<number, TrackEnrichmentResult | "loading"> = {};
  let aiPlaylistBusy = false;
  let aiPlaylistMessage = "";
  let spotifyGapSummary: SpotifyGapSummary | null = null;
  let spotifyActionMessage = "";
  let spotifyActionBusy = false;

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
    await loadSpotifyGapSummary();
    // G-064: load discovery session + graph stats in background
    loadDiscoverySession();
    loadGraphStats();
  }

  async function loadSpotifyGapSummary(): Promise<void> {
    spotifyGapSummary = await api.getSpotifyGapSummary(6).catch(() => null);
  }

  async function loadGraphStats() {
    try {
      graphStats = await api.getGraphStats();
    } catch { /* graph table may be empty */ }
  }

  async function buildGraph() {
    graphBuilding = true;
    graphMessage = "";
    try {
      const added = await api.buildArtistGraph();
      graphMessage = `Graph built: ${added} new artist pairs.`;
      await loadGraphStats();
    } catch (e) {
      graphMessage = e instanceof Error ? e.message : "Graph build failed.";
    } finally {
      graphBuilding = false;
    }
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
    acquisitionQueueAll = await api.acquisitionQueue(undefined);
    leadQueueItemByKey = indexLeadQueueItems(acquisitionQueueAll);
    acquisitionQueue = statusFilter === "all"
      ? acquisitionQueueAll
      : acquisitionQueueAll.filter((item) => item.status === statusFilter);
  }

  async function loadRecommendations() {
    recsLoading = true;
    recsError = "";
    leadsQueueMessage = "";
    leadOutcomeByKey = {};
    try {
      const bundle = await api.getRecommendationBundle(25);
      recommendations = bundle.recommendations;
      recommendationLeads = bundle.acquisitionLeads;
      recsLoaded = true;
      const topRecommendation = recommendations[0];
      setWorkspaceBridgeActions(buildDiscoverActions(topRecommendation?.track.artist ?? null));
    } catch (e) {
      recsError = String(e);
    } finally {
      recsLoading = false;
    }
  }

  function openLyraPrompt(nextPrompt: string): Promise<void> {
    const trimmed = nextPrompt.trim();
    setComposerText(trimmed);
    return goto(`/playlists?compose=1&prompt=${encodeURIComponent(trimmed)}`);
  }

  function buildDiscoverActions(anchorArtist: string | null): Array<{ label: string; href?: string; detail?: string; emphasis?: "default" | "accent" }> {
    const topArtist = spotifyGapSummary?.topArtists[0]?.artist;
    const actions = [
      {
        label: "Three exits",
        href: "/playlists?compose=1&prompt=" + encodeURIComponent("give me three exits from this scene, one safe, one interesting, one dangerous"),
        detail: "Safe, interesting, and dangerous scene departures.",
        emphasis: "accent" as const,
      },
      topArtist
        ? {
            label: `Recover ${topArtist}`,
            href: "/playlists?compose=1&prompt=" + encodeURIComponent(`rebuild the world i used to live in around ${topArtist}, but route it through what my local library is still missing`),
            detail: "Use Spotify memory as route pressure instead of only acquisition data."
          }
        : null,
      anchorArtist
        ? {
            label: `Bridge from ${anchorArtist}`,
            href: `/artists/${encodeURIComponent(anchorArtist)}`,
            detail: "Open the artist route and use adjacency instead of flat similarity."
          }
        : null,
    ].filter(Boolean);
    return actions as Array<{ label: string; href?: string; detail?: string; emphasis?: "default" | "accent" }>;
  }

  function recommendationLyraTake(rec: RecommendationResult, payload?: ExplainPayload | "loading"): string {
    if (!payload || payload === "loading") {
      if (spotifyGapSummary?.topArtists.some((artist) => artist.artist.toLowerCase() === rec.track.artist.toLowerCase())) {
        return "This looks close to a missing world from your Spotify history, not just a generic nearest neighbor.";
      }
      return rec.score > 0.82
        ? "Lyra sees this as a close fit to your current taste pressure."
        : "Lyra sees this as a route-worthy detour rather than a strict home-base match.";
    }
    return payload.reasons[0] ?? "Lyra found a plausible route into this track.";
  }

  async function queueSpotifyCandidate(artist: string, title: string, album?: string | null): Promise<void> {
    spotifyActionBusy = true;
    spotifyActionMessage = "";
    try {
      await api.addToAcquisitionQueue(artist, title, album ?? undefined, "spotify_gap_discover");
      spotifyActionMessage = `Queued ${artist} - ${title} into acquisition from Discover.`;
      await loadQueue();
      await loadSpotifyGapSummary();
    } finally {
      spotifyActionBusy = false;
    }
  }

  async function recoverMissingWorld(entries: SpotifyGapSummary["missingCandidates"]): Promise<void> {
    if (!entries.length) return;
    spotifyActionBusy = true;
    spotifyActionMessage = "";
    try {
      const payload = entries.slice(0, 6).map((entry) => [entry.artist, entry.title, entry.album ?? null] as [string, string, string | null]);
      const added = await api.bulkAddToAcquisitionQueue(payload, "spotify_missing_world");
      spotifyActionMessage = added.length
        ? `Queued ${added.length} missing-world tracks from Spotify memory.`
        : "Those missing-world tracks are already owned or queued.";
      await loadQueue();
      await loadSpotifyGapSummary();
    } finally {
      spotifyActionBusy = false;
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

  async function enqueueRecommendationLead(lead: AcquisitionLead): Promise<void> {
    leadsQueueBusy = true;
    leadsQueueMessage = "";
    try {
      const report = await api.enqueueRecommendationLeads([lead]);
      applyLeadOutcomeReport(report.outcomes);
      leadsQueueMessage = formatLeadHandoffSummary(report);
      await loadQueue();
    } catch (e) {
      leadsQueueMessage = e instanceof Error ? e.message : "Failed to queue lead.";
    } finally {
      leadsQueueBusy = false;
    }
  }

  async function enqueueAllRecommendationLeads(): Promise<void> {
    if (!recommendationLeads.length) return;
    leadsQueueBusy = true;
    leadsQueueMessage = "";
    try {
      const report = await api.enqueueRecommendationLeads(recommendationLeads);
      applyLeadOutcomeReport(report.outcomes);
      leadsQueueMessage = formatLeadHandoffSummary(report);
      await loadQueue();
    } catch (e) {
      leadsQueueMessage = e instanceof Error ? e.message : "Failed to queue recommendation leads.";
    } finally {
      leadsQueueBusy = false;
    }
  }

  function leadKey(lead: Pick<AcquisitionLead, "artist" | "title" | "provider">): string {
    return `${lead.artist.toLowerCase()}::${lead.title.toLowerCase()}`;
  }

  function applyLeadOutcomeReport(outcomes: AcquisitionLeadOutcome[]): void {
    const next = { ...leadOutcomeByKey };
    for (const outcome of outcomes) {
      next[leadKey(outcome)] = outcome;
    }
    leadOutcomeByKey = next;
  }

  function indexLeadQueueItems(queue: AcquisitionQueueItem[]): Record<string, AcquisitionQueueItem> {
    const byKey: Record<string, AcquisitionQueueItem> = {};
    for (const item of queue) {
      const key = `${item.artist.toLowerCase()}::${item.title.toLowerCase()}`;
      const existing = byKey[key];
      if (!existing || item.id > existing.id) {
        byKey[key] = item;
      }
    }
    return byKey;
  }

  function isLeadActive(status?: string): boolean {
    if (!status) return false;
    return ["queued", "validating", "acquiring", "staging", "scanning", "organizing", "indexing"].includes(status);
  }

  function leadLiveClass(status: string): string {
    return `lead-live-${status}`;
  }

  function leadLiveLabel(status: string): string {
    if (isLeadActive(status)) {
      return `In ${status}`;
    }
    if (status === "completed") return "Completed";
    if (status === "failed") return "Failed";
    if (status === "cancelled") return "Cancelled";
    if (status === "skipped") return "Skipped";
    return status;
  }

  function formatLeadHandoffSummary(report: {
    queuedCount: number;
    duplicateCount: number;
    errorCount: number;
  }): string {
    return `Lead handoff: ${report.queuedCount} queued, ${report.duplicateCount} already active, ${report.errorCount} failed.`;
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

  async function runGenreHunt(): Promise<void> {
    huntLoading = true;
    huntMessage = "";
    huntResults = [];
    huntBridgeArtists = [];
    try {
      const [targets, bridges] = await Promise.all([
        api.crossGenreHunt(huntGenreA, huntGenreB, 12),
        api.findLocalBridgeArtists(huntGenreA, huntGenreB),
      ]);
      huntResults = targets;
      huntBridgeArtists = bridges;
      if (!huntResults.length && !huntBridgeArtists.length) {
        huntMessage = "No local tracks found spanning these genres. Try a different pair.";
      }
    } catch (e) {
      huntMessage = e instanceof Error ? e.message : "Genre hunt failed.";
    } finally {
      huntLoading = false;
    }
  }

  async function runDeepcutHunt(): Promise<void> {
    deepcutLoading = true;
    try {
      deepcutResults = await api.deepcutHunt(null, null, 0.35, 16);
    } catch {
      deepcutResults = [];
    } finally {
      deepcutLoading = false;
    }
  }

  async function queueScoutTarget(target: ScoutTarget): Promise<void> {
    await api.addToAcquisitionQueue(target.artist, target.title, target.album || undefined, "genre_hunt");
    huntMessage = `Queued ${target.artist} — ${target.title} for acquisition.`;
    await loadQueue();
  }

  function scoreBar(score: number): string {
    const pct = Math.round(score * 100);
    return `${pct}%`;
  }

  onMount(() => {
    let unlistenAcquisition: (() => void) | null = null;
    api
      .on<AcquisitionEventPayload>("lyra://acquisition-updated", (payload) => {
        acquisitionQueueAll = payload.queue;
        leadQueueItemByKey = indexLeadQueueItems(payload.queue);
        acquisitionQueue = statusFilter === "all"
          ? payload.queue
          : payload.queue.filter((item) => item.status === statusFilter);
      })
      .then((unlisten) => {
        unlistenAcquisition = unlisten;
      })
      .catch(() => {
        unlistenAcquisition = null;
      });

    setWorkspacePage(
      "Discover",
      "Oracle discovery workspace",
      "Follow recommendations, bridge leads, taste signals, and acquisition candidates without leaving the shell.",
      "bridge"
    );
    setWorkspaceBridgeActions(buildDiscoverActions(null));
    load();

    return () => {
      if (unlistenAcquisition) {
        unlistenAcquisition();
      }
    };
  });
</script>

<section>
  <p class="eyebrow">Discover</p>
  <h2>For You - Vibes - Acquisition</h2>
</section>

{#if spotifyGapSummary?.available}
  <div class="spotify-gap-panel">
    <div class="panel-head-row">
      <div>
        <p class="panel-head eyebrow">Missing worlds</p>
        <strong class="spotify-summary">{spotifyGapSummary.summaryLines[0]}</strong>
        {#if spotifyGapSummary.summaryLines[1]}
          <p class="muted">{spotifyGapSummary.summaryLines[1]}</p>
        {/if}
      </div>
      <div class="route-chip-row">
        <button class="route-chip accent" on:click={() => openLyraPrompt("give me three exits from this scene, one safe, one interesting, one dangerous")}>Three exits</button>
        <button class="route-chip" on:click={() => openLyraPrompt("same pulse, different world")}>Same pulse</button>
        <button class="route-chip" on:click={() => openLyraPrompt("take me somewhere adjacent but don’t give me the canon")}>Less canon</button>
      </div>
    </div>
    <div class="spotify-stats-row">
      <span><strong>{spotifyGapSummary.historyCount}</strong> history plays</span>
      <span><strong>{spotifyGapSummary.ownedOverlapCount}</strong> already owned</span>
      <span><strong>{spotifyGapSummary.recoverableMissingCount}</strong> recoverable gaps</span>
    </div>
    {#if spotifyGapSummary.topArtists.length}
      <div class="spotify-worlds">
        {#each spotifyGapSummary.topArtists.slice(0, 3) as artist}
          <button class="spotify-world-card" on:click={() => openLyraPrompt(`rebuild the world i used to live in around ${artist.artist}, but route it through what my local library is still missing`)}>
            <strong>{artist.artist}</strong>
            <span>{artist.playCount} plays</span>
            <small>{artist.missingTrackCount} still missing locally</small>
          </button>
        {/each}
      </div>
    {/if}
    {#if spotifyGapSummary.missingCandidates.length}
      <div class="spotify-candidate-row">
        <div class="candidate-copy">
          <strong>Fast missing-world recovery</strong>
          <small>Queue the strongest missing hinge tracks directly from Discover.</small>
        </div>
        <button on:click={() => recoverMissingWorld(spotifyGapSummary?.missingCandidates ?? [])} disabled={spotifyActionBusy}>
          {spotifyActionBusy ? "Queueing..." : "Queue top missing tracks"}
        </button>
      </div>
      {#if spotifyActionMessage}
        <p class="muted">{spotifyActionMessage}</p>
      {/if}
    {/if}
  </div>
{/if}

<!-- G-064: Genre Hunt panel -->
<div class="hunt-panel">
  <div class="panel-head-row">
    <div>
      <p class="panel-head eyebrow">Genre Hunt</p>
      <small class="muted">Find local tracks spanning two genre worlds</small>
    </div>
    <button class="load-btn" on:click={() => { huntOpen = !huntOpen; }}>
      {huntOpen ? 'Hide' : 'Open hunt'}
    </button>
  </div>
  {#if huntOpen}
    <div class="hunt-controls">
      <select bind:value={huntGenreA} class="genre-select">
        {#each ["rock","electronic","hip hop","jazz","metal","folk","ambient","classical","punk","indie","pop","r&b","country","blues","reggae"] as g}
          <option value={g}>{g}</option>
        {/each}
      </select>
      <span class="hunt-arrow">→</span>
      <select bind:value={huntGenreB} class="genre-select">
        {#each ["electronic","jazz","folk","classical","hip hop","r&b","ambient","drone","noise","bluegrass","world","soul","dub"] as g}
          <option value={g}>{g}</option>
        {/each}
      </select>
      <button class="load-btn" disabled={huntLoading} on:click={runGenreHunt}>
        {huntLoading ? 'Hunting...' : 'Hunt'}
      </button>
      <div class="preset-chips">
        {#each GENRE_PAIRS.slice(0, 6) as [a, b]}
          <button class="route-chip" on:click={() => { huntGenreA = a; huntGenreB = b; runGenreHunt(); }}>
            {a} → {b}
          </button>
        {/each}
      </div>
    </div>
    {#if huntMessage}
      <p class="muted">{huntMessage}</p>
    {/if}
    {#if huntBridgeArtists.length}
      <div class="bridge-artist-row">
        <p class="eyebrow" style="margin:8px 0 4px">Bridge artists in library</p>
        {#each huntBridgeArtists as ba}
          <a class="bridge-artist-chip" href={`/artists/${encodeURIComponent(ba.name)}`}>
            {ba.name} <small>({ba.trackCount} tracks)</small>
          </a>
        {/each}
      </div>
    {/if}
    {#if huntResults.length}
      <div class="hunt-results">
        {#each huntResults as target}
          <div class="hunt-track">
            <div class="hunt-track-info">
              <span class="hunt-title">{target.title}</span>
              <a class="hunt-artist" href={`/artists/${encodeURIComponent(target.artist)}`}>{target.artist}</a>
              <small class="muted">{target.album}{target.year ? ` · ${target.year}` : ''} · {target.genre}</small>
              {#if target.tags.length}
                <small class="muted">{target.tags.slice(0, 3).join(', ')}</small>
              {/if}
            </div>
            <div class="hunt-track-actions">
              <button class="sim-btn" on:click={() => openLyraPrompt(`bridge from ${huntGenreA} into ${huntGenreB} starting from ${target.artist}`)}>Ask Lyra</button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<!-- G-063: Deep Cuts panel -->
<div class="hunt-panel">
  <div class="panel-head-row">
    <div>
      <p class="panel-head eyebrow">Deep Cuts</p>
      <small class="muted">High acclaim, low popularity — your underrated library</small>
    </div>
    <button class="load-btn" on:click={() => { deepcutOpen = !deepcutOpen; if (deepcutOpen && !deepcutResults.length && !deepcutLoading) runDeepcutHunt(); }}>
      {deepcutOpen ? 'Hide' : 'Surface cuts'}
    </button>
  </div>
  {#if deepcutOpen}
    {#if deepcutLoading}
      <p class="muted">Surfacing cuts...</p>
    {:else if deepcutResults.length}
      <div class="hunt-results">
        {#each deepcutResults.slice(0, 12) as cut}
          <div class="hunt-track">
            <div class="hunt-track-info">
              <span class="hunt-title">{cut.title}</span>
              <a class="hunt-artist" href={`/artists/${encodeURIComponent(cut.artist)}`}>{cut.artist}</a>
              <small class="muted">{cut.album} · {cut.genre}</small>
              <small class="deep-cut-rank">obscurity {Math.round(cut.obscurityScore * 100)} · rank {Math.round(cut.deepCutRank * 100)}</small>
            </div>
            <div class="hunt-track-actions">
              <button class="sim-btn" on:click={() => openLyraPrompt(`give me more like ${cut.artist} — ${cut.title}, the underrated side`)}>Ask Lyra</button>
            </div>
          </div>
        {/each}
      </div>
    {:else}
      <p class="muted">No deep cuts found. Enrich your library to score obscurity.</p>
    {/if}
  {/if}
</div>

<!-- Taste profile panel -->
{#if tasteProfile && tasteProfile.totalSignals > 0}
<div class="taste-panel">
  <div class="taste-head">
    <p class="panel-head eyebrow">Your taste profile</p>
    <span class="taste-meta">{tasteProfile.totalSignals} signals · confidence {Math.round(tasteProfile.confidence * 100)}%</span>
    <div class="taste-seed-row">
      <button class="seed-btn" disabled={seedPending} on:click={() => reseedFromSpotify(false)}>
        {seedPending ? 'Seeding…' : 'Seed from Spotify history'}
      </button>
      <button class="seed-btn seed-force" disabled={seedPending} on:click={() => reseedFromSpotify(true)}
        title="Override existing profile">Force reseed</button>
      {#if seedResult}<span class="seed-result muted">{seedResult}</span>{/if}
    </div>
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

<!-- Empty-profile seed prompt -->
{#if !tasteProfile || tasteProfile.totalSignals === 0}
<div class="taste-cold-prompt">
  <p class="eyebrow">Taste profile</p>
  <p class="muted">No taste signals yet. Seed your profile from your Spotify history to make Lyra routes personal immediately.</p>
  <button class="seed-btn" disabled={seedPending} on:click={() => reseedFromSpotify(false)}>
    {seedPending ? 'Seeding…' : 'Seed from Spotify history'}
  </button>
  {#if seedResult}<span class="seed-result muted">{seedResult}</span>{/if}
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
    {#if recommendationLeads.length}
      <div class="lead-panel">
        <div class="panel-head-row">
          <p class="panel-head eyebrow">Acquisition leads</p>
          <button class="load-btn" on:click={enqueueAllRecommendationLeads} disabled={leadsQueueBusy}>
            {leadsQueueBusy ? "Queueing..." : "Queue all leads"}
          </button>
        </div>
        {#if leadsQueueMessage}
          <p class="muted">{leadsQueueMessage}</p>
        {/if}
        <div class="lead-grid">
          {#each recommendationLeads as lead}
            {@const outcome = leadOutcomeByKey[leadKey(lead)]}
            {@const liveQueueItem = leadQueueItemByKey[leadKey(lead)]}
            <div class="lead-card">
              <div class="lead-title-row">
                <strong>{lead.title}</strong>
                <span class="provider-badge">{lead.provider}</span>
              </div>
              <a class="rec-artist" href={`/artists/${encodeURIComponent(lead.artist)}`}>{lead.artist}</a>
              <p class="muted">{lead.reason}</p>
              {#if liveQueueItem}
                <p class={`lead-live ${leadLiveClass(liveQueueItem.status)}`}>
                  {leadLiveLabel(liveQueueItem.status)}
                  <span> · #{liveQueueItem.id}</span>
                </p>
              {/if}
              {#if outcome}
                <p class="lead-outcome lead-outcome-{outcome.status}">
                  {outcome.status === "queued" ? "Queued" : outcome.status === "duplicate_active" ? "Already active" : "Queue failed"}
                  {#if outcome.queueItemId}
                    <span> · #{outcome.queueItemId}</span>
                  {/if}
                </p>
                {#if outcome.detail}
                  <p class="lead-outcome-detail">{outcome.detail}</p>
                {/if}
              {/if}
              <div class="score-row">
                <div class="score-bar-bg">
                  <div class="score-bar-fill" style={`width:${Math.round(lead.score * 100)}%`}></div>
                </div>
                <span class="score-label">{Math.round(lead.score * 100)}%</span>
              </div>
              <button on:click={() => enqueueRecommendationLead(lead)} disabled={leadsQueueBusy || isLeadActive(liveQueueItem?.status) || liveQueueItem?.status === "completed" || outcome?.status === "duplicate_active"}>
                {#if isLeadActive(liveQueueItem?.status)}
                  In {liveQueueItem?.status}
                {:else if liveQueueItem?.status === "completed"}
                  Completed
                {:else if outcome?.status === "duplicate_active"}
                  Already active
                {:else}
                  Queue lead
                {/if}
              </button>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <div class="discover-route-bar">
      <button class="route-chip accent" on:click={() => openLyraPrompt("give me three exits from this scene, one safe, one interesting, one dangerous")}>Safe / interesting / dangerous</button>
      <button class="route-chip" on:click={() => openLyraPrompt("stay in the ache, lose the gloss")}>Lose the gloss</button>
      <button class="route-chip" on:click={() => openLyraPrompt("what’s the rewarding risk here")}>Rewarding risk</button>
      <button class="route-chip" on:click={() => openLyraPrompt("less obvious, still aching, keep the pulse")}>Keep the pulse</button>
    </div>
    <div class="recs-grid">
      {#each recommendations as rec}
        <div class="rec-card">
          <div class="rec-meta">
            <div class="rec-title-row">
              <strong class="rec-title">{rec.track.title}</strong>
              <span class="provider-badge provider-{rec.provider.replace('/', '-')}">{rec.provider}</span>
            </div>
            <a class="rec-artist" href={`/artists/${encodeURIComponent(rec.track.artist)}`}>{rec.track.artist}</a>
            {#if rec.track.album}<span class="rec-album">{rec.track.album}</span>{/if}
            <div class="score-row">
              <div class="score-bar-bg">
                <div class="score-bar-fill" style="width:{scoreBar(rec.score)}"></div>
              </div>
              <span class="score-label">{Math.round(rec.score * 100)}%</span>
            </div>
            <p class="lyra-take">{rec.whyThisTrack || recommendationLyraTake(rec, expandedExplain[rec.track.id])}</p>
            {#if rec.evidence?.length > 0}
              <div class="inline-evidence">
                {#each rec.evidence.slice(0, 2) as ev}
                  <span class="ev-chip ev-{ev.typeLabel}">{ev.text}</span>
                {/each}
              </div>
            {/if}
          </div>
          <div class="rec-actions">
            <button on:click={() => enqueueRec(rec.track.id)}>+ Queue</button>
            <button on:click={() => openLyraPrompt(`bridge from ${rec.track.artist} into something adjacent but less obvious`)}>
              Route
            </button>
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
                {#if ep.whyThisTrack}
                  <p class="explain-why">{ep.whyThisTrack}</p>
                {/if}
                {#if ep.evidenceItems?.length > 0}
                  <div class="evidence-list">
                    {#each ep.evidenceItems as ev}
                      <div class="evidence-row">
                        <span class="ev-label ev-{ev.typeLabel}">{ev.typeLabel}</span>
                        <span class="ev-source">{ev.source}</span>
                        <span class="ev-text">{ev.text}</span>
                      </div>
                    {/each}
                  </div>
                {/if}
                {#if ep.inferredByLyra?.length > 0}
                  <div class="inferred-section">
                    <span class="inferred-label">Inferred by Lyra</span>
                    {#each ep.inferredByLyra as line}
                      <p class="inferred-line">{line}</p>
                    {/each}
                  </div>
                {/if}
                {#if !ep.whyThisTrack}
                  {#each ep.reasons as reason}
                    <p class="reason">{reason}</p>
                  {/each}
                {/if}
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

<!-- G-064: Artist graph panel -->
<div class="graph-panel">
  <div class="panel-head-row">
    <p class="panel-head eyebrow">Artist Graph</p>
    <button class="load-btn" on:click={buildGraph} disabled={graphBuilding}>
      {graphBuilding ? "Building..." : "Build Graph"}
    </button>
  </div>
  {#if graphStats}
    <div class="graph-stats">
      <span>{graphStats.totalArtists} artists</span>
      <span class="muted">·</span>
      <span>{graphStats.totalConnections} edges</span>
      {#if graphStats.topConnected.length > 0}
        <span class="muted">· Top: {graphStats.topConnected.map(n => n.artist).join(", ")}</span>
      {/if}
    </div>
  {:else}
    <p class="muted">No graph data yet. Click "Build Graph" to compute dimension-affinity edges from your library.</p>
  {/if}
  {#if graphMessage}
    <p class="muted" style="margin-top:6px">{graphMessage}</p>
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
          <button class="go-btn" on:click={() => openLyraPrompt(`bridge from ${interaction.artistName} into a rewarding risk`)}>
            Route
          </button>
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
  /* G-064: Genre Hunt + Deep Cuts */
  .hunt-panel { border-radius: 14px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 14px 16px; display: grid; gap: 10px; margin-bottom: 14px; }
  .hunt-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
  .genre-select { background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.14); border-radius: 8px; color: #d0e8f8; padding: 6px 10px; font: inherit; cursor: pointer; }
  .hunt-arrow { color: #8cd94a; font-weight: bold; padding: 0 2px; }
  .preset-chips { display: flex; flex-wrap: wrap; gap: 6px; width: 100%; margin-top: 4px; }
  .bridge-artist-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .bridge-artist-chip { padding: 4px 10px; border-radius: 999px; background: rgba(140,217,74,0.1); border: 1px solid rgba(140,217,74,0.25); color: #8cd94a; font-size: 0.8rem; text-decoration: none; }
  .hunt-results { display: grid; gap: 6px; margin-top: 4px; }
  .hunt-track { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.07); }
  .hunt-track:last-child { border-bottom: none; }
  .hunt-track-info { display: grid; gap: 2px; flex: 1; min-width: 0; }
  .hunt-title { font-size: 0.9rem; color: #d0e8f8; }
  .hunt-artist { color: #a8c4e0; text-decoration: underline; font-size: 0.8rem; }
  .hunt-track-actions { flex-shrink: 0; }
  .deep-cut-rank { color: #8cd94a; font-size: 0.72rem; }
  .sim-btn { color: #7affc6; border: 1px solid rgba(122,255,198,0.3); border-radius: 8px; background: none; padding: 4px 10px; font: inherit; cursor: pointer; font-size: 0.78rem; }

  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; color: #9cb2c7; font-size: 0.72rem; }
  .muted { color: #9cb2c7; }
  .error { color: #e55; font-size: 0.85rem; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 20px; }
  .panel { display: flex; flex-direction: column; gap: 10px; }
  .panel-head { margin: 0; }
  .panel-head-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .route-chip-row, .discover-route-bar { display: flex; flex-wrap: wrap; gap: 8px; }
  .route-chip {
    padding: 7px 12px;
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: #cfe5f3;
    font: inherit;
    cursor: pointer;
  }
  .route-chip.accent { background: rgba(122,255,198,0.12); border-color: rgba(122,255,198,0.18); color: #d6f8ea; }
  .discover-route-bar { margin-bottom: 12px; }

  .spotify-gap-panel {
    margin: 0 0 20px;
    padding: 16px 18px;
    border-radius: 18px;
    background: linear-gradient(135deg, rgba(24, 35, 24, 0.75), rgba(21, 26, 37, 0.88));
    border: 1px solid rgba(146, 208, 170, 0.16);
    display: grid;
    gap: 12px;
  }
  .spotify-summary { display: block; margin-top: 4px; font-size: 1rem; color: #f0f7fb; }
  .spotify-stats-row { display: flex; flex-wrap: wrap; gap: 14px; color: #9cb2c7; font-size: 0.82rem; }
  .spotify-worlds { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
  .spotify-world-card {
    display: grid;
    gap: 4px;
    padding: 12px 14px;
    border-radius: 14px;
    text-align: left;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
  }
  .spotify-world-card small, .spotify-world-card span { color: #9cb2c7; }
  .spotify-candidate-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .candidate-copy { display: grid; gap: 2px; }
  .candidate-copy small { color: #9cb2c7; }

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
  .lead-panel {
    padding: 12px 14px;
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.1);
    background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.03));
    display: grid;
    gap: 10px;
  }
  .lead-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 8px; }
  .lead-card {
    padding: 10px 12px;
    border-radius: 12px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    display: grid;
    gap: 6px;
  }
  .lead-title-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .lead-outcome {
    margin: 0;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .lead-live {
    margin: 0;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: #9cb2c7;
  }
  .lead-live-queued,
  .lead-live-validating,
  .lead-live-acquiring,
  .lead-live-staging,
  .lead-live-scanning,
  .lead-live-organizing,
  .lead-live-indexing {
    color: #7affc6;
  }
  .lead-live-completed { color: #a8f5cf; }
  .lead-live-failed,
  .lead-live-cancelled { color: #ff9a9a; }
  .lead-live-skipped { color: #9cb2c7; }
  .lead-outcome-queued { color: #7affc6; }
  .lead-outcome-duplicate_active { color: #ffd166; }
  .lead-outcome-error { color: #ff9a9a; }
  .lead-outcome-detail {
    margin: -2px 0 0;
    font-size: 0.7rem;
    color: #9cb2c7;
  }
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
  .rec-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 6px; }
  .rec-title { font-size: 0.95rem; }
  .rec-artist { color: #9cb2c7; font-size: 0.82rem; }
  .rec-album { color: #7a95a8; font-size: 0.75rem; }
  .lyra-take { margin: 6px 0 0; color: #d0e8f8; font-size: 0.8rem; line-height: 1.4; }
  .score-row { display: flex; align-items: center; gap: 8px; margin-top: 4px; }

  /* Provider badges */
  .provider-badge {
    flex-shrink: 0;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: rgba(255,255,255,0.07);
    color: #9cb2c7;
    border: 1px solid rgba(255,255,255,0.1);
    white-space: nowrap;
  }
  .provider-badge.provider-local-taste { color: #7affc6; background: rgba(122,255,198,0.08); border-color: rgba(122,255,198,0.16); }
  .provider-badge.provider-local-deep_cut { color: #ffd166; background: rgba(255,209,102,0.1); border-color: rgba(255,209,102,0.18); }
  .provider-badge.provider-scout-bridge { color: #a8c4e0; background: rgba(168,196,224,0.1); border-color: rgba(168,196,224,0.18); }
  .provider-badge.provider-graph-co_play { color: #f4a261; background: rgba(244,162,97,0.1); border-color: rgba(244,162,97,0.18); }

  /* Inline evidence chips under lyra-take */
  .inline-evidence { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; }
  .ev-chip {
    font-size: 0.68rem;
    color: #9cb2c7;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 6px;
    padding: 2px 7px;
    line-height: 1.4;
  }
  .ev-chip.ev-scout_bridge, .ev-chip.ev-scout-bridge { color: #a8c4e0; background: rgba(168,196,224,0.07); }
  .ev-chip.ev-deep_cut { color: #ffd166; background: rgba(255,209,102,0.07); }
  .ev-chip.ev-co_play { color: #f4a261; background: rgba(244,162,97,0.07); }

  /* Explain panel structured layout */
  .explain-why { color: #d0e8f8; font-size: 0.82rem; line-height: 1.45; font-style: italic; margin: 0 0 6px; }
  .evidence-list { display: grid; gap: 4px; margin: 4px 0; }
  .evidence-row { display: grid; grid-template-columns: auto auto 1fr; gap: 8px; align-items: start; font-size: 0.72rem; }
  .ev-label {
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    background: rgba(255,255,255,0.06);
    color: #7a95a8;
    white-space: nowrap;
  }
  .ev-label.ev-taste_alignment { color: #7affc6; background: rgba(122,255,198,0.08); }
  .ev-label.ev-deep_cut { color: #ffd166; background: rgba(255,209,102,0.08); }
  .ev-label.ev-scout_bridge { color: #a8c4e0; background: rgba(168,196,224,0.08); }
  .ev-label.ev-co_play { color: #f4a261; background: rgba(244,162,97,0.08); }
  .ev-label.ev-dimension_match { color: #7affc6; background: rgba(122,255,198,0.06); }
  .ev-source { color: #7a95a8; font-size: 0.62rem; white-space: nowrap; }
  .ev-text { color: #c0d8ea; line-height: 1.4; }
  .inferred-section { margin-top: 6px; padding: 6px 8px; border-radius: 7px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07); }
  .inferred-label { display: block; font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.1em; color: #7a95a8; margin-bottom: 4px; }
  .inferred-line { color: #9cb2c7; font-size: 0.72rem; line-height: 1.4; margin: 0; }
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
  .taste-head { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
  .taste-meta { font-size: 0.72rem; color: #9cb2c7; }
  .taste-seed-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .seed-btn { font-size: 0.78rem; padding: 5px 11px; border-radius: 8px; background: rgba(140,217,74,0.1); border: 1px solid rgba(140,217,74,0.25); color: #8cd94a; cursor: pointer; }
  .seed-btn:hover { background: rgba(140,217,74,0.18); }
  .seed-btn:disabled { opacity: 0.5; cursor: default; }
  .seed-force { background: rgba(255,180,50,0.08); border-color: rgba(255,180,50,0.2); color: #ffb432; }
  .seed-force:hover { background: rgba(255,180,50,0.14); }
  .seed-result { font-size: 0.75rem; }
  .taste-cold-prompt { margin-bottom: 20px; padding: 14px 16px; border-radius: 14px; background: rgba(140,217,74,0.04); border: 1px solid rgba(140,217,74,0.12); display: flex; flex-direction: column; gap: 8px; }
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

  /* G-064: Artist graph panel */
  .graph-panel {
    margin-bottom: 20px;
    padding: 14px 18px;
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(168,196,224,0.07), rgba(168,196,224,0.025));
    border: 1px solid rgba(168,196,224,0.12);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .graph-stats { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; flex-wrap: wrap; }

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


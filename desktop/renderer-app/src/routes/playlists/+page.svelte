<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { get } from "svelte/store";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import {
    setWorkspaceBridgeActions,
    setWorkspaceExplanation,
    setWorkspacePage,
    setWorkspaceProvenance,
    setWorkspaceTrack
  } from "$lib/stores/workspace";
  import type {
    ComposerResponse,
    ComposerDiagnosticEntry,
    ComposerRunRecord,
    ComposedPlaylistDraft,
    ExplainPayload,
    PlaylistSummary,
    SpotifyGapSummary,
    SteerPayload,
    TrackEnrichmentResult
  } from "$lib/types";

  let playlists: PlaylistSummary[] = [];
  let name = "";
  let prompt = "";
  let trackCount = 20;
  let composing = false;
  let composerResult: ComposerResponse | null = null;
  let draft: ComposedPlaylistDraft | null = null;
  let previewTracks: ComposedPlaylistDraft["tracks"] = [];
  let saveMessage = "";
  let generatedProof: Record<number, TrackEnrichmentResult | "loading"> = {};
  let composerDiagnostics: ComposerDiagnosticEntry[] = [];
  let recentComposerRuns: ComposerRunRecord[] = [];
  let spotifyGapSummary: SpotifyGapSummary | null = null;
  let resultPreference: "auto" | "playlist" | "bridge" | "discovery" = "auto";
  let noveltyBias = 0.56;
  let adventurousness = 0.56;
  let contrastSharpness = 0.5;
  let warmthBias = 0.5;
  let explanationDepth = "balanced";

  $: draft = composerResult?.draft ?? null;
  $: previewTracks =
    draft?.tracks ??
    composerResult?.bridge?.steps.map((step, index) => ({
      track: step.track,
      phaseKey: step.role,
      phaseLabel: step.role,
      fitScore: step.fitScore,
      reason: {
        summary: step.role,
        phase: step.role,
        whyThisTrack: step.why,
        transitionNote: step.leadsToNext,
        evidence: step.adjacencySignals.map((signal) => `${signal.dimension}: ${signal.note}`),
        explicitFromPrompt: [],
        inferredByLyra: [...step.preserves, ...step.changes],
        confidence: step.fitScore
      },
      position: index
    })) ??
    composerResult?.discovery?.directions.flatMap((direction) => direction.tracks) ??
    [];
  $: routeVariants =
    composerResult?.framing.routeComparison?.variants ??
    composerResult?.bridge?.variants ??
    composerResult?.discovery?.variants ??
    [];
  $: resultLabel =
    composerResult?.action === "playlist"
      ? "Playlist draft"
      : composerResult?.action === "bridge"
        ? "Bridge route"
        : composerResult?.action === "discovery"
          ? "Discovery route"
          : composerResult?.action === "explain"
            ? "Explanation"
            : "Steer revision";
  $: tasteSummary =
    composerResult?.tasteMemory.summaryLines[0] ??
    $shell.tasteMemory.summaryLines[0] ??
    "Lyra has not accumulated enough recent steering pressure to claim a pattern yet.";
  $: memoryPreferences =
    composerResult?.tasteMemory.rememberedPreferences.slice(0, 3) ??
    $shell.tasteMemory.rememberedPreferences.slice(0, 3);
  $: recommendedFlavor =
    composerResult?.discovery?.primaryFlavor ?? composerResult?.bridge?.routeFlavor ?? null;
  $: spotifyTopArtists = spotifyGapSummary?.topArtists.slice(0, 4) ?? [];
  $: spotifyMissingCandidates = spotifyGapSummary?.missingCandidates.slice(0, 4) ?? [];

  function variantTone(flavor: string): string {
    if (flavor === "safe" || flavor === "direct_bridge") return "safe";
    if (flavor === "dangerous" || flavor === "contrast") return "dangerous";
    return "interesting";
  }

  function steerPayload(): SteerPayload {
    return {
      noveltyBias,
      adventurousness,
      contrastSharpness,
      warmthBias,
      explanationDepth
    };
  }

  function effectivePrompt(): string {
    const trimmed = prompt.trim();
    if (resultPreference === "bridge" && !trimmed.toLowerCase().includes("bridge")) {
      return `bridge from ${trimmed}`;
    }
    if (resultPreference === "discovery" && !/adjacent|discover|less obvious|three ways|three exits/i.test(trimmed)) {
      return `${trimmed} | give me three exits from this scene, one safe, one interesting, one dangerous`;
    }
    return trimmed;
  }

  async function applyNudge(nudge: string): Promise<void> {
    prompt = `${prompt.trim()} | ${nudge}`;
    await composeDraft();
  }

  function routeAuditionTracks(flavor: string) {
    const discoveryDirection = composerResult?.discovery?.directions.find(
      (direction) => direction.flavor === flavor
    );
    if (discoveryDirection) {
      return discoveryDirection.tracks.slice(0, 3);
    }
    if (composerResult?.bridge && composerResult.bridge.routeFlavor === flavor) {
      return composerResult.bridge.steps.slice(0, 3).map((step, index) => ({
        track: step.track,
        phaseKey: step.role,
        phaseLabel: step.role,
        fitScore: step.fitScore,
        reason: {
          summary: step.role,
          phase: step.role,
          whyThisTrack: step.why,
          transitionNote: step.leadsToNext,
          evidence: step.adjacencySignals.map((signal) => `${signal.dimension}: ${signal.note}`),
          explicitFromPrompt: [],
          inferredByLyra: [...step.preserves, ...step.changes],
          confidence: step.fitScore
        },
        position: index
      }));
    }
    return [];
  }

  async function playRouteAudition(flavor: string): Promise<void> {
    const [first] = routeAuditionTracks(flavor);
    if (!first) return;
    const playback = await api.playTrack(first.track.id);
    shell.update((state) => ({ ...state, playback }));
  }

  async function queueRouteAudition(flavor: string): Promise<void> {
    const tracks = routeAuditionTracks(flavor);
    if (!tracks.length) return;
    const queue = await api.enqueueTracks(tracks.map((item) => item.track.id));
    shell.update((state) => ({ ...state, queue }));
  }

  async function recordRouteFeedback(routeKind: string, outcome: "accepted" | "rejected"): Promise<void> {
    if (!composerResult) return;
    const snapshot = await api.recordRouteFeedback(
      routeKind,
      composerResult.action,
      outcome,
      "ui route comparison",
      outcome === "accepted"
        ? `User chose the ${routeKind} lane from Cassette route comparison.`
        : `User rejected the ${routeKind} lane from Cassette route comparison.`
    );
    shell.update((state) => ({ ...state, tasteMemory: snapshot }));
    composerResult = { ...composerResult, tasteMemory: snapshot };
  }

  async function refresh(): Promise<void> {
    playlists = await api.playlists();
    composerDiagnostics = await api.getComposerDiagnostics(8).catch(() => []);
    recentComposerRuns = await api.getRecentComposerRuns(8).catch(() => []);
    spotifyGapSummary = await api.getSpotifyGapSummary(6).catch(() => null);
  }

  async function queueSpotifyCandidate(artist: string, title: string, album?: string | null): Promise<void> {
    await api.addToAcquisitionQueue(artist, title, album ?? undefined, "spotify_gap");
    spotifyGapSummary = await api.getSpotifyGapSummary(6).catch(() => spotifyGapSummary);
    saveMessage = `Queued ${artist} - ${title} from the Spotify gap lane.`;
  }

  function promptSpotifyRecovery(artist: string): void {
    prompt = `rebuild the world i used to live in around ${artist}, but route it through what my local library is still missing`;
  }

  async function loadComposerRun(runId: number): Promise<void> {
    const detail = await api.getComposerRun(runId);
    composerResult = detail.response;
    prompt = detail.record.prompt;
    composerDiagnostics = await api.getComposerDiagnostics(8).catch(() => composerDiagnostics);
  }

  async function create(): Promise<void> {
    if (!name.trim()) return;
    const playlist = await api.createPlaylist(name.trim());
    name = "";
    await goto(`/playlists/${playlist.id}`);
  }

  async function composeDraft(): Promise<void> {
    if (!prompt.trim()) return;
    composing = true;
    composerResult = null;
    saveMessage = "";
    generatedProof = {};
    try {
      composerResult = await api.composeWithLyra(effectivePrompt(), trackCount, steerPayload());
      composerDiagnostics = await api.getComposerDiagnostics(8).catch(() => composerDiagnostics);
      const workspaceTracks =
        composerResult.draft?.tracks ??
        composerResult.bridge?.steps.map((step, index) => ({
          track: step.track,
          phaseKey: step.role,
          phaseLabel: step.role,
          fitScore: step.fitScore,
          reason: {
            summary: step.role,
            phase: step.role,
            whyThisTrack: step.why,
            transitionNote: step.leadsToNext,
            evidence: step.adjacencySignals.map((signal) => `${signal.dimension}: ${signal.note}`),
            explicitFromPrompt: [],
            inferredByLyra: [...step.preserves, ...step.changes],
            confidence: step.fitScore
          },
          position: index
        })) ??
        composerResult.discovery?.directions.flatMap((direction) => direction.tracks) ??
        [];
      setWorkspaceBridgeActions(
        workspaceTracks.slice(0, 4).map((item) => ({
          label: item.track.artist,
          href: `/artists/${encodeURIComponent(item.track.artist)}`,
          detail: item.reason.summary
        }))
      );
    } finally {
      composing = false;
    }
  }

  async function saveDraft(): Promise<void> {
    if (!draft) return;
    saveMessage = "Saving to Cassette...";
    try {
      const detail = await api.saveComposedPlaylist(draft.name, draft);
      saveMessage = `Saved "${detail.name}" with ${detail.items.length} tracks.`;
      await refresh();
      composerResult = null;
    } catch (error) {
      saveMessage = error instanceof Error ? error.message : "Failed to save.";
    }
  }

  async function enqueueDraft(): Promise<void> {
    if (!draft) return;
    const queue = await api.enqueueTracks(draft.tracks.map((item) => item.track.id));
    shell.update((state) => ({ ...state, queue }));
  }

  function currentNarrative(): string | null {
    return (
      draft?.narrative ??
      composerResult?.bridge?.narrative ??
      composerResult?.discovery?.narrative ??
      composerResult?.explanation ??
      null
    );
  }

  async function inspectDraftTrack(trackId: number): Promise<void> {
    const item = previewTracks.find((entry) => entry.track.id === trackId);
    if (!item) return;
    setWorkspaceTrack(item.track);
    setWorkspaceExplanation(
      {
        trackId,
        whyThisTrack: item.reason.whyThisTrack || item.reason.summary,
        reasons: [
          item.reason.summary,
          item.reason.whyThisTrack,
          item.reason.transitionNote,
          ...item.reason.evidence
        ],
        evidenceItems: item.reason.evidence.map((text) => ({
          typeLabel: "composer_reason",
          source: `lyra:${item.phaseKey}`,
          text,
          weight: item.reason.confidence,
        })),
        explicitFromPrompt: item.reason.explicitFromPrompt ?? [],
        inferredByLyra: item.reason.inferredByLyra ?? [],
        confidence: item.reason.confidence,
        source: `lyra:${item.phaseKey}`
      } satisfies ExplainPayload,
      item.track
    );
  }

  async function toggleDraftProof(trackId: number): Promise<void> {
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
      const track = previewTracks.find((item) => item.track.id === trackId)?.track ?? null;
      setWorkspaceProvenance(result.entries, track);
    } catch {
      const next = { ...generatedProof };
      delete next[trackId];
      generatedProof = next;
    }
  }

  onMount(() => {
    setWorkspacePage(
      "Cassette",
      "Lyra workspace",
      "Prototype shell for bridge-finding, discovery, playlist authorship, and explanation.",
      "bridge"
    );
    trackCount = get(shell).settings.composerDefaultTrackCount ?? 20;
    void refresh();
    const params = page.url?.searchParams;
    prompt = params?.get("prompt") ?? params?.get("mood") ?? "";
    if (prompt) {
      void composeDraft();
    }
  });
</script>

<section class="workspace-header">
  <div>
    <p class="eyebrow">Cassette</p>
    <h2>Lyra composer workspace</h2>
    <p class="subcopy">The composer stays central. Playback stays in support. Routes, memory, and explanation stay visible enough to judge the intelligence honestly.</p>
  </div>
  <div class="header-actions">
    <input bind:value={name} placeholder="New playlist name" />
    <button on:click={create}>Create playlist</button>
  </div>
</section>

<section class="oracle-grid">
  <aside class="workspace-left">
    <article class="panel">
      <span class="section-label">Spotify memory + gaps</span>
      {#if !spotifyGapSummary}
        <small>Loading Spotify evidence...</small>
      {:else if !spotifyGapSummary.available}
        {#each spotifyGapSummary.summaryLines as line}
          <small>{line}</small>
        {/each}
      {:else}
        <strong class="memory-summary">{spotifyGapSummary.summaryLines[0]}</strong>
        {#if spotifyGapSummary.summaryLines[1]}
          <small>{spotifyGapSummary.summaryLines[1]}</small>
        {/if}
        <div class="memory-list compact-list">
          <div class="memory-item">
            <span>History</span>
            <strong>{spotifyGapSummary.historyCount}</strong>
          </div>
          <div class="memory-item">
            <span>Liked/library</span>
            <strong>{spotifyGapSummary.libraryCount}</strong>
          </div>
          <div class="memory-item">
            <span>Still missing</span>
            <strong>{spotifyGapSummary.recoverableMissingCount}</strong>
          </div>
        </div>
        {#if spotifyTopArtists.length}
          <div class="memory-list">
            {#each spotifyTopArtists as artist}
              <button class="history-link" on:click={() => promptSpotifyRecovery(artist.artist)}>
                <strong>{artist.artist}</strong>
                <small>{artist.playCount} plays | {artist.missingTrackCount} still missing</small>
                <span>Use this world as a Lyra recovery seed</span>
              </button>
            {/each}
          </div>
        {/if}
        {#if spotifyMissingCandidates.length}
          <div class="memory-list">
            {#each spotifyMissingCandidates as candidate}
              <div class="memory-item spotify-gap-item">
                <div>
                  <span>{candidate.artist}</span>
                  <strong>{candidate.title}</strong>
                  <small>{candidate.playCount} plays{candidate.alreadyQueued ? " | already queued" : ""}</small>
                </div>
                <button
                  class="ghost-button"
                  disabled={candidate.alreadyQueued}
                  on:click={() => void queueSpotifyCandidate(candidate.artist, candidate.title, candidate.album)}
                >
                  {candidate.alreadyQueued ? "Queued" : "Acquire"}
                </button>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </article>

    <article class="panel">
      <span class="section-label">Entry points</span>
      <button class="prompt-chip" on:click={() => (prompt = "bridge from Brand New into late-night electronic melancholy")}>Bridge a scene</button>
      <button class="prompt-chip" on:click={() => (prompt = "give me three exits from this scene, one safe, one interesting, one dangerous")}>Compare exits</button>
      <button class="prompt-chip" on:click={() => (prompt = "this is close but too clean, I want it dirtier and more human")}>Steer texture</button>
    </article>

    <article class="panel">
      <span class="section-label">Recent memory</span>
      <strong class="memory-summary">{tasteSummary}</strong>
      {#if memoryPreferences.length}
        <div class="memory-chip-row">
          {#each memoryPreferences as preference}
            <span class="memory-chip">{preference.preferredPole}</span>
          {/each}
        </div>
      {/if}
      <small>{composerResult?.tasteMemory.sessionPosture.confidenceNote ?? $shell.tasteMemory.sessionPosture.confidenceNote}</small>
    </article>

    <article class="panel">
      <span class="section-label">Recent Lyra work</span>
      {#if !recentComposerRuns.length}
        <small>No recent routes yet.</small>
      {/if}
      {#each recentComposerRuns as run}
        <button class="history-link" on:click={() => void loadComposerRun(run.id)}>
          <strong>{run.summary}</strong>
          <small>{run.action} | {run.activeRole} | {run.mode}</small>
          <span>{run.prompt}</span>
        </button>
      {/each}
    </article>

    <article class="panel">
      <span class="section-label">Saved playlists</span>
      {#if !playlists.length}
        <small>No saved drafts yet.</small>
      {/if}
      {#each playlists.slice(0, 6) as playlist}
        <a class="playlist-link" href={`/playlists/${playlist.id}`}>
          <strong>{playlist.name}</strong>
          <small>{playlist.itemCount} items</small>
        </a>
      {/each}
    </article>
  </aside>

  <div class="workspace-main">
    <article class="composer-panel">
      <div class="composer-head">
        <div>
          <span class="section-label">Ask Lyra</span>
          <strong>Steer with intent, not forms</strong>
        </div>
        <div class="result-toggle">
          <label>
            Result
            <select bind:value={resultPreference}>
              <option value="auto">Auto</option>
              <option value="playlist">Playlist</option>
              <option value="bridge">Bridge</option>
              <option value="discovery">Discovery</option>
            </select>
          </label>
        </div>
      </div>

      <textarea
        bind:value={prompt}
        rows="4"
        placeholder="less obvious, still aching, keep the pulse"
        on:keydown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void composeDraft();
          }
        }}
      ></textarea>

      <div class="steering-row">
        <label>Tracks <input type="range" min="8" max="40" step="4" bind:value={trackCount} /><strong>{trackCount}</strong></label>
        <label>Obviousness <input type="range" min="0" max="1" step="0.01" bind:value={noveltyBias} /></label>
        <label>Adventure <input type="range" min="0" max="1" step="0.01" bind:value={adventurousness} /></label>
        <label>Transition <input type="range" min="0" max="1" step="0.01" bind:value={contrastSharpness} /></label>
        <label>Nocturnal <input type="range" min="0" max="1" step="0.01" bind:value={warmthBias} /></label>
        <label>
          Explanation
          <select bind:value={explanationDepth}>
            <option value="light">Light</option>
            <option value="balanced">Balanced</option>
            <option value="deep">Deep</option>
          </select>
        </label>
        <button class="ask-btn" on:click={composeDraft} disabled={composing}>
          {composing ? "Lyra is shaping the route..." : "Ask Lyra"}
        </button>
      </div>
    </article>

    {#if composerResult}
      <div class="result-bar">
        <article class="result-card">
          <span class="section-label">Result type</span>
          <strong>{resultLabel}</strong>
          <small>{composerResult.activeRole} | {composerResult.providerStatus.selectedProvider} | {composerResult.providerStatus.mode}</small>
        </article>
        <article class="result-card">
          <span class="section-label">Lyra read</span>
          <strong>{composerResult.intent.sourceEnergy} -> {composerResult.intent.destinationEnergy}</strong>
          <small>{composerResult.intent.transitionStyle}</small>
        </article>
        <article class="result-card">
          <span class="section-label">Fallback status</span>
          <strong>{composerResult.framing.fallback.label}</strong>
          <small>{composerResult.framing.confidence.phrasing}</small>
        </article>
        <article class="result-card accent-card">
          <span class="section-label">Lyra posture</span>
          <strong>{composerResult.framing.lead}</strong>
          <small>{composerResult.framing.rationale}</small>
        </article>
      </div>

      {#if routeVariants.length}
        <div class="route-comparison">
          {#each routeVariants as variant}
            <article
              class="route-variant route-{variantTone(variant.flavor)}"
              class:active-variant={recommendedFlavor === variant.flavor}
            >
              <span class="section-label">{variant.label}</span>
              <strong>{variant.logic}</strong>
              <small>Preserves: {variant.preserves.join(", ")}</small>
              <small>Changes: {variant.changes.join(", ")}</small>
              <small>{variant.riskNote}</small>
              <small>{variant.rewardNote}</small>
              {#if routeAuditionTracks(variant.flavor).length}
                <div class="audition-strip">
                  {#each routeAuditionTracks(variant.flavor) as item}
                    <span>{item.track.artist} - {item.track.title}</span>
                  {/each}
                </div>
                <div class="variant-actions">
                  <button class="ghost-button" on:click={() => void playRouteAudition(variant.flavor)}>Play audition</button>
                  <button class="ghost-button" on:click={() => void queueRouteAudition(variant.flavor)}>Queue teaser</button>
                </div>
              {/if}
              <div class="variant-actions">
                <button class="ghost-button" on:click={() => void recordRouteFeedback(variant.flavor, "accepted")}>This lane works</button>
                <button class="ghost-button" on:click={() => void recordRouteFeedback(variant.flavor, "rejected")}>Not this lane</button>
              </div>
            </article>
          {/each}
        </div>
      {/if}

      <div class="result-canvas">
        <div class="canvas-main">
          {#if currentNarrative()}
            <article class="narrative-panel">
              <span class="section-label">Lyra's read</span>
              <p>{currentNarrative()}</p>
            </article>
          {/if}

          {#if composerResult.bridge}
            <article class="canvas-panel">
              <div class="canvas-title">
                <div>
                  <span class="section-label">Bridge route</span>
                  <strong>{composerResult.bridge.sourceLabel} -> {composerResult.bridge.destinationLabel}</strong>
                </div>
                <small>{Math.round(composerResult.bridge.confidence * 100)}% confidence</small>
              </div>
              {#each composerResult.bridge.steps as step}
                <div class="bridge-step">
                  <div>
                    <span class="step-role">{step.role}</span>
                    <strong>{step.track.title}</strong>
                    <small>{step.track.artist}</small>
                  </div>
                  <div class="step-notes">
                    <small>Preserves: {step.preserves.join(", ")}</small>
                    <small>Changes: {step.changes.join(", ")}</small>
                    <small>{step.leadsToNext}</small>
                  </div>
                </div>
              {/each}
            </article>
          {:else if composerResult.discovery}
            <article class="canvas-panel">
              <div class="canvas-title">
                <div>
                  <span class="section-label">Discovery routes</span>
                  <strong>{composerResult.discovery.seedLabel}</strong>
                </div>
                <small>{Math.round(composerResult.discovery.confidence * 100)}% confidence</small>
              </div>
              {#each composerResult.discovery.directions as direction}
                <div class="discovery-direction">
                  <div>
                    <span class="step-role">{direction.label}</span>
                    <strong>{direction.description}</strong>
                    <small>{direction.why}</small>
                  </div>
                  <div class="direction-meta">
                    <small>Preserves: {direction.preserves.join(", ")}</small>
                    <small>Changes: {direction.changes.join(", ")}</small>
                    <small>{direction.rewardNote}</small>
                  </div>
                </div>
              {/each}
            </article>
          {:else if composerResult.explanation}
            <article class="canvas-panel">
              <span class="section-label">Explanation</span>
              <p>{composerResult.explanation}</p>
            </article>
          {/if}

          <article class="canvas-panel">
            <div class="canvas-title">
              <div>
                <span class="section-label">Result canvas</span>
                <strong>{draft?.name ?? resultLabel}</strong>
              </div>
              <div class="draft-actions">
                {#if draft}
                  <button on:click={saveDraft}>Save playlist</button>
                  <button on:click={enqueueDraft}>Queue all</button>
                {/if}
              </div>
            </div>
            <div class="preview-list">
              {#each previewTracks as item}
                <article class="preview-row">
                  <div class="preview-top">
                    <span class="preview-pos">{item.position + 1}</span>
                    <div>
                      <strong>{item.track.title}</strong>
                      <small>{item.track.artist}</small>
                    </div>
                    <div class="preview-phase">
                      <span>{item.phaseLabel}</span>
                      <small>{Math.round(item.fitScore * 100)}%</small>
                    </div>
                  </div>
                  <small>{item.reason.whyThisTrack}</small>
                  <small>{item.reason.transitionNote}</small>
                  <div class="preview-actions">
                    <button on:click={() => inspectDraftTrack(item.track.id)}>Why</button>
                    <button on:click={() => toggleDraftProof(item.track.id)}>
                      {generatedProof[item.track.id] ? "Hide proof" : "Proof"}
                    </button>
                  </div>
                  {#if generatedProof[item.track.id]}
                    <div class="proof-inline">
                      {#if generatedProof[item.track.id] === "loading"}
                        <small>Loading provenance...</small>
                      {:else}
                        {@const proof = generatedProof[item.track.id] as TrackEnrichmentResult}
                        <small>{proof.enrichmentState}{proof.primaryMbid ? ` | ${proof.primaryMbid}` : ""}</small>
                        {#each proof.entries.slice(0, 2) as entry}
                          <small>{entry.provider}: {entry.status} | {Math.round(entry.confidence * 100)}%</small>
                        {/each}
                      {/if}
                    </div>
                  {/if}
                </article>
              {/each}
            </div>
          </article>
        </div>

        <aside class="canvas-right">
          <article class="panel">
            <span class="section-label">Lyra read</span>
            <strong class="memory-summary">{composerResult.framing.lyraRead.summary}</strong>
            <small>{composerResult.framing.lyraRead.confidenceNote}</small>
            {#if composerResult.framing.lyraRead.cues.length}
              <div class="memory-list">
                {#each composerResult.framing.lyraRead.cues as cue}
                  <div class="memory-item">
                    <small>{cue}</small>
                  </div>
                {/each}
              </div>
            {/if}
          </article>

          <article class="panel">
            <span class="section-label">Parsed intent</span>
            <strong>{composerResult.intent.familiarityVsNovelty}</strong>
            <small>{composerResult.intent.discoveryAggressiveness}</small>
            <small>{composerResult.intent.textureDescriptors.join(", ")}</small>
            <small>{composerResult.intent.sequencingNotes.join(" ")}</small>
          </article>

          <article class="panel">
            <span class="section-label">Taste-memory cues</span>
            <strong class="memory-summary">{composerResult.tasteMemory.sessionPosture.summary}</strong>
            <small>{composerResult.tasteMemory.sessionPosture.confidenceNote}</small>
            {#if composerResult.tasteMemory.rememberedPreferences.length}
              <div class="memory-list">
                {#each composerResult.tasteMemory.rememberedPreferences.slice(0, 3) as preference}
                  <div class="memory-item">
                    <span>{preference.axisLabel}</span>
                    <strong>{preference.preferredPole}</strong>
                    <small>{preference.recencyNote} | {preference.confidenceNote}</small>
                  </div>
                {/each}
              </div>
            {/if}
          </article>

          <article class="panel">
            <span class="section-label">Why this works</span>
            <strong>{composerResult.framing.lead}</strong>
            <small>{composerResult.framing.rationale}</small>
            {#if composerResult.framing.routeComparison}
              <small>{composerResult.framing.routeComparison.summary}</small>
            {/if}
            {#if composerResult.framing.challenge}
              <small class="challenge-line">{composerResult.framing.challenge}</small>
            {/if}
          </article>

          <article class="panel">
            <span class="section-label">Confidence and fallback</span>
            <small>{composerResult.framing.confidence.level}</small>
            <small>{composerResult.framing.fallback.message}</small>
            {#each composerResult.uncertainty as note}
              <small>{note}</small>
            {/each}
          </article>

          {#if composerDiagnostics.length}
            <article class="panel">
              <span class="section-label">Composer diagnostics</span>
              {#each composerDiagnostics.slice(0, 4) as diagnostic}
                <div class="memory-item">
                  <span>{diagnostic.eventType}</span>
                  <strong>{diagnostic.message}</strong>
                  <small>{diagnostic.provider} | {diagnostic.mode}{diagnostic.action ? ` | ${diagnostic.action}` : ""}</small>
                </div>
              {/each}
            </article>
          {/if}

          {#if composerResult.framing.nextNudges.length}
            <article class="panel">
              <span class="section-label">Follow-on nudges</span>
              {#each composerResult.framing.nextNudges as nudge}
                <button class="prompt-chip" on:click={() => applyNudge(nudge)}>{nudge}</button>
              {/each}
            </article>
          {/if}
        </aside>
      </div>
    {/if}

    {#if saveMessage}
      <p class="status-line">{saveMessage}</p>
    {/if}
  </div>
</section>

<style>
  .workspace-header,
  .oracle-grid,
  .workspace-main,
  .composer-panel,
  .steering-row,
  .result-bar,
  .route-comparison,
  .result-canvas,
  .preview-actions,
  .header-actions {
    display: flex;
    gap: 1rem;
  }

  .workspace-header,
  .bridge-step,
  .discovery-direction,
  .preview-top,
  .canvas-title {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
  }

  .workspace-header {
    align-items: end;
    margin-bottom: 1rem;
  }

  .workspace-header h2,
  .workspace-header p {
    margin: 0;
  }

  .oracle-grid {
    align-items: start;
  }

  .workspace-left {
    width: 18rem;
    display: grid;
    gap: 1rem;
  }

  .workspace-main {
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .composer-panel,
  .panel,
  .result-card,
  .route-variant,
  .canvas-panel,
  .narrative-panel {
    border-radius: 22px;
    border: 1px solid rgba(255, 244, 224, 0.08);
    background:
      radial-gradient(circle at top right, rgba(255, 210, 120, 0.1), transparent 30%),
      radial-gradient(circle at bottom left, rgba(247, 141, 107, 0.07), transparent 28%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.026));
    box-shadow: 0 22px 44px rgba(0, 0, 0, 0.2);
  }

  .composer-panel,
  .panel,
  .result-card,
  .route-variant,
  .canvas-panel,
  .narrative-panel {
    padding: 1rem;
  }

  .composer-panel,
  .panel,
  .canvas-panel,
  .narrative-panel {
    display: grid;
    gap: 0.8rem;
  }

  .composer-head {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: start;
  }

  .composer-panel {
    background:
      radial-gradient(circle at top left, rgba(246, 196, 114, 0.18), transparent 22%),
      radial-gradient(circle at bottom right, rgba(247, 141, 107, 0.1), transparent 24%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0.03));
  }

  .steering-row {
    flex-wrap: wrap;
    align-items: end;
  }

  .steering-row label,
  .result-toggle label {
    display: grid;
    gap: 0.35rem;
  }

  .result-bar,
  .route-comparison {
    flex-wrap: wrap;
  }

  .result-card,
  .route-variant {
    flex: 1 1 14rem;
    display: grid;
    gap: 0.35rem;
  }

  .variant-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.35rem;
  }

  .audition-strip {
    display: grid;
    gap: 0.3rem;
    padding: 0.65rem 0.75rem;
    border-radius: 14px;
    background: rgba(9, 13, 20, 0.28);
    border: 1px solid rgba(255, 255, 255, 0.06);
    color: #c8d7e2;
    font-size: 0.78rem;
  }

  .accent-card {
    background:
      radial-gradient(circle at top right, rgba(246, 196, 114, 0.18), transparent 26%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.03));
  }

  .active-variant {
    border-color: rgba(246, 196, 114, 0.4);
    background:
      radial-gradient(circle at top right, rgba(246, 196, 114, 0.18), transparent 30%),
      linear-gradient(180deg, rgba(255, 255, 255, 0.09), rgba(255, 255, 255, 0.03));
    transform: translateY(-2px);
  }

  .route-safe {
    border-color: rgba(150, 214, 187, 0.16);
  }

  .route-interesting {
    border-color: rgba(246, 196, 114, 0.18);
  }

  .route-dangerous {
    border-color: rgba(247, 141, 107, 0.2);
  }

  .result-canvas {
    align-items: start;
  }

  .canvas-main {
    flex: 1;
    display: grid;
    gap: 1rem;
    min-width: 0;
  }

  .canvas-right {
    width: 20rem;
    display: grid;
    gap: 1rem;
  }

  .preview-list {
    display: grid;
    gap: 0.75rem;
    max-height: 42rem;
    overflow: auto;
  }

  .preview-row,
  .playlist-link,
  .history-link,
  .prompt-chip,
  button,
  input,
  textarea,
  select {
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.05);
    color: inherit;
    font: inherit;
  }

  .preview-row,
  .playlist-link,
  .history-link {
    padding: 0.8rem;
    display: grid;
    gap: 0.45rem;
  }

  .prompt-chip,
  button,
  input,
  textarea,
  select {
    padding: 0.72rem 0.86rem;
  }

  button {
    transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
  }

  button:hover,
  .playlist-link:hover,
  .history-link:hover,
  .route-variant:hover {
    transform: translateY(-1px);
  }

  textarea {
    min-height: 7.5rem;
    resize: vertical;
    background: rgba(10, 12, 17, 0.34);
  }

  .ask-btn {
    background: linear-gradient(120deg, #f6c472 0%, #f78d6b 100%);
    color: #21140c;
    border-color: transparent;
  }

  .ghost-button {
    background: rgba(12, 16, 24, 0.34);
    border-color: rgba(255, 255, 255, 0.1);
    color: #dbe5ed;
  }

  .eyebrow,
  .section-label,
  .subcopy,
  small,
  .status-line {
    color: #9db2c2;
  }

  h2,
  .composer-head strong,
  .canvas-title strong,
  .result-card strong,
  .panel strong,
  .narrative-panel p {
    font-family: "Georgia", "Times New Roman", serif;
  }

  .eyebrow,
  .section-label {
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-size: 0.72rem;
  }

  .playlist-link strong,
  .history-link strong,
  .preview-top strong,
  .canvas-title strong {
    display: block;
  }

  .history-link {
    text-align: left;
  }

  .history-link span {
    color: #c7d5e0;
    font-size: 0.84rem;
    line-height: 1.35;
  }

  .preview-pos,
  .step-role {
    color: #f6c472;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.72rem;
  }

  .preview-phase,
  .step-notes,
  .direction-meta {
    display: grid;
    gap: 0.2rem;
  }

  .memory-summary {
    color: #eef4f8;
    line-height: 1.5;
  }

  .memory-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
  }

  .memory-chip {
    padding: 0.3rem 0.62rem;
    border-radius: 999px;
    border: 1px solid rgba(246, 196, 114, 0.2);
    background: rgba(246, 196, 114, 0.08);
    color: #ecd8af;
    font-size: 0.76rem;
  }

  .memory-list {
    display: grid;
    gap: 0.5rem;
  }

  .compact-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .memory-item {
    display: grid;
    gap: 0.18rem;
    padding: 0.65rem 0.75rem;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.035);
  }

  .spotify-gap-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.75rem;
  }

  .challenge-line {
    color: #f0c983;
  }

  .proof-inline {
    display: grid;
    gap: 0.2rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }

  @media (max-width: 1280px) {
    .oracle-grid,
    .result-canvas {
      flex-direction: column;
    }

    .workspace-left,
    .canvas-right {
      width: 100%;
    }
  }
</style>

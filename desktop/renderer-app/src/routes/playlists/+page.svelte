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
    ComposedPlaylistDraft,
    ExplainPayload,
    PlaylistSummary,
    SteerPayload,
    TrackEnrichmentResult
  } from "$lib/types";

  let playlists: PlaylistSummary[] = [];
  let name = "";
  let composeOpen = false;
  let prompt = "";
  let trackCount = 20;
  let composing = false;
  let composerResult: ComposerResponse | null = null;
  let draft: ComposedPlaylistDraft | null = null;
  let previewTracks: ComposedPlaylistDraft["tracks"] = [];
  let saveMessage = "";
  let generatedProof: Record<number, TrackEnrichmentResult | "loading"> = {};
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
        transitionNote: `${Math.round(step.distanceFromSource * 100)}% from source, ${Math.round(step.distanceFromDestination * 100)}% from destination.`,
        evidence: [],
        explicitFromPrompt: [],
        inferredByLyra: [],
        confidence: step.fitScore
      },
      position: index
    })) ??
    composerResult?.discovery?.directions.flatMap((direction) => direction.tracks) ??
    [];

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
    if (resultPreference === "discovery" && !/adjacent|discover|less obvious|three ways/i.test(trimmed)) {
      return `${trimmed} into something adjacent but less obvious`;
    }
    return trimmed;
  }

  async function refresh(): Promise<void> {
    playlists = await api.playlists();
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
            transitionNote: `${Math.round(step.distanceFromSource * 100)}% from source, ${Math.round(step.distanceFromDestination * 100)}% from destination.`,
            evidence: [],
            explicitFromPrompt: [],
            inferredByLyra: [],
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
    saveMessage = "Saving...";
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

  async function inspectDraftTrack(trackId: number): Promise<void> {
    const item = previewTracks.find((entry) => entry.track.id === trackId);
    if (!item) return;
    setWorkspaceTrack(item.track);
    setWorkspaceExplanation(
      {
        trackId,
        reasons: [
          item.reason.summary,
          item.reason.whyThisTrack,
          item.reason.transitionNote,
          ...item.reason.evidence
        ],
        confidence: item.reason.confidence,
        source: `composer:${item.phaseKey}`
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
      "Playlists",
      "Composer-first playlist authorship",
      "Steer Lyra across draft, bridge, discovery, and explanation outputs instead of treating composition as a one-shot playlist generator.",
      "bridge"
    );
    trackCount = get(shell).settings.composerDefaultTrackCount ?? 20;
    void refresh();
    const params = page.url?.searchParams;
    if (params?.get("compose") === "1" || params?.get("generate") === "1") {
      composeOpen = true;
      prompt = params.get("prompt") ?? params.get("mood") ?? "";
      if (prompt) {
        void composeDraft();
      }
    }
  });
</script>

<section class="header">
  <div>
    <p class="eyebrow">Playlists</p>
    <h2>Composer-first playlist authorship</h2>
  </div>
  <div class="create-row">
    <input bind:value={name} placeholder="New playlist name" />
    <button on:click={create}>Create</button>
    <button class="generate-btn" on:click={() => (composeOpen = !composeOpen)}>
      {composeOpen ? "Hide Composer" : "Open Composer"}
    </button>
  </div>
</section>

{#if composeOpen}
  <section class="compose-panel">
    <p class="eyebrow">Lyra Composer</p>
    <textarea
      bind:value={prompt}
      rows="3"
      placeholder="mall goth sprint into neon confession booth"
      on:keydown={(event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          void composeDraft();
        }
      }}
    ></textarea>

    <div class="compose-controls">
      <label>
        Tracks
        <input type="range" min="8" max="40" step="4" bind:value={trackCount} />
        <strong>{trackCount}</strong>
      </label>
      <label>
        Result
        <select bind:value={resultPreference}>
          <option value="auto">Auto</option>
          <option value="playlist">Draft</option>
          <option value="bridge">Bridge</option>
          <option value="discovery">Discovery</option>
        </select>
      </label>
      <button class="gen-action-btn" on:click={composeDraft} disabled={composing}>
        {composing ? "Interpreting + routing..." : "Ask Lyra"}
      </button>
    </div>

    <div class="steering-grid">
      <label>
        Less obvious / more obvious
        <input type="range" min="0" max="1" step="0.01" bind:value={noveltyBias} />
      </label>
      <label>
        More familiar / more adventurous
        <input type="range" min="0" max="1" step="0.01" bind:value={adventurousness} />
      </label>
      <label>
        Smoother / sharper
        <input type="range" min="0" max="1" step="0.01" bind:value={contrastSharpness} />
      </label>
      <label>
        Brighter / more nocturnal
        <input type="range" min="0" max="1" step="0.01" bind:value={warmthBias} />
      </label>
      <label>
        Explanation
        <select bind:value={explanationDepth}>
          <option value="light">Light</option>
          <option value="balanced">Balanced</option>
          <option value="deep">Deep</option>
        </select>
      </label>
    </div>

    {#if composerResult}
      <div class="draft-head">
        <div>
          <strong>{draft?.name ?? composerResult.action}</strong>
          <small>{composerResult.activeRole} • {composerResult.providerStatus.selectedProvider} • {composerResult.providerStatus.mode}</small>
        </div>
        <div class="draft-actions">
          {#if draft}
            <button on:click={saveDraft}>Save Playlist</button>
            <button on:click={enqueueDraft}>Queue All</button>
          {/if}
        </div>
      </div>

      <div class="intent-summary-grid">
        <article class="summary-card">
          <span class="summary-label">Parsed intent</span>
          <strong>{composerResult.intent.sourceEnergy} → {composerResult.intent.destinationEnergy}</strong>
          <small>{composerResult.action} • {composerResult.intent.transitionStyle}</small>
          <small>{composerResult.intent.textureDescriptors.join(", ")}</small>
        </article>
        <article class="summary-card">
          <span class="summary-label">Discovery stance</span>
          <strong>{composerResult.intent.familiarityVsNovelty}</strong>
          <small>{composerResult.intent.discoveryAggressiveness}</small>
          <small>{composerResult.uncertainty.join(" ")}</small>
        </article>
        <article class="summary-card">
          <span class="summary-label">Provider</span>
          <strong>{composerResult.providerStatus.selectedProvider}</strong>
          <small>{composerResult.providerStatus.providerKind} • {composerResult.providerStatus.mode}</small>
          <small>{composerResult.providerStatus.fallbackReason ?? "Provider assisted language only; retrieval stayed local."}</small>
        </article>
      </div>

      {#if draft}
        <div class="phase-strip">
          {#each draft.phases as phase}
            <article class="phase-card">
              <span class="summary-label">{phase.label}</span>
              <strong>{Math.round(phase.targetEnergy * 100)}% energy</strong>
              <small>{phase.summary}</small>
            </article>
          {/each}
        </div>
      {:else if composerResult.bridge}
        <div class="phase-strip">
          {#each composerResult.bridge.steps as step}
            <article class="phase-card">
              <span class="summary-label">{step.role}</span>
              <strong>{step.track.title}</strong>
              <small>{step.track.artist}</small>
            </article>
          {/each}
        </div>
      {:else if composerResult.discovery}
        <div class="phase-strip">
          {#each composerResult.discovery.directions as direction}
            <article class="phase-card">
              <span class="summary-label">{direction.label}</span>
              <strong>{direction.tracks.length} tracks</strong>
              <small>{direction.description}</small>
            </article>
          {/each}
        </div>
      {/if}

      {#if draft?.narrative}
        <p class="narrative">{draft.narrative}</p>
      {:else if composerResult.bridge?.narrative}
        <p class="narrative">{composerResult.bridge.narrative}</p>
      {:else if composerResult.discovery?.narrative}
        <p class="narrative">{composerResult.discovery.narrative}</p>
      {:else if composerResult.explanation}
        <p class="narrative">{composerResult.explanation}</p>
      {/if}

      {#if composerResult.bridge}
        <div class="route-card">
          <strong>{composerResult.bridge.sourceLabel} → {composerResult.bridge.destinationLabel}</strong>
          <small>{Math.round(composerResult.bridge.confidence * 100)}% confidence</small>
          {#each composerResult.bridge.alternateDirections as option}
            <span class="route-option">{option}</span>
          {/each}
        </div>
      {:else if composerResult.discovery}
        <div class="route-card">
          <strong>{composerResult.discovery.seedLabel}</strong>
          {#each composerResult.discovery.directions as direction}
            <small>{direction.label}: {direction.why}</small>
          {/each}
        </div>
      {/if}

      <div class="preview-list">
        {#each previewTracks as item}
          <article class="preview-row">
            <span class="preview-pos">{item.position + 1}</span>
            <div class="preview-info">
              <strong>{item.track.title}</strong>
              <small>{item.track.artist}</small>
            </div>
            <div class="preview-phase">
              <span>{item.phaseLabel}</span>
              <small>{Math.round(item.fitScore * 100)}%</small>
            </div>
            <span class="reason-badge" title={item.reason.summary}>{item.reason.summary}</span>
            <div class="preview-actions">
              <button on:click={() => inspectDraftTrack(item.track.id)}>Why</button>
              <button on:click={() => toggleDraftProof(item.track.id)}>
                {generatedProof[item.track.id] ? "Hide Proof" : "Proof"}
              </button>
            </div>
            <div class="reason-detail">
              <small>{item.reason.whyThisTrack}</small>
              <small>{item.reason.transitionNote}</small>
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
          </article>
        {/each}
      </div>

      {#if composerResult.alternativesConsidered.length}
        <div class="route-card">
          <strong>Alternate directions</strong>
          {#each composerResult.alternativesConsidered as option}
            <small>{option}</small>
          {/each}
        </div>
      {/if}
    {/if}

    {#if saveMessage}
      <p class="muted">{saveMessage}</p>
    {/if}
  </section>
{/if}

<div class="grid">
  {#if !playlists.length}
    <p class="muted">No playlists yet.</p>
  {/if}
  {#each playlists as playlist}
    <a class="card" href={`/playlists/${playlist.id}`}>
      <strong>{playlist.name}</strong>
      <small>{playlist.itemCount} items</small>
      <span>{playlist.description || "Ready for sequencing, queueing, and later refinement."}</span>
    </a>
  {/each}
</div>

<style>
  .eyebrow, .muted, small { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .header { display: flex; justify-content: space-between; align-items: end; margin-bottom: 20px; gap: 12px; }
  .create-row, .grid, .draft-head, .draft-actions, .compose-controls, .preview-actions, .proof-inline-row { display: flex; gap: 12px; }
  .grid { flex-wrap: wrap; }
  .card,
  .compose-panel,
  .summary-card,
  .phase-card,
  .preview-row,
  .route-card {
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.03));
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 16px 32px rgba(0,0,0,0.14), inset 0 1px 0 rgba(255,255,255,0.05);
  }
  .card {
    width: min(320px, 100%);
    padding: 18px;
    display: grid;
    gap: 10px;
  }
  input, button, textarea, select {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.055);
    color: inherit;
    font: inherit;
  }
  textarea {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
    min-height: 88px;
  }
  .compose-panel {
    margin-bottom: 24px;
    padding: 18px 20px;
    display: grid;
    gap: 14px;
  }
  .compose-controls {
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
  }
  .compose-controls label,
  .steering-grid label {
    display: grid;
    gap: 8px;
  }
  .steering-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
  }
  .gen-action-btn { color: #7affc6; border-color: rgba(122,255,198,0.3); }
  .draft-head {
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
  }
  .intent-summary-grid,
  .phase-strip {
    display: grid;
    gap: 12px;
  }
  .intent-summary-grid {
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }
  .phase-strip {
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  }
  .summary-card,
  .phase-card,
  .route-card {
    padding: 14px;
    display: grid;
    gap: 6px;
  }
  .summary-label {
    font-size: 0.68rem;
    color: #88a8bf;
    text-transform: uppercase;
    letter-spacing: 0.14em;
  }
  .narrative {
    font-size: 0.9rem;
    color: #d7e5f3;
    line-height: 1.6;
    margin: 0;
    padding: 12px 14px;
    border-left: 2px solid rgba(122,255,198,0.32);
    background: rgba(255,255,255,0.03);
    border-radius: 0 12px 12px 0;
  }
  .route-option {
    display: inline-flex;
    align-items: center;
    padding: 6px 10px;
    border-radius: 999px;
    background: rgba(122,255,198,0.08);
    color: #cdeee2;
  }
  .preview-list {
    display: grid;
    gap: 8px;
    max-height: 620px;
    overflow-y: auto;
  }
  .preview-row {
    padding: 12px 14px;
    display: grid;
    grid-template-columns: 32px minmax(0, 1fr) 120px auto auto;
    gap: 12px;
    align-items: center;
  }
  .preview-pos { color: #6a8aab; text-align: right; }
  .preview-info, .preview-phase, .reason-detail { display: grid; gap: 2px; }
  .preview-info strong, .reason-badge { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .preview-phase {
    padding: 4px 8px;
    border-radius: 10px;
    background: rgba(255,255,255,0.05);
  }
  .reason-badge {
    font-size: 0.72rem;
    color: #a8c4e0;
    max-width: 320px;
  }
  .reason-detail {
    grid-column: 2 / -1;
    color: #a8c4e0;
  }
  .proof-inline {
    grid-column: 2 / -1;
    padding-top: 8px;
    border-top: 1px solid rgba(255,255,255,0.06);
    display: grid;
    gap: 6px;
  }
  code { color: #a8c4e0; }
  .generate-btn { color: #a8c4e0; }

  @media (max-width: 980px) {
    .preview-row {
      grid-template-columns: 32px minmax(0, 1fr);
    }
    .preview-phase,
    .reason-badge,
    .preview-actions {
      grid-column: 2;
    }
  }
</style>

<script lang="ts">
  import { goto } from "$app/navigation";
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import {
    setComposerText,
    setWorkspaceArtist,
    setWorkspaceBridgeActions,
    setWorkspaceExplanation,
    setWorkspacePage,
    setWorkspaceProvenance,
    setWorkspaceTrack
  } from "$lib/stores/workspace";
  import type { ArtistProfile, ExplainPayload, RelatedArtist, TrackEnrichmentResult } from "$lib/types";

  let profile: ArtistProfile | null = null;
  let loading = true;
  let error = "";

  // G-064: Related artists + discovery
  let relatedArtists: RelatedArtist[] = [];
  let relatedLoading = false;
  let playSimilarBusy = false;
  let bridgeBusy = false;
  let bridgeTarget: RelatedArtist | null = null;
  let huntMessage = "";
  let expandedExplain: Record<number, ExplainPayload | "loading"> = {};
  let expandedProof: Record<number, TrackEnrichmentResult | "loading"> = {};

  async function loadProfile() {
    loading = true;
    error = "";
    relatedArtists = [];
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
        setWorkspacePage(
          "Artist",
          artistName,
          "Artist context could not be loaded from the local library.",
          "context"
        );
      } else {
        setWorkspacePage(
          "Artist",
          profile.artist,
          "Trace related artists, bridge actions, and library tracks without leaving the oracle shell.",
          "provenance"
        );
        setWorkspaceArtist(profile.artist);
        setWorkspaceProvenance(profile.provenance, profile.topTracks[0] ?? null);
        // Load related artists in background
        await loadRelated(profile.artist);
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load artist profile.";
    } finally {
      loading = false;
    }
  }

  async function loadRelated(artistName: string) {
    relatedLoading = true;
    try {
      relatedArtists = await api.getRelatedArtists(artistName, 8);
      setWorkspaceBridgeActions(
        relatedArtists.slice(0, 4).map((related) => ({
          label: related.name,
          href: `/artists/${encodeURIComponent(related.name)}`,
          detail: related.why,
          emphasis: related.localTrackCount > 0 ? "accent" : "default"
        })),
        artistName
      );
    } finally {
      relatedLoading = false;
    }
  }

  async function playTrack(trackId: number) {
    const playback = await api.playTrack(trackId);
    shell.update((s) => ({ ...s, playback }));
    setWorkspaceTrack(profile?.topTracks.find((track) => track.id === trackId) ?? playback.currentTrack ?? null);
  }

  async function queueTrack(trackId: number) {
    const queue = await api.enqueueTracks([trackId]);
    shell.update((s) => ({ ...s, queue }));
    setWorkspaceTrack(profile?.topTracks.find((track) => track.id === trackId) ?? null);
  }

  async function playArtist(): Promise<void> {
    if (!profile) return;
    const playback = await api.playArtist(profile.artist);
    shell.update((s) => ({ ...s, playback }));
    const queue = await api.queue();
    shell.update((s) => ({ ...s, queue }));
    setWorkspaceArtist(profile.artist);
    setWorkspaceTrack(playback.currentTrack ?? profile.topTracks[0] ?? null);
  }

  async function queueArtist(): Promise<void> {
    if (!profile) return;
    const trackIds = profile.topTracks.map((t) => t.id);
    if (!trackIds.length) return;
    const queue = await api.enqueueTracks(trackIds);
    shell.update((s) => ({ ...s, queue }));
    setWorkspaceArtist(profile.artist);
    setWorkspaceTrack(profile.topTracks[0] ?? null);
  }

  async function playAlbum(albumTitle: string): Promise<void> {
    if (!profile) return;
    const playback = await api.playAlbum(profile.artist, albumTitle);
    shell.update((s) => ({ ...s, playback }));
    const queue = await api.queue();
    shell.update((s) => ({ ...s, queue }));
    setWorkspaceArtist(profile.artist);
    setWorkspaceTrack(playback.currentTrack ?? profile.topTracks.find((track) => track.album === albumTitle) ?? null);
  }

  // G-064: Play similar from a related artist
  async function playSimilar(relatedName: string): Promise<void> {
    playSimilarBusy = true;
    try {
      const queue = await api.playSimilarToArtist(relatedName, 20);
      shell.update((s) => ({ ...s, queue }));
      setWorkspaceArtist(relatedName);
      setWorkspaceBridgeActions(
        [
          {
            label: `Open ${relatedName}`,
            href: `/artists/${encodeURIComponent(relatedName)}`,
            detail: "Inspect this related artist in context."
          },
          {
            label: "Review queue",
            href: "/queue",
            detail: "Carry the similar-artist mix into active listening."
          }
        ],
        relatedName
      );
    } finally {
      playSimilarBusy = false;
    }
  }

  // G-064: Queue Bridge - mix current artist + related artist tracks
  async function queueBridge(related: RelatedArtist): Promise<void> {
    if (!profile) return;
    bridgeBusy = true;
    bridgeTarget = related;
    try {
      // First get similar track IDs from related artist (as queue items)
      const similarQueue = await api.playSimilarToArtist(related.name, 10);
      // Then enqueue current artist top tracks
      const myIds = profile.topTracks.slice(0, 5).map(t => t.id);
      if (myIds.length) {
        const bridgedQueue = await api.enqueueTracks(myIds);
        shell.update((s) => ({ ...s, queue: bridgedQueue }));
      } else {
        shell.update((s) => ({ ...s, queue: similarQueue }));
      }
      setWorkspaceBridgeActions(
        [
          {
            label: `${profile.artist} -> ${related.name}`,
            href: "/queue",
            detail: "Bridge mix queued for immediate review.",
            emphasis: "accent"
          },
          {
            label: `Open ${related.name}`,
            href: `/artists/${encodeURIComponent(related.name)}`,
            detail: "Inspect the related artist profile next."
          }
        ],
        profile.artist
      );
    } finally {
      bridgeBusy = false;
      bridgeTarget = null;
    }
  }

  function strengthColor(s: number): string {
    if (s >= 0.7) return "#7affc6";
    if (s >= 0.4) return "#ffd166";
    return "#9cb2c7";
  }

  // G-064: Add a non-library related artist to acquisition queue
  async function huntArtist(artistName: string): Promise<void> {
    huntMessage = "";
    try {
      await api.addToAcquisitionQueue(artistName, "discography", undefined, "discovery");
      huntMessage = `Added ${artistName} to acquisition queue.`;
    } catch (e) {
      huntMessage = e instanceof Error ? e.message : "Failed to queue.";
    }
  }

  function openLyraPrompt(prompt: string): Promise<void> {
    const trimmed = prompt.trim();
    setComposerText(trimmed);
    return goto(`/playlists?compose=1&prompt=${encodeURIComponent(trimmed)}`);
  }

  async function toggleTrackExplain(trackId: number): Promise<void> {
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
      const track = profile?.topTracks.find((item) => item.id === trackId) ?? null;
      setWorkspaceExplanation(payload, track);
    } catch {
      const next = { ...expandedExplain };
      delete next[trackId];
      expandedExplain = next;
    }
  }

  async function toggleTrackProof(trackId: number): Promise<void> {
    if (expandedProof[trackId]) {
      const next = { ...expandedProof };
      delete next[trackId];
      expandedProof = next;
      return;
    }
    expandedProof = { ...expandedProof, [trackId]: "loading" };
    try {
      const payload = await api.getTrackEnrichment(trackId);
      expandedProof = { ...expandedProof, [trackId]: payload };
      const track = profile?.topTracks.find((item) => item.id === trackId) ?? null;
      setWorkspaceProvenance(payload.entries, track);
    } catch {
      const next = { ...expandedProof };
      delete next[trackId];
      expandedProof = next;
    }
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
        <p class="muted">{profile.trackCount} tracks - {profile.albumCount} albums</p>
        {#if profile.genres.length}
          <p class="genres">{profile.genres.join(" | ")}</p>
        {/if}
        {#if profile.lastfmUrl}
          <a href={profile.lastfmUrl} target="_blank" rel="noopener">Last.fm profile</a>
        {/if}
        <div class="actions hero-actions">
          <button on:click={playArtist}>Play Artist</button>
          <button on:click={queueArtist}>Queue Artist</button>
          <button on:click={() => openLyraPrompt(`bridge from ${profile!.artist} into late-night adjacency`)}>
            Bridge with Lyra
          </button>
        </div>
        <div class="route-chip-row">
          <button class="route-chip" on:click={() => openLyraPrompt(`give me three exits from ${profile!.artist}, one safe, one interesting, one dangerous`)}>
            Three exits
          </button>
          <button class="route-chip" on:click={() => openLyraPrompt(`leave this genre around ${profile!.artist}, keep the wound`)}>
            Keep the wound
          </button>
          <button class="route-chip" on:click={() => openLyraPrompt(`same pulse as ${profile!.artist}, different world`)}>
            Same pulse
          </button>
        </div>
      </div>
    </header>

    <section class="panel">
      <div class="panel-head">
        <p class="eyebrow">Identity</p>
        {#if profile.primaryMbid}
          <code class="mbid-pill">{profile.primaryMbid}</code>
        {/if}
      </div>
      <div class="identity-grid">
        <div class="identity-card">
          <span class="identity-label">Identity confidence</span>
          <strong>{Math.round(profile.identityConfidence * 100)}%</strong>
        </div>
        <div class="identity-card">
          <span class="identity-label">Evidence sources</span>
          <strong>{profile.provenance.length}</strong>
        </div>
      </div>
      {#if profile.provenance.length}
        <div class="provenance-list">
          {#each profile.provenance as entry}
            <div class="prov-row">
              <div>
                <strong>{entry.provider}</strong>
                <small>{entry.status} - {Math.round(entry.confidence * 100)}%</small>
              </div>
              <div class="prov-copy">
                {#if entry.mbid}
                  <code>{entry.mbid}</code>
                {:else if entry.note}
                  <small>{entry.note}</small>
                {:else if entry.releaseTitle}
                  <small>{entry.releaseTitle}</small>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>

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
      <!-- G-064: Related artists with connection strength and Play Similar -->
      <article class="panel">
        <p class="eyebrow">Related Artists</p>
        {#if relatedLoading}
          <p class="muted">Loading related artists...</p>
        {:else if relatedArtists.length === 0}
          <p class="muted">No related artists found. Build listening history to discover connections.</p>
        {:else}
          {#each relatedArtists as related}
            <div class="related-row">
              <div class="related-info">
                <a class="related-name" href={`/artists/${encodeURIComponent(related.name)}`}>{related.name}</a>
                <div class="strength-row">
                  <span class="conn-type">{related.connectionType}</span>
                  <div class="strength-bar-bg">
                    <div class="strength-bar" style="width:{Math.round(related.connectionStrength*100)}%; background:{strengthColor(related.connectionStrength)}"></div>
                  </div>
                  <span class="strength-label" style="color:{strengthColor(related.connectionStrength)}">{Math.round(related.connectionStrength*100)}%</span>
                </div>
                {#if related.localTrackCount > 0}
                  <small>{related.localTrackCount} local tracks</small>
                {:else}
                  <small class="muted">Not in library</small>
                {/if}
                <small class="route-why">{related.why}</small>
                <small>Preserves: {related.preserves.join(", ")}</small>
                <small>Changes: {related.changes.join(", ")}</small>
                <small class="route-risk">{related.riskNote}</small>
              </div>
              <div class="related-actions">
                {#if related.localTrackCount > 0}
                  <button class="sim-btn" disabled={playSimilarBusy} on:click={() => playSimilar(related.name)}>
                    {playSimilarBusy ? 'Working...' : 'Play Similar'}
                  </button>
                  <button class="bridge-btn" disabled={bridgeBusy}
                    on:click={() => queueBridge(related)}
                    title="Queue bridge: mix current artist + {related.name}">
                    {bridgeBusy && bridgeTarget?.name === related.name ? 'Working...' : 'Queue Bridge'}
                  </button>
                  <button class="sim-btn" on:click={() => openLyraPrompt(`bridge from ${profile!.artist} into ${related.name}, but tell me the rewarding risk`)}>
                    Ask Lyra
                  </button>
                {:else}
                  <button class="hunt-btn" on:click={() => huntArtist(related.name)}
                    title="Add {related.name} to acquisition queue">
                    Hunt
                  </button>
                {/if}
              </div>
            </div>
          {/each}
        {/if}

        <!-- Fallback: co-play connections from profile -->
        {#if relatedArtists.length === 0 && profile.connections.length > 0}
          <p class="eyebrow" style="margin-top:12px">Co-play Connections</p>
          {#each profile.connections as connection}
            <a class="conn-row" href={`/artists/${encodeURIComponent(connection.artist)}`}>
              <span>{connection.artist}</span>
              <small>{connection.score} co-plays</small>
            </a>
          {/each}
        {/if}
        {#if huntMessage}
          <p class="muted" style="margin-top:8px;font-size:0.8rem">{huntMessage}</p>
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
              <button on:click={() => openLyraPrompt(`start from ${track.artist} - ${track.title} and take me somewhere adjacent but not the canon`)}>
                Route
              </button>
              <button on:click={() => toggleTrackExplain(track.id)}>
                {expandedExplain[track.id] ? "Hide Why" : "Why"}
              </button>
              <button on:click={() => toggleTrackProof(track.id)}>
                {expandedProof[track.id] ? "Hide Proof" : "Proof"}
              </button>
            </div>
          </div>
          {#if expandedExplain[track.id]}
            <div class="track-detail-panel">
              {#if expandedExplain[track.id] === "loading"}
                <small class="muted">Loading Lyra read...</small>
              {:else}
                {@const payload = expandedExplain[track.id] as ExplainPayload}
                {#each payload.reasons as reason}
                  <small class="route-why">{reason}</small>
                {/each}
                <small class="muted">Confidence {Math.round(payload.confidence * 100)}%</small>
              {/if}
            </div>
          {/if}
          {#if expandedProof[track.id]}
            <div class="track-detail-panel proof-panel">
              {#if expandedProof[track.id] === "loading"}
                <small class="muted">Loading provenance...</small>
              {:else}
                {@const payload = expandedProof[track.id] as TrackEnrichmentResult}
                {#each payload.entries.slice(0, 3) as entry}
                  <small>{entry.provider}: {entry.status} - {Math.round(entry.confidence * 100)}%</small>
                {/each}
              {/if}
            </div>
          {/if}
        {/each}
      </article>
    </section>
  {/if}
</section>

<style>
  .artist-page { display: grid; gap: 16px; }
  .hero, .panel { border-radius: 14px; background: rgba(255,255,255,0.05); padding: 16px; }
  .hero { display: grid; grid-template-columns: 120px 1fr; gap: 14px; }
  .panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .hero-art { width: 120px; height: 120px; object-fit: cover; border-radius: 12px; }
  .hero-art.fallback { display: grid; place-items: center; background: rgba(255,255,255,0.12); font-size: 2rem; }
  .eyebrow, .muted, small { color: #9cb2c7; }
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; }
  .genres { color: #d0e8f8; margin-top: 4px; }
  .route-chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
  .route-chip { padding: 6px 11px; border-radius: 999px; font-size: 0.78rem; }
  .mbid-pill { font-size: 0.72rem; color: #a8c4e0; }
  .identity-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
  .identity-card { border-radius: 10px; background: rgba(255,255,255,0.04); padding: 10px 12px; display: grid; gap: 4px; }
  .identity-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.12em; color: #6a8aab; }
  .provenance-list { display: grid; gap: 8px; }
  .prov-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-top: 1px solid rgba(255,255,255,0.08); }
  .prov-copy { display: grid; justify-items: end; text-align: right; }
  .prov-copy code { font-size: 0.72rem; color: #a8c4e0; }
  .grid { display: grid; grid-template-columns: 1fr 1.3fr; gap: 16px; }
  .conn-row, .track-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }
  .track-detail-panel {
    display: grid;
    gap: 4px;
    padding: 10px 12px;
    margin: 0 0 6px;
    border-radius: 10px;
    background: rgba(255,255,255,0.035);
  }
  .proof-panel { background: rgba(122,255,198,0.05); }
  .track-row:last-child, .conn-row:last-child { border-bottom: none; }
  .actions { display: flex; gap: 8px; }
  .hero-actions { margin-top: 10px; }
  .albums-list { margin-top: 12px; display: grid; gap: 6px; }
  .album-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }
  button { padding: 6px 10px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); color: inherit; cursor: pointer; }

  /* G-064: Related artists */
  .related-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  .related-row:last-child { border-bottom: none; }
  .related-info { display: grid; gap: 4px; flex: 1; min-width: 0; }
  .related-name { color: #a8c4e0; text-decoration: underline; font-size: 0.9rem; }
  .strength-row { display: flex; align-items: center; gap: 6px; }
  .conn-type { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.1em; color: #6a8aab; flex-shrink: 0; }
  .strength-bar-bg { width: 80px; height: 4px; border-radius: 2px; background: rgba(255,255,255,0.08); flex-shrink: 0; }
  .strength-bar { height: 100%; border-radius: 2px; transition: width 0.3s ease; }
  .strength-label { font-size: 0.68rem; flex-shrink: 0; }
  .related-actions { display: flex; gap: 6px; flex-shrink: 0; }
  .route-why { color: #d9e7f1; line-height: 1.4; }
  .route-risk { color: #f0c983; line-height: 1.4; }
  .sim-btn { color: #7affc6; border-color: rgba(122,255,198,0.3); font-size: 0.78rem; padding: 4px 10px; }
  .bridge-btn { color: #ffd166; border-color: rgba(255,209,102,0.3); font-size: 0.78rem; padding: 4px 10px; }
  .hunt-btn { color: #ff9f7a; border-color: rgba(255,159,122,0.3); font-size: 0.78rem; padding: 4px 10px; }

  @media (max-width: 900px) {
    .hero { grid-template-columns: 1fr; }
    .hero-art { width: 100%; max-width: 240px; }
    .identity-grid { grid-template-columns: 1fr; }
    .grid { grid-template-columns: 1fr; }
  }
</style>

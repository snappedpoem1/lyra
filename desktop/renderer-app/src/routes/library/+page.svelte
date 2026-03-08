<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import { shell } from "$lib/stores/lyra";
  import { setWorkspacePage, setWorkspaceProvenance, setWorkspaceTrack } from "$lib/stores/workspace";
  import type { CurationLogEntry, DuplicateCluster, EnrichmentEntry, GeneratedPlaylist, LibraryCleanupPreview, PlaylistSummary, TrackEnrichmentResult, TrackRecord, TrackScores } from "$lib/types";

  const SCORE_DIMS = ["energy","valence","tension","density","warmth","movement","space","rawness","complexity","nostalgia"] as const;

  let query = "";
  let tracks: TrackRecord[] = [];
  let playlists: PlaylistSummary[] = [];
  let addToPlaylistTrackId: number | null = null;
  let expandedScores: Record<number, TrackScores | null | "loading"> = {};
  let expandedEnrich: Record<number, Record<string, unknown> | null | "loading"> = {};
  let expandedEnrichV2: Record<number, TrackEnrichmentResult | null | "loading"> = {};
  let duplicates: DuplicateCluster[] = [];
  let dupsLoaded = false;
  let dupsOpen = false;
  let enrichLibraryPending = false;
  let viewMode: "all" | "liked" | "new" = "all";

  // G-062 Curation state
  let curationTab: "duplicates" | "cleanup" | "log" = "duplicates";
  let curationOpen = false;
  let cleanupPreview: LibraryCleanupPreview | null = null;
  let cleanupLoading = false;
  let curationLog: CurationLogEntry[] = [];
  let curationLogLoading = false;
  let resolvingCluster: number | null = null;

  async function loadTracks() {
    if (viewMode === "liked") {
      tracks = await api.listLikedTracks();
    } else if (viewMode === "new") {
      tracks = await api.tracks(undefined, "recently_added");
    } else {
      tracks = await api.tracks(query);
    }
  }

  async function toggleLike(track: TrackRecord) {
    const nowLiked = await api.toggleLike(track.id);
    tracks = tracks.map((t) => t.id === track.id ? { ...t, liked: nowLiked, likedAt: nowLiked ? new Date().toISOString() : null } : t);
    setWorkspaceTrack(track);
  }

  async function play(trackId: number) {
    const playback = await api.playTrack(trackId);
    shell.update((state) => ({ ...state, playback }));
    setWorkspaceTrack(tracks.find((item) => item.id === trackId) ?? null);
  }

  async function queue(trackId: number) {
    const updated = await api.enqueueTracks([trackId]);
    shell.update((state) => ({ ...state, queue: updated }));
    setWorkspaceTrack(tracks.find((item) => item.id === trackId) ?? null);
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
    setWorkspaceTrack(tracks.find((item) => item.id === trackId) ?? null);
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
      // Also load the structured enrichment result
      const structured = await api.getTrackEnrichment(trackId);
      expandedEnrichV2 = { ...expandedEnrichV2, [trackId]: structured };
      setWorkspaceProvenance(structured.entries, tracks.find((item) => item.id === trackId) ?? null);
    } catch {
      expandedEnrich = { ...expandedEnrich, [trackId]: null };
    }
  }

  async function refreshEnrich(trackId: number) {
    expandedEnrich = { ...expandedEnrich, [trackId]: "loading" };
    try {
      const result = await api.refreshTrackEnrichment(trackId);
      expandedEnrich = { ...expandedEnrich, [trackId]: result };
      const structured = await api.getTrackEnrichment(trackId);
      expandedEnrichV2 = { ...expandedEnrichV2, [trackId]: structured };
      setWorkspaceProvenance(structured.entries, tracks.find((item) => item.id === trackId) ?? null);
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

  onMount(() => {
    setWorkspacePage(
      "Library",
      "Local catalog",
      "Inspect tracks, enrichment evidence, and curation risk inside the canonical shell.",
      "provenance"
    );
    loadTracks();
  });

  async function loadDuplicates() {
    duplicates = await api.findDuplicates();
    dupsLoaded = true;
    dupsOpen = true;
    curationOpen = true;
  }

  // G-062 curation
  async function resolveCluster(keepId: number, removeIds: number[], clusterIdx: number) {
    resolvingCluster = clusterIdx;
    try {
      await api.resolveDuplicateCluster(keepId, removeIds);
      duplicates = duplicates.filter((_, i) => i !== clusterIdx);
    } finally {
      resolvingCluster = null;
    }
  }

  async function loadCleanupPreview() {
    cleanupLoading = true;
    try {
      cleanupPreview = await api.previewLibraryCleanup();
    } finally {
      cleanupLoading = false;
    }
  }

  async function loadCurationLog() {
    curationLogLoading = true;
    try {
      curationLog = await api.getCurationLog();
    } finally {
      curationLogLoading = false;
    }
  }

  async function undoCuration(logId: number) {
    await api.undoCuration(logId);
    await loadCurationLog();
  }

  function severityColor(severity: string): string {
    if (severity === "high") return "#ff6b8a";
    if (severity === "medium") return "#ffd166";
    return "#9cb2c7";
  }

  function stateColor(state: string): string {
    if (state === "enriched") return "#7affc6";
    if (state === "failed") return "#ff6b8a";
    return "#9cb2c7";
  }
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Library</p>
    <h2>Local catalog</h2>
    <div class="view-tabs">
      <button class="tab-btn" class:active={viewMode === 'all'} on:click={() => { viewMode = 'all'; loadTracks(); }}>All</button>
      <button class="tab-btn" class:active={viewMode === 'liked'} on:click={() => { viewMode = 'liked'; loadTracks(); }}>Liked</button>
    </div>
  </div>
  <div class="search-row">
    <input bind:value={query} placeholder="Search title, artist, or album"
      disabled={viewMode === 'liked'}
      on:keydown={(e) => e.key === 'Enter' && loadTracks()} />
    <button on:click={loadTracks} disabled={viewMode === 'liked'}>Search</button>
    <button class="dups-btn" on:click={() => dupsLoaded ? (curationOpen = !curationOpen) : loadDuplicates()}
      title="Curation workflows">Curation{duplicates.length ? ` (${duplicates.length} dups)` : ''}</button>
    <button class="enrich-btn" on:click={runEnrichLibrary} disabled={enrichLibraryPending}
      title="Enrich up to 50 unenriched tracks via MusicBrainz">
      {enrichLibraryPending ? 'Enriching...' : 'Enrich Library'}
    </button>
  </div>
</section>

<!-- G-062: Curation Panel -->
{#if curationOpen}
  <section class="curation-section">
    <div class="curation-tabs">
      <button class="tab-btn" class:active={curationTab === 'duplicates'}
        on:click={() => { curationTab = 'duplicates'; if (!dupsLoaded) loadDuplicates(); }}>
        Duplicates{duplicates.length ? ` (${duplicates.length})` : ''}
      </button>
      <button class="tab-btn" class:active={curationTab === 'cleanup'}
        on:click={() => { curationTab = 'cleanup'; if (!cleanupPreview) loadCleanupPreview(); }}>
        Cleanup Preview
      </button>
      <button class="tab-btn" class:active={curationTab === 'log'}
        on:click={() => { curationTab = 'log'; if (!curationLog.length) loadCurationLog(); }}>
        Curation Log
      </button>
    </div>

    {#if curationTab === 'duplicates'}
      {#if !dupsLoaded}
        <p class="muted">Loading...</p>
      {:else if duplicates.length === 0}
        <p class="muted">No duplicate tracks found.</p>
      {:else}
        {#each duplicates as cluster, ci}
          <div class="dup-cluster">
            {#each cluster.tracks as track, ti}
              <div class="dup-row">
                <span class="dup-title">{track.title}</span>
                <span class="dup-artist">{track.artist}</span>
                <span class="dup-path">{track.path}</span>
                <button on:click={() => play(track.id)}>Play</button>
                <button class="keep-btn"
                  disabled={resolvingCluster === ci}
                  on:click={() => {
                    const removeIds = cluster.tracks.filter((_, i) => i !== ti).map(t => t.id);
                    resolveCluster(track.id, removeIds, ci);
                  }}>
                  {resolvingCluster === ci ? 'Working...' : 'Keep This'}
                </button>
              </div>
            {/each}
          </div>
        {/each}
      {/if}

    {:else if curationTab === 'cleanup'}
      <div class="cleanup-head">
        <button on:click={loadCleanupPreview} disabled={cleanupLoading}>
          {cleanupLoading ? 'Scanning...' : 'Refresh Preview'}
        </button>
      </div>
      {#if !cleanupPreview}
        <p class="muted">Click "Refresh Preview" to scan for issues.</p>
      {:else if cleanupPreview.issues.length === 0}
        <p class="muted">No library issues detected.</p>
      {:else}
        <div class="cleanup-table">
          {#each cleanupPreview.issues as issue}
            <div class="cleanup-row">
              <span class="badge" style="color:{severityColor(issue.severity)}">{issue.severity}</span>
              <span class="issue-type">{issue.issueType.replace(/_/g, ' ')}</span>
              <span class="issue-current">{issue.currentValue}</span>
              <span class="issue-arrow">-&gt;</span>
              <span class="issue-suggested muted">{issue.suggestedValue}</span>
            </div>
          {/each}
        </div>
      {/if}

    {:else if curationTab === 'log'}
      <div class="cleanup-head">
        <button on:click={loadCurationLog} disabled={curationLogLoading}>
          {curationLogLoading ? 'Loading...' : 'Refresh Log'}
        </button>
      </div>
      {#if curationLog.length === 0}
        <p class="muted">No curation actions yet.</p>
      {:else}
        {#each curationLog as entry}
          <div class="log-row" class:undone={entry.undone}>
            <span class="log-ts muted">{entry.createdAt.slice(0, 16).replace('T', ' ')}</span>
            <span class="log-action">{entry.action}</span>
            <span class="log-detail muted">{entry.detail}</span>
            {#if !entry.undone}
              <button class="undo-btn" on:click={() => undoCuration(entry.logId)}>Undo</button>
            {:else}
              <span class="muted" style="font-size:0.72rem">Undone</span>
            {/if}
          </div>
        {/each}
      {/if}
    {/if}
  </section>
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
          <a class="artist-link" href={`/artists/${encodeURIComponent(track.artist)}`}>{track.artist}</a>
          - {track.album}{track.year ? ` - ${track.year}` : ''}{track.genre ? ` - ${track.genre}` : ''}
          {#if track.bpm}<span class="pill">{Math.round(track.bpm)} BPM</span>{/if}
        </small>
      </div>
      <div class="actions">
        <button class="like-btn" class:liked={track.liked} on:click={() => toggleLike(track)}
          title={track.liked ? 'Unlike' : 'Like'}>{track.liked ? 'Liked' : 'Like'}</button>
        <button on:click={() => play(track.id)}>Play</button>
        <button on:click={() => queue(track.id)}>Queue</button>
        <button on:click={() => openAddToPlaylist(track.id)}>+ Playlist</button>
        <button class="scores-toggle" on:click={() => toggleScores(track.id)}
          title="Show scores">{expandedScores[track.id] !== undefined ? 'Hide' : 'Show'}</button>
        <button class="enrich-toggle" on:click={() => toggleEnrich(track.id)}
          title="Show enrichment data">{expandedEnrich[track.id] !== undefined ? 'Hide' : 'Enrich'}</button>
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
        <div class="score-panel muted-panel"><small>No scores - run legacy import to populate.</small></div>
      {/if}
    {/if}
    {#if expandedEnrich[track.id] !== undefined}
      {#if expandedEnrich[track.id] === "loading"}
        <div class="enrich-panel muted-panel"><small>Fetching enrichment data...</small></div>
      {:else if expandedEnrich[track.id] === null}
        <div class="enrich-panel muted-panel"><small>Enrichment failed.</small></div>
      {:else}
        {@const er = expandedEnrich[track.id] as Record<string, unknown>}
        {@const structuredRaw = expandedEnrichV2[track.id]}
        {@const structured = (structuredRaw && structuredRaw !== "loading") ? structuredRaw as TrackEnrichmentResult : null}
        {@const providers = typeof er.providers === 'object' && er.providers !== null
          ? er.providers as Record<string, unknown>
          : {}}
        {@const mbRaw = providers['musicbrainz'] as Record<string, unknown> | undefined}
        {@const mb = mbRaw?.payload as Record<string, unknown> | undefined}
        {@const lfRaw = providers['lastfm'] as Record<string, unknown> | undefined}
        {@const lf = lfRaw?.payload as Record<string, unknown> | undefined}
        {@const dcRaw = providers['discogs'] as Record<string, unknown> | undefined}
        {@const dc = dcRaw?.payload as Record<string, unknown> | undefined}
        {@const gnRaw = providers['genius'] as Record<string, unknown> | undefined}
        {@const gn = gnRaw?.payload as Record<string, unknown> | undefined}
        {@const lrcRaw = providers['lrc_sidecar'] as Record<string, unknown> | undefined}
        {@const lrc = lrcRaw?.payload as Record<string, unknown> | undefined}
        <div class="enrich-panel">
          <!-- G-061: Enrichment state header -->
          <div class="enrich-section-head">
            <div class="enrich-state-row">
              {#if structured}
                <span class="state-badge" style="color:{stateColor(structured.enrichmentState)}">
                  {structured.enrichmentState === 'enriched' ? 'Enriched' :
                   structured.enrichmentState === 'failed' ? 'Failed' : 'Not Enriched'}
                </span>
                {#if structured.primaryMbid}
                  <span class="mbid-label">MusicBrainz ID</span>
                  <code class="mbid-value">{structured.primaryMbid}</code>
                {/if}
              {/if}
            </div>
            <button class="refresh-btn" on:click={() => refreshEnrich(track.id)} title="Force refresh all enrichment">Refresh</button>
          </div>

          <!-- G-061: Per-provider entries with confidence -->
          {#if structured && structured.entries.length > 0}
            {#each structured.entries as entry}
              <div class="enrich-entry">
                <div class="entry-head">
                  <span class="source-badge">{entry.provider}</span>
                  <span class="state-badge" style="color:{stateColor(entry.status === 'ok' ? 'enriched' : 'failed')}">
                    {entry.status.replace(/_/g, ' ')}
                  </span>
                  <div class="confidence-bar-bg">
                    <div class="confidence-bar" style="width:{Math.round(entry.confidence*100)}%"></div>
                  </div>
                  <span class="confidence-label">{Math.round(entry.confidence*100)}% match</span>
                </div>
                {#if entry.note}
                  <div class="enrich-row">
                    <span class="elabel">Note</span>
                    <span class="evalue">{entry.note}</span>
                  </div>
                {/if}
                {#if entry.mbid}
                  <div class="enrich-row">
                    <span class="elabel">MBID</span>
                    <code class="evalue">{entry.mbid}</code>
                  </div>
                {/if}
                {#if entry.releaseTitle}
                  <div class="enrich-row">
                    <span class="elabel">Release</span>
                    <span class="evalue">{entry.releaseTitle}{entry.releaseDate ? ` - ${entry.releaseDate}` : ''}</span>
                  </div>
                {/if}
                {#if entry.listeners !== null && entry.listeners !== undefined}
                  <div class="enrich-row">
                    <span class="elabel">Listeners</span>
                    <span class="evalue">{entry.listeners.toLocaleString()}</span>
                  </div>
                {/if}
                {#if entry.tags && entry.tags.length > 0}
                  <div class="enrich-row">
                    <span class="elabel">Tags</span>
                    <span class="evalue">{entry.tags.join(' | ')}</span>
                  </div>
                {/if}
                {#if entry.label}
                  <div class="enrich-row">
                    <span class="elabel">Label</span>
                    <span class="evalue">{entry.label}</span>
                  </div>
                {/if}
                {#if entry.year}
                  <div class="enrich-row">
                    <span class="elabel">Year</span>
                    <span class="evalue">{entry.year}</span>
                  </div>
                {/if}
                {#if entry.lyricsUrl}
                  <div class="enrich-row">
                    <span class="elabel">Lyrics</span>
                    <a class="evalue" href={entry.lyricsUrl} target="_blank" rel="noopener">Open on Genius</a>
                  </div>
                {/if}
              </div>
            {/each}
          {:else}
            <!-- Fallback: raw provider display -->
            <div class="enrich-section-head">
              <span class="elabel-section">MusicBrainz</span>
            </div>
            {#if mb && mb.status === 'ok'}
              <div class="enrich-row">
                <span class="elabel">MBID</span>
                <code class="evalue">{mb.recordingMbid ?? '-'}</code>
              </div>
              <div class="enrich-row">
                <span class="elabel">Release</span>
                <span class="evalue">{mb.releaseTitle ?? '-'}{mb.releaseDate ? ` - ${mb.releaseDate}` : ''}</span>
              </div>
              <div class="enrich-row">
                <span class="elabel">Match</span>
                <span class="evalue">{mb.matchScore ?? '-'}%</span>
              </div>
            {:else}
              <span class="muted"><small>MusicBrainz: {mb?.status ?? 'not fetched'}</small></span>
            {/if}

            {#if lf && lf.status === 'ok'}
              <div class="enrich-section-head"><span class="elabel-section">Last.fm</span></div>
              <div class="enrich-row">
                <span class="elabel">Listeners</span>
                <span class="evalue">{(lf.listeners as number ?? 0).toLocaleString()}</span>
              </div>
              {#if Array.isArray(lf.tags) && (lf.tags as string[]).length}
                <div class="enrich-row">
                  <span class="elabel">Tags</span>
                  <span class="evalue">{(lf.tags as string[]).join(' | ')}</span>
                </div>
              {/if}
            {:else if lf && lf.status === 'not_configured'}
              <div class="enrich-section-head"><span class="elabel-section">Last.fm</span></div>
              <span class="muted"><small>Not configured - add API key in Settings</small></span>
            {/if}

            {#if dc && dc.status === 'ok'}
              <div class="enrich-section-head"><span class="elabel-section">Discogs</span></div>
              {#if dc.year}<div class="enrich-row"><span class="elabel">Year</span><span class="evalue">{dc.year}</span></div>{/if}
              {#if Array.isArray(dc.genres) && (dc.genres as string[]).length}
                <div class="enrich-row">
                  <span class="elabel">Genre</span>
                  <span class="evalue">{(dc.genres as string[]).join(' | ')}</span>
                </div>
              {/if}
              {#if dc.label}<div class="enrich-row"><span class="elabel">Label</span><span class="evalue">{dc.label}</span></div>{/if}
              {#if dc.country}<div class="enrich-row"><span class="elabel">Country</span><span class="evalue">{dc.country}</span></div>{/if}
            {/if}

            {#if gn && gn.status === 'ok'}
              <div class="enrich-section-head"><span class="elabel-section">Genius</span></div>
              <div class="enrich-row">
                <span class="elabel">Lyrics</span>
                <a class="evalue" href={gn.url as string} target="_blank" rel="noopener">{gn.fullTitle ?? 'Open on Genius'}</a>
              </div>
            {/if}

            {#if lrc && lrc.status === 'ok'}
              <div class="enrich-section-head"><span class="elabel-section">Lyrics (LRC)</span></div>
              <pre class="lrc-content">{lrc.lrcContent}</pre>
            {/if}
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
  .artist-link { color: #a8c4e0; text-decoration: underline; }
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
  .like-btn { color: #9cb2c7; font-size: 1rem; padding: 6px 10px; }
  .like-btn.liked { color: #ff6b8a; }
  .view-tabs { display: flex; gap: 6px; margin-top: 8px; }
  .tab-btn { padding: 5px 14px; border-radius: 20px; font-size: 0.78rem; border: 1px solid rgba(255,255,255,0.12); background: transparent; color: #9cb2c7; cursor: pointer; }
  .tab-btn.active { background: rgba(255,255,255,0.1); color: #d0e8f8; }
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
  .enrich-state-row { display: flex; align-items: center; gap: 10px; flex: 1; }
  .state-badge { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }
  .mbid-label { font-size: 0.68rem; color: #6a8aab; text-transform: uppercase; letter-spacing: 0.12em; }
  .mbid-value { font-size: 0.72rem; color: #a8c4e0; font-family: monospace; }
  .enrich-entry { padding: 8px 0; border-top: 1px solid rgba(255,255,255,0.06); }
  .entry-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .source-badge {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    padding: 2px 7px;
    border-radius: 6px;
    background: rgba(168,196,224,0.12);
    color: #a8c4e0;
    flex-shrink: 0;
  }
  .confidence-bar-bg { flex: 1; height: 4px; border-radius: 2px; background: rgba(255,255,255,0.08); max-width: 120px; }
  .confidence-bar { height: 100%; border-radius: 2px; background: linear-gradient(90deg, #34cfab, #5ad1ff); }
  .confidence-label { font-size: 0.68rem; color: #9cb2c7; flex-shrink: 0; }
  .enrich-row { display: flex; gap: 10px; align-items: baseline; }
  .elabel { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.12em; color: #9cb2c7; min-width: 90px; }
  .evalue { font-size: 0.8rem; color: #d0e8f8; word-break: break-all; }
  code.evalue { font-family: monospace; font-size: 0.72rem; color: #a8c4e0; }
  .enrich-section-head { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; }
  .elabel-section { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.18em; color: #6a8aab; }
  .refresh-btn { padding: 3px 8px; font-size: 0.68rem; color: #a8c4e0; }
  a.evalue { color: #a8c4e0; text-decoration: underline; }
  .lrc-content {
    font-size: 0.72rem;
    color: #9cb2c7;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
    padding: 6px 10px;
    border-radius: 8px;
    background: rgba(255,255,255,0.03);
    font-family: monospace;
  }
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
  /* G-062: Curation section */
  .curation-section {
    margin-bottom: 18px;
    padding: 14px 16px;
    border-radius: 14px;
    background: rgba(255,255,255,0.04);
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .curation-tabs { display: flex; gap: 8px; margin-bottom: 4px; }
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
  .keep-btn { color: #7affc6; border-color: rgba(122,255,198,0.3); }
  .cleanup-head { display: flex; gap: 10px; }
  .cleanup-table { display: flex; flex-direction: column; gap: 6px; }
  .cleanup-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 10px;
    border-radius: 8px;
    background: rgba(255,255,255,0.03);
    font-size: 0.82rem;
  }
  .issue-type { text-transform: capitalize; min-width: 140px; color: #d0e8f8; }
  .issue-current { color: #9cb2c7; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .issue-arrow { color: #6a8aab; flex-shrink: 0; }
  .issue-suggested { font-size: 0.75rem; flex: 1; }
  .badge { font-size: 0.68rem; padding: 2px 7px; border-radius: 5px; font-weight: 600; flex-shrink: 0; }
  .log-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 10px;
    border-radius: 8px;
    background: rgba(255,255,255,0.03);
    font-size: 0.82rem;
  }
  .log-row.undone { opacity: 0.5; }
  .log-ts { min-width: 140px; font-size: 0.72rem; flex-shrink: 0; }
  .log-action { font-weight: 600; min-width: 120px; color: #d0e8f8; flex-shrink: 0; }
  .log-detail { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .undo-btn { color: #ffd166; border-color: rgba(255,209,102,0.3); padding: 4px 10px; font-size: 0.75rem; flex-shrink: 0; }
</style>

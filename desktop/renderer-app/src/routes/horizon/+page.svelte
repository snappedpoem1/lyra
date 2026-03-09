<script lang="ts">
  import { onMount } from "svelte";
  import { setWorkspacePage } from "$lib/stores/workspace";

  type IndexerHealth = {
    name: string;
    enabled: boolean;
    status: string;
    lastCheck?: string;
    categories?: number[];
  };

  type UpcomingRelease = {
    artist: string;
    title: string;
    publishDate?: string;
    seeders?: number;
    size?: number;
    indexer?: string;
  };

  let indexers: IndexerHealth[] = [];
  let upcoming: UpcomingRelease[] = [];
  let loadingIndexers = false;
  let loadingUpcoming = false;
  let error: string | null = null;
  let daysAhead = 30;

  onMount(async () => {
    setWorkspacePage(
      "Horizon",
      "Release Intelligence",
      "Monitor upcoming releases and indexer health from Prowlarr"
    );
    await loadIndexerHealth();
    await loadUpcomingReleases();
  });

  async function loadIndexerHealth(): Promise<void> {
    loadingIndexers = true;
    error = null;
    try {
      const response = await fetch("/api/horizon/indexers");
      const data = await response.json();
      if (data.ok) {
        indexers = data.indexers || [];
      } else {
        error = data.error || "Failed to load indexer health";
      }
    } catch (err) {
      error = `Failed to fetch indexer health: ${err}`;
    } finally {
      loadingIndexers = false;
    }
  }

  async function loadUpcomingReleases(): Promise<void> {
    loadingUpcoming = true;
    error = null;
    try {
      const response = await fetch(`/api/horizon/upcoming?days=${daysAhead}`);
      const data = await response.json();
      if (data.ok) {
        upcoming = data.releases || [];
      } else {
        error = data.error || "Failed to load upcoming releases";
      }
    } catch (err) {
      error = `Failed to fetch upcoming releases: ${err}`;
    } finally {
      loadingUpcoming = false;
    }
  }

  function formatBytes(bytes?: number): string {
    if (!bytes) return "—";
    const gb = bytes / (1024 * 1024 * 1024);
    if (gb >= 1) return `${gb.toFixed(2)} GB`;
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(2)} MB`;
  }

  function formatDate(dateStr?: string): string {
    if (!dateStr) return "—";
    const date = new Date(dateStr);
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }
</script>

<div class="horizon-container">
  <div class="horizon-header">
    <h1>Horizon Intelligence</h1>
    <p class="subtitle">Release discovery and indexer monitoring</p>
  </div>

  {#if error}
    <div class="error-banner">
      <span class="error-icon">⚠</span>
      <span>{error}</span>
    </div>
  {/if}

  <div class="panels">
    <!-- Indexer Health Panel -->
    <section class="panel indexer-health">
      <div class="panel-header">
        <h2>Indexer Health</h2>
        <button on:click={loadIndexerHealth} disabled={loadingIndexers} class="refresh-btn">
          {loadingIndexers ? "Loading..." : "Refresh"}
        </button>
      </div>
      <div class="panel-content">
        {#if loadingIndexers}
          <div class="loading">Loading indexer health...</div>
        {:else if indexers.length === 0}
          <div class="empty">No indexers configured</div>
        {:else}
          <div class="indexer-grid">
            {#each indexers as indexer}
              <div class="indexer-card" class:disabled={!indexer.enabled}>
                <div class="indexer-name">{indexer.name}</div>
                <div class="indexer-status" class:active={indexer.enabled}>
                  {indexer.enabled ? "Active" : "Disabled"}
                </div>
                {#if indexer.lastCheck}
                  <div class="indexer-lastcheck">
                    Last: {formatDate(indexer.lastCheck)}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </section>

    <!-- Upcoming Releases Panel -->
    <section class="panel upcoming-releases">
      <div class="panel-header">
        <h2>Upcoming Releases</h2>
        <div class="controls">
          <label>
            Days ahead:
            <input
              type="number"
              bind:value={daysAhead}
              min="1"
              max="365"
              on:change={loadUpcomingReleases}
              class="days-input"
            />
          </label>
          <button on:click={loadUpcomingReleases} disabled={loadingUpcoming} class="refresh-btn">
            {loadingUpcoming ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>
      <div class="panel-content">
        {#if loadingUpcoming}
          <div class="loading">Loading upcoming releases...</div>
        {:else if upcoming.length === 0}
          <div class="empty">No upcoming releases found</div>
        {:else}
          <div class="release-list">
            {#each upcoming as release}
              <div class="release-card">
                <div class="release-info">
                  <div class="release-artist">{release.artist}</div>
                  <div class="release-title">{release.title}</div>
                </div>
                <div class="release-meta">
                  {#if release.publishDate}
                    <span class="meta-item">📅 {formatDate(release.publishDate)}</span>
                  {/if}
                  {#if release.seeders !== undefined}
                    <span class="meta-item">🌱 {release.seeders}</span>
                  {/if}
                  {#if release.size}
                    <span class="meta-item">💾 {formatBytes(release.size)}</span>
                  {/if}
                  {#if release.indexer}
                    <span class="meta-item">📡 {release.indexer}</span>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </section>
  </div>
</div>

<style>
  .horizon-container {
    padding: 2rem;
    max-width: 1400px;
    margin: 0 auto;
  }

  .horizon-header {
    margin-bottom: 2rem;
  }

  .horizon-header h1 {
    font-size: 2rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }

  .subtitle {
    color: var(--text-secondary, #666);
    font-size: 0.95rem;
  }

  .error-banner {
    background: #fee;
    border: 1px solid #fcc;
    padding: 1rem;
    border-radius: 6px;
    margin-bottom: 1.5rem;
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  .error-icon {
    font-size: 1.25rem;
  }

  .panels {
    display: grid;
    grid-template-columns: 1fr 2fr;
    gap: 1.5rem;
  }

  @media (max-width: 1024px) {
    .panels {
      grid-template-columns: 1fr;
    }
  }

  .panel {
    background: var(--surface-bg, #fff);
    border: 1px solid var(--border-color, #ddd);
    border-radius: 8px;
    overflow: hidden;
  }

  .panel-header {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border-color, #ddd);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .panel-header h2 {
    font-size: 1.1rem;
    font-weight: 600;
    margin: 0;
  }

  .controls {
    display: flex;
    gap: 1rem;
    align-items: center;
  }

  .controls label {
    font-size: 0.9rem;
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .days-input {
    width: 4rem;
    padding: 0.25rem 0.5rem;
    border: 1px solid var(--border-color, #ddd);
    border-radius: 4px;
  }

  .refresh-btn {
    padding: 0.5rem 1rem;
    background: var(--accent-bg, #0066ff);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.9rem;
  }

  .refresh-btn:hover:not(:disabled) {
    background: var(--accent-bg-hover, #0052cc);
  }

  .refresh-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .panel-content {
    padding: 1.25rem;
  }

  .loading,
  .empty {
    text-align: center;
    padding: 2rem;
    color: var(--text-secondary, #666);
    font-size: 0.95rem;
  }

  .indexer-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 1rem;
  }

  .indexer-card {
    padding: 1rem;
    border: 1px solid var(--border-color, #ddd);
    border-radius: 6px;
    background: var(--card-bg, #fafafa);
  }

  .indexer-card.disabled {
    opacity: 0.5;
  }

  .indexer-name {
    font-weight: 600;
    margin-bottom: 0.5rem;
  }

  .indexer-status {
    font-size: 0.85rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    display: inline-block;
    background: #eee;
    color: #666;
  }

  .indexer-status.active {
    background: #e0f7e0;
    color: #2d7a2d;
  }

  .indexer-lastcheck {
    font-size: 0.75rem;
    color: var(--text-muted, #999);
    margin-top: 0.5rem;
  }

  .release-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .release-card {
    padding: 1rem;
    border: 1px solid var(--border-color, #ddd);
    border-radius: 6px;
    background: var(--card-bg, #fafafa);
  }

  .release-info {
    margin-bottom: 0.75rem;
  }

  .release-artist {
    font-weight: 600;
    font-size: 1rem;
  }

  .release-title {
    color: var(--text-secondary, #666);
    font-size: 0.9rem;
  }

  .release-meta {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .meta-item {
    font-size: 0.85rem;
    color: var(--text-muted, #777);
  }
</style>

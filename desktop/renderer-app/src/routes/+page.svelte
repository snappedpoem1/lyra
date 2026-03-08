<script lang="ts">
  import { onMount } from "svelte";
  import { shell } from "$lib/stores/lyra";
  import { setWorkspacePage } from "$lib/stores/workspace";

  $: taste = $shell.tasteProfile;
  $: topDims = Object.entries(taste?.dimensions ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  onMount(() => {
    setWorkspacePage(
      "Oracle Home",
      "Your library, your signal",
      "See the current library shape, taste confidence, and the next lane for curation and discovery.",
      "context"
    );
  });
</script>

<section>
  <p class="eyebrow">Home</p>
  <h2>Your library, your signal</h2>
  <div class="hero">
    <article>
      <span>Library</span>
      <strong>{$shell.libraryOverview.trackCount}</strong>
      <small>Tracks in local catalog</small>
    </article>
    <article>
      <span>Playlists</span>
      <strong>{$shell.playlists.length}</strong>
      <small>Including vibe playlists</small>
    </article>
    <article>
      <span>Providers</span>
      <strong>{$shell.providers.filter((p) => p.isConfigured).length}</strong>
      <small>Configured data sources</small>
    </article>
    {#if $shell.acquisitionQueuePending > 0}
      <article class="acquire">
        <span>Pending</span>
        <strong>{$shell.acquisitionQueuePending}</strong>
        <small>Items in acquisition queue</small>
      </article>
    {/if}
  </div>

  {#if taste && taste.totalSignals > 0}
    <div class="taste-section">
      <p class="eyebrow">Your taste profile</p>
<small class="muted">{taste.totalSignals} signals - confidence {Math.round(taste.confidence * 100)}%</small>
      <div class="dims">
        {#each topDims as [dim, val]}
          <div class="dim-row">
            <span class="dim-label">{dim}</span>
            <div class="dim-bar-bg">
              <div class="dim-bar" style="width: {Math.round(val * 100)}%"></div>
            </div>
            <span class="dim-val">{Math.round(val * 100)}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</section>

<style>
  .eyebrow { text-transform: uppercase; letter-spacing: 0.16em; color: #9cb2c7; font-size: 0.72rem; }
  .muted { color: #9cb2c7; }
  .hero { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 20px 0; }
  article { padding: 24px; border-radius: 24px; background: rgba(255,255,255,0.05); display: grid; gap: 10px; }
  article.acquire { border: 1px solid #cbff6b40; }
  strong { font-size: 2.5rem; }
  small { color: #9cb2c7; }
  .taste-section { margin-top: 28px; display: grid; gap: 12px; }
  .dims { display: grid; gap: 10px; max-width: 480px; }
  .dim-row { display: grid; grid-template-columns: 110px 1fr 36px; gap: 10px; align-items: center; }
  .dim-label { text-transform: capitalize; font-size: 0.85rem; }
  .dim-bar-bg { height: 6px; border-radius: 3px; background: rgba(255,255,255,0.1); }
  .dim-bar { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #cbff6b, #7affc6); }
  .dim-val { font-size: 0.75rem; color: #9cb2c7; text-align: right; }
  @media (max-width: 900px) { .hero { grid-template-columns: 1fr; } }
</style>

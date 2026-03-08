<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { get } from "svelte/store";
  import { api } from "$lib/tauri";
  import { errorMessage, legacyImportReport, loadShell, registerLyraEvents, shell } from "$lib/stores/lyra";
  import {
    setComposerText,
    setInspectorTab,
    setWorkspaceArtist,
    setWorkspacePage,
    setWorkspaceTrack,
    toggleLeftRail,
    toggleRightRail,
    workspace,
    type BridgeAction,
    type InspectorTab,
  } from "$lib/stores/workspace";

  const nav = [
    { href: "/", label: "Oracle Home", short: "Home" },
    { href: "/library", label: "Library", short: "Library" },
    { href: "/playlists", label: "Playlists", short: "Playlists" },
    { href: "/discover", label: "Discover", short: "Discover" },
    { href: "/queue", label: "Queue", short: "Queue" },
    { href: "/acquisition", label: "Acquisition", short: "Acquire" },
    { href: "/settings", label: "Settings", short: "Settings" }
  ];

  const inspectorTabs: Array<{ value: InspectorTab; label: string }> = [
    { value: "context", label: "Context" },
    { value: "explain", label: "Why" },
    { value: "provenance", label: "Provenance" },
    { value: "bridge", label: "Bridge" },
    { value: "queue", label: "Queue" },
    { value: "acquisition", label: "Acquire" }
  ];

  let newPlaylistName = "";
  let rootPath = "";
  let nowPlayingArt: string | null = null;
  let lastArtTrackId: number | null = null;
  let dispose: () => void = () => {};

  onMount(() => {
    void loadShell();
    dispose = registerLyraEvents();
    const interval = window.setInterval(async () => {
      const playback = await api.playback();
      shell.update((state) => ({ ...state, playback }));
    }, 1000);
    return () => {
      window.clearInterval(interval);
    };
  });

  onDestroy(() => {
    dispose();
  });

  async function quickCreatePlaylist(): Promise<void> {
    if (!newPlaylistName.trim()) return;
    const playlist = await api.createPlaylist(newPlaylistName.trim());
    newPlaylistName = "";
    await loadShell();
    goto(`/playlists/${playlist.id}`);
  }

  async function quickAddRoot(): Promise<void> {
    if (!rootPath.trim()) return;
    await api.addLibraryRoot(rootPath.trim());
    rootPath = "";
    await loadShell();
  }

  async function transport(action: "toggle" | "next" | "previous"): Promise<void> {
    const playback =
      action === "toggle"
        ? await api.togglePlayback()
        : action === "next"
          ? await api.playNext()
          : await api.playPrevious();
    shell.update((state) => ({ ...state, playback }));
  }

  async function setShuffle(enabled: boolean): Promise<void> {
    const playback = await api.setShuffle(enabled);
    shell.update((state) => ({ ...state, playback }));
  }

  async function setRepeatMode(mode: "off" | "all" | "one"): Promise<void> {
    const playback = await api.setRepeatMode(mode);
    shell.update((state) => ({ ...state, playback }));
  }

  async function playQueueFromPanel(index: number): Promise<void> {
    const playback = await api.playQueueIndex(index);
    shell.update((state) => ({ ...state, playback }));
  }

  async function setVolume(event: Event): Promise<void> {
    const target = event.target as HTMLInputElement;
    const volume = parseFloat(target.value);
    const playback = await api.setVolume(volume);
    shell.update((state) => ({ ...state, playback }));
  }

  async function seek(event: Event): Promise<void> {
    const target = event.target as HTMLInputElement;
    const position = parseFloat(target.value);
    const playback = await api.seekTo(position);
    shell.update((state) => ({ ...state, playback }));
  }

  function active(href: string): boolean {
    return page.url.pathname === href;
  }

  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  async function refreshNowPlayingArt(trackId: number | null | undefined): Promise<void> {
    if (!trackId) {
      nowPlayingArt = null;
      return;
    }
    if (trackId === lastArtTrackId) {
      return;
    }
    lastArtTrackId = trackId;
    try {
      const result = await api.enrichTrack(trackId);
      const providers = (result.providers ?? {}) as Record<string, unknown>;
      const genius = providers.genius as Record<string, unknown> | undefined;
      const discogs = providers.discogs as Record<string, unknown> | undefined;
      const geniusPayload = genius?.payload as Record<string, unknown> | undefined;
      const discogsPayload = discogs?.payload as Record<string, unknown> | undefined;
      nowPlayingArt = (geniusPayload?.artUrl as string | undefined)
        ?? (discogsPayload?.coverImage as string | undefined)
        ?? null;
    } catch {
      nowPlayingArt = null;
    }
  }

  async function focusQueueItem(index: number): Promise<void> {
    const item = $shell.queue[index];
    if (!item) return;
    setWorkspaceArtist(item.artist);
    const current = $shell.playback.currentTrack;
    if (current && current.id === item.trackId) {
      setWorkspaceTrack(current);
    }
    setInspectorTab("queue");
    await playQueueFromPanel(index);
  }

  function defaultBridgeActions(pathname: string): BridgeAction[] {
    if (pathname.startsWith("/discover")) {
      return [
        { label: "Open playlists", href: "/playlists", detail: "Shape discoveries into authored journeys." },
        { label: "Review acquisition lane", href: "/acquisition", detail: "Promote strong leads into owned library growth." }
      ];
    }
    if (pathname.startsWith("/library")) {
      return [
        { label: "Deepen provenance", href: "/library", detail: "Inspect enrichment and identity before curation." },
        { label: "Send to playlists", href: "/playlists", detail: "Move local context into authored sequencing." }
      ];
    }
    if (pathname.startsWith("/acquisition")) {
      return [
        { label: "Open discovery", href: "/discover", detail: "Turn promising leads into queue candidates." },
        { label: "Open queue", href: "/queue", detail: "Carry successful acquisitions into active listening." }
      ];
    }
    return [
      { label: "Discover bridge paths", href: "/discover", detail: "Follow related artists, sessions, and queueable leads." },
      { label: "Shape a playlist", href: "/playlists", detail: "Turn context into a sequence with reasons." }
    ];
  }

  async function runComposer(): Promise<void> {
    const raw = get(workspace).composerText.trim();
    if (!raw) return;
    const command = raw.toLowerCase();

    if (command.includes("library")) {
      await goto("/library");
    } else if (command.includes("playlist")) {
      await goto("/playlists");
    } else if (command.includes("discover") || command.includes("bridge")) {
      await goto("/discover");
    } else if (command.includes("acquire") || command.includes("wishlist")) {
      await goto("/acquisition");
      setInspectorTab("acquisition");
    } else if (command.includes("queue")) {
      await goto("/queue");
      setInspectorTab("queue");
    } else if (command.includes("settings")) {
      await goto("/settings");
    } else if ($shell.playback.currentTrack?.artist && command.includes("artist")) {
      await goto(`/artists/${encodeURIComponent($shell.playback.currentTrack.artist)}`);
    }

    setComposerText("");
  }

  $: void refreshNowPlayingArt($shell.playback.currentTrackId);

  $: if (!$workspace.pageTitle || $workspace.pageTitle === "Oracle workspace") {
    setWorkspacePage(
      "Lyra",
      "Oracle workspace",
      "One shell for playlist making, discovery, acquisition, and explanation.",
      "context"
    );
  }

  $: currentTrack = $shell.playback.currentTrack ?? null;
  $: activeTrack = $workspace.selectedTrack ?? currentTrack;
  $: activeArtist = $workspace.selectedArtist ?? activeTrack?.artist ?? null;
  $: fallbackBridgeActions = defaultBridgeActions(page.url.pathname);
</script>

<svelte:head>
  <title>Lyra</title>
</svelte:head>

<div class="shell-frame">
  <header class="shell-topbar">
    <div class="topbar-left">
      <button class="icon-btn" on:click={toggleLeftRail} aria-label="Toggle navigation rail">
        {$workspace.leftRailOpen ? "Hide Rail" : "Show Rail"}
      </button>
      <div class="workspace-headline">
        <p class="eyebrow">{$workspace.pageEyebrow}</p>
        <h1>{$workspace.pageTitle}</h1>
        <p class="subtitle">{$workspace.pageSubtitle}</p>
      </div>
    </div>
    <div class="topbar-right">
      <button class="icon-btn" on:click={() => setInspectorTab("context")}>Context</button>
      <button class="icon-btn" on:click={() => setInspectorTab("explain")}>Why</button>
      <button class="icon-btn" on:click={toggleRightRail} aria-label="Toggle inspector rail">
        {$workspace.rightRailOpen ? "Hide Inspector" : "Show Inspector"}
      </button>
    </div>
  </header>

  <div class="app-shell" class:left-collapsed={!$workspace.leftRailOpen} class:right-collapsed={!$workspace.rightRailOpen}>
    <aside class="nav-rail">
      <div class="rail-section brand-block">
        <p class="eyebrow">Lyra Oracle</p>
        <h2>Playlist-first music intelligence</h2>
        <p class="muted">Navigate the library, shape playlists, follow bridges, and keep acquisition visible.</p>
      </div>

      <nav class="nav-list rail-section">
        {#each nav as item}
          <a class:active={active(item.href)} href={item.href}>
            <span class="nav-label">{item.label}</span>
            <small>{item.short}</small>
          </a>
        {/each}
      </nav>

      <div class="rail-section quick-actions">
        <label>
          <span>New playlist</span>
          <input bind:value={newPlaylistName} placeholder="Act I - soft ignition" />
        </label>
        <button on:click={quickCreatePlaylist}>Create playlist</button>
        <label>
          <span>Library root</span>
          <input bind:value={rootPath} placeholder="C:\Music" />
        </label>
        <button on:click={quickAddRoot}>Add root</button>
      </div>

      <div class="rail-section shell-signals">
        <div>
          <span class="signal-label">Library</span>
          <strong>{$shell.libraryOverview.trackCount}</strong>
        </div>
        <div>
          <span class="signal-label">Playlists</span>
          <strong>{$shell.playlists.length}</strong>
        </div>
        <div>
          <span class="signal-label">Queued Acquisition</span>
          <strong>{$shell.acquisitionQueuePending}</strong>
        </div>
      </div>
    </aside>

    <main class="center-panel">
      {#if $errorMessage}
        <section class="error-banner">{$errorMessage}</section>
      {/if}
      <slot />
    </main>

    <aside class="inspector-rail">
      <div class="inspector-tabs">
        {#each inspectorTabs as tab}
          <button
            class="tab-toggle"
            class:active-tab={$workspace.inspectorTab === tab.value}
            on:click={() => setInspectorTab(tab.value)}
          >
            {tab.label}
          </button>
        {/each}
      </div>

      {#if $workspace.inspectorTab === "context"}
        <section class="inspector-panel">
          <p class="eyebrow">Context</p>
          <strong>{activeTrack?.title ?? activeArtist ?? "No focused context yet"}</strong>
          <p class="muted">
            {#if activeTrack}
              {activeTrack.artist}{activeTrack.album ? ` - ${activeTrack.album}` : ""}
            {:else if activeArtist}
              Artist context is active for {activeArtist}.
            {:else}
              Pick a track, artist, or queue item to anchor the right rail.
            {/if}
          </p>
          {#if currentTrack}
            <div class="context-card">
              <span class="signal-label">Now playing</span>
              <strong>{currentTrack.title}</strong>
              <small>{currentTrack.artist}</small>
            </div>
          {/if}
          {#if $legacyImportReport}
            <div class="context-card">
              <span class="signal-label">Legacy import</span>
              <small>{$legacyImportReport.notes.join(" | ")}</small>
            </div>
          {/if}
        </section>
      {:else if $workspace.inspectorTab === "explain"}
        <section class="inspector-panel">
          <p class="eyebrow">Why This Track</p>
          {#if $workspace.explanation}
            <strong>{activeTrack?.title ?? `Track #${$workspace.explanation.trackId}`}</strong>
            <div class="stack-list">
              {#each $workspace.explanation.reasons as reason}
                <div class="context-card"><small>{reason}</small></div>
              {/each}
            </div>
            <small class="muted">Confidence {Math.round($workspace.explanation.confidence * 100)}% - {$workspace.explanation.source}</small>
          {:else}
            <p class="muted">Discover and playlist surfaces can push reason payloads into this rail.</p>
          {/if}
        </section>
      {:else if $workspace.inspectorTab === "provenance"}
        <section class="inspector-panel">
          <p class="eyebrow">Provenance</p>
          {#if $workspace.provenance.length}
            {#each $workspace.provenance as entry}
              <div class="context-card">
                <div class="row-inline">
                  <strong>{entry.provider}</strong>
                  <span class="muted">{entry.status} - {Math.round(entry.confidence * 100)}%</span>
                </div>
                {#if entry.releaseTitle}
                  <small>{entry.releaseTitle}</small>
                {/if}
                {#if entry.mbid}
                  <small class="mono">{entry.mbid}</small>
                {/if}
                {#if entry.note}
                  <small>{entry.note}</small>
                {/if}
              </div>
            {/each}
          {:else}
            <p class="muted">Library and artist surfaces can pin enrichment evidence here.</p>
          {/if}
        </section>
      {:else if $workspace.inspectorTab === "bridge"}
        <section class="inspector-panel">
          <p class="eyebrow">Bridge Actions</p>
          {#each ($workspace.bridgeActions.length ? $workspace.bridgeActions : fallbackBridgeActions) as action}
            <a class="bridge-card" href={action.href ?? page.url.pathname}>
              <strong>{action.label}</strong>
              {#if action.detail}
                <small>{action.detail}</small>
              {/if}
            </a>
          {/each}
        </section>
      {:else if $workspace.inspectorTab === "queue"}
        <section class="inspector-panel">
          <div class="row-inline">
            <p class="eyebrow">Queue</p>
            <strong>{$shell.queue.length}</strong>
          </div>
          <div class="stack-list">
            {#if !$shell.queue.length}
              <p class="muted">Queue is empty.</p>
            {/if}
            {#each $shell.queue as item, index}
              <button class:current={index === $shell.playback.queueIndex} class="queue-card" on:click={() => focusQueueItem(index)}>
                <span>{item.title}</span>
                <small>{item.artist}</small>
              </button>
            {/each}
          </div>
        </section>
      {:else if $workspace.inspectorTab === "acquisition"}
        <section class="inspector-panel">
          <p class="eyebrow">Acquisition Context</p>
          {#if $workspace.acquisition}
            <div class="acq-stats">
              <div><span class="signal-label">Pending</span><strong>{$workspace.acquisition.pending}</strong></div>
              <div><span class="signal-label">Active</span><strong>{$workspace.acquisition.active}</strong></div>
              <div><span class="signal-label">Failed</span><strong>{$workspace.acquisition.failed}</strong></div>
            </div>
            <small class="muted">Worker {$workspace.acquisition.workerRunning ? "running" : "stopped"}</small>
            {#if $workspace.acquisition.preflight}
              <div class="context-card">
                <span class="signal-label">Preflight</span>
                {#each $workspace.acquisition.preflight.notes as note}
                  <small>{note}</small>
                {/each}
              </div>
            {/if}
            {#if $workspace.acquisition.recentEvents.length}
              <div class="stack-list">
                {#each $workspace.acquisition.recentEvents as event}
                  <div class="context-card">
                    <strong>{event.at}</strong>
                    <small>{event.message}</small>
                  </div>
                {/each}
              </div>
            {/if}
          {:else}
            <p class="muted">Open Acquisition to keep queue trust, lifecycle, and preflight visible here.</p>
          {/if}
        </section>
      {/if}
    </aside>
  </div>

  <section class="composer-line">
    <div class="composer-copy">
      <p class="eyebrow">Lyra Input</p>
      <small>Persistent oracle line for navigation, focus, and next-action intent.</small>
    </div>
    <input
      value={$workspace.composerText}
      on:input={(event) => setComposerText((event.currentTarget as HTMLInputElement).value)}
      on:keydown={(event) => event.key === "Enter" && runComposer()}
      placeholder="Type: discover bridge tracks, open acquisition, go to playlists, artist context..."
    />
    <button on:click={runComposer}>Run</button>
  </section>

  <footer class="transport">
    <div class="now-playing">
      <p class="eyebrow">Mini Player</p>
      <div class="now-playing-meta">
        {#if nowPlayingArt}
          <img class="now-playing-art" src={nowPlayingArt} alt={$shell.playback.currentTrack?.title ?? "Now playing"} />
        {:else}
          <div class="now-playing-art fallback">PLAY</div>
        {/if}
        <div>
          <strong>{$shell.playback.currentTrack?.title ?? "Nothing loaded"}</strong>
          {#if $shell.playback.currentTrack?.artist}
            <small><a href={`/artists/${encodeURIComponent($shell.playback.currentTrack.artist)}`}>{$shell.playback.currentTrack.artist}</a></small>
          {:else}
            <small>Pick something from Library, Playlists, or Discover.</small>
          {/if}
        </div>
      </div>
    </div>
    <div class="playback-controls">
      <div class="transport-actions">
        <button on:click={() => transport("previous")}>Prev</button>
        <button class="accent play-pause" on:click={() => transport("toggle")}>
          {$shell.playback.status === "playing" ? "Pause" : "Play"}
        </button>
        <button on:click={() => transport("next")}>Next</button>
        <button class:active-toggle={$shell.playback.shuffle} on:click={() => setShuffle(!$shell.playback.shuffle)}>Shuffle</button>
        <button class:active-toggle={$shell.playback.repeatMode === "one"} on:click={() => setRepeatMode($shell.playback.repeatMode === "one" ? "off" : "one")}>Repeat 1</button>
        <button class:active-toggle={$shell.playback.repeatMode === "all"} on:click={() => setRepeatMode($shell.playback.repeatMode === "all" ? "off" : "all")}>Repeat All</button>
      </div>
      <div class="progress-bar">
        <span class="time">{formatTime($shell.playback.positionSeconds)}</span>
        <input
          type="range"
          min="0"
          max={$shell.playback.durationSeconds || 100}
          value={$shell.playback.positionSeconds}
          on:input={seek}
          class="seek-slider"
        />
        <span class="time">{formatTime($shell.playback.durationSeconds)}</span>
      </div>
    </div>
    <div class="volume-control">
      <span>Vol</span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.01"
        value={$shell.playback.volume}
        on:input={setVolume}
        class="volume-slider"
      />
      <span class="volume-label">{Math.round($shell.playback.volume * 100)}%</span>
    </div>
  </footer>
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", sans-serif;
    background:
      radial-gradient(circle at top left, rgba(90, 145, 255, 0.12), transparent 28%),
      linear-gradient(165deg, #081019 0%, #0d1721 35%, #121e2b 100%);
    color: #eff5fb;
  }

  :global(a) { color: inherit; text-decoration: none; }
  :global(button), :global(input) { font: inherit; }
  :global(html), :global(body) { height: 100%; overflow: hidden; }

  .shell-frame {
    display: grid;
    grid-template-rows: auto 1fr auto auto;
    height: 100vh;
  }

  .shell-topbar,
  .topbar-left,
  .topbar-right,
  .row-inline,
  .transport-actions,
  .progress-bar,
  .volume-control,
  .composer-line,
  .inspector-tabs {
    display: flex;
    gap: 0.75rem;
  }

  .shell-topbar,
  .row-inline,
  .composer-line {
    align-items: center;
    justify-content: space-between;
  }

  .shell-topbar {
    padding: 0.9rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    background: linear-gradient(180deg, rgba(10, 16, 23, 0.88), rgba(8, 12, 18, 0.7));
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    backdrop-filter: blur(18px);
  }

  .workspace-headline h1,
  .workspace-headline p,
  .brand-block h2,
  .brand-block p {
    margin: 0;
  }

  .subtitle,
  .muted,
  small,
  .signal-label {
    color: #94abc0;
  }

  .eyebrow {
    margin: 0 0 0.2rem;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: #88a8bf;
  }

  .icon-btn,
  .tab-toggle,
  .queue-card,
  .bridge-card,
  .nav-list a,
  button {
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.03));
    color: inherit;
    padding: 0.72rem 0.9rem;
    cursor: pointer;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  }

  .icon-btn,
  .tab-toggle {
    padding: 0.55rem 0.8rem;
  }

  .app-shell {
    display: grid;
    grid-template-columns: 270px minmax(0, 1fr) 340px;
    min-height: 0;
  }

  .app-shell.left-collapsed {
    grid-template-columns: 0 minmax(0, 1fr) 340px;
  }

  .app-shell.right-collapsed {
    grid-template-columns: 270px minmax(0, 1fr) 0;
  }

  .app-shell.left-collapsed.right-collapsed {
    grid-template-columns: 0 minmax(0, 1fr) 0;
  }

  .nav-rail,
  .inspector-rail,
  .center-panel {
    min-height: 0;
    overflow: auto;
    box-sizing: border-box;
  }

  .nav-rail,
  .inspector-rail {
    padding: 1rem;
    background: linear-gradient(180deg, rgba(13, 20, 28, 0.82), rgba(10, 15, 22, 0.72));
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(18px);
  }

  .inspector-rail {
    border-right: none;
    border-left: 1px solid rgba(255, 255, 255, 0.06);
  }

  .center-panel {
    padding: 1rem 1.1rem;
  }

  .nav-rail,
  .inspector-rail {
    display: grid;
    gap: 1rem;
  }

  .rail-section,
  .inspector-panel,
  .composer-line,
  .transport,
  .error-banner {
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0.028));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
  }

  .rail-section,
  .inspector-panel,
  .error-banner {
    padding: 0.9rem;
  }

  .nav-list,
  .quick-actions,
  .stack-list {
    display: grid;
    gap: 0.7rem;
  }

  .nav-list a.active,
  .tab-toggle.active-tab,
  .queue-card.current,
  button.accent {
    background: linear-gradient(120deg, #cbff6b 0%, #7affc6 100%);
    color: #0f1720;
    border-color: transparent;
  }

  .nav-list a {
    display: grid;
    gap: 0.12rem;
  }

  .signal-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  .shell-signals {
    display: grid;
    gap: 0.7rem;
  }

  .shell-signals strong {
    display: block;
    font-size: 1.4rem;
  }

  .context-card,
  .bridge-card,
  .queue-card {
    display: grid;
    gap: 0.22rem;
    padding: 0.72rem 0.78rem;
    border-radius: 14px;
    background: rgba(255,255,255,0.035);
    border: 1px solid rgba(255,255,255,0.05);
  }

  .bridge-card,
  .queue-card {
    text-align: left;
  }

  .acq-stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem;
  }

  .acq-stats strong {
    display: block;
    margin-top: 0.18rem;
    font-size: 1.3rem;
  }

  .mono {
    font-family: Consolas, monospace;
    word-break: break-all;
  }

  .composer-line {
    margin: 0 1rem 0.85rem;
    padding: 0.85rem 1rem;
    backdrop-filter: blur(18px);
  }

  .composer-copy {
    min-width: 15rem;
  }

  .composer-line input {
    flex: 1;
    min-width: 0;
    padding: 0.8rem 0.95rem;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(6, 12, 18, 0.64);
    color: inherit;
  }

  .transport {
    display: grid;
    grid-template-columns: 1.3fr minmax(24rem, 1fr) 15rem;
    align-items: center;
    gap: 1rem;
    padding: 0.95rem 1rem;
    margin: 0 1rem 1rem;
    background: linear-gradient(180deg, rgba(10, 15, 21, 0.94), rgba(7, 11, 16, 0.92));
    backdrop-filter: blur(16px);
  }

  .now-playing-meta {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    min-width: 0;
  }

  .now-playing-art {
    width: 56px;
    height: 56px;
    border-radius: 10px;
    object-fit: cover;
    flex-shrink: 0;
  }

  .now-playing-art.fallback {
    display: grid;
    place-items: center;
    background: linear-gradient(180deg, rgba(255,255,255,0.12), rgba(255,255,255,0.06));
    font-size: 0.92rem;
    letter-spacing: 0.14em;
  }

  .now-playing strong,
  .now-playing small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .playback-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.55rem;
    min-width: 0;
  }

  .progress-bar {
    width: 100%;
    align-items: center;
  }

  .time,
  .volume-label {
    font-size: 0.84rem;
    color: #9cb2c7;
    min-width: 40px;
    text-align: center;
  }

  .seek-slider,
  .volume-slider {
    flex: 1;
    height: 5px;
    border-radius: 999px;
    background: rgba(255,255,255,0.12);
    outline: none;
    -webkit-appearance: none;
    appearance: none;
  }

  .seek-slider::-webkit-slider-thumb,
  .volume-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: linear-gradient(120deg, #cbff6b 0%, #7affc6 100%);
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }

  .volume-control .volume-slider {
    width: 110px;
  }

  .active-toggle {
    border-color: rgba(122, 255, 198, 0.5);
    background: rgba(122, 255, 198, 0.15);
  }

  .error-banner {
    margin-bottom: 0.85rem;
    background: rgba(255, 92, 92, 0.12);
    border-color: rgba(255, 92, 92, 0.32);
  }

  label {
    display: grid;
    gap: 0.35rem;
  }

  input {
    padding: 0.7rem 0.82rem;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.05);
    color: inherit;
  }

  @media (max-width: 1180px) {
    .app-shell,
    .app-shell.left-collapsed,
    .app-shell.right-collapsed,
    .app-shell.left-collapsed.right-collapsed {
      grid-template-columns: minmax(0, 1fr);
    }

    .nav-rail,
    .inspector-rail {
      display: none;
    }

    .transport {
      grid-template-columns: 1fr;
    }

    .composer-line,
    .shell-topbar,
    .topbar-left,
    .topbar-right {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>

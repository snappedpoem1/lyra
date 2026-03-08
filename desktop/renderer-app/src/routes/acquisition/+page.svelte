<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { api } from "$lib/tauri";
  import {
    setWorkspaceAcquisition,
    setWorkspaceBridgeActions,
    setWorkspacePage
  } from "$lib/stores/workspace";
  import type { AcquisitionPreflight, AcquisitionQueueItem } from "$lib/types";

  type AcquisitionActivity = {
    id: string;
    at: number;
    tone: "info" | "success" | "warning" | "error";
    message: string;
  };

  let items: AcquisitionQueueItem[] = [];
  let statusFilter = "";
  let loading = false;
  let processing = false;
  let workerRunning = false;
  let workerLoading = false;
  let preflight: AcquisitionPreflight | null = null;
  let preflightLoading = false;
  let clearBusy = false;
  let retryAllBusy = false;
  let activity: AcquisitionActivity[] = [];
  let refreshHandle: ReturnType<typeof setInterval> | null = null;

  let newArtist = "";
  let newTitle = "";
  let newAlbum = "";
  let newSource = "manual";

  const statusOptions = [
    { value: "", label: "All" },
    { value: "pending", label: "Pending" },
    { value: "in_progress", label: "In Progress" },
    { value: "completed", label: "Completed" },
    { value: "failed", label: "Failed" },
    { value: "skipped", label: "Skipped" },
  ];

  onMount(async () => {
    setWorkspacePage(
      "Acquisition",
      "Acquisition workflow",
      "Steer staged queue work, validate trust, and keep lifecycle events visible inside the canonical shell.",
      "acquisition"
    );
    setWorkspaceBridgeActions([
      {
        label: "Review discovery leads",
        href: "/discover",
        detail: "Turn promising recommendations into acquisition candidates."
      },
      {
        label: "Open queue",
        href: "/queue",
        detail: "Carry completed acquisitions into active listening."
      },
      {
        label: "Shape playlists",
        href: "/playlists",
        detail: "Move newly owned tracks into authored journeys."
      }
    ]);
    await Promise.all([loadQueue(), checkWorkerStatus(), loadPreflight()]);
    syncRefreshLoop();
  });

  onDestroy(() => {
    stopRefreshLoop();
    setWorkspaceAcquisition(null);
  });

  function stopRefreshLoop(): void {
    if (refreshHandle) {
      clearInterval(refreshHandle);
      refreshHandle = null;
    }
  }

  function syncRefreshLoop(): void {
    const shouldRefresh = workerRunning || items.some((item) => item.status === "in_progress");
    if (!shouldRefresh) {
      stopRefreshLoop();
      return;
    }
    if (refreshHandle) {
      return;
    }
    refreshHandle = setInterval(async () => {
      await Promise.all([loadQueue(), checkWorkerStatus()]);
    }, 2000);
  }

  function pushActivity(entry: AcquisitionActivity): void {
    activity = [entry, ...activity].slice(0, 14);
  }

  function toTimestamp(value?: string | null): number {
    if (!value) {
      return Date.now();
    }
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : Date.now();
  }

  function describeChange(previous: AcquisitionQueueItem | undefined, current: AcquisitionQueueItem): AcquisitionActivity | null {
    const label = `${current.artist} - ${current.title}`;
    const at = toTimestamp(current.updatedAt ?? current.completedAt ?? current.addedAt);

    if (!previous) {
      return {
        id: `${current.id}-${at}-queued`,
        at,
        tone: "info",
        message: `${label} queued from ${current.source ?? "manual"}.`,
      };
    }

    if (previous.status !== current.status) {
      const tone: AcquisitionActivity["tone"] =
        current.status === "completed"
          ? "success"
          : current.status === "failed"
            ? "error"
            : current.status === "skipped"
              ? "warning"
              : "info";
      return {
        id: `${current.id}-${at}-status`,
        at,
        tone,
        message: `${label} moved to ${current.status.replace("_", " ")}.`,
      };
    }

    if (previous.lifecycleStage !== current.lifecycleStage || previous.lifecycleNote !== current.lifecycleNote) {
      return {
        id: `${current.id}-${at}-stage`,
        at,
        tone: "info",
        message: `${label}: ${stageLabel(current)}.`,
      };
    }

    if (previous.error !== current.error && current.error) {
      return {
        id: `${current.id}-${at}-error`,
        at,
        tone: "error",
        message: `${label}: ${current.error}`,
      };
    }

    return null;
  }

  async function loadQueue(): Promise<void> {
    loading = true;
    try {
      const nextItems = await api.acquisitionQueue(statusFilter || undefined);
      const previousById = new Map(items.map((item) => [item.id, item]));
      for (const item of nextItems) {
        const event = describeChange(previousById.get(item.id), item);
        if (event) {
          pushActivity(event);
        }
      }
      items = nextItems;
      syncRefreshLoop();
    } finally {
      loading = false;
    }
  }

  async function loadPreflight(): Promise<void> {
    preflightLoading = true;
    try {
      preflight = await api.acquisitionPreflight();
    } finally {
      preflightLoading = false;
    }
  }

  async function checkWorkerStatus(): Promise<void> {
    try {
      workerRunning = await api.acquisitionWorkerStatus();
      syncRefreshLoop();
    } catch (err) {
      console.error("Failed to check worker status:", err);
    }
  }

  async function startWorker(): Promise<void> {
    workerLoading = true;
    try {
      const started = await api.startAcquisitionWorker();
      if (started) {
        workerRunning = true;
        pushActivity({
          id: `worker-start-${Date.now()}`,
          at: Date.now(),
          tone: "info",
          message: "Background acquisition worker started.",
        });
      }
      syncRefreshLoop();
    } finally {
      workerLoading = false;
    }
  }

  async function stopWorker(): Promise<void> {
    workerLoading = true;
    try {
      await api.stopAcquisitionWorker();
      workerRunning = false;
      pushActivity({
        id: `worker-stop-${Date.now()}`,
        at: Date.now(),
        tone: "warning",
        message: "Background acquisition worker stopped.",
      });
      syncRefreshLoop();
    } finally {
      workerLoading = false;
    }
  }

  async function addItem(): Promise<void> {
    if (!newArtist.trim() || !newTitle.trim()) return;
    loading = true;
    try {
      items = await api.addToAcquisitionQueue(
        newArtist.trim(),
        newTitle.trim(),
        newAlbum.trim() || undefined,
        newSource.trim() || undefined
      );
      pushActivity({
        id: `manual-add-${Date.now()}`,
        at: Date.now(),
        tone: "info",
        message: `${newArtist.trim()} - ${newTitle.trim()} added to the acquisition queue.`,
      });
      newArtist = "";
      newTitle = "";
      newAlbum = "";
      await loadPreflight();
    } finally {
      loading = false;
    }
  }

  async function processNext(): Promise<void> {
    processing = true;
    try {
      const processed = await api.processAcquisitionQueue();
      if (processed) {
        pushActivity({
          id: `process-next-${Date.now()}`,
          at: Date.now(),
          tone: "info",
          message: "Started processing the next acquisition item.",
        });
        await loadQueue();
      }
      syncRefreshLoop();
    } finally {
      processing = false;
    }
  }

  async function retryItem(id: number): Promise<void> {
    loading = true;
    try {
      items = await api.updateAcquisitionItem(id, "pending");
      pushActivity({
        id: `retry-item-${id}-${Date.now()}`,
        at: Date.now(),
        tone: "info",
        message: `Retry queued for item #${id}.`,
      });
    } finally {
      loading = false;
    }
  }

  async function retryFailed(): Promise<void> {
    retryAllBusy = true;
    try {
      const retried = await api.retryFailedAcquisition();
      if (retried > 0) {
        pushActivity({
          id: `retry-all-${Date.now()}`,
          at: Date.now(),
          tone: "info",
          message: `Retry queued for ${retried} failed item${retried === 1 ? "" : "s"}.`,
        });
        await loadQueue();
      }
    } finally {
      retryAllBusy = false;
    }
  }

  async function skipItem(id: number): Promise<void> {
    loading = true;
    try {
      items = await api.updateAcquisitionItem(id, "skipped");
      pushActivity({
        id: `skip-item-${id}-${Date.now()}`,
        at: Date.now(),
        tone: "warning",
        message: `Item #${id} marked as skipped.`,
      });
    } finally {
      loading = false;
    }
  }

  async function clearCompleted(): Promise<void> {
    clearBusy = true;
    try {
      const removed = await api.clearCompletedAcquisition();
      if (removed > 0) {
        pushActivity({
          id: `clear-completed-${Date.now()}`,
          at: Date.now(),
          tone: "info",
          message: `Cleared ${removed} completed or skipped item${removed === 1 ? "" : "s"}.`,
        });
      }
      await loadQueue();
    } finally {
      clearBusy = false;
    }
  }

  async function updatePriority(item: AcquisitionQueueItem, value: string): Promise<void> {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return;
    items = await api.setAcquisitionPriority(item.id, parsed);
  }

  async function nudgePriority(item: AcquisitionQueueItem, delta: number): Promise<void> {
    const next = Math.max(0, Math.min(1, item.priorityScore + delta));
    items = await api.setAcquisitionPriority(item.id, Number(next.toFixed(2)));
    pushActivity({
      id: `priority-${item.id}-${Date.now()}`,
      at: Date.now(),
      tone: "info",
      message: `${item.artist} - ${item.title} priority set to ${next.toFixed(2)}.`,
    });
  }

  function getStatusBadgeClass(status: string): string {
    switch (status) {
      case "pending": return "badge-pending";
      case "in_progress": return "badge-progress";
      case "completed": return "badge-success";
      case "failed": return "badge-error";
      case "skipped": return "badge-warning";
      default: return "";
    }
  }

  function stageLabel(item: AcquisitionQueueItem): string {
    const stage = item.lifecycleStage ?? "acquire";
    const note = item.lifecycleNote ?? "";
    return `${stage}${note ? `: ${note}` : ""}`;
  }

  function stagePct(item: AcquisitionQueueItem): number {
    return Math.round((item.lifecycleProgress ?? 0) * 100);
  }

  function formatBytes(bytes: number): string {
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(0)} MB`;
  }

  function formatClock(at: number): string {
    return new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(at));
  }

  $: failedCount = items.filter((item) => item.status === "failed").length;
  $: pendingCount = items.filter((item) => item.status === "pending").length;
  $: activeCount = items.filter((item) => item.status === "in_progress").length;
  $: setWorkspaceAcquisition({
    pending: pendingCount,
    active: activeCount,
    failed: failedCount,
    workerRunning,
    preflight,
    recentEvents: activity.slice(0, 6).map((entry) => ({
      at: formatClock(entry.at),
      message: entry.message,
      tone: entry.tone
    }))
  });
</script>

<div class="page-acquisition">
  <header class="page-header">
    <div>
      <p class="eyebrow">Canonical Workspace</p>
      <h1>Acquisition Queue</h1>
      <p class="lede">
        Watch the staged lifecycle, steer queue priority, and keep transitional downloader trust visible.
      </p>
    </div>
    <div class="actions">
      <button on:click={processNext} disabled={processing || loading}>
        {processing ? "Processing..." : "Process Next"}
      </button>
      <button on:click={retryFailed} disabled={retryAllBusy || failedCount === 0}>
        {retryAllBusy ? "Retrying..." : `Retry Failed${failedCount ? ` (${failedCount})` : ""}`}
      </button>
      <button on:click={clearCompleted} disabled={clearBusy || loading}>
        {clearBusy ? "Clearing..." : "Clear Completed"}
      </button>
      <button on:click={loadQueue} disabled={loading}>Refresh</button>
    </div>
  </header>

  <section class="summary-grid">
    <article class="summary-card">
      <span class="summary-label">Pending</span>
      <strong>{pendingCount}</strong>
    </article>
    <article class="summary-card">
      <span class="summary-label">Active</span>
      <strong>{activeCount}</strong>
    </article>
    <article class="summary-card">
      <span class="summary-label">Failed</span>
      <strong>{failedCount}</strong>
    </article>
    <article class="summary-card">
      <span class="summary-label">Worker</span>
      <strong>{workerRunning ? "Running" : "Stopped"}</strong>
    </article>
  </section>

  <div class="workspace-grid">
    <div class="main-column">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Preflight</h2>
            <p>Disk space and transitional downloader/tool readiness before queue motion.</p>
          </div>
          <button on:click={loadPreflight} disabled={preflightLoading}>
            {preflightLoading ? "Checking..." : "Recheck"}
          </button>
        </div>
        {#if preflight}
          <div class="preflight-grid">
            <span class:ok={preflight.pythonAvailable} class:bad={!preflight.pythonAvailable}>
              Python: {preflight.pythonAvailable ? "OK" : "Missing"}
            </span>
            <span class:ok={preflight.downloaderAvailable} class:bad={!preflight.downloaderAvailable}>
              Tools: {preflight.downloaderAvailable ? "Ready" : "Missing"}
            </span>
            <span class:ok={preflight.diskOk} class:bad={!preflight.diskOk}>
              Disk: {preflight.diskOk ? "OK" : "Low"}
            </span>
            <span>Free: {formatBytes(preflight.freeBytes)} / Required: {formatBytes(preflight.requiredBytes)}</span>
          </div>
          <ul class="note-list">
            {#each preflight.notes as note}
              <li>{note}</li>
            {/each}
          </ul>
        {/if}
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Worker Control</h2>
            <p>Background queue runner for staged acquisition processing.</p>
          </div>
          <div class="worker-actions">
            <span class="status-indicator {workerRunning ? 'running' : 'stopped'}">
              {workerRunning ? "Running" : "Stopped"}
            </span>
            {#if workerRunning}
              <button on:click={stopWorker} disabled={workerLoading}>
                {workerLoading ? "Stopping..." : "Stop Worker"}
              </button>
            {:else}
              <button on:click={startWorker} disabled={workerLoading}>
                {workerLoading ? "Starting..." : "Start Worker"}
              </button>
            {/if}
            <button on:click={checkWorkerStatus} disabled={workerLoading}>Check Status</button>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Add To Queue</h2>
            <p>Seed the canonical acquisition workflow without leaving the workspace.</p>
          </div>
        </div>
        <div class="form-grid">
          <input type="text" bind:value={newArtist} placeholder="Artist *" />
          <input type="text" bind:value={newTitle} placeholder="Title *" />
          <input type="text" bind:value={newAlbum} placeholder="Album (optional)" />
          <input type="text" bind:value={newSource} placeholder="Source" />
          <button on:click={addItem} disabled={!newArtist.trim() || !newTitle.trim() || loading}>Add</button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Queue</h2>
            <p>Per-item progress, errors, and priority controls for the staged lifecycle.</p>
          </div>
          <label class="filter-label">
            <span>Status</span>
            <select bind:value={statusFilter} on:change={loadQueue}>
              {#each statusOptions as opt}
                <option value={opt.value}>{opt.label}</option>
              {/each}
            </select>
          </label>
        </div>

        {#if loading && items.length === 0}
          <p>Loading acquisition queue...</p>
        {:else if items.length === 0}
          <p class="empty-state">No acquisition items found for the current filter.</p>
        {:else}
          <table class="queue-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Status</th>
                <th>Lifecycle</th>
                <th>Priority</th>
                <th>Error</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {#each items as item (item.id)}
                <tr>
                  <td>
                    <div class="item-copy">
                      <strong>{item.artist}</strong>
                      <span>{item.title}</span>
                      {#if item.album}
                        <small>{item.album}</small>
                      {/if}
                    </div>
                  </td>
                  <td>
                    <span class="badge {getStatusBadgeClass(item.status)}">{item.status.replace("_", " ")}</span>
                  </td>
                  <td>
                    <div class="lifecycle-cell">
                      <small>{stageLabel(item)}</small>
                      <div class="bar-bg">
                        <div class="bar-fill" style={`width: ${stagePct(item)}%`}></div>
                      </div>
                      <small>{stagePct(item)}%</small>
                    </div>
                  </td>
                  <td>
                    <div class="priority-cell">
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={item.priorityScore}
                        on:change={(event) => updatePriority(item, (event.currentTarget as HTMLInputElement).value)}
                      />
                      <div class="priority-actions">
                        <small>{item.priorityScore.toFixed(2)}</small>
                        <button class="btn-ghost" on:click={() => nudgePriority(item, 0.15)}>Prioritize</button>
                        <button class="btn-ghost" on:click={() => nudgePriority(item, -0.15)}>Defer</button>
                      </div>
                    </div>
                  </td>
                  <td class="error-cell">{item.error || "-"}</td>
                  <td class="actions-cell">
                    {#if item.status === "failed"}
                      <button class="btn-small" on:click={() => retryItem(item.id)}>Retry</button>
                    {/if}
                    {#if item.status === "pending" || item.status === "failed"}
                      <button class="btn-small btn-danger" on:click={() => skipItem(item.id)}>Skip</button>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    </div>

    <aside class="side-column">
      <section class="panel activity-panel">
        <div class="panel-head">
          <div>
            <h2>Lifecycle Events</h2>
            <p>Recent queue and worker activity surfaced inside the acquisition workspace.</p>
          </div>
        </div>
        {#if activity.length === 0}
          <p class="empty-state">No lifecycle events captured yet.</p>
        {:else}
          <ul class="activity-list">
            {#each activity as entry (entry.id)}
              <li class={`activity-item tone-${entry.tone}`}>
                <span class="activity-time">{formatClock(entry.at)}</span>
                <span class="activity-message">{entry.message}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </aside>
  </div>
</div>

<style>
  .page-acquisition {
    padding: 1.5rem;
    max-width: 1480px;
    margin: 0 auto;
    display: grid;
    gap: 1rem;
  }

  .page-header,
  .panel-head,
  .actions,
  .worker-actions,
  .priority-actions,
  .actions-cell {
    display: flex;
    gap: 0.75rem;
  }

  .page-header,
  .panel-head {
    justify-content: space-between;
    align-items: flex-start;
  }

  .page-header {
    background:
      radial-gradient(circle at top left, rgba(120, 201, 255, 0.15), transparent 35%),
      linear-gradient(135deg, rgba(13, 17, 27, 0.96), rgba(19, 32, 43, 0.92));
    border: 1px solid rgba(122, 162, 191, 0.18);
    border-radius: 18px;
    padding: 1.25rem;
  }

  .eyebrow {
    margin: 0 0 0.25rem;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-size: 0.72rem;
    color: #88a8bf;
  }

  h1,
  h2,
  p {
    margin: 0;
  }

  .lede {
    margin-top: 0.45rem;
    color: #a5b8c8;
    max-width: 56rem;
  }

  .summary-grid,
  .workspace-grid,
  .preflight-grid,
  .form-grid {
    display: grid;
    gap: 0.85rem;
  }

  .summary-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 2.4fr) minmax(20rem, 1fr);
    align-items: start;
  }

  .main-column,
  .side-column {
    display: grid;
    gap: 1rem;
  }

  .summary-card,
  .panel {
    border-radius: 16px;
    border: 1px solid rgba(122, 162, 191, 0.14);
    background: linear-gradient(180deg, rgba(18, 24, 33, 0.94), rgba(9, 14, 20, 0.96));
    box-shadow: 0 14px 30px rgba(0, 0, 0, 0.16);
  }

  .summary-card {
    padding: 1rem;
    display: grid;
    gap: 0.25rem;
  }

  .summary-label {
    color: #86a1b5;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .summary-card strong {
    font-size: 1.55rem;
  }

  .panel {
    padding: 1rem;
    display: grid;
    gap: 0.9rem;
  }

  .panel-head p {
    color: #97adbf;
    margin-top: 0.25rem;
  }

  .preflight-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .note-list,
  .activity-list {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 0.6rem;
  }

  .note-list li {
    color: #b2c1ce;
    padding: 0.6rem 0.75rem;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.035);
  }

  .form-grid {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }

  .form-grid input,
  .filter-label select,
  button,
  .queue-table input[type="range"] {
    font: inherit;
  }

  .form-grid input,
  .filter-label select {
    padding: 0.72rem 0.8rem;
    border-radius: 10px;
    border: 1px solid rgba(145, 176, 201, 0.16);
    background: rgba(3, 8, 13, 0.72);
    color: inherit;
  }

  .filter-label {
    display: grid;
    gap: 0.35rem;
    min-width: 10rem;
  }

  button {
    border: 1px solid rgba(122, 162, 191, 0.2);
    border-radius: 10px;
    padding: 0.68rem 0.95rem;
    background: rgba(13, 48, 72, 0.5);
    color: #ecf4f9;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .btn-small,
  .btn-ghost {
    padding: 0.35rem 0.55rem;
    font-size: 0.84rem;
  }

  .btn-ghost {
    background: rgba(255, 255, 255, 0.035);
  }

  .btn-danger {
    color: #ff9a9a;
  }

  .ok {
    color: #7cf0b1;
  }

  .bad {
    color: #ff8f8f;
  }

  .status-indicator {
    padding: 0.55rem 0.8rem;
    border-radius: 999px;
    border: 1px solid rgba(122, 162, 191, 0.18);
    background: rgba(255, 255, 255, 0.035);
  }

  .status-indicator.running {
    color: #7cf0b1;
  }

  .status-indicator.stopped {
    color: #ff9c8f;
  }

  .queue-table {
    width: 100%;
    border-collapse: collapse;
    overflow: hidden;
  }

  .queue-table th,
  .queue-table td {
    padding: 0.8rem 0.65rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    text-align: left;
    vertical-align: top;
  }

  .queue-table th {
    color: #86a1b5;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .item-copy {
    display: grid;
    gap: 0.16rem;
  }

  .item-copy span,
  .item-copy small,
  .error-cell {
    color: #b7c5d1;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    padding: 0.26rem 0.5rem;
    border-radius: 999px;
    font-size: 0.75rem;
    text-transform: uppercase;
  }

  .badge-pending {
    background: rgba(118, 170, 255, 0.16);
    color: #8bb8ff;
  }

  .badge-progress {
    background: rgba(255, 197, 95, 0.16);
    color: #ffcb78;
  }

  .badge-success {
    background: rgba(85, 216, 154, 0.16);
    color: #7cf0b1;
  }

  .badge-error {
    background: rgba(255, 128, 128, 0.16);
    color: #ff9b9b;
  }

  .badge-warning {
    background: rgba(255, 174, 102, 0.16);
    color: #ffbf84;
  }

  .lifecycle-cell,
  .priority-cell {
    display: grid;
    gap: 0.35rem;
    min-width: 11rem;
  }

  .bar-bg {
    height: 0.42rem;
    border-radius: 999px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.08);
  }

  .bar-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #36b19b, #75c2ff);
  }

  .activity-panel {
    position: sticky;
    top: 1rem;
  }

  .activity-item {
    display: grid;
    gap: 0.18rem;
    padding: 0.8rem;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(255, 255, 255, 0.028);
  }

  .activity-time {
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #86a1b5;
  }

  .tone-success {
    border-color: rgba(124, 240, 177, 0.18);
  }

  .tone-error {
    border-color: rgba(255, 128, 128, 0.22);
  }

  .tone-warning {
    border-color: rgba(255, 185, 120, 0.2);
  }

  .empty-state {
    color: #98aebf;
    padding: 0.8rem 0;
  }

  @media (max-width: 1100px) {
    .summary-grid,
    .workspace-grid,
    .preflight-grid,
    .form-grid {
      grid-template-columns: 1fr;
    }

    .activity-panel {
      position: static;
    }

    .page-header,
    .panel-head,
    .actions,
    .worker-actions {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>

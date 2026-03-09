<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { api } from "$lib/tauri";
  import {
    setWorkspaceAcquisition,
    setWorkspaceBridgeActions,
    setWorkspacePage
  } from "$lib/stores/workspace";
  import type {
    AcquisitionEventPayload,
    AcquisitionPreflight,
    AcquisitionQueueItem,
    LibraryRootRecord
  } from "$lib/types";

  type AcquisitionActivity = {
    id: string;
    at: number;
    tone: "info" | "success" | "warning" | "error";
    message: string;
  };

  const statusOptions = [
    { value: "", label: "All" },
    { value: "queued", label: "Queued" },
    { value: "validating", label: "Validating" },
    { value: "acquiring", label: "Acquiring" },
    { value: "staging", label: "Staging" },
    { value: "organizing", label: "Organizing" },
    { value: "scanning", label: "Scanning" },
    { value: "indexing", label: "Indexing" },
    { value: "completed", label: "Completed" },
    { value: "failed", label: "Failed" },
    { value: "cancelled", label: "Cancelled" }
  ];
  const liveStates = ["queued", "validating", "acquiring", "staging", "organizing", "scanning", "indexing"];

  let items: AcquisitionQueueItem[] = [];
  let statusFilter = "";
  let loading = false;
  let processing = false;
  let workerRunning = false;
  let workerLoading = false;
  let preflight: AcquisitionPreflight | null = null;
  let libraryRoots: LibraryRootRecord[] = [];
  let preflightLoading = false;
  let clearBusy = false;
  let retryAllBusy = false;
  let selectedId: number | null = null;
  let activity: AcquisitionActivity[] = [];
  let eventDisposer: (() => void) | null = null;

  let newArtist = "";
  let newTitle = "";
  let newAlbum = "";
  let newSource = "manual";
  let newTargetRootId = "";

  onMount(async () => {
    setWorkspacePage(
      "Acquisition",
      "Acquisition workflow",
      "Drive queue work from preflight to library availability without dropping context.",
      "acquisition"
    );
    setWorkspaceBridgeActions([
      { label: "Review discovery leads", href: "/discover", detail: "Turn promising recommendations into acquisition candidates." },
      { label: "Open queue", href: "/queue", detail: "Carry successful acquisitions into active listening." },
      { label: "Shape playlists", href: "/playlists", detail: "Move newly owned tracks into authored journeys." }
    ]);

    await Promise.all([loadQueue(), checkWorkerStatus(), loadPreflight(), loadLibraryRoots()]);
    eventDisposer = await api.on<AcquisitionEventPayload>("lyra://acquisition-updated", (payload) => {
      workerRunning = payload.workerRunning;
      reconcileQueue(payload.queue, payload.latestItemId ?? null);
    });
  });

  onDestroy(() => {
    eventDisposer?.();
    setWorkspaceAcquisition(null);
  });

  function pushActivity(entry: AcquisitionActivity): void {
    activity = [entry, ...activity].slice(0, 18);
  }

  function toTimestamp(value?: string | null): number {
    if (!value) return Date.now();
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : Date.now();
  }

  function humanizeStatus(status: string): string {
    return status.replace(/_/g, " ");
  }

  function describeChange(previous: AcquisitionQueueItem | undefined, current: AcquisitionQueueItem): AcquisitionActivity | null {
    const label = `${current.artist} - ${current.title}`;
    const at = toTimestamp(current.updatedAt ?? current.completedAt ?? current.addedAt);
    if (!previous) {
      return { id: `${current.id}-${at}-created`, at, tone: "info", message: `${label} entered the acquisition queue from ${current.source ?? "manual"}.` };
    }
    if (previous.status !== current.status) {
      const tone =
        current.status === "completed"
          ? "success"
          : current.status === "failed"
            ? "error"
            : current.status === "cancelled"
              ? "warning"
              : "info";
      return { id: `${current.id}-${at}-status`, at, tone, message: `${label} moved to ${humanizeStatus(current.status)}.` };
    }
    if (previous.lifecycleNote !== current.lifecycleNote && current.lifecycleNote) {
      return { id: `${current.id}-${at}-note`, at, tone: "info", message: `${label}: ${current.lifecycleNote}` };
    }
    if (previous.failureReason !== current.failureReason && current.failureReason) {
      return { id: `${current.id}-${at}-failure`, at, tone: "error", message: `${label}: ${current.failureReason}` };
    }
    return null;
  }

  function reconcileQueue(nextItems: AcquisitionQueueItem[], latestItemId: number | null): void {
    const previousById = new Map(items.map((item) => [item.id, item]));
    for (const item of nextItems) {
      const event = describeChange(previousById.get(item.id), item);
      if (event) pushActivity(event);
    }
    items = nextItems;
    if (latestItemId && items.some((item) => item.id === latestItemId)) {
      selectedId = latestItemId;
    } else if (!selectedItem && items.length) {
      selectedId = items[0].id;
    } else if (selectedId && !items.some((item) => item.id === selectedId)) {
      selectedId = items[0]?.id ?? null;
    }
  }

  async function loadQueue(): Promise<void> {
    loading = true;
    try {
      reconcileQueue(await api.acquisitionQueue(statusFilter || undefined), selectedId);
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

  async function loadLibraryRoots(): Promise<void> {
    libraryRoots = await api.libraryRoots();
    if (!newTargetRootId && libraryRoots.length) {
      newTargetRootId = String(libraryRoots[0].id);
    }
  }

  async function checkWorkerStatus(): Promise<void> {
    workerRunning = await api.acquisitionWorkerStatus();
  }

  async function startWorker(): Promise<void> {
    workerLoading = true;
    try {
      const started = await api.startAcquisitionWorker();
      if (started) {
        workerRunning = true;
        pushActivity({ id: `worker-start-${Date.now()}`, at: Date.now(), tone: "info", message: "Background acquisition worker started." });
      }
    } finally {
      workerLoading = false;
    }
  }

  async function stopWorker(): Promise<void> {
    workerLoading = true;
    try {
      await api.stopAcquisitionWorker();
      workerRunning = false;
      pushActivity({ id: `worker-stop-${Date.now()}`, at: Date.now(), tone: "warning", message: "Background acquisition worker stopped." });
    } finally {
      workerLoading = false;
    }
  }

  async function addItem(): Promise<void> {
    if (!newArtist.trim() || !newTitle.trim()) return;
    loading = true;
    try {
      const queue = await api.addToAcquisitionQueue(
        newArtist.trim(),
        newTitle.trim(),
        newAlbum.trim() || undefined,
        newSource.trim() || undefined,
        newTargetRootId ? Number.parseInt(newTargetRootId, 10) : undefined
      );
      reconcileQueue(queue, queue.at(-1)?.id ?? null);
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
      await api.processAcquisitionQueue();
    } finally {
      processing = false;
    }
  }

  async function retryItem(id: number): Promise<void> {
    loading = true;
    try {
      reconcileQueue(await api.updateAcquisitionItem(id, "queued"), id);
    } finally {
      loading = false;
    }
  }

  async function retryFailed(): Promise<void> {
    retryAllBusy = true;
    try {
      const retried = await api.retryFailedAcquisition();
      if (retried > 0) {
        pushActivity({ id: `retry-all-${Date.now()}`, at: Date.now(), tone: "info", message: `Retry queued for ${retried} failed item${retried === 1 ? "" : "s"}.` });
        await loadQueue();
      }
    } finally {
      retryAllBusy = false;
    }
  }

  async function cancelItem(id: number): Promise<void> {
    loading = true;
    try {
      reconcileQueue(await api.cancelAcquisitionItem(id, "User cancelled from acquisition workspace"), id);
    } finally {
      loading = false;
    }
  }

  async function clearCompleted(): Promise<void> {
    clearBusy = true;
    try {
      const removed = await api.clearCompletedAcquisition();
      if (removed > 0) {
        pushActivity({ id: `clear-${Date.now()}`, at: Date.now(), tone: "info", message: `Cleared ${removed} completed or cancelled item${removed === 1 ? "" : "s"}.` });
      }
      await loadQueue();
    } finally {
      clearBusy = false;
    }
  }

  async function updatePriority(item: AcquisitionQueueItem, value: string): Promise<void> {
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) return;
    reconcileQueue(await api.setAcquisitionPriority(item.id, parsed), item.id);
  }

  async function moveItem(item: AcquisitionQueueItem, offset: number): Promise<void> {
    const newPosition = Math.max(0, item.queuePosition - 1 + offset);
    reconcileQueue(await api.moveAcquisitionQueueItem(item.id, newPosition), item.id);
  }

  async function updateTargetRoot(item: AcquisitionQueueItem, value: string): Promise<void> {
    reconcileQueue(
      await api.setAcquisitionTargetRoot(item.id, value ? Number.parseInt(value, 10) : undefined),
      item.id
    );
  }

  function stagePct(item: AcquisitionQueueItem): number {
    return Math.round((item.lifecycleProgress ?? 0) * 100);
  }

  function formatBytes(bytes: number): string {
    return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  }

  function formatClock(at: number): string {
    return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date(at));
  }

  function badgeClass(status: string): string {
    switch (status) {
      case "queued": return "badge-queued";
      case "validating": return "badge-validating";
      case "acquiring": return "badge-acquiring";
      case "staging": return "badge-staging";
      case "organizing": return "badge-organizing";
      case "scanning": return "badge-scanning";
      case "indexing": return "badge-indexing";
      case "completed": return "badge-success";
      case "failed": return "badge-error";
      case "cancelled": return "badge-warning";
      default: return "";
    }
  }

  function isRetryable(item: AcquisitionQueueItem): boolean {
    return item.status === "failed" || item.status === "cancelled";
  }

  function isCancelable(item: AcquisitionQueueItem): boolean {
    return liveStates.includes(item.status);
  }

  function detailValue(value?: string | number | boolean | null): string {
    if (value === null || value === undefined || value === "") return "-";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    return String(value);
  }

  $: filteredItems = statusFilter ? items.filter((item) => item.status === statusFilter) : items;
  $: failedCount = items.filter((item) => item.status === "failed").length;
  $: pendingCount = items.filter((item) => liveStates.includes(item.status)).length;
  $: activeCount = items.filter((item) => ["acquiring", "staging", "organizing", "scanning", "indexing"].includes(item.status)).length;
  $: selectedItem = filteredItems.find((item) => item.id === selectedId) ?? filteredItems[0] ?? null;
  $: setWorkspaceAcquisition({
    pending: pendingCount,
    active: activeCount,
    failed: failedCount,
    workerRunning,
    preflight,
    recentEvents: activity.slice(0, 6).map((entry) => ({ at: formatClock(entry.at), message: entry.message, tone: entry.tone }))
  });
</script>

<div class="page-acquisition">
  <header class="page-header">
    <div>
      <p class="eyebrow">Canonical Workspace</p>
      <h1>Acquisition workflow</h1>
      <p class="lede">
        Queue work, validate trust, and follow each item from provider waterfall to usable library availability.
      </p>
    </div>
    <div class="actions">
      <button on:click={processNext} disabled={processing || loading || !pendingCount}>{processing ? "Processing..." : "Process next"}</button>
      <button on:click={retryFailed} disabled={retryAllBusy || !failedCount}>{retryAllBusy ? "Retrying..." : `Retry failed${failedCount ? ` (${failedCount})` : ""}`}</button>
      <button on:click={clearCompleted} disabled={clearBusy}>{clearBusy ? "Clearing..." : "Clear completed"}</button>
      <button on:click={loadQueue} disabled={loading}>Refresh</button>
    </div>
  </header>

  <section class="summary-grid">
    <article class="summary-card"><span class="summary-label">Queued/live</span><strong>{pendingCount}</strong></article>
    <article class="summary-card"><span class="summary-label">Active</span><strong>{activeCount}</strong></article>
    <article class="summary-card"><span class="summary-label">Failed</span><strong>{failedCount}</strong></article>
    <article class="summary-card"><span class="summary-label">Worker</span><strong>{workerRunning ? "Running" : "Stopped"}</strong></article>
  </section>

  <div class="workspace-grid">
    <div class="main-column">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Preflight</h2>
            <p>Show disk, provider/tool, library-root, and staging-path readiness before work begins.</p>
          </div>
          <button on:click={loadPreflight} disabled={preflightLoading}>{preflightLoading ? "Checking..." : "Recheck"}</button>
        </div>
        {#if preflight}
          <div class="preflight-status {preflight.ready ? 'ready' : 'blocked'}">{preflight.ready ? "Ready to process acquisitions" : "Preflight blockers need attention"}</div>
          <div class="preflight-grid">
            {#each preflight.checks as check}
              <article class={`check-card status-${check.status}`}>
                <span>{check.label}</span>
                <strong>{check.status}</strong>
                <small>{check.detail}</small>
              </article>
            {/each}
          </div>
          <ul class="note-list">
            {#each preflight.notes as note}
              <li>{note}</li>
            {/each}
          </ul>
          <small class="muted-inline">Free: {formatBytes(preflight.freeBytes)} / Required: {formatBytes(preflight.requiredBytes)}</small>
        {/if}
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Worker control</h2>
            <p>Keep the background acquisition loop moving or stop it before a risky environment change.</p>
          </div>
          <div class="worker-actions">
            <span class={`status-indicator ${workerRunning ? 'running' : 'stopped'}`}>{workerRunning ? "Running" : "Stopped"}</span>
            {#if workerRunning}
              <button on:click={stopWorker} disabled={workerLoading}>{workerLoading ? "Stopping..." : "Stop worker"}</button>
            {:else}
              <button on:click={startWorker} disabled={workerLoading}>{workerLoading ? "Starting..." : "Start worker"}</button>
            {/if}
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Add queue item</h2>
            <p>Seed the canonical acquisition workflow with destination intent and local validation context.</p>
          </div>
        </div>
        <div class="form-grid">
          <input type="text" bind:value={newArtist} placeholder="Artist *" />
          <input type="text" bind:value={newTitle} placeholder="Title *" />
          <input type="text" bind:value={newAlbum} placeholder="Album (optional)" />
          <input type="text" bind:value={newSource} placeholder="Lead source" />
          <select bind:value={newTargetRootId}>
            <option value="">First accessible root</option>
            {#each libraryRoots as root}
              <option value={String(root.id)}>{root.path}</option>
            {/each}
          </select>
          <button on:click={addItem} disabled={!newArtist.trim() || !newTitle.trim() || loading}>Add</button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Queue lifecycle</h2>
            <p>Track progress, provider choice, diagnostics, retry state, and downstream organize/scan/index completion.</p>
          </div>
          <label class="filter-label">
            <span>Status</span>
            <select bind:value={statusFilter} on:change={loadQueue}>
              {#each statusOptions as option}
                <option value={option.value}>{option.label}</option>
              {/each}
            </select>
          </label>
        </div>

        {#if loading && !filteredItems.length}
          <p class="empty-state">Loading acquisition queue...</p>
        {:else if !filteredItems.length}
          <p class="empty-state">No acquisition items match the current filter.</p>
        {:else}
          <table class="queue-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>State</th>
                <th>Progress</th>
                <th>Source / provider</th>
                <th>Diagnostics</th>
                <th>Priority</th>
                <th>Destination</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {#each filteredItems as item (item.id)}
                <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
                <tr class:selected={selectedItem?.id === item.id} on:click={() => (selectedId = item.id)}>
                  <td>
                    <div class="item-copy">
                      <strong>{item.artist}</strong>
                      <span>{item.title}</span>
                      {#if item.album}<small>{item.album}</small>{/if}
                    </div>
                  </td>
                  <td>
                    <span class={`badge ${badgeClass(item.status)}`}>{humanizeStatus(item.status)}</span>
                    {#if item.cancelRequested}<small class="flag">cancel requested</small>{/if}
                  </td>
                  <td>
                    <div class="lifecycle-cell">
                      <small>{item.lifecycleNote ?? humanizeStatus(item.status)}</small>
                      <div class="bar-bg"><div class="bar-fill" style={`width: ${stagePct(item)}%`}></div></div>
                      <small>{stagePct(item)}%</small>
                    </div>
                  </td>
                  <td class="meta-cell">
                    <small>Lead: {item.source ?? "-"}</small>
                    <small>Provider: {item.selectedProvider ?? "-"}</small>
                    <small>Tier: {item.selectedTier ?? "-"}</small>
                  </td>
                  <td class="meta-cell">
                    <small>{item.statusMessage ?? "-"}</small>
                    <small>{item.validationSummary ?? "-"}</small>
                    <small class="danger">{item.failureReason ?? item.error ?? "-"}</small>
                  </td>
                  <td>
                    <div class="priority-cell" on:click|stopPropagation>
                      <input type="range" min="1" max="10" step="0.1" value={item.priorityScore} on:change={(event) => updatePriority(item, (event.currentTarget as HTMLInputElement).value)} />
                      <small>{item.priorityScore.toFixed(2)} • #{item.queuePosition}</small>
                    </div>
                  </td>
                  <td>
                    <div class="destination-cell" on:click|stopPropagation>
                      <select
                        value={item.targetRootId ? String(item.targetRootId) : ""}
                        on:change={(event) => updateTargetRoot(item, (event.currentTarget as HTMLSelectElement).value)}
                      >
                        <option value="">First accessible root</option>
                        {#each libraryRoots as root}
                          <option value={String(root.id)}>{root.path}</option>
                        {/each}
                      </select>
                      <small>{item.targetRootPath ?? "First accessible root"}</small>
                    </div>
                  </td>
                  <td>
                    <div class="actions-cell" on:click|stopPropagation>
                      <button class="btn-small" on:click={() => moveItem(item, -1)} disabled={item.queuePosition <= 1}>Up</button>
                      <button class="btn-small" on:click={() => moveItem(item, 1)} disabled={item.queuePosition >= items.length}>Down</button>
                      {#if isRetryable(item)}<button class="btn-small" on:click={() => retryItem(item.id)}>Retry</button>{/if}
                      {#if isCancelable(item)}<button class="btn-small btn-danger" on:click={() => cancelItem(item.id)}>Cancel</button>{/if}
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    </div>

    <aside class="side-column">
      <section class="panel detail-panel">
        <div class="panel-head">
          <div>
            <h2>Item detail</h2>
            <p>Inspect stage ownership, downstream state, output path, and exact failure semantics.</p>
          </div>
        </div>
        {#if selectedItem}
          <div class="detail-stack">
            <div class="detail-hero">
              <strong>{selectedItem.artist} - {selectedItem.title}</strong>
              <span class={`badge ${badgeClass(selectedItem.status)}`}>{humanizeStatus(selectedItem.status)}</span>
            </div>
            <div class="detail-grid">
              <div><span>Lifecycle stage</span><strong>{detailValue(selectedItem.lifecycleStage)}</strong></div>
              <div><span>Status message</span><strong>{detailValue(selectedItem.statusMessage)}</strong></div>
              <div><span>Provider / tier</span><strong>{detailValue(selectedItem.selectedProvider)} / {detailValue(selectedItem.selectedTier)}</strong></div>
              <div><span>Worker</span><strong>{detailValue(selectedItem.workerLabel)}</strong></div>
              <div><span>Validation confidence</span><strong>{selectedItem.validationConfidence !== undefined && selectedItem.validationConfidence !== null ? `${Math.round(selectedItem.validationConfidence * 100)}%` : "-"}</strong></div>
              <div><span>Destination root</span><strong>{detailValue(selectedItem.targetRootPath)}</strong></div>
              <div><span>Retry count</span><strong>{selectedItem.retryCount}</strong></div>
              <div><span>Track id</span><strong>{detailValue(selectedItem.downstreamTrackId)}</strong></div>
              <div><span>Started</span><strong>{detailValue(selectedItem.startedAt)}</strong></div>
              <div><span>Completed</span><strong>{detailValue(selectedItem.completedAt)}</strong></div>
            </div>
            <div class="downstream-grid">
              <article class:selected={selectedItem.organizeCompleted}><span>Organize</span><strong>{selectedItem.organizeCompleted ? "Done" : "Pending"}</strong></article>
              <article class:selected={selectedItem.scanCompleted}><span>Scan</span><strong>{selectedItem.scanCompleted ? "Done" : "Pending"}</strong></article>
              <article class:selected={selectedItem.indexCompleted}><span>Index</span><strong>{selectedItem.indexCompleted ? "Done" : "Pending"}</strong></article>
            </div>
            <div class="detail-block"><span>Output path</span><code>{detailValue(selectedItem.outputPath)}</code></div>
            <div class="detail-block"><span>Validation summary</span><code>{detailValue(selectedItem.validationSummary)}</code></div>
            <div class="detail-block"><span>Failure detail</span><code>{detailValue(selectedItem.failureStage)} | {detailValue(selectedItem.failureReason)} | {detailValue(selectedItem.failureDetail ?? selectedItem.error)}</code></div>
          </div>
        {:else}
          <p class="empty-state">Select a queue item to inspect its lifecycle and diagnostics.</p>
        {/if}
      </section>

      <section class="panel activity-panel">
        <div class="panel-head">
          <div>
            <h2>Lifecycle events</h2>
            <p>Live backend updates from queue actions and worker progress.</p>
          </div>
        </div>
        {#if !activity.length}
          <p class="empty-state">No lifecycle events captured yet.</p>
        {:else}
          <ul class="activity-list">
            {#each activity as entry (entry.id)}
              <li class={`activity-item tone-${entry.tone}`}>
                <span class="activity-time">{formatClock(entry.at)}</span>
                <span>{entry.message}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </aside>
  </div>
</div>

<style>
  .page-acquisition { padding: 1.5rem; max-width: 1500px; margin: 0 auto; display: grid; gap: 1rem; }
  .page-header, .panel-head, .actions, .worker-actions, .actions-cell { display: flex; gap: 0.75rem; }
  .page-header, .panel-head { justify-content: space-between; align-items: flex-start; }
  .page-header {
    background: radial-gradient(circle at top left, rgba(120, 201, 255, 0.15), transparent 35%), linear-gradient(135deg, rgba(13, 17, 27, 0.96), rgba(19, 32, 43, 0.92));
    border: 1px solid rgba(122, 162, 191, 0.18);
    border-radius: 18px;
    padding: 1.25rem;
  }
  .eyebrow { margin: 0 0 0.25rem; text-transform: uppercase; letter-spacing: 0.16em; font-size: 0.72rem; color: #88a8bf; }
  h1, h2, p { margin: 0; }
  .lede { margin-top: 0.45rem; color: #a5b8c8; max-width: 58rem; }
  .summary-grid, .workspace-grid, .preflight-grid, .form-grid, .detail-grid, .downstream-grid { display: grid; gap: 0.85rem; }
  .summary-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .workspace-grid { grid-template-columns: minmax(0, 2.6fr) minmax(22rem, 1fr); align-items: start; }
  .main-column, .side-column { display: grid; gap: 1rem; }
  .summary-card, .panel {
    border-radius: 16px;
    border: 1px solid rgba(122, 162, 191, 0.14);
    background: linear-gradient(180deg, rgba(18, 24, 33, 0.94), rgba(9, 14, 20, 0.96));
    box-shadow: 0 14px 30px rgba(0, 0, 0, 0.16);
  }
  .summary-card { padding: 1rem; display: grid; gap: 0.25rem; }
  .summary-label { color: #86a1b5; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; }
  .summary-card strong { font-size: 1.55rem; }
  .panel { padding: 1rem; display: grid; gap: 0.9rem; }
  .panel-head p, .muted-inline { color: #97adbf; }
  .preflight-status { padding: 0.85rem 1rem; border-radius: 12px; font-weight: 600; }
  .preflight-status.ready { background: rgba(92, 212, 153, 0.12); color: #88f0b8; }
  .preflight-status.blocked { background: rgba(255, 139, 139, 0.12); color: #ffaaaa; }
  .preflight-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .check-card { display: grid; gap: 0.2rem; padding: 0.9rem; border-radius: 12px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.05); }
  .status-ok { border-color: rgba(124, 240, 177, 0.2); }
  .status-warning { border-color: rgba(255, 195, 107, 0.2); }
  .status-failed { border-color: rgba(255, 138, 138, 0.22); }
  .note-list, .activity-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 0.6rem; }
  .note-list li { color: #b2c1ce; padding: 0.6rem 0.75rem; border-radius: 10px; background: rgba(255, 255, 255, 0.035); }
  .form-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .form-grid input, .form-grid select, .filter-label select, .destination-cell select, button, .queue-table input[type="range"] { font: inherit; }
  .form-grid input, .form-grid select, .filter-label select, .destination-cell select {
    padding: 0.72rem 0.8rem;
    border-radius: 10px;
    border: 1px solid rgba(145, 176, 201, 0.16);
    background: rgba(3, 8, 13, 0.72);
    color: inherit;
  }
  .filter-label { display: grid; gap: 0.35rem; min-width: 10rem; }
  button { border: 1px solid rgba(122, 162, 191, 0.2); border-radius: 10px; padding: 0.68rem 0.95rem; background: rgba(13, 48, 72, 0.5); color: #ecf4f9; cursor: pointer; }
  button:disabled { opacity: 0.55; cursor: default; }
  .btn-small { padding: 0.35rem 0.55rem; font-size: 0.84rem; }
  .btn-danger { color: #ff9a9a; }
  .status-indicator { padding: 0.55rem 0.8rem; border-radius: 999px; border: 1px solid rgba(122, 162, 191, 0.18); background: rgba(255, 255, 255, 0.035); }
  .status-indicator.running { color: #7cf0b1; }
  .status-indicator.stopped { color: #ff9c8f; }
  .queue-table { width: 100%; border-collapse: collapse; overflow: hidden; }
  .queue-table th, .queue-table td { padding: 0.8rem 0.65rem; border-bottom: 1px solid rgba(255, 255, 255, 0.06); text-align: left; vertical-align: top; }
  .queue-table tbody tr { cursor: pointer; }
  .queue-table tbody tr.selected { background: rgba(117, 194, 255, 0.08); }
  .queue-table th { color: #86a1b5; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; }
  .item-copy, .meta-cell, .lifecycle-cell, .priority-cell, .destination-cell, .detail-stack, .detail-block { display: grid; gap: 0.35rem; }
  .item-copy span, .item-copy small, .meta-cell small { color: #b7c5d1; }
  .danger { color: #ffb0b0; }
  .badge { display: inline-flex; align-items: center; padding: 0.26rem 0.5rem; border-radius: 999px; font-size: 0.75rem; text-transform: uppercase; }
  .badge-queued { background: rgba(118, 170, 255, 0.16); color: #8bb8ff; }
  .badge-validating { background: rgba(185, 151, 255, 0.16); color: #cab1ff; }
  .badge-acquiring { background: rgba(255, 197, 95, 0.16); color: #ffcb78; }
  .badge-staging { background: rgba(255, 168, 112, 0.16); color: #ffc28a; }
  .badge-organizing { background: rgba(102, 224, 196, 0.16); color: #88f0d3; }
  .badge-scanning { background: rgba(95, 211, 255, 0.16); color: #8fdcff; }
  .badge-indexing { background: rgba(129, 206, 255, 0.16); color: #8fcfff; }
  .badge-success { background: rgba(85, 216, 154, 0.16); color: #7cf0b1; }
  .badge-error { background: rgba(255, 128, 128, 0.16); color: #ff9b9b; }
  .badge-warning { background: rgba(255, 174, 102, 0.16); color: #ffbf84; }
  .flag { display: block; margin-top: 0.3rem; color: #ffcb78; text-transform: uppercase; font-size: 0.68rem; letter-spacing: 0.08em; }
  .bar-bg { height: 0.42rem; border-radius: 999px; overflow: hidden; background: rgba(255, 255, 255, 0.08); }
  .bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #36b19b, #75c2ff); }
  .detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .detail-grid div, .detail-block { padding: 0.8rem; border-radius: 12px; background: rgba(255, 255, 255, 0.03); }
  .detail-grid span, .detail-block span { color: #89a5b8; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; }
  .detail-hero { display: flex; justify-content: space-between; gap: 0.8rem; align-items: center; }
  .downstream-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .downstream-grid article { padding: 0.8rem; border-radius: 12px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.04); }
  .downstream-grid article.selected { border-color: rgba(124, 240, 177, 0.2); }
  code { white-space: pre-wrap; word-break: break-word; }
  .activity-panel { position: sticky; top: 1rem; }
  .activity-item { display: grid; gap: 0.18rem; padding: 0.8rem; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.028); }
  .activity-time { font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.08em; color: #86a1b5; }
  .tone-success { border-color: rgba(124, 240, 177, 0.18); }
  .tone-error { border-color: rgba(255, 128, 128, 0.22); }
  .tone-warning { border-color: rgba(255, 185, 120, 0.2); }
  .empty-state { color: #98aebf; padding: 0.8rem 0; }
  @media (max-width: 1180px) {
    .summary-grid, .workspace-grid, .preflight-grid, .form-grid, .detail-grid, .downstream-grid { grid-template-columns: 1fr; }
    .activity-panel { position: static; }
    .page-header, .panel-head, .actions, .worker-actions, .detail-hero { flex-direction: column; align-items: stretch; }
  }
</style>

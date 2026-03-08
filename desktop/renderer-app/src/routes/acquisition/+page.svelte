<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import type { AcquisitionPreflight, AcquisitionQueueItem } from "$lib/types";

  let items: AcquisitionQueueItem[] = [];
  let statusFilter: string | undefined = undefined;
  let loading = false;
  let processing = false;
  let workerRunning = false;
  let workerLoading = false;
  let preflight: AcquisitionPreflight | null = null;
  let preflightLoading = false;
  let clearBusy = false;

  let newArtist = "";
  let newTitle = "";
  let newAlbum = "";
  let newSource = "manual";

  const statusOptions = [
    { value: undefined, label: "All" },
    { value: "pending", label: "Pending" },
    { value: "in_progress", label: "In Progress" },
    { value: "completed", label: "Completed" },
    { value: "failed", label: "Failed" },
    { value: "skipped", label: "Skipped" },
  ];

  onMount(async () => {
    await Promise.all([loadQueue(), checkWorkerStatus(), loadPreflight()]);
  });

  async function loadQueue(): Promise<void> {
    loading = true;
    try {
      items = await api.acquisitionQueue(statusFilter);
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
    } catch (err) {
      console.error("Failed to check worker status:", err);
    }
  }

  async function startWorker(): Promise<void> {
    workerLoading = true;
    try {
      const started = await api.startAcquisitionWorker();
      if (started) workerRunning = true;
    } finally {
      workerLoading = false;
    }
  }

  async function stopWorker(): Promise<void> {
    workerLoading = true;
    try {
      await api.stopAcquisitionWorker();
      workerRunning = false;
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
      if (processed) await loadQueue();
    } finally {
      processing = false;
    }
  }

  async function retryItem(id: number): Promise<void> {
    loading = true;
    try {
      items = await api.updateAcquisitionItem(id, "pending");
    } finally {
      loading = false;
    }
  }

  async function skipItem(id: number): Promise<void> {
    loading = true;
    try {
      items = await api.updateAcquisitionItem(id, "skipped");
    } finally {
      loading = false;
    }
  }

  async function clearCompleted(): Promise<void> {
    clearBusy = true;
    try {
      await api.clearCompletedAcquisition();
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

  function getStatusBadgeClass(status: string): string {
    switch (status) {
      case "pending": return "badge-pending";
      case "in_progress": return "badge-progress";
      case "completed": return "badge-success";
      case "failed": return "badge-error";
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
</script>

<div class="page-acquisition">
  <header>
    <h1>Acquisition Queue</h1>
    <div class="actions">
      <button on:click={processNext} disabled={processing || loading}>
        {processing ? "Processing..." : "Process Next"}
      </button>
      <button on:click={clearCompleted} disabled={clearBusy || loading}>
        {clearBusy ? "Clearing..." : "Clear Completed"}
      </button>
      <button on:click={loadQueue} disabled={loading}>Refresh</button>
    </div>
  </header>

  <section class="preflight">
    <div class="preflight-head">
      <h2>Preflight</h2>
      <button on:click={loadPreflight} disabled={preflightLoading}>{preflightLoading ? "Checking..." : "Recheck"}</button>
    </div>
    {#if preflight}
      <div class="preflight-grid">
        <span class:ok={preflight.pythonAvailable} class:bad={!preflight.pythonAvailable}>Python: {preflight.pythonAvailable ? "OK" : "Missing"}</span>
        <span class:ok={preflight.downloaderAvailable} class:bad={!preflight.downloaderAvailable}>Downloader: {preflight.downloaderAvailable ? "OK" : "Missing"}</span>
        <span class:ok={preflight.diskOk} class:bad={!preflight.diskOk}>Disk: {preflight.diskOk ? "OK" : "Low"}</span>
        <span>Free: {formatBytes(preflight.freeBytes)} / Required: {formatBytes(preflight.requiredBytes)}</span>
      </div>
      <ul>
        {#each preflight.notes as note}
          <li>{note}</li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="worker-control">
    <h2>Background Worker</h2>
    <div class="worker-status">
      <span class="status-indicator {workerRunning ? 'running' : 'stopped'}">
        {workerRunning ? "Running" : "Stopped"}
      </span>
      {#if workerRunning}
        <button on:click={stopWorker} disabled={workerLoading}>{workerLoading ? "Stopping..." : "Stop Worker"}</button>
      {:else}
        <button on:click={startWorker} disabled={workerLoading}>{workerLoading ? "Starting..." : "Start Worker"}</button>
      {/if}
      <button on:click={checkWorkerStatus} disabled={workerLoading}>Check Status</button>
    </div>
  </section>

  <section class="add-form">
    <h2>Add to Queue</h2>
    <div class="form-grid">
      <input type="text" bind:value={newArtist} placeholder="Artist *" />
      <input type="text" bind:value={newTitle} placeholder="Title *" />
      <input type="text" bind:value={newAlbum} placeholder="Album (optional)" />
      <input type="text" bind:value={newSource} placeholder="Source" />
      <button on:click={addItem} disabled={!newArtist.trim() || !newTitle.trim() || loading}>+ Add</button>
    </div>
  </section>

  <section class="filter-bar">
    <label>
      Status:
      <select bind:value={statusFilter} on:change={loadQueue}>
        {#each statusOptions as opt}
          <option value={opt.value}>{opt.label}</option>
        {/each}
      </select>
    </label>
    <span class="count">{items.length} item{items.length !== 1 ? 's' : ''}</span>
  </section>

  {#if loading && items.length === 0}
    <p>Loading...</p>
  {:else if items.length === 0}
    <p class="empty-state">No acquisition items found.</p>
  {:else}
    <table class="queue-table">
      <thead>
        <tr>
          <th>Artist</th>
          <th>Title</th>
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
            <td>{item.artist}</td>
            <td>{item.title}</td>
            <td><span class="badge {getStatusBadgeClass(item.status)}">{item.status}</span></td>
            <td>
              <div class="lifecycle-cell">
                <small>{stageLabel(item)}</small>
                <div class="bar-bg"><div class="bar-fill" style="width: {stagePct(item)}%"></div></div>
                <small>{stagePct(item)}%</small>
              </div>
            </td>
            <td>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={item.priorityScore}
                on:change={(e) => updatePriority(item, (e.currentTarget as HTMLInputElement).value)}
              />
              <small>{item.priorityScore.toFixed(2)}</small>
            </td>
            <td class="error-cell">{item.error || "-"}</td>
            <td class="actions-cell">
              {#if item.status === "failed"}<button class="btn-small" on:click={() => retryItem(item.id)}>Retry</button>{/if}
              {#if item.status === "pending" || item.status === "failed"}<button class="btn-small btn-danger" on:click={() => skipItem(item.id)}>Skip</button>{/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .page-acquisition { padding: 1.25rem; max-width: 1400px; margin: 0 auto; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
  .actions { display: flex; gap: 0.5rem; }
  .preflight, .worker-control, .add-form { background: rgba(255, 255, 255, 0.05); padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
  .preflight-head { display: flex; justify-content: space-between; align-items: center; }
  .preflight-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.5rem; margin: 0.5rem 0; }
  .ok { color: #22c55e; }
  .bad { color: #ef4444; }
  .worker-status { display: flex; align-items: center; gap: 1rem; }
  .status-indicator.running { color: #22c55e; }
  .status-indicator.stopped { color: #ef4444; }
  .form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr auto; gap: 0.75rem; margin-top: 0.75rem; }
  .form-grid input { padding: 0.5rem; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; background: rgba(0,0,0,0.3); color: #fff; }
  .filter-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; padding: 0.75rem; background: rgba(255,255,255,0.05); border-radius: 4px; }
  .queue-table { width: 100%; border-collapse: collapse; background: rgba(255,255,255,0.05); border-radius: 8px; overflow: hidden; }
  .queue-table th, .queue-table td { padding: 0.6rem; border-bottom: 1px solid rgba(255,255,255,0.06); }
  .badge { padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.75rem; text-transform: uppercase; }
  .badge-pending { background: rgba(100,149,237,0.3); color: #6495ed; }
  .badge-progress { background: rgba(255,165,0,0.3); color: #ffa500; }
  .badge-success { background: rgba(34,197,94,0.3); color: #22c55e; }
  .badge-error { background: rgba(239,68,68,0.3); color: #ef4444; }
  .lifecycle-cell { display: grid; gap: 4px; min-width: 180px; }
  .bar-bg { height: 5px; border-radius: 3px; background: rgba(255,255,255,0.12); }
  .bar-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #34cfab, #5ad1ff); }
  .actions-cell { display: flex; gap: 0.5rem; }
  .btn-small { padding: 0.25rem 0.5rem; border-radius: 4px; }
  .btn-danger { color: #ef4444; }
  .empty-state { text-align: center; padding: 2rem; opacity: 0.6; }
</style>

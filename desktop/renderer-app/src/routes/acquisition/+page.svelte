<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/tauri";
  import type { AcquisitionQueueItem } from "$lib/types";

  let items: AcquisitionQueueItem[] = [];
  let statusFilter: string | undefined = undefined;
  let loading = false;
  let processing = false;
  let workerRunning = false;
  let workerLoading = false;

  // Form for adding new items
  let newArtist = "";
  let newTitle = "";
  let newAlbum = "";
  let newSource = "";

  let statusOptions = [
    { value: undefined, label: "All" },
    { value: "pending", label: "Pending" },
    { value: "in_progress", label: "In Progress" },
    { value: "completed", label: "Completed" },
    { value: "failed", label: "Failed" }
  ];

  onMount(() => {
    loadQueue();
    checkWorkerStatus();
  });

  async function loadQueue() {
    loading = true;
    try {
      items = await api.acquisitionQueue(statusFilter);
    } finally {
      loading = false;
    }
  }

  async function checkWorkerStatus() {
    try {
      workerRunning = await api.acquisitionWorkerStatus();
    } catch (err) {
      console.error("Failed to check worker status:", err);
    }
  }

  async function startWorker() {
    workerLoading = true;
    try {
      const started = await api.startAcquisitionWorker();
      if (started) {
        workerRunning = true;
      } else {
        alert("Worker is already running");
      }
    } catch (err) {
      alert(`Failed to start worker: ${err}`);
    } finally {
      workerLoading = false;
    }
  }

  async function stopWorker() {
    workerLoading = true;
    try {
      await api.stopAcquisitionWorker();
      workerRunning = false;
    } catch (err) {
      alert(`Failed to stop worker: ${err}`);
    } finally {
      workerLoading = false;
    }
  }

  async function addItem() {
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
      newSource = "";
    } finally {
      loading = false;
    }
  }

  async function processNext() {
    processing = true;
    try {
      const processed = await api.processAcquisitionQueue();
      if (processed) {
        await loadQueue();
      } else {
        alert("Queue is empty");
      }
    } catch (err) {
      alert(`Error: ${err}`);
    } finally {
      processing = false;
    }
  }

  async function retryItem(id: number) {
    loading = true;
    try {
      items = await api.updateAcquisitionItem(id, "pending");
    } finally {
      loading = false;
    }
  }

  async function deleteItem(id: number) {
    loading = true;
    try {
      items = await api.updateAcquisitionItem(id, "skipped");
    } finally {
      loading = false;
    }
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

  $: {
    void loadQueue();
  }
</script>

<div class="page-acquisition">
  <header>
    <h1>Acquisition Queue</h1>
    <div class="actions">
      <button onclick={processNext} disabled={processing || loading}>
        {processing ? "Processing..." : "Process Next"}
      </button>
      <button onclick={loadQueue} disabled={loading}>Refresh</button>
    </div>
  </header>

  <section class="worker-control">
    <h2>Background Worker</h2>
    <div class="worker-status">
      <span class="status-indicator {workerRunning ? 'running' : 'stopped'}">
        {workerRunning ? "● Running" : "○ Stopped"}
      </span>
      {#if workerRunning}
        <button onclick={stopWorker} disabled={workerLoading}>
          {workerLoading ? "Stopping..." : "Stop Worker"}
        </button>
      {:else}
        <button onclick={startWorker} disabled={workerLoading}>
          {workerLoading ? "Starting..." : "Start Worker"}
        </button>
      {/if}
      <button onclick={checkWorkerStatus} disabled={workerLoading}>Check Status</button>
    </div>
  </section>

  <section class="add-form">
    <h2>Add to Queue</h2>
    <div class="form-grid">
      <input type="text" bind:value={newArtist} placeholder="Artist *" />
      <input type="text" bind:value={newTitle} placeholder="Title *" />
      <input type="text" bind:value={newAlbum} placeholder="Album (optional)" />
      <input type="text" bind:value={newSource} placeholder="Source (optional)" />
      <button onclick={addItem} disabled={!newArtist.trim() || !newTitle.trim() || loading}>
        + Add
      </button>
    </div>
  </section>

  <section class="filter-bar">
    <label>
      Status:
      <select bind:value={statusFilter}>
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
          <th>Album</th>
          <th>Status</th>
          <th>Priority</th>
          <th>Source</th>
          <th>Added</th>
          <th>Error</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {#each items as item (item.id)}
          <tr>
            <td>{item.artist}</td>
            <td>{item.title}</td>
            <td>{item.album || '—'}</td>
            <td>
              <span class="badge {getStatusBadgeClass(item.status)}">
                {item.status}
              </span>
            </td>
            <td>{item.priorityScore?.toFixed(2) || '0.00'}</td>
            <td>{item.source || '—'}</td>
            <td>
              {new Date(item.addedAt).toLocaleDateString()}
            </td>
            <td class="error-cell">
              {#if item.error}
                <span class="error-text" title={item.error}>
                  {item.error.substring(0, 50)}{item.error.length > 50 ? '...' : ''}
                </span>
              {:else}
                —
              {/if}
            </td>
            <td class="actions-cell">
              {#if item.status === "failed"}
                <button class="btn-small" onclick={() => retryItem(item.id)}>Retry</button>
              {/if}
              {#if item.status === "pending" || item.status === "failed"}
                <button class="btn-small btn-danger" onclick={() => deleteItem(item.id)}>Skip</button>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .page-acquisition {
    padding: 2rem;
    max-width: 1400px;
    margin: 0 auto;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }

  .actions {
    display: flex;
    gap: 0.5rem;
  }

  .worker-control {
    background: rgba(100, 150, 255, 0.1);
    padding: 1.5rem;
    border-radius: 8px;
    margin-bottom: 2rem;
    border: 1px solid rgba(100, 150, 255, 0.3);
  }

  .worker-control h2 {
    margin-top: 0;
    margin-bottom: 1rem;
    font-size: 1.1rem;
  }

  .worker-status {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .status-indicator {
    font-weight: 600;
    padding: 0.5rem 1rem;
    border-radius: 20px;
  }

  .status-indicator.running {
    background: rgba(46, 204, 113, 0.2);
    color: #2ecc71;
  }

  .status-indicator.stopped {
    background: rgba(255, 87, 87, 0.2);
    color: #ff5757;
  }

  .add-form {
    background: rgba(255, 255, 255, 0.05);
    padding: 1.5rem;
    border-radius: 8px;
    margin-bottom: 2rem;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 1fr auto;
    gap: 0.75rem;
    margin-top: 1rem;
  }

  .form-grid input {
    padding: 0.5rem;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.3);
    color: #fff;
  }

  .filter-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding: 0.75rem;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 4px;
  }

  .filter-bar label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .filter-bar select {
    padding: 0.25rem 0.5rem;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    color: #fff;
  }

  .count {
    color: rgba(255, 255, 255, 0.6);
    font-size: 0.9rem;
  }

  .queue-table {
    width: 100%;
    border-collapse: collapse;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    overflow: hidden;
  }

  .queue-table thead {
    background: rgba(0, 0, 0, 0.3);
  }

  .queue-table th {
    padding: 0.75rem;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid rgba(255, 255, 255, 0.1);
  }

  .queue-table td {
    padding: 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }

  .queue-table tbody tr:hover {
    background: rgba(255, 255, 255, 0.08);
  }

  .badge {
    display: inline-block;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
  }

  .badge-pending {
    background: rgba(100, 149, 237, 0.3);
    color: #6495ed;
  }

  .badge-progress {
    background: rgba(255, 165, 0, 0.3);
    color: #ffa500;
  }

  .badge-success {
    background: rgba(34, 197, 94, 0.3);
    color: #22c55e;
  }

  .badge-error {
    background: rgba(239, 68, 68, 0.3);
    color: #ef4444;
  }

  .error-cell {
    max-width: 200px;
  }

  .error-text {
    color: #ef4444;
    font-size: 0.9rem;
  }

  .actions-cell {
    display: flex;
    gap: 0.5rem;
  }

  .btn-small {
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    border-radius: 4px;
    background: rgba(100, 149, 237, 0.3);
    border: 1px solid rgba(100, 149, 237, 0.5);
    color: #6495ed;
    cursor: pointer;
  }

  .btn-small:hover {
    background: rgba(100, 149, 237, 0.5);
  }

  .btn-danger {
    background: rgba(239, 68, 68, 0.3);
    border-color: rgba(239, 68, 68, 0.5);
    color: #ef4444;
  }

  .btn-danger:hover {
    background: rgba(239, 68, 68, 0.5);
  }

  .empty-state {
    text-align: center;
    padding: 3rem;
    color: rgba(255, 255, 255, 0.5);
  }

  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>

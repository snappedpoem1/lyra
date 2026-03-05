/**
 * agentActionRouter — maps AgentResponse.action + intent to app-side effects.
 *
 * Call after every successful queryAgent(). Reads intent fields and fires
 * store mutations / navigation / backend API calls without rendering anything.
 *
 * Register the TanStack navigate function from AppShell once on mount.
 */
import type { AgentResponse } from "@/types/domain";
import { useUiStore } from "@/stores/uiStore";
import { useSearchStore } from "@/stores/searchStore";

// Injected by AppShell — avoids circular dep on router hook
let _navigate: ((opts: { to: string }) => void) | null = null;

export function registerNavigate(fn: (opts: { to: string }) => void) {
  _navigate = fn;
}

function nav(to: string) { _navigate?.({ to }); }

/** Fire a backend API call without blocking the action router. */
async function callApi(path: string, body?: unknown): Promise<void> {
  try {
    await fetch(`http://localhost:5000${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    // best-effort — router must not throw
  }
}

export function routeAgentAction(response: AgentResponse): void {
  const { action, intent } = response;
  const i = (intent ?? {}) as Record<string, unknown>;

  switch (action) {
    // ── Navigation ───────────────────────────────────────────────────────
    case "navigate":
    case "open_page": {
      const route = (i.route ?? i.page) as string | undefined;
      if (route) nav(route);
      break;
    }

    // ── Dossier ──────────────────────────────────────────────────────────
    case "open_dossier":
    case "openDossier": {
      const trackId = (i.track_id ?? i.trackId) as string | undefined;
      if (trackId) useUiStore.getState().openDossier(trackId);
      break;
    }

    // ── Search with pre-filled query ─────────────────────────────────────
    case "search": {
      const query = (i.query ?? i.text) as string | undefined;
      if (query) {
        useSearchStore.getState().setQuery(query);
        nav("/search");
      }
      break;
    }

    // ── Radio modes ──────────────────────────────────────────────────────
    case "start_radio": {
      const mode = (i.mode ?? "chaos") as string;
      const seed = i.track_id ?? i.seed;
      callApi(`/api/radio/${mode === "flow" ? "flow" : "chaos"}`, seed ? { seed_track_id: seed } : {});
      nav("/queue");
      break;
    }

    // ── Queue a specific track ────────────────────────────────────────────
    case "queue_track": {
      const trackId = (i.track_id ?? i.trackId) as string | undefined;
      if (trackId) {
        callApi("/api/radio/queue", { track_id: trackId });
        nav("/queue");
      }
      break;
    }

    // ── Generate a playlist from intent ──────────────────────────────────
    case "generate_playlist": {
      const mood = (i.mood ?? i.query ?? i.text ?? "") as string;
      callApi("/api/playlust/generate", { prompt: mood, duration: 60 });
      nav("/playlists");
      break;
    }

    // ── Acquire a track ──────────────────────────────────────────────────
    case "acquire_track": {
      const artist = i.artist as string | undefined;
      const title = i.title as string | undefined;
      if (artist && title) {
        callApi("/api/acquire/queue", { artist, title, source: "agent" });
      }
      break;
    }

    // ── Enrich an artist ─────────────────────────────────────────────────
    case "enrich_artist": {
      const artist = (i.artist ?? i.name) as string | undefined;
      if (artist) callApi("/api/enrich/artist", { artist });
      break;
    }

    // ── Named page shortcuts ─────────────────────────────────────────────
    case "open_oracle":     nav("/oracle");    break;
    case "open_queue":      nav("/queue");     break;
    case "open_library":    nav("/library");   break;
    case "open_playlists":  nav("/playlists"); break;
    case "open_settings":   nav("/settings");  break;
    case "open_vibes":      nav("/vibes");     break;
    case "open_search":     nav("/search");    break;

    // ── Artist page ──────────────────────────────────────────────────────
    case "open_artist": {
      const name = (i.artist ?? i.name) as string | undefined;
      if (name) nav(`/artist/${encodeURIComponent(name)}`);
      break;
    }

    default:
      // "respond", "error", "suggest" — text shown in thread, no routing
      break;
  }
}

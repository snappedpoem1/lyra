/**
 * agentActionRouter — maps AgentResponse.action + intent to app-side effects.
 *
 * Call after every successful queryAgent(). Reads intent fields and fires
 * store mutations / navigation without rendering anything.
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

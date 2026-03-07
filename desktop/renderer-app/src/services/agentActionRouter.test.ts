import { describe, it, expect, vi, beforeEach } from "vitest";
import { routeAgentAction, registerNavigate } from "./agentActionRouter";
import { useUiStore } from "@/stores/uiStore";
import { useSearchStore } from "@/stores/searchStore";
import type { AgentResponse } from "@/types/domain";

vi.mock("@/services/lyraGateway/client", () => ({
  resolveApiUrl: (path: string) => `http://localhost:5000${path}`,
}));

const mockFetch = vi.fn().mockResolvedValue(new Response());
globalThis.fetch = mockFetch;

function makeResponse(action: string, intent: Record<string, unknown> = {}): AgentResponse {
  return { action, intent, thought: "", next: {} };
}

describe("routeAgentAction", () => {
  let navigatedTo: string | null = null;

  beforeEach(() => {
    navigatedTo = null;
    registerNavigate(({ to }) => { navigatedTo = to; });
    vi.clearAllMocks();
    useUiStore.setState({ dossierTrackId: null, rightRailTab: "now-playing" });
    useSearchStore.setState({ query: "", rewrittenQuery: "" });
  });

  it("navigates for 'navigate' action with route intent", () => {
    routeAgentAction(makeResponse("navigate", { route: "/library" }));
    expect(navigatedTo).toBe("/library");
  });

  it("navigates for 'open_page' action using page intent", () => {
    routeAgentAction(makeResponse("open_page", { page: "/settings" }));
    expect(navigatedTo).toBe("/settings");
  });

  it("opens dossier and sets rightRailTab to details", () => {
    routeAgentAction(makeResponse("open_dossier", { track_id: "track-abc" }));
    expect(useUiStore.getState().dossierTrackId).toBe("track-abc");
    expect(useUiStore.getState().rightRailTab).toBe("details");
  });

  it("accepts camelCase trackId for open_dossier", () => {
    routeAgentAction(makeResponse("openDossier", { trackId: "track-xyz" }));
    expect(useUiStore.getState().dossierTrackId).toBe("track-xyz");
  });

  it("sets search query and navigates to /search", () => {
    routeAgentAction(makeResponse("search", { query: "Radiohead" }));
    expect(useSearchStore.getState().query).toBe("Radiohead");
    expect(navigatedTo).toBe("/search");
  });

  it("accepts 'text' intent key for search", () => {
    routeAgentAction(makeResponse("search", { text: "Arca" }));
    expect(useSearchStore.getState().query).toBe("Arca");
  });

  it.each([
    ["open_oracle", "/oracle"],
    ["open_queue", "/queue"],
    ["open_library", "/library"],
    ["open_playlists", "/playlists"],
    ["open_settings", "/settings"],
    ["open_vibes", "/vibes"],
    ["open_search", "/search"],
  ])("navigates for named page shortcut '%s'", (action, expectedRoute) => {
    routeAgentAction(makeResponse(action));
    expect(navigatedTo).toBe(expectedRoute);
  });

  it("navigates to /artist/<name> for open_artist", () => {
    routeAgentAction(makeResponse("open_artist", { artist: "Aphex Twin" }));
    expect(navigatedTo).toBe("/artist/Aphex%20Twin");
  });

  it("posts to acquire endpoint for 'acquire_track' with artist and title", () => {
    routeAgentAction(makeResponse("acquire_track", { artist: "Aphex Twin", title: "Windowlicker" }));
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:5000/api/acquire/queue",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("does not post for 'acquire_track' when artist or title is missing", () => {
    routeAgentAction(makeResponse("acquire_track", { artist: "Aphex Twin" }));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("does not throw for terminal response actions", () => {
    expect(() => routeAgentAction(makeResponse("respond"))).not.toThrow();
    expect(() => routeAgentAction(makeResponse("error"))).not.toThrow();
    expect(() => routeAgentAction(makeResponse("suggest"))).not.toThrow();
  });

  it("does not throw for unknown action values", () => {
    expect(() => routeAgentAction(makeResponse("unrecognised_action"))).not.toThrow();
  });
});

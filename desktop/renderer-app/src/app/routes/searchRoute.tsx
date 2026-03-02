import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { SearchHero } from "@/features/search/SearchHero";
import { SearchResultStack } from "@/features/search/SearchResultStack";
import { DimensionalSearchPanel } from "@/features/search/DimensionalSearchPanel";
import { audioEngine } from "@/services/audio/audioEngine";
import { createVibe, generateVibe } from "@/services/lyraGateway/queries";
import { useQueueStore } from "@/stores/queueStore";
import { useSearchStore } from "@/stores/searchStore";
import { LyraButton } from "@/ui/LyraButton";

type SearchMode = "text" | "dimensional";

export function SearchRoute() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchMode, setSearchMode] = useState<SearchMode>("text");
  const query = useSearchStore((state) => state.query);
  const setQuery = useSearchStore((state) => state.setQuery);
  const [draftQuery, setDraftQuery] = useState(query);
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const { data, isFetching, isError, error } = useQuery({
    queryKey: ["search", query],
    queryFn: () => generateVibe(query),
    enabled: query.trim().length > 0,
  });
  const saveMutation = useMutation({
    mutationFn: ({ prompt, name }: { prompt: string; name: string }) => createVibe(prompt, name),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["playlists"] });
      void navigate({ to: "/vibes" });
    },
  });

  const results = data ? {
    query: data.meta.prompt || query,
    rewrittenQuery: typeof data.meta.generated?.query === "string" ? data.meta.generated.query : undefined,
    tracks: data.run.tracks,
    playlists: [],
    versions: [],
    oraclePivots: [],
  } : null;

  const handleSaveVibe = () => {
    if (!data) {
      return;
    }
    const defaultName =
      (typeof data.meta.generated?.name === "string" && data.meta.generated.name.trim()) ||
      (data.meta.prompt || query).split(/\s+/).slice(0, 4).join(" ").trim() ||
      "Generated Vibe";
    const vibeName = window.prompt("Name this vibe", defaultName)?.trim();
    if (!vibeName) {
      return;
    }
    saveMutation.mutate({ prompt: data.meta.prompt || query, name: vibeName });
  };

  const handleDimTrackSelect = (track: { track_id: string; artist: string; title: string; album?: string | null; filepath?: string; path?: string }) => {
    const item = {
      trackId: track.track_id,
      artist: track.artist,
      title: track.title,
      album: track.album ?? undefined,
      filepath: track.filepath ?? track.path ?? "",
      duration: undefined,
    };
    replaceQueue({
      queueId: `dim-${track.track_id}`,
      origin: "dimensional-search",
      reorderable: true,
      currentIndex: 0,
      items: [item],
    });
    void audioEngine.playTrack(item);
  };

  return (
    <div className="route-stack">
      {/* Mode toggle */}
      <div className="search-mode-toggle">
        <button
          className={`search-mode-btn${searchMode === "text" ? " active" : ""}`}
          onClick={() => setSearchMode("text")}
        >
          Text Search
        </button>
        <button
          className={`search-mode-btn${searchMode === "dimensional" ? " active" : ""}`}
          onClick={() => setSearchMode("dimensional")}
        >
          Dimensional
        </button>
      </div>

      {/* Dimensional mode */}
      {searchMode === "dimensional" && (
        <DimensionalSearchPanel onTrackSelect={handleDimTrackSelect} />
      )}

      {/* Text mode */}
      {searchMode === "text" && (
        <>
      <SearchHero
        query={draftQuery}
        onQueryChange={setDraftQuery}
        onSubmit={() => setQuery(draftQuery.trim())}
        loading={isFetching}
      />
      {!query.trim() && <section className="lyra-panel empty-state-panel">Enter a query to search the live library.</section>}
      {isError && (
        <section className="lyra-panel empty-state-panel">
          <h2>Search unavailable</h2>
          <p>{error instanceof Error ? error.message : "The backend returned an error."}</p>
          <LyraButton onClick={() => setQuery(draftQuery.trim())} disabled={!draftQuery.trim()}>Retry search</LyraButton>
        </section>
      )}
      {saveMutation.isError && (
        <section className="lyra-panel empty-state-panel">
          <h2>Save failed</h2>
          <p>{saveMutation.error instanceof Error ? saveMutation.error.message : "The vibe could not be saved."}</p>
        </section>
      )}
      {query.trim() && !data && !isError && <section className="lyra-panel empty-state-panel">Searching the backend...</section>}
      {results && (
        <SearchResultStack
          results={results}
          onSaveVibe={handleSaveVibe}
          savePending={saveMutation.isPending}
          saveDisabled={!results.tracks.length}
          saveLabel={saveMutation.isSuccess ? "Saved" : "Save to Library"}
          onPlayTrack={(track) => {
            replaceQueue({
              queueId: `search-${track.trackId}`,
              origin: "search",
              reorderable: true,
              currentIndex: 0,
              items: [track],
            });
            void audioEngine.playTrack(track);
          }}
        />
      )}
        </>
      )}
}

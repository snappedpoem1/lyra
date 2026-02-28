import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SearchHero } from "@/features/search/SearchHero";
import { SearchResultStack } from "@/features/search/SearchResultStack";
import { audioEngine } from "@/services/audio/audioEngine";
import { getSearchResults } from "@/services/lyraGateway/queries";
import { useQueueStore } from "@/stores/queueStore";
import { useSearchStore } from "@/stores/searchStore";
import { LyraButton } from "@/ui/LyraButton";

export function SearchRoute() {
  const query = useSearchStore((state) => state.query);
  const setQuery = useSearchStore((state) => state.setQuery);
  const [draftQuery, setDraftQuery] = useState(query);
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const { data, isFetching, isError, error } = useQuery({
    queryKey: ["search", query],
    queryFn: () => getSearchResults(query),
    enabled: query.trim().length > 0,
  });

  return (
    <div className="route-stack">
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
      {query.trim() && !data && !isError && <section className="lyra-panel empty-state-panel">Searching the backend...</section>}
      {data && (
        <SearchResultStack
          results={data}
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
    </div>
  );
}

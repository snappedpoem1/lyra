import { useQuery } from "@tanstack/react-query";
import { SearchHero } from "@/features/search/SearchHero";
import { SearchResultStack } from "@/features/search/SearchResultStack";
import { audioEngine } from "@/services/audio/audioEngine";
import { getSearchResults } from "@/services/lyraGateway/queries";
import { useSearchStore } from "@/stores/searchStore";

export function SearchRoute() {
  const query = useSearchStore((state) => state.query);
  const { data } = useQuery({
    queryKey: ["search", query],
    queryFn: () => getSearchResults(query),
  });

  return (
    <div className="route-stack">
      <SearchHero />
      {!data && <section className="lyra-panel">Search is waiting on the backend.</section>}
      {data && <SearchResultStack results={data} onPlayTrack={(track) => void audioEngine.playTrack(track)} />}
    </div>
  );
}

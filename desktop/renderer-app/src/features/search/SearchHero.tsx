import { useSearchStore } from "@/stores/searchStore";

export function SearchHero() {
  const query = useSearchStore((state) => state.query);
  const setQuery = useSearchStore((state) => state.setQuery);

  return (
    <section className="search-hero lyra-panel">
      <span className="hero-kicker">Search as revelation</span>
      <h1>Excavate the library psyche</h1>
      <input
        className="hero-input"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="haunted warmth with cathedral bass and analog grain"
      />
    </section>
  );
}

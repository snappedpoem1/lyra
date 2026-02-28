import { useSearchStore } from "@/stores/searchStore";

export function SearchHero() {
  const query = useSearchStore((state) => state.query);
  const setQuery = useSearchStore((state) => state.setQuery);

  return (
    <section className="search-hero lyra-panel">
      <span className="hero-kicker">Library Search</span>
      <h1>Search by sound, mood, artist, or thread language</h1>
      <input
        className="hero-input"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="dark ambient with deep bass and analog warmth"
      />
    </section>
  );
}

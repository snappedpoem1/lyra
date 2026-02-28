import { LyraButton } from "@/ui/LyraButton";

export function SearchHero({
  query,
  onQueryChange,
  onSubmit,
  loading,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  return (
    <section className="search-hero lyra-panel">
      <span className="hero-kicker">Library Search</span>
      <h1>Search by sound, mood, artist, or thread language</h1>
      <div className="search-form-row">
        <input
          className="hero-input"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onSubmit();
            }
          }}
          placeholder="dark ambient with deep bass and analog warmth"
        />
        <LyraButton onClick={onSubmit} disabled={!query.trim() || loading}>
          {loading ? "Searching" : "Search"}
        </LyraButton>
      </div>
      <p className="rewrite-copy">Enter a phrase and submit it. Lyra will use live backend search and show exactly what came back.</p>
    </section>
  );
}

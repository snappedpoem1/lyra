import { Icon } from "@/ui/Icon";

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
      <div className="search-hero-inner">
        <div className="search-hero-text">
          <span className="hero-kicker">Semantic Search</span>
          <h1 className="search-hero-headline">What do you want to feel?</h1>
        </div>
        <div className="search-form-row">
          <div className="search-input-wrap">
            <Icon name="search" className="search-input-icon" />
            <input
              className="hero-input search-input-padded"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  onSubmit();
                }
              }}
              placeholder="dark ambient with deep bass and analog warmth…"
              autoFocus
            />
          </div>
          <button
            className="search-go-btn"
            onClick={onSubmit}
            disabled={!query.trim() || loading}
            aria-label="Search"
          >
            {loading ? (
              <span className="search-btn-label">Searching…</span>
            ) : (
              <>
                <Icon name="spark" className="search-btn-icon" />
                <span className="search-btn-label">Find</span>
              </>
            )}
          </button>
        </div>
      </div>
    </section>
  );
}

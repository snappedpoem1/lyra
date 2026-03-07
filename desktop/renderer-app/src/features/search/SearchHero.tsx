import { Button, TextInput } from "@mantine/core";
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
          <TextInput
            className="search-input-wrap"
            value={query}
            onChange={(event) => onQueryChange(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSubmit();
              }
            }}
            leftSection={<Icon name="search" className="search-input-icon" />}
            classNames={{ input: "hero-input search-input-padded" }}
            placeholder="dark ambient with deep bass and analog warmth…"
            autoFocus
          />
          <Button
            className="search-go-btn"
            onClick={onSubmit}
            disabled={!query.trim() || loading}
            aria-label="Search"
            loading={loading}
            leftSection={loading ? undefined : <Icon name="spark" className="search-btn-icon" />}
          >
            <span className="search-btn-label">{loading ? "Searching..." : "Find"}</span>
          </Button>
        </div>
      </div>
    </section>
  );
}

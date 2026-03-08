import { useNavigate } from "@tanstack/react-router";
import { useSearchStore } from "@/stores/searchStore";
import { useUiStore } from "@/stores/uiStore";
import { LyraPanel } from "@/ui/LyraPanel";

export function SemanticSearchOverlay() {
  const open = useUiStore((state) => state.searchOverlayOpen);
  const toggle = useUiStore((state) => state.toggleSearchOverlay);
  const query = useSearchStore((state) => state.query);
  const setQuery = useSearchStore((state) => state.setQuery);
  const navigate = useNavigate();

  if (!open) {
    return null;
  }

  return (
    <div className="overlay-shell" onClick={() => toggle(false)}>
      <LyraPanel className="search-overlay" onClick={(event) => event.stopPropagation()}>
        <div className="overlay-label">Semantic search</div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            navigate({ to: "/search" });
            toggle(false);
          }}
        >
          <input
            autoFocus
            className="hero-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Describe the sound you're looking for..."
          />
        </form>
      </LyraPanel>
    </div>
  );
}

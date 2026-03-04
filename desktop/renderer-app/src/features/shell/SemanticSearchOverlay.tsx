import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useSearchStore } from "@/stores/searchStore";
import { useUiStore } from "@/stores/uiStore";
import { LyraPanel } from "@/ui/LyraPanel";

export function SemanticSearchOverlay() {
  const open = useUiStore((state) => state.searchOverlayOpen);
  const toggle = useUiStore((state) => state.toggleSearchOverlay);
  const setQuery = useSearchStore((state) => state.setQuery);
  const storeQuery = useSearchStore((state) => state.query);
  const [draft, setDraft] = useState("");
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
            const trimmed = draft.trim() || storeQuery.trim();
            if (trimmed) {
              setQuery(trimmed);
            }
            navigate({ to: "/search" });
            toggle(false);
            setDraft("");
          }}
        >
          <input
            autoFocus
            className="hero-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Describe the sound you're looking for..."
          />
        </form>
      </LyraPanel>
    </div>
  );
}

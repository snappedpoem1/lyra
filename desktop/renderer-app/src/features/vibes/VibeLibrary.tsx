import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { getPlaylists } from "@/services/lyraGateway/queries";
import { LyraButton } from "@/ui/LyraButton";

export function VibeLibrary() {
  const navigate = useNavigate();
  const { data: vibes = [], error, isFetching, refetch } = useQuery({
    queryKey: ["playlists"],
    queryFn: getPlaylists,
  });

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Vibe Library</span>
        <h1>Saved vibe worlds you can return to on demand</h1>
        <p>Name the ones worth keeping, then reload them as living playlists.</p>
      </section>

      <section className="lyra-panel workspace-column">
        <div className="section-heading">
          <h2>Saved Vibes</h2>
          <div className="hero-actions">
            <span>{vibes.length} saved</span>
            <LyraButton onClick={() => void refetch()} disabled={isFetching}>
              {isFetching ? "Refreshing" : "Refresh"}
            </LyraButton>
          </div>
        </div>

        {error && (
          <section className="empty-state-panel">
            <h2>Vibe library unavailable</h2>
            <p>{error instanceof Error ? error.message : "The backend returned an error."}</p>
          </section>
        )}

        {!error && !vibes.length && (
          <section className="empty-state-panel">
            <div className="empty-state-glyph" />
            <h2>No saved vibes yet</h2>
            <p>Generate a vibe from search, save it, and it will appear here.</p>
          </section>
        )}

        <div className="compact-list playlist-list">
          {vibes.map((vibe) => (
            <button
              key={vibe.id}
              className="thread-row"
              onClick={() => navigate({ to: "/playlists/$playlistId", params: { playlistId: vibe.id } })}
            >
              <div>
                <strong>{vibe.title}</strong>
                <p>{vibe.subtitle}</p>
                <p>{vibe.lastTouchedLabel ?? "Saved vibe"}</p>
              </div>
              <span>{vibe.trackCount}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

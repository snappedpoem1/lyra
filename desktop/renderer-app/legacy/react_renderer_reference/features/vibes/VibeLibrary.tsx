import { Badge, Group, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { getPlaylists } from "@/services/lyraGateway/queries";
import { LyraButton } from "@/ui/LyraButton";
import { LyraPanel } from "@/ui/LyraPanel";

export function VibeLibrary() {
  const navigate = useNavigate();
  const { data: vibes = [], error, isFetching, refetch } = useQuery({
    queryKey: ["playlists"],
    queryFn: getPlaylists,
  });
  const featuredVibe = vibes[0];

  return (
    <div className="route-stack">
      <LyraPanel className="vibe-archive-hero">
        <div className="vibe-archive-copy">
          <span className="hero-kicker">Vibe Library</span>
          <Title order={1}>Saved atmospheres you can drop back into without rebuilding the mood.</Title>
          <Text className="vibe-archive-summary">
            Treat each saved vibe like a reusable room tone: a stable emotional world
            with enough identity to relaunch as a live sequence.
          </Text>
        </div>
        <Group gap="xs" className="vibe-archive-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {vibes.length} saved
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            Playlist-backed
          </Badge>
          <LyraButton onClick={() => void refetch()} disabled={isFetching}>
            {isFetching ? "Refreshing" : "Refresh"}
          </LyraButton>
        </Group>
      </LyraPanel>

      {error && (
        <LyraPanel className="empty-state-panel">
          <h2>Vibe library unavailable</h2>
          <p>{error instanceof Error ? error.message : "The backend returned an error."}</p>
        </LyraPanel>
      )}

      {!error && !vibes.length && (
        <LyraPanel className="empty-state-panel">
          <div className="empty-state-glyph" aria-hidden="true" />
          <h2>No saved vibes yet</h2>
          <p>Generate a vibe from search, save it, and it will appear here.</p>
        </LyraPanel>
      )}

      {!error && vibes.length > 0 && (
        <section className="vibe-archive-grid">
          <LyraPanel className="vibe-archive-feature">
            <div className="home-card-header">
              <div>
                <span className="insight-kicker">Featured atmosphere</span>
                <h2>{featuredVibe?.title ?? "Saved vibe"}</h2>
              </div>
              <span className="home-card-meta">{featuredVibe?.trackCount ?? 0} tracks</span>
            </div>
            <p className="home-card-body-copy">
              {featuredVibe?.subtitle ?? "Saved mood archive ready for immediate relaunch."}
            </p>
            <div className="vibe-archive-feature-meta">
              <div className="vibe-archive-signal-card">
                <span className="insight-kicker">Last touched</span>
                <strong>{featuredVibe?.lastTouchedLabel ?? "Saved vibe"}</strong>
                <p>Drop back into the most recently active atmosphere.</p>
              </div>
              <div className="vibe-archive-signal-card">
                <span className="insight-kicker">Shape</span>
                <strong>{featuredVibe?.trackCount ?? 0} cues</strong>
                <p>Enough material to relaunch the thread as a working playlist.</p>
              </div>
            </div>
            <div className="home-card-actions">
              <LyraButton
                className="lyra-button--accent"
                onClick={() =>
                  featuredVibe &&
                  navigate({ to: "/playlists/$playlistId", params: { playlistId: featuredVibe.id } })
                }
                disabled={!featuredVibe}
              >
                Open featured vibe
              </LyraButton>
            </div>
          </LyraPanel>

          <LyraPanel className="vibe-archive-list-panel">
            <div className="section-heading">
              <h2>Saved Vibes</h2>
              <span>{vibes.length} entries</span>
            </div>
            <div className="vibe-archive-list">
              {vibes.map((vibe) => (
                <button
                  key={vibe.id}
                  type="button"
                  className="vibe-archive-row"
                  onClick={() => navigate({ to: "/playlists/$playlistId", params: { playlistId: vibe.id } })}
                >
                  <div>
                    <span className="insight-kicker">Saved vibe</span>
                    <strong>{vibe.title}</strong>
                    <p>{vibe.subtitle}</p>
                  </div>
                  <div className="vibe-archive-row-meta">
                    <span>{vibe.lastTouchedLabel ?? "Saved vibe"}</span>
                    <strong>{vibe.trackCount}</strong>
                  </div>
                </button>
              ))}
            </div>
          </LyraPanel>
        </section>
      )}
    </div>
  );
}

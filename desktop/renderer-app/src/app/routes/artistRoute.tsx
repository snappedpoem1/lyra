import { Avatar, Badge, Button, Group, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { audioEngine } from "@/services/audio/audioEngine";
import { getLibraryArtistDetail, getArtistShrine } from "@/services/lyraGateway/queries";
import { useQueueStore } from "@/stores/queueStore";
import { usePlayerStore } from "@/stores/playerStore";
import { Icon } from "@/ui/Icon";
import type { TrackListItem } from "@/types/domain";

/** Hue derived from artist name â€” consistent per-artist color */
function artistHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
  return h;
}

function ArtistAvatar({ name, thumbnail, size = 90 }: { name: string; thumbnail?: string; size?: number }) {
  const hue = artistHue(name);
  const letter = name.trim()[0]?.toUpperCase() ?? "?";
  return (
    <Avatar
      src={thumbnail}
      alt={name}
      radius="xl"
      size={size}
      className="artist-avatar"
      style={{
        background: `linear-gradient(145deg, hsl(${hue},38%,20%), hsl(${(hue + 50) % 360},46%,32%))`,
        color: `hsl(${hue},55%,82%)`,
        border: `2px solid hsl(${hue},30%,35%)`,
        boxShadow: `0 0 32px hsl(${hue},38%,20%)`,
      }}
    >
      {letter}
    </Avatar>
  );
}

function TrackRow({
  track,
  index,
  onPlay,
}: {
  track: TrackListItem;
  index: number;
  onPlay: (track: TrackListItem) => void;
}) {
  return (
    <div
      className="track-row artist-track-row"
      onClick={() => onPlay(track)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onPlay(track)}
    >
      <span className="track-row-index">{index + 1}</span>
      <div className="track-row-main">
        <span className="track-row-title">{track.title}</span>
        <span className="track-row-album">{track.album ?? ""}</span>
      </div>
      <span className="track-row-action">
        <Icon name="play" className="inline-icon" />
      </span>
    </div>
  );
}


export function ArtistRoute() {
  const { name } = useParams({ from: "/artist/$name" });
  const navigate = useNavigate();
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const setCurrentTrack = useQueueStore((state) => state.setCurrentTrack);
  const setTrack = usePlayerStore((state) => state.setTrack);

  // Library detail: track list + album list + years
  const { data: detail, isLoading } = useQuery({
    queryKey: ["artist-detail", name],
    queryFn: () => getLibraryArtistDetail(name),
    enabled: Boolean(name),
  });

  // Shrine: bio, genres, origin, related artists, credits (runs in parallel)
  const { data: shrine } = useQuery({
    queryKey: ["artist-shrine", name],
    queryFn: () => getArtistShrine(name),
    enabled: Boolean(name),
    retry: false,
    staleTime: 10 * 60 * 1000,
  });

  const tracks: TrackListItem[] = detail?.tracks ?? [];
  const albums = detail?.albums ?? [];
  const years = detail?.years ?? [];

  const playAll = async () => {
    if (!tracks.length) return;
    replaceQueue({
      queueId: `artist-${name}`,
      origin: name,
      reorderable: true,
      currentIndex: 0,
      items: tracks,
    });
    setCurrentTrack(tracks[0].trackId);
    setTrack(tracks[0], name, undefined);
    await audioEngine.playTrack(tracks[0]);
  };

  const playTrack = async (track: TrackListItem) => {
    const idx = tracks.findIndex((t) => t.trackId === track.trackId);
    replaceQueue({
      queueId: `artist-${name}`,
      origin: name,
      reorderable: true,
      currentIndex: Math.max(0, idx),
      items: tracks,
    });
    setCurrentTrack(track.trackId);
    setTrack(track, name, undefined);
    await audioEngine.playTrack(track);
  };

  if (isLoading) {
    return (
      <div className="route-stack">
        <Paper className="lyra-panel empty-state-panel" p="xl">
          <Text>Loading artist...</Text>
        </Paper>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="route-stack">
        <Paper className="lyra-panel empty-state-panel" p="xl">
          <Stack gap="sm">
            <Title order={2}>Artist not found</Title>
            <Text>"{name}" has no tracks in the library.</Text>
            <Group>
              <Button color="lyra" variant="light" onClick={() => void navigate({ to: "/library" })}>
                Back to Library
              </Button>
            </Group>
          </Stack>
        </Paper>
      </div>
    );
  }

  const yearRange = years.length > 1
    ? `${years[0]} â€“ ${years[years.length - 1]}`
    : years[0] ?? "";
  const hue = artistHue(name);

  // Credit groups to surface (exclude generic "other")
  const notableCredits = (shrine?.credits ?? []).filter(
    (c) => ["producer", "featured", "composer", "remixer", "lyricist", "mixer"].includes(c.role),
  );
  const creditsByRole = notableCredits.reduce<Record<string, typeof notableCredits>>(
    (acc, c) => { (acc[c.role] ??= []).push(c); return acc; },
    {},
  );

  return (
    <div className="artist-page route-stack">
      {/* Hero */}
      <section className="lyra-panel artist-hero">
        <ArtistAvatar name={name} thumbnail={shrine?.wikiThumbnail || undefined} size={90} />
        <div className="artist-hero-meta">
          <span className="artist-hero-kicker">Artist</span>
          <h1 className="artist-name">{name}</h1>

          {/* Origin / scene tagline */}
          {(shrine?.origin || shrine?.era || shrine?.scene) && (
            <p className="artist-tagline">
              {[shrine.origin, shrine.era, shrine.scene].filter(Boolean).join(" · ")}
            </p>
          )}

          {/* Genres */}
          {(shrine?.genres ?? []).length > 0 && (
            <Group gap="xs" className="artist-genre-chips">
              {(shrine?.genres ?? []).slice(0, 8).map((g) => (
                <Badge key={g} className="artist-genre-chip" variant="light" color="lyra">
                  {g}
                </Badge>
              ))}
            </Group>
          )}

          {shrine?.bio && (
            <p className="artist-bio">{shrine.bio}</p>
          )}

          <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }} spacing="md" className="artist-stats-row">
            <div className="artist-stat">
              <span className="artist-stat-value">{detail.trackCount}</span>
              <span className="artist-stat-label">Tracks</span>
            </div>
            <div className="artist-stat">
              <span className="artist-stat-value">{detail.albumCount}</span>
              <span className="artist-stat-label">Albums</span>
            </div>
            {yearRange && (
              <div className="artist-stat">
                <span className="artist-stat-value">{yearRange}</span>
                <span className="artist-stat-label">Years</span>
              </div>
            )}
            {shrine?.formationYear && (
              <div className="artist-stat">
                <span className="artist-stat-value">{shrine.formationYear}</span>
                <span className="artist-stat-label">Formed</span>
              </div>
            )}
            {shrine?.lastfmListeners != null && shrine.lastfmListeners > 0 && (
              <div className="artist-stat">
                <span className="artist-stat-value">
                  {shrine.lastfmListeners >= 1_000_000
                    ? `${(shrine.lastfmListeners / 1_000_000).toFixed(1)}M`
                    : shrine.lastfmListeners >= 1_000
                    ? `${(shrine.lastfmListeners / 1_000).toFixed(0)}K`
                    : String(shrine.lastfmListeners)}
                </span>
                <span className="artist-stat-label">Listeners</span>
              </div>
            )}
          </SimpleGrid>

          <Group gap="md" className="artist-actions">
            <Button color="lyra" variant="light" onClick={() => void playAll()} disabled={!tracks.length}>
              <Icon name="play" className="inline-icon" /> Play All
            </Button>
            <Button color="lyra" variant="default" onClick={() => void navigate({ to: "/library" })}>
              Library
            </Button>
            {shrine?.wikiUrl && (
              <Button
                component="a"
                href={shrine.wikiUrl}
                target="_blank"
                rel="noopener noreferrer"
                variant="subtle"
                color="gray"
                className="artist-wiki-link"
              >
                Wikipedia ↗
              </Button>
            )}
          </Group>
        </div>
      </section>

      {/* Related Artists */}
      {(shrine?.relatedArtists ?? []).length > 0 && (
        <section className="lyra-panel artist-section">
          <h3 className="artist-section-header">Related Artists</h3>
          <Group gap="sm" className="artist-related-chips">
            {(shrine?.relatedArtists ?? []).slice(0, 12).map((rel) => (
              <Button
                key={rel.target}
                className="artist-related-chip"
                variant="default"
                color="gray"
                onClick={() => void navigate({ to: "/artist/$name", params: { name: rel.target } })}
                title={rel.type}
              >
                {rel.target}
              </Button>
            ))}
          </Group>
        </section>
      )}

      {/* Notable Credits */}
      {Object.keys(creditsByRole).length > 0 && (
        <section className="lyra-panel artist-section">
          <h3 className="artist-section-header">Credits</h3>
          <div className="artist-credits-list">
            {Object.entries(creditsByRole).map(([role, people]) => (
              <div key={role} className="artist-credit-row">
                <Badge variant="light" color="lyra" className="artist-credit-role">{role}</Badge>
                <Text className="artist-credit-names">{people.map((p) => p.name).join(", ")}</Text>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Albums */}
      {albums.length > 0 && (
        <section className="lyra-panel artist-section">
          <h3 className="artist-section-header">Discography</h3>
          <div className="artist-albums-grid">
            {albums.map((album) => (
              <div key={album.name} className="artist-album-card" title={`${album.count} tracks`}>
                <div
                  className="artist-album-art"
                  style={{
                    background: `linear-gradient(145deg, hsl(${artistHue(album.name)},28%,18%), hsl(${(artistHue(album.name) + 60) % 360},36%,26%))`,
                    color: `hsl(${artistHue(album.name)},60%,75%)`,
                  }}
                >
                  {album.name[0]?.toUpperCase()}
                </div>
                <div className="artist-album-name">{album.name}</div>
                <div className="artist-album-count">{album.count} track{album.count !== 1 ? "s" : ""}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Track list */}
      {tracks.length > 0 && (
        <section className="lyra-panel artist-section">
          <h3 className="artist-section-header">All Tracks</h3>
          <div className="track-rows">
            {tracks.map((track, i) => (
              <TrackRow key={track.trackId} track={track} index={i} onPlay={playTrack} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

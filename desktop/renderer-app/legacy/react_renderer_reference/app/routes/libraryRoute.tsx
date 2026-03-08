import { Badge, Group, Text, Title } from "@mantine/core";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LibraryOmensPanel } from "@/features/library/LibraryOmensPanel";
import { audioEngine } from "@/services/audio/audioEngine";
import { getLibraryAlbumDetail, getLibraryAlbums, getLibraryArtistDetail, getLibraryArtists, getLibraryTracks } from "@/services/lyraGateway/queries";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { LyraPanel } from "@/ui/LyraPanel";

export function LibraryRoute() {
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [sortKey, setSortKey] = useState<"title" | "artist" | "album">("artist");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [selectedArtist, setSelectedArtist] = useState<string | null>(null);
  const [selectedAlbum, setSelectedAlbum] = useState<string | null>(null);
  const pageSize = 80;
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const appendTracks = useQueueStore((state) => state.appendTracks);
  const setCurrentTrack = useQueueStore((state) => state.setCurrentTrack);
  const setTrack = usePlayerStore((state) => state.setTrack);
  const { data } = useQuery({
    queryKey: ["library-tracks", pageSize, offset, query, selectedArtist, selectedAlbum],
    queryFn: () => getLibraryTracks(pageSize, offset, query, selectedArtist, selectedAlbum),
  });
  const { data: artistOptions = [] } = useQuery({
    queryKey: ["library-artists", query],
    queryFn: () => getLibraryArtists(query),
  });
  const { data: albumOptions = [] } = useQuery({
    queryKey: ["library-albums", query, selectedArtist],
    queryFn: () => getLibraryAlbums(query, selectedArtist),
  });
  const { data: artistDetail } = useQuery({
    queryKey: ["library-artist-detail", selectedArtist],
    queryFn: () => getLibraryArtistDetail(selectedArtist ?? ""),
    enabled: Boolean(selectedArtist),
  });
  const { data: albumDetail } = useQuery({
    queryKey: ["library-album-detail", selectedArtist, selectedAlbum],
    queryFn: () => getLibraryAlbumDetail(selectedAlbum ?? "", selectedArtist),
    enabled: Boolean(selectedAlbum),
  });

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setOffset(0);
      setQuery(draftQuery.trim());
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [draftQuery]);

  useEffect(() => {
    setOffset(0);
  }, [selectedArtist, selectedAlbum]);

  const tracks = [...(data?.tracks ?? [])].sort((a, b) => {
    const av = String((sortKey === "title" ? a.title : sortKey === "album" ? a.album ?? "" : a.artist) ?? "").toLowerCase();
    const bv = String((sortKey === "title" ? b.title : sortKey === "album" ? b.album ?? "" : b.artist) ?? "").toLowerCase();
    const order = av.localeCompare(bv);
    return sortDir === "asc" ? order : -order;
  });
  const filteredTracks = tracks;
  const total = data?.total ?? 0;
  const hasPrevPage = offset > 0;
  const hasNextPage = offset + pageSize < total;
  const activeSliceTitle = albumDetail?.album ?? artistDetail?.artist ?? "Whole library";
  const activeSliceCopy = albumDetail
    ? `${albumDetail.artist} / ${albumDetail.trackCount} tracks`
    : artistDetail
      ? `${artistDetail.trackCount} tracks across ${artistDetail.albumCount} albums`
      : `${filteredTracks.length} tracks on the current page`;
  const activeSliceMeta = selectedAlbum
    ? albumDetail?.years.join(", ") || "Album slice"
    : selectedArtist
      ? artistDetail?.years.join(", ") || "Artist slice"
      : query
        ? `Filtered by “${query}”`
        : "Ambient browse mode";

  const playTrack = async (track: typeof tracks[number]) => {
    const currentIndex = Math.max(0, filteredTracks.findIndex((item) => item.trackId === track.trackId));
    replaceQueue({
      queueId: `library-${track.trackId}`,
      origin: "library",
      reorderable: true,
      currentIndex,
      items: filteredTracks,
    });
    setCurrentTrack(track.trackId);
    setTrack(track, "Library", track.reason);
    await audioEngine.playTrack(track);
  };

  const queueTrack = (track: typeof tracks[number]) => {
    const existingItems = useQueueStore.getState().queue.items;
    if (!existingItems.length) {
      replaceQueue({
        queueId: `library-page-${offset}`,
        origin: "library",
        reorderable: true,
        currentIndex: Math.max(0, filteredTracks.findIndex((item) => item.trackId === track.trackId)),
        items: filteredTracks,
      });
      setCurrentTrack(track.trackId);
      return;
    }
    appendTracks([track]);
    setCurrentTrack(track.trackId);
  };

  const focusedTracks = albumDetail?.tracks ?? artistDetail?.tracks ?? filteredTracks;
  const playFocusedSlice = async () => {
    if (!focusedTracks.length) {
      return;
    }
    replaceQueue({
      queueId: selectedAlbum ? `album-${selectedAlbum}` : selectedArtist ? `artist-${selectedArtist}` : `library-page-${offset}`,
      origin: selectedAlbum ?? selectedArtist ?? "library",
      reorderable: true,
      currentIndex: 0,
      items: focusedTracks,
    });
    setCurrentTrack(focusedTracks[0].trackId);
    setTrack(focusedTracks[0], selectedAlbum ?? selectedArtist ?? "Library", focusedTracks[0].reason);
    await audioEngine.playTrack(focusedTracks[0]);
  };

  const queueFocusedSlice = () => {
    if (!focusedTracks.length) {
      return;
    }
    replaceQueue({
      queueId: selectedAlbum ? `album-${selectedAlbum}` : selectedArtist ? `artist-${selectedArtist}` : `library-page-${offset}`,
      origin: selectedAlbum ?? selectedArtist ?? "library",
      reorderable: true,
      currentIndex: 0,
      items: focusedTracks,
    });
    setCurrentTrack(focusedTracks[0].trackId);
  };

  useEffect(() => {
    if (selectedArtist && !artistOptions.some((item) => item.name === selectedArtist)) {
      setSelectedArtist(null);
    }
  }, [artistOptions, selectedArtist]);

  useEffect(() => {
    if (selectedAlbum && !albumOptions.some((item) => item.name === selectedAlbum)) {
      setSelectedAlbum(null);
    }
  }, [albumOptions, selectedAlbum]);

  return (
    <div className="route-stack">
      <LyraPanel className="library-archive-hero">
        <div className="library-archive-copy">
          <span className="hero-kicker">Library</span>
          <Title order={1}>Your owned catalog as a playable archive, not a flat file browser.</Title>
          <Text className="library-archive-summary">
            Move between whole-library pulls, artist slices, and album focus without
            leaving the active queue workflow. The archive stays close to playback.
          </Text>
        </div>
        <Group gap="xs" className="library-archive-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {total} indexed tracks
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {artistOptions.length} artists
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {albumOptions.length} albums
          </Badge>
          {query ? (
            <Badge className="home-stat-badge" size="lg" variant="light" color="lyra">
              query: {query}
            </Badge>
          ) : null}
        </Group>
      </LyraPanel>

      <section className="library-archive-grid">
        <LyraPanel className="library-archive-focus">
          <div className="home-card-header">
            <div>
              <span className="insight-kicker">Current slice</span>
              <h2>{activeSliceTitle}</h2>
            </div>
            <span className="home-card-meta">{focusedTracks.length} ready</span>
          </div>
          <p className="home-card-body-copy">{activeSliceCopy}</p>
          <div className="library-archive-signal-strip">
            <div className="library-archive-signal-card">
              <span className="insight-kicker">Browse state</span>
              <strong>{selectedAlbum ? "Album focus" : selectedArtist ? "Artist focus" : "Whole library"}</strong>
              <p>{activeSliceMeta}</p>
            </div>
            <div className="library-archive-signal-card">
              <span className="insight-kicker">Sort</span>
              <strong>{sortKey} / {sortDir}</strong>
              <p>Direct playback and queue actions stay attached to the current view.</p>
            </div>
          </div>
        </LyraPanel>
      </section>

      <LibraryOmensPanel
        tracks={filteredTracks}
        total={total}
        query={draftQuery}
        selectedArtist={selectedArtist}
        selectedAlbum={selectedAlbum}
        artistOptions={artistOptions}
        albumOptions={albumOptions}
        onSelectArtist={(value) => {
          setSelectedArtist(value);
          setSelectedAlbum(null);
        }}
        onSelectAlbum={setSelectedAlbum}
        onClearFilters={() => {
          setSelectedArtist(null);
          setSelectedAlbum(null);
        }}
        artistDetail={artistDetail}
        albumDetail={albumDetail}
        onPlayFocusedSlice={() => void playFocusedSlice()}
        onQueueFocusedSlice={queueFocusedSlice}
        onQueryChange={setDraftQuery}
        onPlayTrack={(track) => void playTrack(track)}
        onQueueTrack={queueTrack}
        sortKey={sortKey}
        sortDir={sortDir}
        onSortChange={toggleSort}
        onPrevPage={() => setOffset((current) => Math.max(0, current - pageSize))}
        onNextPage={() => setOffset((current) => current + pageSize)}
        hasPrevPage={hasPrevPage}
        hasNextPage={hasNextPage}
      />
    </div>
  );

  function toggleSort(nextKey: "title" | "artist" | "album") {
    if (sortKey === nextKey) {
      setSortDir((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(nextKey);
    setSortDir("asc");
  }
}

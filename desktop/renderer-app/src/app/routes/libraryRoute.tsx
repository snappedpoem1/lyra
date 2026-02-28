import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LibraryOmensPanel } from "@/features/library/LibraryOmensPanel";
import { audioEngine } from "@/services/audio/audioEngine";
import { getLibraryAlbums, getLibraryArtists, getLibraryTracks } from "@/services/lyraGateway/queries";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";

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
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Library</span>
        <h1>{total} tracks ready for listening</h1>
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

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LibraryOmensPanel } from "@/features/library/LibraryOmensPanel";
import { audioEngine } from "@/services/audio/audioEngine";
import { getLibraryTracks } from "@/services/lyraGateway/queries";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";

export function LibraryRoute() {
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [sortKey, setSortKey] = useState<"title" | "artist" | "album">("artist");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const pageSize = 20;
  const replaceQueue = useQueueStore((state) => state.replaceQueue);
  const setCurrentTrack = useQueueStore((state) => state.setCurrentTrack);
  const setTrack = usePlayerStore((state) => state.setTrack);
  const { data } = useQuery({
    queryKey: ["library-tracks", pageSize, offset, query],
    queryFn: () => getLibraryTracks(pageSize, offset, query),
  });

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setOffset(0);
      setQuery(draftQuery.trim());
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [draftQuery]);

  const tracks = [...(data?.tracks ?? [])].sort((a, b) => {
    const av = String((sortKey === "title" ? a.title : sortKey === "album" ? a.album ?? "" : a.artist) ?? "").toLowerCase();
    const bv = String((sortKey === "title" ? b.title : sortKey === "album" ? b.album ?? "" : b.artist) ?? "").toLowerCase();
    const order = av.localeCompare(bv);
    return sortDir === "asc" ? order : -order;
  });
  const total = data?.total ?? 0;
  const hasPrevPage = offset > 0;
  const hasNextPage = offset + pageSize < total;

  const playTrack = async (track: typeof tracks[number]) => {
    replaceQueue({
      queueId: `library-${track.trackId}`,
      origin: "library",
      reorderable: true,
      currentIndex: 0,
      items: [track],
    });
    setCurrentTrack(track.trackId);
    setTrack(track, "Library", track.reason);
    await audioEngine.playTrack(track);
  };

  const queueTrack = (track: typeof tracks[number]) => {
    replaceQueue({
      queueId: `library-page-${offset}`,
      origin: "library",
      reorderable: true,
      currentIndex: Math.max(0, tracks.findIndex((item) => item.trackId === track.trackId)),
      items: tracks,
    });
    setCurrentTrack(track.trackId);
  };

  const toggleSort = (nextKey: "title" | "artist" | "album") => {
    if (sortKey === nextKey) {
      setSortDir((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(nextKey);
    setSortDir("asc");
  };

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Library</span>
        <h1>{total} tracks ready for listening</h1>
      </section>
      <LibraryOmensPanel
        tracks={tracks}
        total={total}
        query={draftQuery}
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
}

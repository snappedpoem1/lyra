import { describe, it, expect } from "vitest";
import { mapPlaylistDetail, mapPlaylists } from "./mappers";

describe("mapPlaylistDetail", () => {
  it("handles saved playlist API shape {playlist, tracks}", () => {
    const payload = {
      playlist: { id: "pl-1", name: "Night Drive", description: "4am headspace", track_count: 3, created_at: 1000000, updated_at: 1000001 },
      tracks: [
        { id: "t1", title: "Track A", artist: "Artist A", album: "", duration: 200, path: "/a.flac", scored: true, track_number: 1 },
      ],
    };
    const result = mapPlaylistDetail(payload);
    expect(result.summary.kind).toBe("saved");
    expect(result.summary.id).toBe("pl-1");
    expect(result.summary.title).toBe("Night Drive");
    expect(result.summary.trackCount).toBe(3);
    expect(result.tracks).toHaveLength(1);
    expect(result.arc).toEqual([]);
    expect(result.storyBeats).toEqual([]);
  });

  it("handles vibe/legacy detail shape with top-level title", () => {
    const payload = {
      id: "vibe-1",
      title: "After Midnight Ritual",
      subtitle: "Late night drive",
      narrative: "Built for the quiet hours",
      trackCount: 5,
      freshnessLabel: "Fresh",
      tracks: [],
      arc: [],
      storyBeats: ["Opening with tension", "Drift into warmth"],
      relatedPlaylists: [],
    };
    const result = mapPlaylistDetail(payload);
    expect(result.summary.kind).toBe("vibe");
    expect(result.summary.title).toBe("After Midnight Ritual");
    expect(result.summary.trackCount).toBe(5);
    expect(result.storyBeats).toEqual(["Opening with tension", "Drift into warmth"]);
  });
});

describe("mapPlaylists", () => {
  it("maps vibes array to PlaylistSummary[]", () => {
    const result = mapPlaylists({ vibes: [{ name: "Test Vibe", query: "dark techno", track_count: 10, created_at: 1000 }] });
    expect(result).toHaveLength(1);
    expect(result[0].title).toBe("Test Vibe");
    expect(result[0].trackCount).toBe(10);
    expect(result[0].kind).toBe("vibe");
  });

  it("returns empty array for empty vibes", () => {
    expect(mapPlaylists({ vibes: [] })).toEqual([]);
  });
});

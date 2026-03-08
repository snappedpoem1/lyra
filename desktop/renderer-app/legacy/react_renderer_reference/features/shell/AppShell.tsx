import type { PropsWithChildren } from "react";
import { useEffect, useRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import { CommandPalette } from "@/features/shell/CommandPalette";
import { BottomTransportDock } from "@/features/shell/BottomTransportDock";
import { LeftRail } from "@/features/shell/LeftRail";
import { RightRail } from "@/features/shell/RightRail";
import { SemanticSearchOverlay } from "@/features/shell/SemanticSearchOverlay";
import { TopAtmosphereBar } from "@/features/shell/TopAtmosphereBar";
import { LyraCompanion } from "@/features/companion/LyraCompanion";
import { TrackDossierDrawer } from "@/features/tracks/TrackDossierDrawer";
import { DeveloperHud } from "@/features/dev/DeveloperHud";
import { audioEngine } from "@/services/audio/audioEngine";
import { registerNavigate } from "@/services/agentActionRouter";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { useSettingsStore } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";

export function AppShell({ children }: PropsWithChildren) {
  const toggleCommandPalette = useUiStore((state) => state.toggleCommandPalette);
  const toggleSearchOverlay  = useUiStore((state) => state.toggleSearchOverlay);
  const closeDossier         = useUiStore((state) => state.closeDossier);
  const commandPaletteOpen   = useUiStore((state) => state.commandPaletteOpen);
  const searchOverlayOpen    = useUiStore((state) => state.searchOverlayOpen);
  const dossierTrackId       = useUiStore((state) => state.dossierTrackId);
  const setTrack             = usePlayerStore((state) => state.setTrack);
  const setMuted             = usePlayerStore((state) => state.setMuted);
  const player               = usePlayerStore();
  const queue                = useQueueStore((state) => state.queue);
  const setCurrentIndex      = useQueueStore((state) => state.setCurrentIndex);
  const resumeSession        = useSettingsStore((state) => state.resumeSession);
  const restoredRef          = useRef(false);
  const navigate             = useNavigate();

  // ── Register navigate for agentActionRouter (singleton) ─────────────────
  useEffect(() => {
    registerNavigate((opts) => void navigate(opts));
  }, [navigate]);

  // ── Global keyboard shortcuts ───────────────────────────────────────────
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target  = event.target as HTMLElement | null;
      const inInput = target?.tagName === "INPUT"
                   || target?.tagName === "TEXTAREA"
                   || (target as HTMLElement | null)?.isContentEditable;

      // Ctrl+K — command palette (always fires)
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggleCommandPalette();
        return;
      }

      // Escape — close overlays in priority order
      if (event.key === "Escape") {
        if (commandPaletteOpen) { toggleCommandPalette(false); return; }
        if (searchOverlayOpen)  { toggleSearchOverlay(false);  return; }
        if (dossierTrackId)     { closeDossier();               return; }
      }

      // "/" — semantic search (not in input, not in palette)
      if (event.key === "/" && !inInput && !commandPaletteOpen) {
        event.preventDefault();
        toggleSearchOverlay(true);
        return;
      }

      // Transport shortcuts — skip if palette / overlay open or typing
      if (commandPaletteOpen || searchOverlayOpen || inInput) return;

      switch (event.key) {
        // Space — play / pause
        case " ": {
          event.preventDefault();
          const st = usePlayerStore.getState();
          if (st.status === "playing") {
            audioEngine.pause();
          } else {
            const cur = useQueueStore.getState().queue;
            const track = cur.items[cur.currentIndex];
            if (track) void audioEngine.playTrack(track);
          }
          break;
        }

        // ArrowLeft — seek back 5 s
        case "ArrowLeft": {
          event.preventDefault();
          audioEngine.element.currentTime = Math.max(0, audioEngine.element.currentTime - 5);
          break;
        }

        // ArrowRight — seek forward 5 s
        case "ArrowRight": {
          event.preventDefault();
          const dur = audioEngine.element.duration;
          if (dur > 0) {
            audioEngine.element.currentTime = Math.min(dur, audioEngine.element.currentTime + 5);
          }
          break;
        }

        // J — previous track
        case "j":
        case "J": {
          const q   = useQueueStore.getState().queue;
          const idx = q.currentIndex - 1;
          if (idx >= 0) {
            const t = q.items[idx];
            setCurrentIndex(idx);
            setTrack(t, q.origin, t.reason);
            void audioEngine.playTrack(t);
          }
          break;
        }

        // K — next track
        case "k":
        case "K": {
          const q   = useQueueStore.getState().queue;
          const idx = q.currentIndex + 1;
          if (idx < q.items.length) {
            const t = q.items[idx];
            setCurrentIndex(idx);
            setTrack(t, q.origin, t.reason);
            void audioEngine.playTrack(t);
          }
          break;
        }

        // M — mute toggle
        case "m":
        case "M": {
          const muted = !usePlayerStore.getState().muted;
          setMuted(muted);
          audioEngine.setMuted(muted);
          break;
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    toggleCommandPalette, toggleSearchOverlay, closeDossier,
    commandPaletteOpen, searchOverlayOpen, dossierTrackId,
    setTrack, setMuted, setCurrentIndex,
  ]);

  // ── Session restore — set track metadata without starting playback ──────
  useEffect(() => {
    if (!resumeSession) return;
    const currentTrack = queue.items[queue.currentIndex] ?? null;
    if (!currentTrack) return;
    const ps = usePlayerStore.getState();
    if (!ps.track) setTrack(currentTrack, queue.origin, currentTrack.reason);
  }, [queue, resumeSession, setTrack]);

  // ── Session restore — load audio element to last position ───────────────
  useEffect(() => {
    if (!resumeSession || restoredRef.current) return;
    const currentTrack = player.track ?? queue.items[queue.currentIndex] ?? null;
    if (!currentTrack) return;
    restoredRef.current = true;
    audioEngine.loadTrack(currentTrack, player.currentTimeSec);
  }, [player.track, player.currentTimeSec, queue, resumeSession]);

  // ── Persist exact playback position on window close ─────────────────────
  useEffect(() => {
    const onBeforeUnload = () => {
      const t = audioEngine.element.currentTime;
      const d = audioEngine.element.duration;
      if (t > 0 && d > 0) {
        usePlayerStore.getState().setTime(t, d);
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);

  return (
    <>
      <div className="app-shell">
        <LeftRail />
        <div className="app-main">
          <TopAtmosphereBar />
          <main className="route-canvas">{children}</main>
          <BottomTransportDock />
        </div>
        <RightRail />
      </div>
      <CommandPalette />
      <SemanticSearchOverlay />
      <TrackDossierDrawer />
      <LyraCompanion />
      <DeveloperHud />
    </>
  );
}

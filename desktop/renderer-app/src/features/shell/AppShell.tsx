import type { PropsWithChildren } from "react";
import { useEffect, useRef } from "react";
import { CommandPalette } from "@/features/shell/CommandPalette";
import { BottomTransportDock } from "@/features/shell/BottomTransportDock";
import { LeftRail } from "@/features/shell/LeftRail";
import { RightRail } from "@/features/shell/RightRail";
import { SemanticSearchOverlay } from "@/features/shell/SemanticSearchOverlay";
import { TopAtmosphereBar } from "@/features/shell/TopAtmosphereBar";
import { TrackDossierDrawer } from "@/features/tracks/TrackDossierDrawer";
import { DeveloperHud } from "@/features/dev/DeveloperHud";
import { audioEngine } from "@/services/audio/audioEngine";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { useSettingsStore } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";

export function AppShell({ children }: PropsWithChildren) {
  const toggleCommandPalette = useUiStore((state) => state.toggleCommandPalette);
  const toggleSearchOverlay = useUiStore((state) => state.toggleSearchOverlay);
  const setTrack = usePlayerStore((state) => state.setTrack);
  const player = usePlayerStore();
  const queueItems = useQueueStore((state) => state.queue.items);
  const queueCurrentIndex = useQueueStore((state) => state.queue.currentIndex);
  const queueOrigin = useQueueStore((state) => state.queue.origin);
  const resumeSession = useSettingsStore((state) => state.resumeSession);
  const restoredRef = useRef(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggleCommandPalette();
      }
      if (event.key === "/") {
        const target = event.target as HTMLElement | null;
        if (target?.tagName !== "INPUT" && target?.tagName !== "TEXTAREA") {
          event.preventDefault();
          toggleSearchOverlay(true);
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggleCommandPalette, toggleSearchOverlay]);

  useEffect(() => {
    if (!resumeSession) {
      return;
    }
    const currentTrack = queueItems[queueCurrentIndex] ?? null;
    if (!currentTrack) {
      return;
    }
    const player = usePlayerStore.getState();
    if (!player.track) {
      setTrack(currentTrack, queueOrigin, currentTrack.reason);
    }
  }, [queueItems, queueCurrentIndex, queueOrigin, resumeSession, setTrack]);

  useEffect(() => {
    if (!resumeSession || restoredRef.current) {
      return;
    }
    const currentTrack = player.track ?? queueItems[queueCurrentIndex] ?? null;
    if (!currentTrack) {
      return;
    }
    restoredRef.current = true;
    audioEngine.loadTrack(currentTrack, player.currentTimeSec);
  }, [player.track, player.currentTimeSec, queueItems, queueCurrentIndex, resumeSession]);

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
      <DeveloperHud />
    </>
  );
}

import type { PropsWithChildren } from "react";
import { useEffect } from "react";
import { CommandPalette } from "@/features/shell/CommandPalette";
import { BottomTransportDock } from "@/features/shell/BottomTransportDock";
import { LeftRail } from "@/features/shell/LeftRail";
import { RightRail } from "@/features/shell/RightRail";
import { SemanticSearchOverlay } from "@/features/shell/SemanticSearchOverlay";
import { TopAtmosphereBar } from "@/features/shell/TopAtmosphereBar";
import { TrackDossierDrawer } from "@/features/tracks/TrackDossierDrawer";
import { useUiStore } from "@/stores/uiStore";

export function AppShell({ children }: PropsWithChildren) {
  const toggleCommandPalette = useUiStore((state) => state.toggleCommandPalette);
  const toggleSearchOverlay = useUiStore((state) => state.toggleSearchOverlay);

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
    </>
  );
}

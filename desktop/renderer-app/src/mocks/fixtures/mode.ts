import { useSettingsStore } from "@/stores/settingsStore";

export function fixtureModeEnabled(): boolean {
  return useSettingsStore.getState().fixtureMode;
}

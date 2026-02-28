import { useConnectivityStore } from "@/stores/connectivityStore";
import { useSettingsStore } from "@/stores/settingsStore";

export function DeveloperHud() {
  const enabled = useSettingsStore((state) => state.developerHud);
  const apiBaseUrl = useSettingsStore((state) => state.apiBaseUrl);
  const connectivity = useConnectivityStore();
  const llm = (connectivity.lastHealthPayload?.llm ?? {}) as { model?: string; provider?: string };

  if (!enabled) {
    return null;
  }

  return (
    <aside className="developer-hud">
      <strong>Developer HUD</strong>
      <div>Backend: {apiBaseUrl}</div>
      <div>State: {connectivity.state}</div>
      <div>Error: {connectivity.lastError ?? "none"}</div>
      <div>Status: {connectivity.statusCode ?? "-"}</div>
      <div>LLM: {String(llm.model ?? "n/a")}</div>
      <div>Provider: {String(llm.provider ?? "n/a")}</div>
      <div className="developer-hud-calls">
        {connectivity.recentCalls.map((call) => (
          <div key={`${call.timestamp}-${call.endpoint}`}>
            {call.method} {call.ok ? "OK" : "ERR"} {call.statusCode ?? "-"} {call.endpoint}
          </div>
        ))}
      </div>
    </aside>
  );
}

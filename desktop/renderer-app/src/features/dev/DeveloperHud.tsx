import { Badge, ScrollArea, Stack, Text } from "@mantine/core";
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
    <aside className="developer-hud lyra-panel">
      <Stack gap="xs">
        <div className="developer-hud-head">
          <strong>Developer HUD</strong>
          <Badge color={connectivity.state === "LIVE" ? "lyra" : connectivity.state === "FIXTURE" ? "yellow" : "red"}>
            {connectivity.state}
          </Badge>
        </div>
        <Text size="xs">Backend: {apiBaseUrl}</Text>
        <Text size="xs">Error: {connectivity.lastError ?? "none"}</Text>
        <Text size="xs">Status: {connectivity.statusCode ?? "-"}</Text>
        <Text size="xs">LLM: {String(llm.model ?? "n/a")}</Text>
        <Text size="xs">Provider: {String(llm.provider ?? "n/a")}</Text>
        <ScrollArea.Autosize mah={180} type="auto">
          <div className="developer-hud-calls">
            {connectivity.recentCalls.map((call) => (
              <div key={`${call.timestamp}-${call.endpoint}`} className="developer-hud-call-row">
                {call.method} {call.ok ? "OK" : "ERR"} {call.statusCode ?? "-"} {call.endpoint}
              </div>
            ))}
          </div>
        </ScrollArea.Autosize>
      </Stack>
    </aside>
  );
}

import { useMemo } from "react";
import { Badge, Button, Group } from "@mantine/core";
import { IconSparkles, IconWaveSine } from "@tabler/icons-react";
import { useNavigate } from "@tanstack/react-router";
import { useConnectivityStore } from "@/stores/connectivityStore";
import { usePlayerStore } from "@/stores/playerStore";
import { useSettingsStore } from "@/stores/settingsStore";

function companionMood(status: string, connectivity: string): { label: string; line: string } {
  if (connectivity !== "LIVE") {
    return { label: "watchful", line: "Monitoring degraded signals." };
  }
  if (status === "playing") {
    return { label: "locked-in", line: "Listening thread is active." };
  }
  if (status === "paused") {
    return { label: "hovering", line: "Queue held in orbit." };
  }
  return { label: "seeking", line: "Ready for the next revelation." };
}

export function LyraCompanion() {
  const enabled = useSettingsStore((state) => state.companionEnabled);
  const style = useSettingsStore((state) => state.companionStyle);
  const connectivity = useConnectivityStore((state) => state.state);
  const track = usePlayerStore((state) => state.track);
  const status = usePlayerStore((state) => state.status);
  const navigate = useNavigate();

  const mood = useMemo(() => companionMood(status, connectivity), [connectivity, status]);

  if (!enabled) {
    return null;
  }

  return (
    <aside className={`lyra-companion ${style === "pixel" ? "is-pixel" : "is-orb"}`}>
      <div className="lyra-companion-core" aria-hidden="true">
        {style === "pixel" ? (
          <div className="lyra-companion-face">
            <span className="eye" />
            <span className="eye" />
            <span className="mouth" />
          </div>
        ) : (
          <div className="lyra-companion-orb">
            <div className="lyra-companion-orb-glow" />
            <div className="lyra-companion-orb-center" />
          </div>
        )}
      </div>
      <div className="lyra-companion-panel lyra-panel">
        <Group justify="space-between" align="center" gap={8}>
          <div className="lyra-companion-title-wrap">
            <span className="lyra-companion-kicker">Companion</span>
            <strong className="lyra-companion-title">Lyra Pulse</strong>
          </div>
          <Badge color={connectivity === "LIVE" ? "lyra" : "red"} variant="light">
            {mood.label}
          </Badge>
        </Group>
        <p className="lyra-companion-line">{mood.line}</p>
        <div className="lyra-companion-thread">
          <IconWaveSine size={14} stroke={1.7} />
          <span>{track ? `${track.artist} - ${track.title}` : "No active thread yet."}</span>
        </div>
        <Group gap={6}>
          <Button
            size="xs"
            variant="default"
            className="lyra-button"
            leftSection={<IconSparkles size={14} stroke={1.7} />}
            onClick={() => void navigate({ to: "/settings" })}
          >
            Tune Shell
          </Button>
        </Group>
      </div>
    </aside>
  );
}

import { useNavigate } from "@tanstack/react-router";
import { useUiStore } from "@/stores/uiStore";
import { LyraPanel } from "@/ui/LyraPanel";

const commands = [
  { label: "Open Sanctuary", to: "/" },
  { label: "Open Playlists", to: "/playlists" },
  { label: "Open Search", to: "/search" },
  { label: "Open Oracle", to: "/oracle" },
  { label: "Open Queue", to: "/queue" },
];

export function CommandPalette() {
  const open = useUiStore((state) => state.commandPaletteOpen);
  const toggle = useUiStore((state) => state.toggleCommandPalette);
  const navigate = useNavigate();

  if (!open) {
    return null;
  }

  return (
    <div className="overlay-shell" onClick={() => toggle(false)}>
      <LyraPanel className="command-palette" onClick={(event) => event.stopPropagation()}>
        <input autoFocus className="command-input" placeholder="Command Lyra..." />
        <div className="command-list">
          {commands.map((command) => (
            <button
              key={command.to}
              className="command-item"
              onClick={() => {
                navigate({ to: command.to });
                toggle(false);
              }}
            >
              {command.label}
            </button>
          ))}
        </div>
      </LyraPanel>
    </div>
  );
}

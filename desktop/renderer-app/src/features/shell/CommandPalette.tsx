import { useState, useCallback } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useUiStore } from "@/stores/uiStore";
import { useAgentStore } from "@/stores/agentStore";
import { queryAgent } from "@/services/lyraGateway/queries";
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

  const messages = useAgentStore((state) => state.messages);
  const loading = useAgentStore((state) => state.loading);
  const addUserMessage = useAgentStore((state) => state.addUserMessage);
  const addAgentResponse = useAgentStore((state) => state.addAgentResponse);
  const setLoading = useAgentStore((state) => state.setLoading);

  const [input, setInput] = useState("");

  const handleSubmit = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const navMatch = commands.find((c) => c.label.toLowerCase() === text.toLowerCase());
    if (navMatch) {
      navigate({ to: navMatch.to });
      toggle(false);
      setInput("");
      return;
    }

    addUserMessage(text);
    setInput("");
    setLoading(true);
    try {
      const response = await queryAgent(text);
      addAgentResponse(response);
    } catch (error) {
      addAgentResponse({
        action: "error",
        thought: error instanceof Error ? error.message : "Agent request failed.",
        intent: {},
        next: "",
        response: "Lyra could not reach the agent backend.",
      });
    }
  }, [input, loading, navigate, toggle, addUserMessage, addAgentResponse, setLoading]);

  if (!open) {
    return null;
  }

  return (
    <div className="overlay-shell" onClick={() => toggle(false)}>
      <LyraPanel className="command-palette" onClick={(event) => event.stopPropagation()}>
        <input
          autoFocus
          className="command-input"
          placeholder="Command Lyra... ask anything"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void handleSubmit();
            }
            if (e.key === "Escape") {
              toggle(false);
            }
          }}
        />

        {messages.length > 0 && (
          <div className="agent-thread">
            {messages.map((msg, i) => (
              <div key={i} className={`agent-message agent-message--${msg.role}`}>
                <span className="agent-role">{msg.role === "user" ? "You" : "Lyra"}</span>
                <p className="agent-text">{msg.text}</p>
                {msg.thought && msg.role === "lyra" && (
                  <p className="agent-thought">{msg.thought}</p>
                )}
                {msg.action && msg.role === "lyra" && (
                  <span className="agent-action-tag">{msg.action}</span>
                )}
              </div>
            ))}
            {loading && (
              <div className="agent-message agent-message--lyra">
                <span className="agent-role">Lyra</span>
                <p className="agent-text agent-text--loading">Tracing DNA...</p>
              </div>
            )}
          </div>
        )}

        <div className="command-list">
          {commands
            .filter((c) => !input || c.label.toLowerCase().includes(input.toLowerCase()))
            .map((command) => (
              <button
                key={command.to}
                className="command-item"
                onClick={() => {
                  navigate({ to: command.to });
                  toggle(false);
                  setInput("");
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

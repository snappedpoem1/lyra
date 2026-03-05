import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useUiStore } from "@/stores/uiStore";
import { useAgentStore } from "@/stores/agentStore";
import { usePlayerStore } from "@/stores/playerStore";
import { useQueueStore } from "@/stores/queueStore";
import { queryAgent } from "@/services/lyraGateway/queries";
import { routeAgentAction } from "@/services/agentActionRouter";
import { audioEngine } from "@/services/audio/audioEngine";
import { LyraPanel } from "@/ui/LyraPanel";

// ─── Command registry ────────────────────────────────────────────────────────

interface PaletteCommand {
  label: string;
  hint?: string;
  action: () => void;
}

function buildCommands(
  navigate: ReturnType<typeof useNavigate>,
  close: () => void,
): PaletteCommand[] {
  const nav = (to: string) => () => { navigate({ to }); close(); };

  return [
    { label: "Home",             hint: "⌂",     action: nav("/") },
    { label: "Library",          hint: "L",     action: nav("/library") },
    { label: "Search",           hint: "/",     action: nav("/search") },
    { label: "Oracle / Auto-DJ",               action: nav("/oracle") },
    { label: "Queue",            hint: "Q",     action: nav("/queue") },
    { label: "Playlists",                       action: nav("/playlists") },
    { label: "Vibes",                           action: nav("/vibes") },
    { label: "Settings",                        action: nav("/settings") },
    {
      label: "Play / Pause",     hint: "Space",
      action: () => {
        const st = usePlayerStore.getState();
        if (st.status === "playing") {
          audioEngine.pause();
        } else {
          const q = useQueueStore.getState().queue;
          const t = q.items[q.currentIndex];
          if (t) void audioEngine.playTrack(t);
        }
        close();
      },
    },
    {
      label: "Next Track",       hint: "K",
      action: () => {
        const q = useQueueStore.getState().queue;
        const i = q.currentIndex + 1;
        if (i < q.items.length) void audioEngine.playTrack(q.items[i]);
        close();
      },
    },
    {
      label: "Previous Track",   hint: "J",
      action: () => {
        const q = useQueueStore.getState().queue;
        const i = q.currentIndex - 1;
        if (i >= 0) void audioEngine.playTrack(q.items[i]);
        close();
      },
    },
    {
      label: "Toggle Mute",      hint: "M",
      action: () => {
        const m = !usePlayerStore.getState().muted;
        usePlayerStore.getState().setMuted(m);
        audioEngine.setMuted(m);
        close();
      },
    },
  ];
}

// ─── Component ───────────────────────────────────────────────────────────────

export function CommandPalette() {
  const open    = useUiStore((state) => state.commandPaletteOpen);
  const toggle  = useUiStore((state) => state.toggleCommandPalette);
  const navigate = useNavigate();

  const messages         = useAgentStore((state) => state.messages);
  const loading          = useAgentStore((state) => state.loading);
  const addUserMessage   = useAgentStore((state) => state.addUserMessage);
  const addAgentResponse = useAgentStore((state) => state.addAgentResponse);
  const setLoading       = useAgentStore((state) => state.setLoading);

  const [input, setInput]         = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef                  = useRef<HTMLInputElement>(null);
  const listRef                   = useRef<HTMLDivElement>(null);

  const close = useCallback(() => toggle(false), [toggle]);

  const commands = buildCommands(navigate, close);
  const filtered = commands.filter(
    (c) => !input || c.label.toLowerCase().includes(input.toLowerCase()),
  );

  useEffect(() => { setActiveIdx(0); }, [input]);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 20);
    } else {
      setInput("");
      setActiveIdx(0);
    }
  }, [open]);

  const runCommand = useCallback((cmd: PaletteCommand) => {
    cmd.action();
  }, []);

  const handleSubmit = useCallback(async () => {
    if (filtered[activeIdx]) {
      runCommand(filtered[activeIdx]);
      return;
    }
    const text = input.trim();
    if (!text || loading) return;

    addUserMessage(text);
    setInput("");
    setLoading(true);
    try {
      const response = await queryAgent(text);
      addAgentResponse(response);
      routeAgentAction(response);
    } catch (error) {
      addAgentResponse({
        action: "error",
        thought: error instanceof Error ? error.message : "Agent request failed.",
        intent: {},
        next: "",
        response: "Lyra could not reach the agent backend.",
      });
    } finally {
      setLoading(false);
    }
  }, [input, loading, filtered, activeIdx, navigate, close, addUserMessage, addAgentResponse, setLoading, runCommand]);

  if (!open) return null;

  return (
    <div className="overlay-shell" onClick={close}>
      <LyraPanel className="command-palette" onClick={(event) => event.stopPropagation()}>

        <input
          ref={inputRef}
          className="command-input"
          placeholder="Command or ask Lyra…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter")     { e.preventDefault(); void handleSubmit(); }
            if (e.key === "Escape")    { close(); }
            if (e.key === "ArrowDown") {
              e.preventDefault();
              const next = Math.min(activeIdx + 1, filtered.length - 1);
              setActiveIdx(next);
              (listRef.current?.children[next] as HTMLElement | undefined)?.scrollIntoView({ block: "nearest" });
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              const prev = Math.max(activeIdx - 1, 0);
              setActiveIdx(prev);
              (listRef.current?.children[prev] as HTMLElement | undefined)?.scrollIntoView({ block: "nearest" });
            }
          }}
        />

        <div className="palette-hint-row">
          <span className="kbd">↑↓</span><span className="palette-hint-sep">navigate</span>
          <span className="kbd">↵</span><span className="palette-hint-sep">run</span>
          <span className="kbd">Esc</span><span className="palette-hint-sep">close</span>
          <span className="kbd">Ctrl K</span><span className="palette-hint-sep">toggle</span>
          <span className="kbd">Space</span><span className="palette-hint-sep">play</span>
          <span className="kbd">J / K</span><span className="palette-hint-sep">prev/next</span>
        </div>

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
                <p className="agent-text agent-text--loading">Tracing DNA…</p>
              </div>
            )}
          </div>
        )}

        <div className="command-list" ref={listRef}>
          {filtered.map((command, i) => (
            <button
              key={command.label}
              className={`command-item${i === activeIdx ? " is-active" : ""}`}
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => runCommand(command)}
            >
              <span className="command-item-label">{command.label}</span>
              {command.hint && <span className="kbd command-item-hint">{command.hint}</span>}
            </button>
          ))}
          {filtered.length === 0 && input.trim() && (
            <button
              className="command-item command-item--ask is-active"
              onClick={() => void handleSubmit()}
            >
              <span className="command-item-label">Ask Lyra: "{input}"</span>
              <span className="kbd">↵</span>
            </button>
          )}
        </div>
      </LyraPanel>
    </div>
  );
}

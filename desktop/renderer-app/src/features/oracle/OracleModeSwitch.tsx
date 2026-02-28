import { useOracleStore } from "@/stores/oracleStore";

const modes = ["flow", "chaos", "discovery", "constellation"] as const;

export function OracleModeSwitch() {
  const mode = useOracleStore((state) => state.mode);
  const setMode = useOracleStore((state) => state.setMode);
  return (
    <div className="lyra-tabs">
      {modes.map((item) => (
        <button key={item} className={`tab-button ${mode === item ? "is-active" : ""}`} onClick={() => setMode(item)}>
          {item}
        </button>
      ))}
    </div>
  );
}

import { SegmentedControl } from "@mantine/core";
import { useOracleStore } from "@/stores/oracleStore";

const modes = ["flow", "chaos", "discovery", "constellation"] as const;

export function OracleModeSwitch() {
  const mode = useOracleStore((state) => state.mode);
  const setMode = useOracleStore((state) => state.setMode);
  return (
    <SegmentedControl
      className="lyra-tabs"
      value={mode}
      onChange={(value) => setMode(value as (typeof modes)[number])}
      data={modes.map((item) => ({ label: item, value: item }))}
    />
  );
}

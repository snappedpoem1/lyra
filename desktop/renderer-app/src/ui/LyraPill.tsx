import type { PropsWithChildren } from "react";

export function LyraPill({ children, className = "" }: PropsWithChildren<{ className?: string }>) {
  return <span className={`lyra-pill ${className}`.trim()}>{children}</span>;
}

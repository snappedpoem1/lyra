import type { PropsWithChildren } from "react";

export function LyraTabs({ children, className = "" }: PropsWithChildren<{ className?: string }>) {
  return <div className={`lyra-tabs ${className}`.trim()}>{children}</div>;
}

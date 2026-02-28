import type { HTMLAttributes, PropsWithChildren } from "react";

export function LyraPanel({
  children,
  className = "",
  ...props
}: PropsWithChildren<HTMLAttributes<HTMLElement>>) {
  return (
    <section className={`lyra-panel ${className}`.trim()} {...props}>
      {children}
    </section>
  );
}

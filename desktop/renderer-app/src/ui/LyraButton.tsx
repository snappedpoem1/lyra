import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

export function LyraButton({
  children,
  className = "",
  ...props
}: PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>>) {
  return (
    <button className={`lyra-button ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

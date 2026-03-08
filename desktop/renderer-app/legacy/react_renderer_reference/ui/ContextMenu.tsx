import { useEffect, useRef } from "react";

export interface ContextMenuItem {
  label: string;
  icon?: string;          // text glyph, e.g. "▶" "+" "◉" "⊕"
  action: () => void;
  danger?: boolean;
}

interface ContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
}

export function ContextMenu({ x, y, items, onClose }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  // Clamp to viewport
  const MENU_W = 220;
  const MENU_ITEM_H = 32;
  const left = Math.min(x, window.innerWidth  - MENU_W - 8);
  const top  = Math.min(y, window.innerHeight - items.length * MENU_ITEM_H - 16);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const closeKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown",   closeKey);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown",   closeKey);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="ctx-menu"
      style={{ left, top }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {items.map((item, i) => (
        <button
          key={i}
          className={`ctx-item${item.danger ? " ctx-item--danger" : ""}`}
          onClick={() => { item.action(); onClose(); }}
        >
          {item.icon && <span className="ctx-icon">{item.icon}</span>}
          {item.label}
        </button>
      ))}
    </div>
  );
}

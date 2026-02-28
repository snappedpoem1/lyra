import { Link, useRouterState } from "@tanstack/react-router";
import { Icon } from "@/ui/Icon";

const nav = [
  { to: "/", label: "Sanctuary", icon: "spark" as const },
  { to: "/playlists", label: "Playlists", icon: "vinyl" as const },
  { to: "/search", label: "Search", icon: "search" as const },
  { to: "/oracle", label: "Oracle", icon: "spark" as const },
  { to: "/queue", label: "Queue", icon: "queue" as const },
  { to: "/library", label: "Library", icon: "details" as const },
];

export function LeftRail() {
  const location = useRouterState({ select: (state) => state.location.pathname });
  return (
    <aside className="left-rail lyra-panel">
      <div className="window-drag">
        <div className="brand-mark">Lyra</div>
        <p className="brand-copy">playlist oracle for local devotion</p>
      </div>
      <nav className="left-nav">
        {nav.map((item) => (
          <Link key={item.to} to={item.to} className={`nav-item ${location === item.to ? "is-active" : ""}`}>
            <Icon name={item.icon} className="nav-icon" />
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
      <div className="rail-footnote">
        <span>Late-night bias retained</span>
        <span>Local files sacred</span>
      </div>
    </aside>
  );
}

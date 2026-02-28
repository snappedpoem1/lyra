import { Link, useRouterState } from "@tanstack/react-router";
import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { usePlayerStore } from "@/stores/playerStore";
import { Icon } from "@/ui/Icon";

const nav = [
  { to: "/", label: "Now Playing", icon: "spark" as const },
  { to: "/library", label: "Media Library", icon: "details" as const },
  { to: "/playlists", label: "Playlists", icon: "vinyl" as const },
  { to: "/queue", label: "Playlist Queue", icon: "queue" as const },
  { to: "/search", label: "Search", icon: "search" as const },
  { to: "/oracle", label: "Auto-DJ", icon: "spark" as const },
];

export function LeftRail() {
  const location = useRouterState({ select: (state) => state.location.pathname });
  const track = usePlayerStore((state) => state.track);
  const status = usePlayerStore((state) => state.status);
  return (
    <aside className="left-rail lyra-panel">
      <div className="window-drag">
        <div className="brand-mark">LYRA PLAYER</div>
        <p className="brand-copy">library / playlist / transport</p>
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
        <span><ConnectivityBadge /></span>
        <span>{track ? `${track.artist} | ${track.title}` : "No track loaded"}</span>
        <span>{status.toUpperCase()}</span>
      </div>
    </aside>
  );
}

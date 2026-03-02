import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { ConnectivityBadge } from "@/features/system/ConnectivityBadge";
import { usePlayerStore } from "@/stores/playerStore";
import type { IconName } from "@/ui/Icon";
import { Icon } from "@/ui/Icon";

const nav: { to: string; label: string; icon: IconName }[] = [
  { to: "/",          label: "Now Playing",   icon: "home"     },
  { to: "/library",   label: "Library",       icon: "library"  },
  { to: "/search",    label: "Search",        icon: "search"   },
  { to: "/vibes",     label: "Vibes",         icon: "vibes"    },
  { to: "/playlists", label: "Playlists",     icon: "playlust" },
  { to: "/queue",     label: "Queue",         icon: "queue"    },
  { to: "/oracle",    label: "Auto-DJ",       icon: "spark"    },
];

export function LeftRail() {
  const location = useRouterState({ select: (state) => state.location.pathname });
  const navigate = useNavigate();
  const track = usePlayerStore((state) => state.track);
  const status = usePlayerStore((state) => state.status);

  const handleArtistClick = () => {
    if (track?.artist) {
      void navigate({ to: "/artist/$name", params: { name: track.artist } });
    }
  };

  return (
    <aside className="left-rail lyra-panel">
      <div className="window-drag">
        <div className="brand-mark">LYRA</div>
        <p className="brand-tagline">Music Intelligence</p>
      </div>

      <nav className="left-nav" aria-label="Main navigation">
        {nav.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className={`nav-item ${location === item.to ? "is-active" : ""}`}
          >
            <Icon name={item.icon} className="nav-icon" />
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>

      <div className="rail-footnote">
        <ConnectivityBadge />
        {track ? (
          <button
            className="rail-now-playing no-drag"
            onClick={handleArtistClick}
            title={`Go to ${track.artist}`}
          >
            <span className="rail-now-title">{track.title}</span>
            <span className="rail-now-artist">{track.artist}</span>
          </button>
        ) : (
          <span className="rail-idle">No track loaded</span>
        )}
        <span className={`rail-status rail-status--${status}`}>{status.toUpperCase()}</span>
      </div>
    </aside>
  );
}

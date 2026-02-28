import { createRootRoute, createRoute, createRouter, Outlet } from "@tanstack/react-router";
import { AppShell } from "@/features/shell/AppShell";
import { HomeRoute } from "@/app/routes/homeRoute";
import { PlaylistsRoute } from "@/app/routes/playlistsRoute";
import { PlaylistDetailRoute } from "@/app/routes/playlistDetailRoute";
import { SearchRoute } from "@/app/routes/searchRoute";
import { OracleRoute } from "@/app/routes/oracleRoute";
import { QueueRoute } from "@/app/routes/queueRoute";
import { LibraryRoute } from "@/app/routes/libraryRoute";
import { SettingsRoute } from "@/app/routes/settingsRoute";

const rootRoute = createRootRoute({
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomeRoute,
});

const playlistsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/playlists",
  component: PlaylistsRoute,
});

const playlistDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/playlists/$playlistId",
  component: PlaylistDetailRoute,
});

const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/search",
  component: SearchRoute,
});

const oracleRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/oracle",
  component: OracleRoute,
});

const queueRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/queue",
  component: QueueRoute,
});

const libraryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/library",
  component: LibraryRoute,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: SettingsRoute,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  playlistsRoute,
  playlistDetailRoute,
  searchRoute,
  oracleRoute,
  queueRoute,
  libraryRoute,
  settingsRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

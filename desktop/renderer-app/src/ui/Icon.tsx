export type IconName =
  | "play" | "pause" | "search" | "queue" | "spark" | "vinyl" | "close" | "details"
  | "skip-back" | "skip-forward" | "volume" | "volume-mute" | "volume-low"
  | "artist" | "home" | "settings" | "moon" | "library" | "playlust" | "vibes";

interface IconProps {
  name: IconName;
  className?: string;
}

const paths: Record<IconName, string> = {
  play: "M8 5v14l11-7-11-7z",
  pause: "M7 5h4v14H7zm6 0h4v14h-4z",
  search: "M15.5 14h-.79l-.28-.27a6 6 0 10-.71.71l.27.28v.79L20 21.5 21.5 20l-6-6zM10 15a5 5 0 110-10 5 5 0 010 10z",
  queue: "M4 7h16v2H4zm0 5h16v2H4zm0 5h10v2H4z",
  spark: "M12 2l2.1 5.9L20 10l-5.9 2.1L12 18l-2.1-5.9L4 10l5.9-2.1L12 2z",
  vinyl: "M12 4a8 8 0 100 16A8 8 0 0012 4zm0 4a4 4 0 110 8 4 4 0 010-8zm0 2a2 2 0 100 4 2 2 0 000-4z",
  close: "M6 6l12 12M18 6L6 18",
  details: "M5 5h14v4H5zm0 5h14v4H5zm0 5h14v4H5z",
  /* Transport controls */
  "skip-back": "M6 6h2v12H6zm10 12L8 12l8-6v12z",
  "skip-forward": "M18 6h-2v12h2V6zM8 6l8 6-8 6V6z",
  /* Volume */
  volume: "M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.06c1.48-.73 2.5-2.25 2.5-4.03zm2.5 0a7 7 0 00-5-6.58v2.06A5 5 0 0119 12a5 5 0 01-4.5 4.97v2.06A7 7 0 0019 12z",
  "volume-low": "M18.5 12c0-1.77-1-3.29-2.5-4.03v8.05c1.5-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z",
  "volume-mute": "M16.5 12c0-1.77-1-3.29-2.5-4.03v2.21l2.45 2.45A4.5 4.5 0 0016.5 12zM5 9v6h4l5 5V4L9 9H5zM19 9.5l-1.5 1.5 1.5 1.5 1.5-1.5L19 9.5zm0 8l1.5-1.5L19 14.5l-1.5 1.5 1.5 1.5z",
  /* Navigation */
  artist: "M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z",
  home: "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
  settings: "M12 15.5a3.5 3.5 0 110-7 3.5 3.5 0 010 7zm7.43-2.92c.04-.34.07-.67.07-1.08s-.02-.74-.07-1.08l2.11-1.65a.5.5 0 00.12-.64l-2-3.46a.5.5 0 00-.61-.22l-2.49 1a7.37 7.37 0 00-1.83-1.06l-.38-2.65A.49.49 0 0014 2h-4a.49.49 0 00-.49.42l-.38 2.65a7.37 7.37 0 00-1.83 1.06l-2.49-1a.5.5 0 00-.61.22l-2 3.46a.49.49 0 00.12.64l2.11 1.65A7.6 7.6 0 004.37 12c0 .38.02.73.07 1.08L2.33 14.73a.5.5 0 00-.12.64l2 3.46a.5.5 0 00.61.22l2.49-1c.57.41 1.17.74 1.83 1.06l.38 2.65c.07.24.25.42.49.42h4c.24 0 .42-.18.49-.42l.38-2.65a7.37 7.37 0 001.83-1.06l2.49 1a.5.5 0 00.61-.22l2-3.46a.49.49 0 00-.12-.64l-2.11-1.65z",
  moon: "M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z",
  library: "M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-1 9H9V9h10v2zm-4 4H9v-2h6v2zm4-8H9V5h10v2z",
  playlust: "M12 2l2.1 5.9L20 10l-5.9 2.1L12 18l-2.1-5.9L4 10l5.9-2.1L12 2zM12 9a3 3 0 100 6 3 3 0 000-6z",
  vibes: "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
};

export function Icon({ name, className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}

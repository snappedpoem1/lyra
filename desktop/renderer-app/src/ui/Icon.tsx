interface IconProps {
  name: "play" | "pause" | "search" | "queue" | "spark" | "vinyl" | "close" | "details";
  className?: string;
}

const paths: Record<IconProps["name"], string> = {
  play: "M8 5v14l11-7-11-7z",
  pause: "M7 5h4v14H7zm6 0h4v14h-4z",
  search: "M15.5 14h-.79l-.28-.27a6 6 0 10-.71.71l.27.28v.79L20 21.5 21.5 20l-6-6zM10 15a5 5 0 110-10 5 5 0 010 10z",
  queue: "M4 7h16v2H4zm0 5h16v2H4zm0 5h10v2H4z",
  spark: "M12 2l2.1 5.9L20 10l-5.9 2.1L12 18l-2.1-5.9L4 10l5.9-2.1L12 2z",
  vinyl: "M12 12m-8 0a8 8 0 1016 0 8 8 0 10-16 0zm0 0m-2 0a2 2 0 104 0 2 2 0 10-4 0z",
  close: "M6 6l12 12M18 6L6 18",
  details: "M5 5h14v4H5zm0 5h14v4H5zm0 5h14v4H5z",
};

export function Icon({ name, className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className={className} aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}

export const DIMENSIONS = [
  "energy",
  "valence",
  "tension",
  "density",
  "warmth",
  "movement",
  "space",
  "rawness",
  "complexity",
  "nostalgia",
] as const;

export type DimensionKey = (typeof DIMENSIONS)[number];
